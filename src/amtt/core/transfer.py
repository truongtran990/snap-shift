"""
Transfer module for Android Media Transfer Tool.
Handles file transfer operations and organization.
"""

import hashlib
import shutil
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Optional, List, Generator
import os
import time

from amtt.core.filesystem import FileInfo, FileType
from amtt.core.batch import BatchConfig
from amtt.core.transfer_log import TransferLogger, TransferLogEntry
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn


class OrganizationStrategy(Enum):
    """File organization strategies"""

    NONE = auto()
    BY_DATE = auto()
    BY_TYPE = auto()
    BY_TYPE_AND_DATE = auto()


@dataclass
class TransferProgress:
    """Progress information for a file transfer"""

    current_file: str
    total_files: int
    current_size: int
    total_size: int
    current_batch: int
    total_batches: int
    started_at: datetime
    successful_files: List[str] = field(default_factory=list)
    failed_files: List[str] = field(default_factory=list)


@dataclass
class TransferResult:
    """Result of a file transfer operation"""

    successful_files: List[str] = field(default_factory=list)
    failed_files: List[str] = field(default_factory=list)
    total_size: int = 0
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    duration: float = 0.0
    failed_paths: List[str] = field(default_factory=list)


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
        self._logger = TransferLogger()

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

    def _create_batches(self, files: List[str]) -> Generator[List[str], None, None]:
        """
        Create batches of files for transfer
        
        Args:
            files: List of file paths to transfer
            
        Yields:
            List of file paths for each batch
        """
        current_batch = []
        current_batch_size = 0
        
        for file_path in files:
            try:
                # Get file info
                file_info = self._filesystem.get_file_info(file_path)
                file_size = file_info.size or 0
                
                # If this single file is larger than batch size, make it its own batch
                if file_size > BatchConfig.MAX_BATCH_SIZE:
                    if current_batch:
                        yield current_batch
                    yield [file_path]
                    current_batch = []
                    current_batch_size = 0
                    continue
                
                # If adding this file would exceed batch limits, yield current batch
                if (current_batch_size + file_size > BatchConfig.MAX_BATCH_SIZE or
                    len(current_batch) >= BatchConfig.MAX_FILES_PER_BATCH):
                    yield current_batch
                    current_batch = []
                    current_batch_size = 0
                
                # Add file to current batch
                current_batch.append(file_path)
                current_batch_size += file_size
                
            except Exception as e:
                print(f"Warning: Failed to get info for {file_path}: {e}")
                continue
        
        # Yield any remaining files
        if current_batch:
            yield current_batch

    def _get_total_size(self, files: List[str]) -> int:
        """Calculate total size of files to transfer"""
        total_size = 0
        for file_path in files:
            try:
                file_info = self._filesystem.get_file_info(file_path)
                total_size += file_info.size or 0
            except Exception:
                continue
        return total_size

    def _format_size(self, size: int) -> str:
        """Format size in bytes to human readable string"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024:
                return f"{size:.1f}{unit}"
            size /= 1024
        return f"{size:.1f}TB"

    def transfer_files(
        self,
        source_paths: List[str],
        destination_dir: str,
        delete_source: bool = True,
        progress_callback=None
    ) -> TransferResult:
        """
        Transfer files in batches
        
        Args:
            source_paths: List of source file paths
            destination_dir: Destination directory
            delete_source: Whether to delete source files after successful transfer (default: True)
            progress_callback: Callback for progress updates
            
        Returns:
            TransferResult with transfer statistics
        """
        result = TransferResult()
        
        # Check if source paths exist and contain files
        available_files = []
        for source_path in source_paths:
            try:
                # Check if path is a file or directory
                file_info = self._filesystem.get_file_info(source_path)
                
                if file_info.type == FileType.FOLDER:
                    # Get all files in directory
                    try:
                        for file_info in self._filesystem.list_files(source_path):
                            if file_info.type != FileType.FOLDER:  # Skip folders
                                available_files.append(file_info.path)
                    except Exception as e:
                        print(f"\n[yellow]Directory is empty or all files have been transferred: {source_path}[/yellow]")
                        continue
                else:
                    # Single file
                    available_files.append(source_path)
                    
            except Exception as e:
                print(f"\n[red]Error accessing {source_path}: {str(e)}[/red]")
                result.failed_paths.append(source_path)
                continue
        
        if not available_files:
            print("\n[yellow]No files found to transfer in any of the source paths[/yellow]")
            result.completed_at = datetime.now()
            result.duration = (result.completed_at - result.started_at).total_seconds()
            
            # Log empty transfer
            self._logger.add_entry(TransferLogEntry(
                timestamp=datetime.now().isoformat(),
                source_dir=source_paths[0] if source_paths else "",
                destination_dir=destination_dir,
                successful_files=[],
                failed_files=[],
                failed_paths=result.failed_paths,
                total_size=0,
                duration=result.duration,
                delete_source=delete_source
            ))
            
            return result
            
        total_size = self._get_total_size(available_files)
        print(f"\nFound {len(available_files)} files to transfer ({self._format_size(total_size)})")
        
        # Create batches
        batches = list(self._create_batches(available_files))
        total_batches = len(batches)
        
        # Process each batch
        for batch_num, batch in enumerate(batches, 1):
            batch_size = self._get_total_size(batch)
            
            # Create progress message
            batch_info = (
                f"Batch {batch_num}/{total_batches} "
                f"({self._format_size(batch_size)}/{self._format_size(total_size)})"
            )
            print(f"\nProcessing {batch_info}")
            
            # Process files in this batch
            for file_num, source_path in enumerate(batch, 1):
                try:
                    # Get source file info
                    file_info = self._filesystem.get_file_info(source_path)
                    file_size = file_info.size or 0
                    
                    # Create destination path
                    rel_path = source_path.replace("/Internal shared storage/", "", 1)
                    dest_path = os.path.join(destination_dir, rel_path)
                    
                    # Ensure destination directory exists
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    
                    # Copy file
                    print(
                        f"Copying {file_num}/{len(batch)}: "
                        f"{os.path.basename(source_path)} "
                        f"({self._format_size(file_size)})"
                    )
                    
                    try:
                        source_full_path = os.path.join(self._device.mount_point, source_path.lstrip("/"))
                        shutil.copy2(source_full_path, dest_path)
                        
                        # Delete source file if requested
                        if delete_source:
                            try:
                                os.remove(source_full_path)
                            except Exception as e:
                                print(f"[yellow]Warning: Failed to delete source file {source_path}: {e}[/yellow]")
                        
                        # Update result
                        result.successful_files.append(source_path)
                        result.total_size += file_size
                        
                    except Exception as e:
                        print(f"[red]Error copying {source_path}: {e}[/red]")
                        result.failed_files.append(source_path)
                    
                    # Update progress
                    if progress_callback:
                        progress_callback(TransferProgress(
                            current_file=source_path,
                            total_files=len(available_files),
                            current_size=result.total_size,
                            total_size=total_size,
                            current_batch=batch_num,
                            total_batches=total_batches,
                            started_at=result.started_at,
                            successful_files=result.successful_files,
                            failed_files=result.failed_files
                        ))
                        
                except Exception as e:
                    print(f"[red]Error processing {source_path}: {e}[/red]")
                    result.failed_files.append(source_path)
            
            # Delay between batches (except for the last batch)
            if batch_num < total_batches:
                print(f"Waiting {BatchConfig.BATCH_DELAY}s before next batch...")
                time.sleep(BatchConfig.BATCH_DELAY)
        
        result.completed_at = datetime.now()
        result.duration = (result.completed_at - result.started_at).total_seconds()
        
        # Log transfer result
        self._logger.add_entry(TransferLogEntry(
            timestamp=datetime.now().isoformat(),
            source_dir=source_paths[0] if source_paths else "",
            destination_dir=destination_dir,
            successful_files=result.successful_files,
            failed_files=result.failed_files,
            failed_paths=result.failed_paths,
            total_size=result.total_size,
            duration=result.duration,
            delete_source=delete_source
        ))
        
        # Print final summary
        if result.successful_files:
            print(
                f"\n[green]Successfully transferred "
                f"{len(result.successful_files)} files "
                f"({self._format_size(result.total_size)})"
            )
            if delete_source:
                print("[green]Source files have been deleted[/green]")
            
        if result.failed_files:
            print(
                f"\n[red]Failed to transfer {len(result.failed_files)} files:"
            )
            for file in result.failed_files:
                print(f"  - {file}")
                
        if result.failed_paths:
            print(
                f"\n[red]Failed to access {len(result.failed_paths)} paths:"
            )
            for path in result.failed_paths:
                print(f"  - {path}")
                
        if result.duration > 0:
            print(f"\nTransfer completed in {result.duration:.1f} seconds")
            
        return result

    def create_directory(self, path: str):
        """Create a directory at the specified path"""
        self._filesystem.create_directory(path)
