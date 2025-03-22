"""
Device connection module for Android Media Transfer Tool.
Handles MTP device detection and connection management.
"""

from dataclasses import dataclass
import subprocess
import json
from pathlib import Path
import os
import re
import glob
import urllib.parse

from amtt.core.filesystem import FileSystem
from amtt.core.transfer import TransferManager
from amtt.core.config import ConfigManager, PathConfig


@dataclass
class StorageInfo:
    """Information about a storage unit on the device"""

    id: int
    name: str
    capacity: int


class Device:
    """Represents a connected Android device"""

    def __init__(self, name: str, serial: str, storage_info: list[StorageInfo], mount_point: Path):
        """Initialize device instance"""
        self.name = name
        self.serial = serial
        self.storage_info = storage_info
        self.mount_point = mount_point
        
        # Initialize managers
        self.filesystem = FileSystem(self)
        self.transfer_manager = TransferManager(self, self.filesystem)
        self.config_manager = ConfigManager()
        
        # Get device configuration
        self.device_id, self.config = self.config_manager.get_device_config(
            serial=self.serial,
            model=self.name
        )
        
        # Validate device information
        if not self.name or not self.serial:
            raise ValueError("Device must have both name and serial number")
        if not self.storage_info:
            raise ValueError("Device must have at least one storage unit")

    @property
    def friendly_name(self) -> str:
        """Get user-friendly name for the device"""
        return self.config.friendly_name

    def set_friendly_name(self, name: str):
        """Set user-friendly name for the device"""
        self.config_manager.set_friendly_name(self.device_id, name)
        # Reload config
        _, self.config = self.config_manager.get_device_config(
            serial=self.serial,
            model=self.name
        )

    def get_configured_paths(self) -> list[PathConfig]:
        """Get list of configured paths for this device"""
        return self.config_manager.get_enabled_paths(self.device_id)

    def add_path(self, path: str, description: str):
        """Add a new path to device configuration"""
        self.config_manager.add_path(self.device_id, path, description)

    def remove_path(self, path: str):
        """Remove a path from device configuration"""
        self.config_manager.remove_path(self.device_id, path)

    def set_path_enabled(self, path: str, enabled: bool):
        """Enable or disable a path"""
        self.config_manager.set_path_enabled(self.device_id, path, enabled)

    def set_local_path(self, path: str, local_path: str):
        """Set local download path for a device path"""
        self.config_manager.set_local_path(self.device_id, path, local_path)


class DeviceConnectionError(Exception):
    """Raised when there are issues connecting to a device"""

    pass


class DeviceManager:
    """Manages MTP device connections and operations"""

    # Common mount points for Android devices
    COMMON_MOUNT_POINTS = [
        "/run/user/{uid}/gvfs",  # Modern Linux with GVFS
        "/media/{user}",         # Ubuntu/Debian style
        "/mnt",                  # Traditional Linux mount point
        "~/.gvfs",              # Old GVFS location
    ]

    def __init__(self):
        """Initialize the device manager"""
        self._connected_devices: list[Device] = []

    def _try_adb_devices(self) -> list[dict]:
        """Try to find devices using ADB if available"""
        try:
            result = subprocess.run(
                ["adb", "devices", "-l"],
                capture_output=True,
                text=True,
                check=True
            )
            
            devices = []
            for line in result.stdout.splitlines()[1:]:  # Skip header line
                if not line.strip():
                    continue
                    
                parts = line.split()
                if len(parts) >= 2 and parts[1] == "device":
                    # Get device info using adb
                    try:
                        model = subprocess.run(
                            ["adb", "-s", parts[0], "shell", "getprop", "ro.product.model"],
                            capture_output=True,
                            text=True,
                            check=True
                        ).stdout.strip()
                        
                        devices.append({
                            "type": "adb",
                            "name": model or "Android Device",
                            "serial": parts[0],
                            "transport": "adb"
                        })
                    except subprocess.CalledProcessError:
                        continue
                        
            return devices
        except (subprocess.CalledProcessError, FileNotFoundError):
            return []

    def _try_gio_mount(self) -> list[dict]:
        """Try to find devices using gio mount"""
        try:
            result = subprocess.run(
                ["gio", "mount", "-l"],
                capture_output=True,
                text=True,
                check=True
            )
            
            devices = []
            current_device = {}
            
            for line in result.stdout.splitlines():
                line = line.strip()
                if not line:
                    if current_device:
                        devices.append(current_device)
                        current_device = {}
                    continue
                    
                if line.startswith("Volume("):
                    current_device = {}
                    # Extract device name from Volume line
                    # Example: "Volume(0): Mi 11 Lite 5G"
                    name = line.split(":", 1)[1].strip()
                    current_device["name"] = name
                elif "Type:" in line and "MTP" in line:
                    current_device["type"] = "mtp"
                elif line.startswith("Mount(") and "mtp://" in line:
                    # Extract mount point from line like "Mount(0): Mi 11 Lite 5G -> mtp://Xiaomi_Mi_11_Lite_5G_6b38b99f/"
                    parts = line.split(" -> ")
                    if len(parts) == 2:
                        url = parts[1].strip()
                        current_device["mount_point"] = url
                        # Extract serial from URL
                        serial = url.split("/")[-2]
                        # Clean up serial number
                        serial = serial.replace("mtp:host=", "")
                        current_device["serial"] = serial
                        current_device["transport"] = "mtp"
                    
            if current_device:
                devices.append(current_device)
                
            # Filter out incomplete devices and clean up names
            valid_devices = []
            for device in devices:
                if device.get("type") == "mtp" and "mount_point" in device:
                    # Clean up device name
                    name = device["name"]
                    # Remove any "mtp:" prefix
                    if name.startswith("mtp:"):
                        name = name[4:].strip()
                    # Remove any host= prefix
                    if name.startswith("host="):
                        name = name[5:].strip()
                    # Remove any serial number from name
                    if device["serial"] in name:
                        name = name.replace(device["serial"], "").strip()
                    # Remove any trailing separators
                    name = name.rstrip("_-: ")
                    device["name"] = name
                    valid_devices.append(device)
                    
            return valid_devices
        except (subprocess.CalledProcessError, FileNotFoundError):
            return []

    def _try_find_mount_point(self) -> list[dict]:
        """Try to find devices by scanning common mount points"""
        devices = []
        uid = os.getuid()
        user = os.getenv("USER", "")
        
        for mount_pattern in self.COMMON_MOUNT_POINTS:
            mount_base = os.path.expanduser(
                mount_pattern.format(uid=uid, user=user)
            )
            
            # Look for MTP/Android mounts
            for mount_point in glob.glob(f"{mount_base}/*"):
                if any(x in mount_point.lower() for x in ["android", "mtp", "phone"]):
                    name = os.path.basename(mount_point)
                    # Clean up name
                    if name.startswith("mtp:"):
                        name = name[4:].strip()
                    if name.startswith("host="):
                        name = name[5:].strip()
                    devices.append({
                        "type": "mtp",
                        "name": name,
                        "mount_point": f"mtp://{name}/",
                        "serial": name,
                        "transport": "mtp"
                    })
                    
        return devices

    def _get_mount_point(self, device_info: dict) -> Path:
        """Get the actual mount point for a device"""
        if device_info["transport"] == "adb":
            # For ADB devices, create a temporary mount point
            mount_dir = Path(f"/tmp/amtt_{device_info['serial']}")
            mount_dir.mkdir(parents=True, exist_ok=True)
            return mount_dir
            
        # For MTP devices, try different methods to get mount point
        methods = [
            # Method 1: Use gio info
            lambda: self._get_gio_mount_point(device_info["mount_point"]),
            
            # Method 2: Check common mount points
            lambda: self._find_in_common_mount_points(device_info["serial"]),
            
            # Method 3: Use direct MTP path
            lambda: Path(f"/run/user/{os.getuid()}/gvfs/mtp:host={device_info['serial']}")
        ]
        
        for method in methods:
            try:
                mount_point = method()
                if mount_point and (
                    mount_point.exists() or 
                    device_info["transport"] == "adb"
                ):
                    return mount_point
            except Exception:
                continue
                
        raise DeviceConnectionError(
            f"Could not find mount point for device: {device_info['name']}"
        )

    def _get_gio_mount_point(self, mtp_url: str) -> Path | None:
        """Get mount point using gio info"""
        try:
            result = subprocess.run(
                ["gio", "info", mtp_url],
                capture_output=True,
                text=True,
                check=True
            )
            
            for line in result.stdout.splitlines():
                if "local path:" in line:
                    return Path(line.split(":", 1)[1].strip())
        except Exception:
            return None

    def _find_in_common_mount_points(self, device_id: str) -> Path | None:
        """Find device in common mount points"""
        uid = os.getuid()
        user = os.getenv("USER", "")
        
        for mount_pattern in self.COMMON_MOUNT_POINTS:
            mount_base = os.path.expanduser(
                mount_pattern.format(uid=uid, user=user)
            )
            
            # Look for exact device ID match
            for mount_point in glob.glob(f"{mount_base}/*{device_id}*"):
                return Path(mount_point)
                
        return None

    def _create_device(self, device_info: dict) -> Device:
        """
        Create a Device instance from device information

        Args:
            device_info: Device information from detection methods

        Returns:
            Device: Initialized device instance
        """
        name = device_info["name"]
        serial = device_info.get("serial", "unknown")
        
        # Get mount point
        mount_point = self._get_mount_point(device_info)
        
        # Get storage info
        storage_info = []
        try:
            if device_info["transport"] == "adb":
                # Use adb to get storage info
                result = subprocess.run(
                    ["adb", "-s", serial, "shell", "df", "/storage/emulated/0"],
                    capture_output=True,
                    text=True,
                    check=True
                )
            else:
                # Use regular df for mounted devices
                result = subprocess.run(
                    ["df", "-h", str(mount_point)],
                    capture_output=True,
                    text=True,
                    check=True
                )
                
            # Skip header line
            lines = result.stdout.splitlines()[1:]
            for line in lines:
                parts = line.split()
                if len(parts) >= 6:
                    total = parts[1]
                    storage_info.append(
                        StorageInfo(
                            id=len(storage_info),
                            name=f"Storage {len(storage_info) + 1}",
                            capacity=self._parse_size(total)
                        )
                    )
        except subprocess.CalledProcessError:
            # Fallback to default storage
            storage_info = [StorageInfo(id=0, name="Device Storage", capacity=0)]
            
        return Device(
            name=name,
            serial=serial,
            storage_info=storage_info,
            mount_point=mount_point
        )

    def _parse_size(self, size_str: str) -> int:
        """Convert size string (e.g., '1.5G') to bytes"""
        try:
            size = float(size_str[:-1])
            unit = size_str[-1].upper()
            multipliers = {
                'K': 1024,
                'M': 1024 * 1024,
                'G': 1024 * 1024 * 1024,
                'T': 1024 * 1024 * 1024 * 1024
            }
            return int(size * multipliers.get(unit, 1))
        except (ValueError, IndexError):
            return 0

    def get_connected_devices(self) -> list[Device]:
        """
        Detect and return list of connected Android devices.
        Tries multiple methods to find devices:
        1. ADB (if available)
        2. GIO/GVFS MTP mounts
        3. Common mount points scan

        Returns:
            List[Device]: List of connected devices

        Raises:
            DeviceConnectionError: If no devices found or connection fails
        """
        try:
            devices = []
            
            # Try all detection methods
            device_infos = (
                self._try_adb_devices() +
                self._try_gio_mount() +
                self._try_find_mount_point()
            )
            
            # Remove duplicates based on serial number
            seen_serials = set()
            unique_devices = []
            for device in device_infos:
                serial = device["serial"]
                # Clean up serial
                if serial.startswith("mtp:host="):
                    serial = serial[9:]
                if serial not in seen_serials:
                    seen_serials.add(serial)
                    unique_devices.append(device)
            
            # Create device instances
            for device_info in unique_devices:
                try:
                    devices.append(self._create_device(device_info))
                except Exception as e:
                    print(f"Warning: Failed to initialize device {device_info['name']}: {e}")
                    continue

            if not devices:
                raise DeviceConnectionError(
                    "No Android devices found. Please make sure:\n"
                    "1. Your device is connected via USB\n"
                    "2. USB debugging is enabled in developer options\n"
                    "3. You have authorized this computer on your device\n"
                    "4. Your device is not in charging-only mode"
                )

            self._connected_devices = devices
            return devices
        except Exception as e:
            raise DeviceConnectionError(f"Failed to connect to device: {str(e)}") from e

    def disconnect_all(self):
        """Safely disconnect all connected devices"""
        for device in self._connected_devices:
            if hasattr(device, "transport") and device.transport == "adb":
                # Clean up temporary mount point
                try:
                    mount_point = Path(f"/tmp/amtt_{device.serial}")
                    if mount_point.exists():
                        mount_point.rmdir()
                except Exception:
                    pass
                    
        self._connected_devices = []
