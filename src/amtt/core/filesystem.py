"""
Filesystem operations for Android Media Transfer Tool.
"""

import os
import shutil
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
import mimetypes
from typing import List, Optional

from amtt.core.config import ConfigManager


class FileType(Enum):
    """Types of files supported by the tool"""

    FOLDER = auto()
    IMAGE = auto()    # jpg, png, gif, etc.
    VIDEO = auto()    # mp4, mov, etc.
    AUDIO = auto()    # mp3, wav, etc.
    DOCUMENT = auto()
    OTHER = auto()    # unsupported types


@dataclass
class FileInfo:
    """Information about a file or directory"""

    name: str
    path: str
    type: FileType
    size: Optional[int] = None
    modified_date: Optional[datetime] = None
    id: int | None = None


class FileSystemError(Exception):
    """Raised when filesystem operations fail"""

    pass


class FileSystem:
    """Handles filesystem operations on the device"""

    # Supported media file extensions
    SUPPORTED_EXTENSIONS = {
        # Images
        FileType.IMAGE: {
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', 
            '.webp', '.heic', '.heif', '.raw', '.dng'
        },
        # Videos
        FileType.VIDEO: {
            '.mp4', '.mov', '.avi', '.mkv', '.webm',
            '.3gp', '.m4v', '.mpg', '.mpeg'
        },
        # Audio recordings
        FileType.AUDIO: {
            '.mp3', '.wav', '.m4a', '.ogg', '.aac',
            '.flac', '.opus'
        }
    }

    def __init__(self, device):
        """
        Initialize filesystem handler

        Args:
            device: Connected Android device instance
        """
        self.device = device
        self.mount_point = device.mount_point

    def _is_media_file(self, path: str) -> bool:
        """Check if file is a supported media type"""
        ext = os.path.splitext(path)[1].lower()
        return any(
            ext in extensions
            for extensions in self.SUPPORTED_EXTENSIONS.values()
        )

    def _get_file_type(self, path: str) -> FileType:
        """Determine file type from extension"""
        if os.path.isdir(path):
            return FileType.FOLDER
            
        ext = os.path.splitext(path)[1].lower()
        
        # Check each type's extensions
        for file_type, extensions in self.SUPPORTED_EXTENSIONS.items():
            if ext in extensions:
                return file_type
                
        return FileType.OTHER

    def _verify_path_safety(self, path: str):
        """Verify that a path is safe to access"""
        if not ConfigManager.is_safe_path(path):
            raise FileSystemError(
                f"Access to path '{path}' is not allowed for safety reasons. "
                "Please use only media directories."
            )

    def list_files(self, path: str) -> List[FileInfo]:
        """
        List files in a directory
        
        Args:
            path: Directory path to list
            
        Returns:
            List of FileInfo objects for files and subdirectories
            
        Raises:
            FileSystemError: If path is invalid or inaccessible
        """
        try:
            # Verify path safety
            self._verify_path_safety(path)
            
            # Get absolute path
            abs_path = os.path.join(self.mount_point, path.lstrip("/"))
            if not os.path.exists(abs_path):
                raise FileSystemError(f"Path does not exist: {path}")
            if not os.path.isdir(abs_path):
                raise FileSystemError(f"Path is not a directory: {path}")
                
            files = []
            for entry in os.scandir(abs_path):
                try:
                    # Skip hidden files and system directories
                    if entry.name.startswith("."):
                        continue
                        
                    file_type = self._get_file_type(entry.path)
                    
                    # For files (not folders), only include media files
                    if file_type != FileType.FOLDER and file_type == FileType.OTHER:
                        continue
                        
                    # Get file info
                    stat = entry.stat()
                    files.append(
                        FileInfo(
                            name=entry.name,
                            path=os.path.join(path, entry.name),
                            type=file_type,
                            size=stat.st_size if file_type != FileType.FOLDER else None,
                            modified_date=datetime.fromtimestamp(stat.st_mtime)
                        )
                    )
                except (OSError, ValueError) as e:
                    print(f"Warning: Failed to read {entry.name}: {e}")
                    continue
                    
            return files
            
        except Exception as e:
            raise FileSystemError(f"Failed to list files: {str(e)}")

    def get_file_info(self, path: str) -> FileInfo:
        """
        Get information about a file or directory
        
        Args:
            path: Path to the file or directory
            
        Returns:
            FileInfo object with file details
            
        Raises:
            FileSystemError: If file is invalid or inaccessible
        """
        try:
            # Verify path safety
            self._verify_path_safety(path)
            
            # Get absolute path
            abs_path = os.path.join(self.mount_point, path.lstrip("/"))
            if not os.path.exists(abs_path):
                raise FileSystemError(f"Path does not exist: {path}")
                
            # Get file type
            file_type = self._get_file_type(abs_path)
            
            # For files (not folders), verify it's a media file
            if file_type != FileType.FOLDER:
                if not self._is_media_file(abs_path):
                    raise FileSystemError(
                        f"File type not supported: {path}. "
                        "Only media files (images, videos, recordings) are allowed."
                    )
                    
            # Get file info
            stat = os.stat(abs_path)
            return FileInfo(
                name=os.path.basename(path),
                path=path,
                type=file_type,
                size=stat.st_size if file_type != FileType.FOLDER else None,
                modified_date=datetime.fromtimestamp(stat.st_mtime)
            )
            
        except Exception as e:
            raise FileSystemError(f"Failed to get file info: {str(e)}")

    def create_directory(self, path: str):
        """
        Create a new directory
        
        Args:
            path: Directory path to create
            
        Raises:
            FileSystemError: If directory cannot be created
        """
        try:
            # Verify path safety
            self._verify_path_safety(path)
            
            # Get absolute path
            abs_path = os.path.join(self.mount_point, path.lstrip("/"))
            
            # Create directory
            os.makedirs(abs_path, exist_ok=True)
            
        except Exception as e:
            raise FileSystemError(f"Failed to create directory: {str(e)}")

    def delete_file(self, path: str):
        """
        Delete a file or directory
        
        Args:
            path: Path to delete
            
        Raises:
            FileSystemError: If file cannot be deleted
        """
        try:
            # Verify path safety
            self._verify_path_safety(path)
            
            # Get absolute path
            abs_path = os.path.join(self.mount_point, path.lstrip("/"))
            if not os.path.exists(abs_path):
                raise FileSystemError(f"Path does not exist: {path}")
                
            # For files, verify it's a media file
            if os.path.isfile(abs_path):
                if not self._is_media_file(abs_path):
                    raise FileSystemError(
                        "Only media files can be deleted. "
                        "System and other files are protected."
                    )
                    
            # Delete file or directory
            if os.path.isdir(abs_path):
                os.rmdir(abs_path)  # Only delete if empty
            else:
                os.remove(abs_path)
                
        except Exception as e:
            raise FileSystemError(f"Failed to delete: {str(e)}")
