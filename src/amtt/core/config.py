"""
Configuration management for Android Media Transfer Tool.
Handles default paths, whitelists, and user preferences.
"""

from dataclasses import dataclass
from pathlib import Path
import json
import os
from typing import Optional, List, Dict, Tuple

@dataclass
class PathConfig:
    """Configuration for a specific path on the Android device"""
    path: str  # Path on the device
    description: str  # Human-readable description
    enabled: bool = True  # Whether this path is enabled
    local_path: Optional[str] = None  # Default local path to save files

@dataclass
class DeviceConfig:
    """Device-specific configuration"""
    friendly_name: str  # User-friendly name for the device
    model: str  # Device model
    paths: List[PathConfig]
    default_local_path: str = "~/Downloads"  # Default download location

class ConfigManager:
    """Manages AMTT configuration"""
    
    # Safe paths that are known to contain media files
    SAFE_PATHS = [
        "/Internal shared storage/DCIM/Camera",
        "/Internal shared storage/DCIM/Screenshots",
        "/Internal shared storage/Pictures",
        "/Internal shared storage/Movies",
        "/Internal shared storage/Music",
        "/Internal shared storage/Recordings",
        "/Internal shared storage/Download"
    ]

    # Paths that should never be accessed
    RESTRICTED_PATHS = [
        ".android",
        "Android/data",
        "Android/obb",
        "Android/media",
        ".system",
        "system",
        ".hidden",
        ".cache",
        "cache",
        ".trash",
        "lost.dir"
    ]
    
    DEFAULT_PATHS = [
        PathConfig(
            path="/Internal shared storage/DCIM/Camera",
            description="Camera photos and videos"
        ),
        PathConfig(
            path="/Internal shared storage/DCIM/Screenshots",
            description="Screen captures"
        ),
        PathConfig(
            path="/Internal shared storage/Pictures",
            description="Pictures and screenshots"
        ),
        PathConfig(
            path="/Internal shared storage/Movies",
            description="Video recordings"
        ),
        PathConfig(
            path="/Internal shared storage/Recordings",
            description="Voice recordings"
        )
    ]

    def __init__(self):
        """Initialize configuration manager"""
        self.config_dir = Path.home() / ".config" / "amtt"
        self.config_file = self.config_dir / "config.json"
        self.device_configs: Dict[str, DeviceConfig] = {}
        self._load_config()

    def _load_config(self):
        """Load configuration from file"""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            
            if not self.config_file.exists():
                # Create default config
                self._save_config()
            
            with open(self.config_file, 'r') as f:
                data = json.load(f)
                
            # Load device configs
            for device_id, device_data in data.get("devices", {}).items():
                paths = [
                    PathConfig(**path_data)
                    for path_data in device_data.get("paths", [])
                ]
                self.device_configs[device_id] = DeviceConfig(
                    friendly_name=device_data.get("friendly_name", "Unknown Device"),
                    model=device_data.get("model", "Unknown Model"),
                    paths=paths,
                    default_local_path=device_data.get(
                        "default_local_path",
                        "~/Downloads"
                    )
                )
        except Exception as e:
            print(f"Warning: Failed to load config: {e}")
            # Use default config
            self.device_configs = {}

    def _save_config(self):
        """Save configuration to file"""
        try:
            data = {
                "devices": {
                    device_id: {
                        "friendly_name": config.friendly_name,
                        "model": config.model,
                        "paths": [
                            {
                                "path": p.path,
                                "description": p.description,
                                "enabled": p.enabled,
                                "local_path": p.local_path
                            }
                            for p in config.paths
                        ],
                        "default_local_path": config.default_local_path
                    }
                    for device_id, config in self.device_configs.items()
                }
            }
            
            with open(self.config_file, 'w') as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            print(f"Warning: Failed to save config: {e}")

    def get_device_id(self, serial: str, model: str) -> str:
        """Generate a consistent device ID from serial and model"""
        # Clean up serial number and model
        serial = serial.strip().replace(" ", "_")
        model = model.strip().replace(" ", "_")
        return f"{model}_{serial}"

    def get_device_config(self, serial: str, model: str) -> Tuple[str, DeviceConfig]:
        """Get configuration for a specific device"""
        device_id = self.get_device_id(serial, model)
        
        if device_id not in self.device_configs:
            # Create default config for new device
            friendly_name = f"My {model}"  # Default friendly name
            self.device_configs[device_id] = DeviceConfig(
                friendly_name=friendly_name,
                model=model,
                paths=self.DEFAULT_PATHS.copy()
            )
            self._save_config()
            
        return device_id, self.device_configs[device_id]

    def set_friendly_name(self, device_id: str, friendly_name: str):
        """Set a user-friendly name for the device"""
        if device_id in self.device_configs:
            self.device_configs[device_id].friendly_name = friendly_name
            self._save_config()

    def update_device_config(self, device_id: str, config: DeviceConfig):
        """Update configuration for a specific device"""
        self.device_configs[device_id] = config
        self._save_config()

    @classmethod
    def is_safe_path(cls, path: str) -> bool:
        """Check if a path is safe to access"""
        # Clean and normalize path
        path = path.replace("\\", "/").strip()
        if not path.startswith("/"):
            path = "/" + path
            
        # Check if path is in restricted list
        if any(restricted in path for restricted in cls.RESTRICTED_PATHS):
            return False
            
        # Check if path starts with a dot (hidden)
        path_parts = path.split("/")
        if any(part.startswith(".") for part in path_parts if part):
            return False
            
        # Check if path is in safe list or is a subpath of a safe path
        return any(
            path.startswith(safe_path)
            for safe_path in cls.SAFE_PATHS
        )

    def add_path(self, device_id: str, path: str, description: str):
        """Add a new path to device configuration"""
        # Verify path safety before adding
        if not self.is_safe_path(path):
            raise ValueError(
                f"Path '{path}' is not allowed. Please use only media directories."
            )
            
        if device_id in self.device_configs:
            config = self.device_configs[device_id]
            if not any(p.path == path for p in config.paths):
                config.paths.append(PathConfig(path=path, description=description))
                self.update_device_config(device_id, config)

    def remove_path(self, device_id: str, path: str):
        """Remove a path from device configuration"""
        if device_id in self.device_configs:
            config = self.device_configs[device_id]
            config.paths = [p for p in config.paths if p.path != path]
            self.update_device_config(device_id, config)

    def set_path_enabled(self, device_id: str, path: str, enabled: bool):
        """Enable or disable a path"""
        if device_id in self.device_configs:
            config = self.device_configs[device_id]
            for p in config.paths:
                if p.path == path:
                    p.enabled = enabled
                    break
            self.update_device_config(device_id, config)

    def set_local_path(self, device_id: str, path: str, local_path: str):
        """Set local download path for a device path"""
        if device_id in self.device_configs:
            config = self.device_configs[device_id]
            for p in config.paths:
                if p.path == path:
                    p.local_path = local_path
                    break
            self.update_device_config(device_id, config)

    def get_enabled_paths(self, device_id: str) -> List[PathConfig]:
        """Get list of enabled paths for a device"""
        if device_id in self.device_configs:
            config = self.device_configs[device_id]
            return [p for p in config.paths if p.enabled]
        return [] 