"""
Filesystem module for Android Media Transfer Tool.
Handles file system navigation and file information retrieval.
"""

import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from pathlib import Path


class FileType(Enum):
    """Enumeration of supported file types"""

    FOLDER = auto()
    IMAGE = auto()
    VIDEO = auto()
    AUDIO = auto()
    DOCUMENT = auto()
    OTHER = auto()


@dataclass
class FileInfo:
    """Information about a file or folder on the device"""

    name: str
    path: str
    type: FileType
    size: int | None = None
    modified_date: datetime | None = None
    id: int | None = None


class FileSystemError(Exception):
    """Raised when there are issues with filesystem operations"""

    pass


class FileSystem:
    """Handles filesystem operations on the connected device"""

    # Mapping of MIME type prefixes to FileType
    MIME_TYPE_MAPPING = {
        "image/": FileType.IMAGE,
        "video/": FileType.VIDEO,
        "audio/": FileType.AUDIO,
        "text/": FileType.DOCUMENT,
        "application/pdf": FileType.DOCUMENT,
        "application/msword": FileType.DOCUMENT,
        "application/vnd.openxmlformats-officedocument": FileType.DOCUMENT,
    }

    def __init__(self, device):
        """
        Initialize filesystem handler

        Args:
            device: Connected Android device instance
        """
        self._device = device
        self._mtp = device._mtp_device

    def _detect_file_type(self, mime_type: str) -> FileType:
        """
        Detect file type from MIME type

        Args:
            mime_type: MIME type string

        Returns:
            FileType: Detected file type
        """
        if mime_type == "folder":
            return FileType.FOLDER

        for mime_prefix, file_type in self.MIME_TYPE_MAPPING.items():
            if mime_type.startswith(mime_prefix):
                return file_type

        return FileType.OTHER

    def _parse_file_info(self, file_data: dict, parent_path: str) -> FileInfo:
        """
        Parse raw file information into FileInfo object

        Args:
            file_data: Raw file data from MTP
            parent_path: Parent directory path

        Returns:
            FileInfo: Parsed file information
        """
        name = file_data["filename"]
        path = os.path.join(parent_path, name)
        file_type = self._detect_file_type(file_data["filetype"])

        # Only regular files have size and modification date
        size = file_data.get("filesize") if file_type != FileType.FOLDER else None

        modified_date = None
        if "modificationdate" in file_data:
            try:
                modified_date = datetime.strptime(
                    file_data["modificationdate"], "%Y-%m-%d %H:%M:%S"
                )
            except ValueError:
                pass  # Invalid date format, leave as None

        return FileInfo(
            name=name,
            path=path,
            type=file_type,
            size=size,
            modified_date=modified_date,
            id=file_data.get("id"),
        )

    def list_files(self, path: str) -> list[FileInfo]:
        """
        List files and folders in the specified path

        Args:
            path: Directory path to list

        Returns:
            List[FileInfo]: List of files and folders

        Raises:
            FileSystemError: If listing fails
        """
        try:
            files = self._mtp.get_files_and_folders(path)
            return [self._parse_file_info(f, path) for f in files]
        except Exception as e:
            raise FileSystemError(f"Failed to list files at {path}: {str(e)}") from e

    def get_file_info(self, path: str) -> FileInfo:
        """
        Get information about a specific file

        Args:
            path: Path to the file

        Returns:
            FileInfo: File information

        Raises:
            FileSystemError: If file not found or info retrieval fails
        """
        try:
            file_data = self._mtp.get_file_info(path)
            parent_path = str(Path(path).parent)
            return self._parse_file_info(file_data, parent_path)
        except Exception as e:
            raise FileSystemError(
                f"Failed to get file info for {path}: {str(e)}"
            ) from e

    def create_directory(self, path: str) -> None:
        """
        Create a new directory

        Args:
            path: Path where to create directory

        Raises:
            FileSystemError: If directory creation fails
        """
        try:
            self._mtp.create_folder(path)
        except Exception as e:
            raise FileSystemError(f"Failed to create directory {path}: {str(e)}") from e

    def delete_file(self, path: str) -> None:
        """
        Delete a file or empty directory

        Args:
            path: Path to file or directory to delete

        Raises:
            FileSystemError: If deletion fails
        """
        try:
            self._mtp.delete_object(path)
        except Exception as e:
            raise FileSystemError(f"Failed to delete {path}: {str(e)}") from e
