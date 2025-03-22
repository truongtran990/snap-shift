"""
Device connection module for Android Media Transfer Tool.
Handles MTP device detection and connection management.
"""

from dataclasses import dataclass

import pymtp


@dataclass
class StorageInfo:
    """Information about a storage unit on the device"""

    id: int
    name: str
    capacity: int


@dataclass
class Device:
    """Represents a connected Android device"""

    name: str
    serial: str
    storage_info: list[StorageInfo]
    _mtp_device: pymtp.MTP

    def __post_init__(self):
        """Validate device information after initialization"""
        if not self.name or not self.serial:
            raise ValueError("Device must have both name and serial number")
        if not self.storage_info:
            raise ValueError("Device must have at least one storage unit")


class DeviceConnectionError(Exception):
    """Raised when there are issues connecting to a device"""

    pass


class DeviceManager:
    """Manages MTP device connections and operations"""

    def __init__(self):
        """Initialize the device manager"""
        self._mtp = None
        self._connected_devices: list[Device] = []

    def _create_device(self, mtp_device) -> Device:
        """
        Create a Device instance from MTP device information

        Args:
            mtp_device: Raw MTP device object

        Returns:
            Device: Initialized device instance
        """
        name = mtp_device.get_devicename()
        serial = mtp_device.get_serialnumber()
        storage_info = [
            StorageInfo(id=sid, name=name, capacity=capacity)
            for sid, name, capacity in mtp_device.get_storage()
        ]
        return Device(name=name, serial=serial, storage_info=storage_info, _mtp_device=mtp_device)

    def get_connected_devices(self) -> list[Device]:
        """
        Detect and return list of connected Android devices

        Returns:
            List[Device]: List of connected devices

        Raises:
            DeviceConnectionError: If no devices found or connection fails
        """
        try:
            self._mtp = pymtp.MTP()
            devices = []
            for device in self._mtp.detect_devices():
                try:
                    devices.append(self._create_device(device))
                except Exception as e:
                    raise DeviceConnectionError(
                        f"Failed to connect to device: {str(e)}"
                    ) from e

            if not devices:
                raise DeviceConnectionError("No Android devices found")

            self._connected_devices = devices
            return devices
        except Exception as e:
            raise DeviceConnectionError(f"Failed to connect to device: {str(e)}") from e

    def disconnect_all(self):
        """Safely disconnect all connected devices"""
        if self._mtp:
            self._mtp.disconnect()
            self._connected_devices = []
            self._mtp = None
