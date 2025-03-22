"""
Transfer module for Android Media Transfer Tool.
Handles file transfer operations and organization.
"""

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Optional

from amtt.core.filesystem import FileInfo, FileType


class OrganizationStrategy(Enum):
    """File organization strategies"""

    NONE = auto()
    BY_DATE = auto()
    BY_TYPE = auto()
    BY_TYPE_AND_DATE = auto()


@dataclass
class TransferProgress:
    """Progress information for a file transfer"""

    filename: str
    bytes_transferred: int
    total_bytes: int
    percentage: float
    speed_bps: float
    eta_seconds: float


@dataclass
class TransferResult:
    """Result of a file transfer operation"""

    source: FileInfo
    destination: Path
    success: bool
    error: str | None = None
    hash: str | None = None


class TransferError(Exception):
    """Raised when file transfer operations fail"""

    pass


class TransferManager:
    """Manages file transfer operations"""

    BUFFER_SIZE = 8192  # 8KB buffer size for file transfers

    def __init__(self, device, filesystem):
        """
        Initialize transfer manager

        Args:
            device: Connected Android device instance
            filesystem: FileSystem instance for the device
        """
        self._device = device
        self._filesystem = filesystem
        self._mtp = device._mtp_device

    def _calculate_hash(self, file_path: Path) -> str:
        """
        Calculate SHA-256 hash of a file

        Args:
            file_path: Path to the file

        Returns:
            str: Hex digest of file hash
        """
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            while True:
                data = f.read(self.BUFFER_SIZE)
                if not data:
                    break
                sha256.update(data)
        return sha256.hexdigest()

    def _get_organized_path(
        self, file_info: FileInfo, base_path: Path, strategy: OrganizationStrategy
    ) -> Path:
        """
        Get organized path based on strategy

        Args:
            file_info: Source file information
            base_path: Base destination path
            strategy: Organization strategy to use

        Returns:
            Path: Organized destination path
        """
        if strategy == OrganizationStrategy.NONE:
            return base_path

        parts = []

        if strategy in (
            OrganizationStrategy.BY_TYPE,
            OrganizationStrategy.BY_TYPE_AND_DATE,
        ):
            type_dirs = {
                FileType.IMAGE: "Images",
                FileType.VIDEO: "Videos",
                FileType.AUDIO: "Audio",
                FileType.DOCUMENT: "Documents",
                FileType.OTHER: "Other",
            }
            parts.append(type_dirs.get(file_info.type, "Other"))

        if strategy in (
            OrganizationStrategy.BY_DATE,
            OrganizationStrategy.BY_TYPE_AND_DATE,
        ):
            if file_info.modified_date:
                date = file_info.modified_date
                parts.extend([str(date.year), f"{date.month:02d}", f"{date.day:02d}"])

        return base_path.joinpath(*parts)

    def _handle_duplicate(self, dest_path: Path, strategy: str = "rename") -> Path:
        """
        Handle duplicate files according to strategy

        Args:
            dest_path: Destination file path
            strategy: Duplicate handling strategy ("rename", "skip", or "overwrite")

        Returns:
            Path: Final destination path
        """
        if not dest_path.exists() or strategy == "overwrite":
            return dest_path

        if strategy == "skip":
            raise TransferError(f"Destination file already exists: {dest_path}")

        # Rename strategy
        counter = 1
        while True:
            stem = dest_path.stem
            suffix = dest_path.suffix
            new_path = dest_path.with_name(f"{stem}_{counter}{suffix}")
            if not new_path.exists():
                return new_path
            counter += 1

    def transfer_file(
        self,
        file_info: FileInfo,
        destination: Path,
        organization: OrganizationStrategy = OrganizationStrategy.NONE,
        verify: bool = False,
        duplicate_strategy: str = "rename",
        progress_callback: Callable[[TransferProgress], None] | None = None,
        delete_source: bool = False,
    ) -> TransferResult:
        """
        Transfer a single file from device to local system

        Args:
            file_info: Source file information
            destination: Destination directory path
            organization: File organization strategy
            verify: Whether to verify transfer with hash
            duplicate_strategy: How to handle duplicate files
            progress_callback: Callback for transfer progress updates
            delete_source: Whether to delete source file after transfer

        Returns:
            TransferResult: Result of the transfer operation

        Raises:
            TransferError: If transfer fails
        """
        try:
            # Get organized destination path
            dest_dir = self._get_organized_path(
                file_info, Path(destination), organization
            )
            dest_dir.mkdir(parents=True, exist_ok=True)

            # Handle duplicates
            dest_path = self._handle_duplicate(
                dest_dir / file_info.name, duplicate_strategy
            )

            # Get file content with progress tracking
            file_content = self._mtp.get_file_content(file_info.path)

            # Write file with progress updates
            bytes_written = 0
            file_hash = hashlib.sha256()

            with open(dest_path, "wb") as f:
                for i in range(0, len(file_content), self.BUFFER_SIZE):
                    chunk = file_content[i : i + self.BUFFER_SIZE]
                    f.write(chunk)
                    file_hash.update(chunk)

                    bytes_written += len(chunk)
                    if progress_callback and file_info.size:
                        progress = TransferProgress(
                            filename=file_info.name,
                            bytes_transferred=bytes_written,
                            total_bytes=file_info.size,
                            percentage=(bytes_written / file_info.size) * 100,
                            speed_bps=0,  # TODO: Implement speed calculation
                            eta_seconds=0,  # TODO: Implement ETA calculation
                        )
                        progress_callback(progress)

            # Verify transfer if requested
            if verify:
                if self._calculate_hash(dest_path) != file_hash.hexdigest():
                    raise TransferError("File verification failed")

            # Delete source if requested
            if delete_source:
                self._filesystem.delete_file(file_info.path)

            return TransferResult(
                source=file_info,
                destination=dest_path,
                success=True,
                hash=file_hash.hexdigest() if verify else None,
            )

        except Exception as e:
            return TransferResult(
                source=file_info,
                destination=dest_path if "dest_path" in locals() else None,
                success=False,
                error=str(e),
            )

    def batch_transfer(
        self, files: list[FileInfo], destination: Path, **kwargs
    ) -> list[TransferResult]:
        """
        Transfer multiple files in batch

        Args:
            files: List of files to transfer
            destination: Destination directory path
            **kwargs: Additional arguments passed to transfer_file

        Returns:
            List[TransferResult]: Results for each transfer
        """
        results = []
        for file_info in files:
            result = self.transfer_file(file_info, destination, **kwargs)
            results.append(result)
        return results
