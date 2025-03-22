"""
Implements command-line commands and user interaction.
"""

import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional
from datetime import datetime

import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn

from amtt.core.device import Device, DeviceConnectionError, DeviceManager
from amtt.core.filesystem import FileInfo, FileSystemError, FileType
from amtt.core.transfer import OrganizationStrategy, TransferProgress, TransferResult
from amtt.core.batch import BatchConfig
from amtt.core.transfer_log import TransferLogger

# Global state
current_device: Device | None = None
DEVICE_INFO_FILE = os.path.join(tempfile.gettempdir(), "amtt_device.json")

# Rich console for pretty output
console = Console()

def save_device_info(device: Device):
    """Save device info to temporary file"""
    info = {
        "name": device.name,
        "serial": device.serial,
        "storage_info": [
            {"id": s.id, "name": s.name, "capacity": s.capacity}
            for s in device.storage_info
        ]
    }
    with open(DEVICE_INFO_FILE, "w") as f:
        json.dump(info, f)

def load_device_info() -> Optional[dict]:
    """Load device info from temporary file"""
    try:
        with open(DEVICE_INFO_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None

def get_current_device() -> Device:
    """Get current device or exit if not connected"""
    global current_device
    
    if current_device is None:
        # Try to load device info and reconnect
        info = load_device_info()
        if info:
            try:
                device_manager = DeviceManager()
                devices = device_manager.get_connected_devices()
                
                # Find the previously connected device
                for device in devices:
                    if device.serial == info["serial"]:
                        current_device = device
                        break
            except Exception:
                pass
    
    if current_device is None:
        console.print("[red]No device connected. Run 'amtt connect' first.[/red]")
        sys.exit(1)
    
    return current_device


def format_size(size: int) -> str:
    """Format size in bytes to human readable string"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}" 
        size /= 1024
    return f"{size:.1f} PB"


def format_progress(p: TransferProgress) -> str:
    """Format transfer progress for display"""
    return (
        f"{p.filename}: {p.percentage:.1f}% "
        f"({format_size(p.bytes_transferred)}/{format_size(p.total_bytes)})"
    )


@click.group()
def cli():
    """Android Media Transfer Tool - Transfer media files from Android devices

    This tool helps you transfer files between your computer and Android device.
    
    Common commands:
    \b
    - connect         Connect to your Android device
    - list           List files and folders on the device
    - transfer       Transfer files to/from the device
    - pull           Copy files from device to computer
    - push           Copy files from computer to device
    """
    pass


@cli.command()
@click.option('--force', is_flag=True, help='Force new connection even if already connected')
def connect(force: bool):
    """Connect to an Android device
    
    This command will:
    1. Look for connected Android devices
    2. Let you choose which device to connect to
    3. Show device information and storage
    
    Your device needs to be:
    - Connected via USB cable
    - Not in charging-only mode
    - Have file transfer enabled
    """
    global current_device

    if current_device is not None and not force:
        console.print(f"[yellow]Already connected to {current_device.name}[/yellow]")
        console.print("Use --force to connect to a different device")
        return

    with console.status("[bold blue]Looking for Android devices...[/bold blue]") as status:
        try:
            device_manager = DeviceManager()
            devices = device_manager.get_connected_devices()

            if not devices:
                console.print("\n[red]No devices found![/red]")
                console.print("\nPlease check:")
                console.print("1. Your device is connected via USB")
                console.print("2. USB debugging is enabled (for ADB)")
                console.print("3. File transfer mode is enabled (for MTP)")
                console.print("4. You have authorized this computer on your device")
                sys.exit(1)

            if len(devices) == 1:
                current_device = devices[0]
            else:
                # Create a table for device selection
                table = Table(title="Available Devices")
                table.add_column("Number", justify="right", style="cyan")
                table.add_column("Name", style="green")
                table.add_column("Serial", style="blue")
                table.add_column("Storage", justify="right", style="magenta")
                
                for i, device in enumerate(devices, 1):
                    total_storage = sum(s.capacity for s in device.storage_info)
                    table.add_row(
                        str(i),
                        device.name,
                        device.serial,
                        format_size(total_storage)
                    )
                
                console.print(table)
                choice = click.prompt(
                    "\nSelect device number",
                    type=click.IntRange(1, len(devices)),
                    default=1
                )
                current_device = devices[choice - 1]

            # Save device info for persistence
            save_device_info(current_device)

            # Show device info in a pretty table
            console.print(f"\n[green]Connected to {current_device.name}[/green]")
            
            table = Table(title="Storage Units")
            table.add_column("Name", style="blue")
            table.add_column("Capacity", justify="right", style="green")
            table.add_column("Type", style="yellow")
            
            for storage in current_device.storage_info:
                table.add_row(
                    storage.name,
                    format_size(storage.capacity),
                    "Internal" if "internal" in storage.name.lower() else "External"
                )
                
            console.print(table)

        except DeviceConnectionError as e:
            console.print(f"\n[red]Failed to connect: {str(e)}[/red]")
            sys.exit(1)


@cli.command()
@click.argument("path", type=str, default="/")
@click.option('--sort', type=click.Choice(['name', 'size', 'date']), default='name',
              help='Sort files by name, size, or date')
@click.option('--reverse', is_flag=True, help='Reverse sort order')
def list(path: str, sort: str, reverse: bool):
    """List files and folders on the device
    
    PATH is the directory to list (default: root directory '/')
    
    Examples:
    \b
    - List root directory:        amtt list
    - List DCIM folder:          amtt list /DCIM
    - List by size:              amtt list /DCIM --sort size
    - List newest first:         amtt list /DCIM --sort date --reverse
    """
    try:
        device = get_current_device()
        
        with console.status(f"[blue]Reading {path}...[/blue]"):
            files = device.filesystem.list_files(path)

        if not files:
            console.print("[yellow]Directory is empty[/yellow]")
            return

        # Group by type
        folders = []
        media_files = []

        for f in files:
            if f.type == FileType.FOLDER:
                folders.append(f)
            else:
                media_files.append(f)

        # Sort function
        def get_sort_key(f: FileInfo):
            if sort == 'size':
                return f.size or 0
            elif sort == 'date':
                return f.modified_date or datetime.min
            return f.name.lower()

        # Show folders first in a table
        if folders:
            table = Table(title="Folders")
            table.add_column("Name", style="blue")
            table.add_column("Modified", style="green")
            
            for f in sorted(folders, key=get_sort_key, reverse=reverse):
                date_str = (
                    f.modified_date.strftime("%Y-%m-%d %H:%M")
                    if f.modified_date
                    else ""
                )
                table.add_row(f"📁 {f.name}/", date_str)
                
            console.print(table)

        # Show files in a table
        if media_files:
            table = Table(title="Files")
            table.add_column("Type", width=3)
            table.add_column("Name")
            table.add_column("Size", justify="right")
            table.add_column("Modified")
            
            type_icons = {
                FileType.IMAGE: "🖼",
                FileType.VIDEO: "🎥",
                FileType.AUDIO: "🎵",
                FileType.DOCUMENT: "📄",
                FileType.OTHER: "📎",
            }
            
            for f in sorted(media_files, key=get_sort_key, reverse=reverse):
                icon = type_icons.get(f.type, "📄")
                size_str = format_size(f.size) if f.size else "?"
                date_str = (
                    f.modified_date.strftime("%Y-%m-%d %H:%M")
                    if f.modified_date
                    else ""
                )
                table.add_row(icon, f.name, size_str, date_str)
                
            console.print(table)

    except Exception as e:
        console.print(f"[red]Failed to list files: {str(e)}[/red]")
        sys.exit(1)


def _get_organization_strategy(organize: str) -> OrganizationStrategy:
    """Convert organize option to OrganizationStrategy."""
    strategy_map = {
        "none": OrganizationStrategy.NONE,
        "date": OrganizationStrategy.BY_DATE,
        "type": OrganizationStrategy.BY_TYPE,
        "both": OrganizationStrategy.BY_TYPE_AND_DATE,
    }
    return strategy_map[organize]


def _handle_transfer_result(result: TransferResult, file_info: FileInfo, verbose: bool):
    """Handle the result of a file transfer."""
    if result.success:
        console.print(f"[green]Successfully transferred {file_info.name}[/green]")
        if verbose:
            console.print(f"Destination: {result.destination}")
            if result.hash:
                console.print(f"Checksum: {result.hash}")
    else:
        console.print(f"[red]Failed to transfer {file_info.name}: {result.error}[/red]")
        sys.exit(1)


def _handle_batch_transfer(
    device: Device,
    source: str,
    destination: str,
    organize: str,
    delete_source: bool,
    duplicate: str,
    verbose: bool,
    verify: bool = False,
):
    """Handle batch transfer of files."""
    with console.status("[blue]Finding files to transfer...[/blue]"):
        files = device.filesystem.list_files(source)
        
    if not files:
        console.print("[yellow]No files match pattern[/yellow]")
        sys.exit(1)

    console.print(f"\nFound {len(files)} files for transfer")
    if not click.confirm("Do you want to proceed?"):
        console.print("[yellow]Transfer cancelled[/yellow]")
        return

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task("Transferring files...", total=len(files))
        
        for file in files:
            progress.update(task, description=f"Transferring {file.name}")
            result = device.transfer_manager.transfer_file(
                file,
                Path(destination),
                organization=_get_organization_strategy(organize),
                delete_source=delete_source,
                duplicate_strategy=duplicate,
                verify=verify
            )
            if result.success:
                progress.advance(task)
            else:
                progress.stop()
                console.print(f"[red]Failed to transfer {file.name}: {result.error}[/red]")
                sys.exit(1)

    console.print(f"[green]Successfully transferred {len(files)} files[/green]")


def _handle_single_transfer(
    device: Device,
    source: str,
    destination: str,
    organize: str,
    delete_source: bool,
    duplicate: str,
    verbose: bool,
    verify: bool = False,
):
    """Handle single file transfer."""
    try:
        file_info = device.filesystem.get_file_info(source)
    except FileSystemError:
        console.print(f"[red]Source file not found: {source}[/red]")
        sys.exit(1)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console
    ) as progress:
        task = progress.add_task(f"Transferring {file_info.name}...", total=100)
        
        def update_progress(p: TransferProgress):
            progress.update(task, completed=p.percentage)
            
        result = device.transfer_manager.transfer_file(
            file_info,
            Path(destination),
            organization=_get_organization_strategy(organize),
            delete_source=delete_source,
            duplicate_strategy=duplicate,
            verify=verify,
            progress_callback=update_progress
        )
        
        if not result.success:
            progress.stop()
            console.print(f"[red]Failed to transfer {file_info.name}: {result.error}[/red]")
            sys.exit(1)

    console.print(f"[green]Successfully transferred {file_info.name}[/green]")


@cli.command()
@click.argument("source", required=False)
@click.argument("destination", required=False)
@click.option(
    "--all",
    is_flag=True,
    help="Transfer files from all default enabled paths"
)
@click.option(
    "--batch-size",
    type=click.INT,
    default=2048,
    help="Maximum size of each batch in MB (default: 2048MB)"
)
@click.option(
    "--batch-files",
    type=click.INT,
    default=50,
    help="Maximum files per batch (default: 50)"
)
@click.option(
    "--batch-delay",
    type=click.FLOAT,
    default=1.0,
    help="Delay between batches in seconds (default: 1.0s)"
)
@click.option(
    "--keep-source",
    is_flag=True,
    help="Keep files in source location after transfer (default: files are deleted after successful transfer)"
)
def transfer(source: str, destination: str, all: bool, batch_size: int, batch_files: int, batch_delay: float, keep_source: bool):
    """Transfer files from device to computer
    
    SOURCE: Path on device (not required when using --all)
    DESTINATION: Local destination directory
    
    By default, files are deleted from the source after successful transfer.
    Use --keep-source to keep the original files.
    Use --all to transfer from all default enabled paths.
    
    Examples:
    \b
    - Transfer from all default paths:
      amtt transfer --all ~/Backup
      
    - Transfer from specific path:
      amtt transfer "/Internal storage/DCIM/Camera" ~/Backup
      
    - Transfer and keep source files:
      amtt transfer "/Internal storage/DCIM/Camera" ~/Backup --keep-source
      
    - Transfer all files and keep source:
      amtt transfer --all ~/Backup --keep-source
    """
    try:
        device = get_current_device()
        
        # Update batch configuration
        BatchConfig.MAX_BATCH_SIZE = batch_size * 1024 * 1024  # Convert MB to bytes
        BatchConfig.MAX_FILES_PER_BATCH = batch_files
        BatchConfig.BATCH_DELAY = batch_delay
        
        if all:
            # When using --all, source becomes destination if provided
            final_destination = source if source else destination
            if not final_destination:
                console.print("[red]Error: Destination path is required[/red]")
                sys.exit(1)
            
            # Get all enabled paths
            enabled_paths = []
            paths = device.get_configured_paths()
            for path_config in paths:
                if path_config.enabled:
                    enabled_paths.append(path_config.path)
            
            if not enabled_paths:
                console.print("[yellow]No enabled paths found in configuration[/yellow]")
                return
                
            console.print(f"[green]Transferring files from {len(enabled_paths)} enabled paths:[/green]")
            for source_path in enabled_paths:
                console.print(f"  • {source_path}")
            
            # Transfer from each enabled path
            total_transferred = 0
            total_failed = 0
            
            for source_path in enabled_paths:
                console.print(f"\n[cyan]Processing {source_path}...[/cyan]")
                result = device.transfer_manager.transfer_files(
                    [source_path],
                    final_destination,
                    delete_source=not keep_source
                )
                total_transferred += len(result.successful_files)
                total_failed += len(result.failed_files)
            
            # Show final summary
            if total_transferred > 0:
                console.print(f"\n[green]Total files transferred: {total_transferred}[/green]")
            if total_failed > 0:
                console.print(f"[red]Total files failed: {total_failed}[/red]")
                
        else:
            # For non-all transfers, we need both source and destination
            if not source:
                console.print("[red]Error: Source path is required[/red]")
                sys.exit(1)
                
            final_destination = destination
            if not final_destination:
                final_destination = click.prompt("Enter destination path", type=str)
                
            # Single path transfer
            result = device.transfer_manager.transfer_files(
                [source],
                final_destination,
                delete_source=not keep_source
            )
            
    except DeviceConnectionError:
        console.print("[red]No device connected. Run 'amtt connect' first.[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")

def _format_size(size: int) -> str:
    """Format size in bytes to human readable string"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


@cli.command()
@click.argument("device_path", type=str)
@click.argument("local_path", type=str, default=".")
@click.option(
    "--organize",
    type=click.Choice(["none", "date", "type", "both"]),
    default="none",
    help="How to organize transferred files",
)
@click.option("--verify", is_flag=True, help="Verify transferred files with checksum")
def pull(device_path: str, local_path: str, organize: str, verify: bool):
    """Copy files FROM device TO computer
    
    DEVICE_PATH: Path on the device
    LOCAL_PATH: Local destination directory (default: current directory)
    
    This is a shortcut for 'transfer' command with common options for
    pulling files from device.
    
    Examples:
    \b
    - Pull photos:
      amtt pull /DCIM/Camera ~/Pictures/
      
    - Pull and organize by date:
      amtt pull /DCIM/Camera ~/Pictures/ --organize date
    """
    transfer.callback(
        device_path,
        local_path,
        organize=organize,
        delete_source=False,
        duplicate="rename",
        verbose=True,
        verify=verify,
        batch=True,
    )


@cli.command()
@click.argument("local_path", type=str)
@click.argument("device_path", type=str, default="/")
@click.option("--verify", is_flag=True, help="Verify transferred files with checksum")
def push(local_path: str, device_path: str, verify: bool):
    """Copy files FROM computer TO device
    
    LOCAL_PATH: Local file or directory to copy
    DEVICE_PATH: Destination path on device (default: root directory)
    
    This is a shortcut for 'transfer' command with common options for
    pushing files to device.
    
    Examples:
    \b
    - Push a file:
      amtt push ~/Documents/file.pdf /Documents/
      
    - Push and verify:
      amtt push ~/Music/song.mp3 /Music/ --verify
    """
    transfer.callback(
        local_path,
        device_path,
        organize="none",
        delete_source=False,
        duplicate="rename",
        verbose=True,
        verify=verify,
        batch=os.path.isdir(local_path),
    )


@click.group()
def paths():
    """Manage configured device paths"""
    pass

@paths.command()
def list():
    """List configured paths for the current device"""
    try:
        device = get_current_device()
        paths = device.get_configured_paths()
        
        table = Table(title=f"Configured Paths for {device.name}")
        table.add_column("Path")
        table.add_column("Description")
        table.add_column("Local Path")
        table.add_column("Enabled")
        
        for path in paths:
            table.add_row(
                path.path,
                path.description,
                path.local_path or "Default",
                "✓" if path.enabled else "✗"
            )
            
        console.print(table)
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")

@paths.command()
@click.argument("path")
@click.argument("description")
def add(path: str, description: str):
    """Add a new path to device configuration"""
    try:
        device = get_current_device()
        device.add_path(path, description)
        console.print(f"[green]Added path: {path}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")

@paths.command()
@click.argument("path")
def remove(path: str):
    """Remove a path from device configuration"""
    try:
        device = get_current_device()
        device.remove_path(path)
        console.print(f"[green]Removed path: {path}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")

@paths.command()
@click.argument("path")
@click.argument("enabled", type=bool)
def enable(path: str, enabled: bool):
    """Enable or disable a path"""
    try:
        device = get_current_device()
        device.set_path_enabled(path, enabled)
        status = "enabled" if enabled else "disabled"
        console.print(f"[green]Path {path} {status}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")

@paths.command()
@click.argument("path")
@click.argument("local_path", type=click.Path())
def set_local_path(path: str, local_path: str):
    """Set local download path for a device path"""
    try:
        device = get_current_device()
        device.set_local_path(path, local_path)
        console.print(f"[green]Set local path for {path} to {local_path}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")

@click.group()
def device():
    """Manage device settings"""
    pass

@device.command()
@click.argument("name")
def rename(name: str):
    """Set a friendly name for the device"""
    try:
        device = get_current_device()
        device.set_friendly_name(name)
        console.print(f"[green]Device renamed to: {name}[/green]")
    except Exception as e:
        console.print(f"[red]Error: {str(e)}[/red]")

@cli.command()
@click.option(
    "--date",
    type=str,
    help="Show logs for specific date (YYYY-MM-DD format)"
)
@click.option(
    "--show-files",
    is_flag=True,
    help="Show detailed file lists in the log"
)
def logs(date: str = None, show_files: bool = False):
    """View transfer operation logs
    
    Examples:
    \b
    - View today's logs:
      amtt logs
      
    - View logs for specific date:
      amtt logs --date 2025-03-22
      
    - View logs with file details:
      amtt logs --show-files
    """
    logger = TransferLogger()
    
    # Get available dates if no date specified
    if date is None:
        dates = logger.get_log_dates()
        if not dates:
            console.print("[yellow]No transfer logs found[/yellow]")
            return
        date = dates[-1]  # Use most recent date
    
    # Get logs for the specified date
    entries = logger.get_entries(date)
    if not entries:
        console.print(f"[yellow]No transfer logs found for {date}[/yellow]")
        return
    
    # Create table for log display
    table = Table(title=f"Transfer Logs for {date}")
    table.add_column("Time", style="cyan")
    table.add_column("Source", style="green")
    table.add_column("Destination", style="blue")
    table.add_column("Status", style="yellow")
    table.add_column("Size", style="magenta")
    table.add_column("Duration", style="cyan")
    
    # Add entries to table
    for entry in entries:
        # Parse timestamp
        time = datetime.fromisoformat(entry.timestamp).strftime("%H:%M:%S")
        
        # Create status summary
        total_files = len(entry.successful_files) + len(entry.failed_files)
        if total_files == 0:
            status = "No files"
        else:
            success_rate = len(entry.successful_files) / total_files * 100
            status = f"{len(entry.successful_files)}/{total_files} ({success_rate:.1f}%)"
        
        # Format size
        size = _format_size(entry.total_size) if entry.total_size > 0 else "0B"
        
        # Add row
        table.add_row(
            time,
            entry.source_dir,
            entry.destination_dir,
            status,
            size,
            f"{entry.duration:.1f}s"
        )
        
        # Show file details if requested
        if show_files and (entry.successful_files or entry.failed_files or entry.failed_paths):
            if entry.successful_files:
                console.print("\n[green]Successfully transferred:[/green]")
                for file in entry.successful_files:
                    console.print(f"  ✓ {file}")
                    
            if entry.failed_files:
                console.print("\n[red]Failed to transfer:[/red]")
                for file in entry.failed_files:
                    console.print(f"  ✗ {file}")
                    
            if entry.failed_paths:
                console.print("\n[red]Failed to access:[/red]")
                for path in entry.failed_paths:
                    console.print(f"  ✗ {path}")
            
            console.print()  # Add blank line between entries
    
    # Display the table
    console.print(table)

# Register command groups
cli.add_command(paths)
cli.add_command(device)

if __name__ == "__main__":
    cli()
