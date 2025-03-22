"""
Implements command-line commands and user interaction.
"""

import sys
from pathlib import Path

import click

from amtt.core.device import Device, DeviceConnectionError, DeviceManager
from amtt.core.filesystem import FileInfo, FileSystemError, FileType
from amtt.core.transfer import OrganizationStrategy, TransferProgress, TransferResult

# Global state
current_device: Device | None = None


def get_current_device() -> Device:
    """Get current device or exit if not connected"""
    if current_device is None:
        click.echo("No device connected. Run 'amtt connect' first.", err=True)
        sys.exit(1)
    return current_device


def format_size(size: int) -> str:
    """Format size in bytes to human readable string"""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}" 
        size /= 1024
    return f"{size:.1f} TB"


def format_progress(p: TransferProgress) -> str:
    """Format transfer progress for display"""
    return (
        f"{p.filename}: {p.percentage:.1f}% "
        f"({format_size(p.bytes_transferred)}/{format_size(p.total_bytes)})"
    )


@click.group()
def cli():
    """Android Media Transfer Tool - Transfer media files from Android devices"""
    pass


@cli.command()
def connect():
    """Connect to an Android device"""
    global current_device

    try:
        device_manager = DeviceManager()
        devices = device_manager.get_connected_devices()

        if not devices:
            click.echo(
                "No devices found. Please connect a device and try again.", err=True
            )
            sys.exit(1)

        if len(devices) == 1:
            current_device = devices[0]
        else:
            # Let user choose if multiple devices
            click.echo("Multiple devices found:")
            for i, device in enumerate(devices):
                click.echo(f"{i + 1}. {device.name} ({device.serial})")
            choice = click.prompt("Select device number", type=int, default=1)
            current_device = devices[choice - 1]

        # Show device info
        click.echo(f"\nConnected to {current_device.name}")
        click.echo("Storage units:")
        for storage in current_device.storage_info:
            click.echo(f"- {storage.name}: {format_size(storage.capacity)}")

    except DeviceConnectionError as e:
        click.echo(f"Failed to connect: {str(e)}", err=True)
        sys.exit(1)


@cli.command()
@click.argument("path", type=str, default="/")
def list(path: str):
    """List files and folders on the device"""
    try:
        device = get_current_device()
        files = device.filesystem.list_files(path)

        if not files:
            click.echo("Directory is empty")
            return

        # Group by type
        folders = []
        media_files = []

        for f in files:
            if f.type == FileType.FOLDER:
                folders.append(f)
            else:
                media_files.append(f)

        # Show folders first
        if folders:
            click.echo("\nFolders:")
            for f in sorted(folders, key=lambda x: x.name):
                click.echo(f"📁 {f.name}/")

        if media_files:
            click.echo("\nFiles:")
            for f in sorted(media_files, key=lambda x: x.name):
                type_icon = {
                    FileType.IMAGE: "🖼",
                    FileType.VIDEO: "🎥",
                    FileType.AUDIO: "🎵",
                    FileType.DOCUMENT: "📄",
                    FileType.OTHER: "📎",
                }.get(f.type, "📄")

                size_str = format_size(f.size) if f.size else "?"
                date_str = (
                    f.modified_date.strftime("%Y-%m-%d %H:%M")
                    if f.modified_date
                    else ""
                )

                click.echo(f"{type_icon} {f.name:<30} {size_str:<10} {date_str}")

    except Exception as e:
        click.echo(f"Failed to list files: {str(e)}", err=True)
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
        click.echo(f"\nSuccessfully transferred {file_info.name}")
        if verbose:
            click.echo(f"Destination: {result.destination}")
            if result.hash:
                click.echo(f"Checksum: {result.hash}")
    else:
        click.echo(f"\nFailed to transfer {file_info.name}: {result.error}", err=True)
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
    files = device.filesystem.list_files(source)
    if not files:
        click.echo("No files match pattern", err=True)
        sys.exit(1)

    click.echo(f"\nFound {len(files)} files for transfer")
    if not click.confirm("Do you want to proceed?"):
        click.echo("Transfer cancelled")
        return

    with click.progressbar(
        files, label="Transferring files", item_show_func=lambda f: f.name if f else ""
    ) as progress_bar:
        results = device.transfer_manager.batch_transfer(
            progress_bar,
            Path(destination),
            organization=_get_organization_strategy(organize),
            delete_source=delete_source,
            duplicate_strategy=duplicate,
            verify=verify,
        )

    success_count = sum(1 for r in results if r.success)
    if success_count == len(files):
        click.echo(f"\nSuccessfully transferred {success_count} files")
    else:
        click.echo(f"\nTransferred {success_count} of {len(files)} files", err=True)
        sys.exit(1)


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
    """Handle transfer of a single file."""
    try:
        file_info = device.filesystem.get_file_info(source)
    except FileSystemError as e:
        click.echo(f"Error: {str(e)}", err=True)
        sys.exit(1)

    with click.progressbar(
        length=file_info.size or 100,
        label=f"Transferring {file_info.name}",
        item_show_func=lambda x: format_progress(x) if x else "",
    ) as progress_bar:
        result = device.transfer_manager.transfer_file(
            file_info,
            Path(destination),
            organization=_get_organization_strategy(organize),
            delete_source=delete_source,
            duplicate_strategy=duplicate,
            verify=verify,
            progress_callback=lambda p: progress_bar.update(p.bytes_transferred),
        )

    _handle_transfer_result(result, file_info, verbose)


@cli.command()
@click.argument("source", type=str)
@click.argument("destination", type=str)
@click.option(
    "--organize",
    type=click.Choice(["none", "date", "type", "both"]),
    default="none",
    help="File organization strategy",
)
@click.option(
    "--delete-source", is_flag=True, help="Delete source files after transfer"
)
@click.option(
    "--duplicate",
    type=click.Choice(["rename", "skip", "overwrite"]),
    default="rename",
    help="How to handle duplicate files",
)
@click.option("--verbose", "-v", is_flag=True, help="Show detailed progress")
@click.option("--batch", is_flag=True, help="Transfer all files in directory")
@click.option("--verify", is_flag=True, help="Verify transferred files with hash")
def transfer(
    source: str,
    destination: str,
    organize: str,
    delete_source: bool,
    duplicate: str,
    verbose: bool,
    batch: bool,
    verify: bool,
):
    """Transfer files from device to local system."""
    device = get_current_device()
    if not device:
        sys.exit(1)

    if batch:
        _handle_batch_transfer(
            device, source, destination, organize, delete_source, duplicate, verbose, verify
        )
    else:
        _handle_single_transfer(
            device, source, destination, organize, delete_source, duplicate, verbose, verify
        )


if __name__ == "__main__":
    cli()
