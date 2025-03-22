from datetime import datetime
from pathlib import Path
from unittest.mock import ANY, Mock, patch

import pytest
from click.testing import CliRunner

from amtt.cli.commands import cli, format_progress, format_size
from amtt.core.device import Device, StorageInfo
from amtt.core.filesystem import FileInfo, FileSystem, FileType
from amtt.core.transfer import TransferManager, TransferProgress, TransferResult


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_device_manager():
    with patch("amtt.cli.commands.DeviceManager") as mock:
        yield mock


@pytest.fixture
def mock_device():
    device = Mock(spec=Device)
    device.name = "Test Device"
    device.serial = "123456789"
    device.storage_info = [StorageInfo(id=1, name="Internal Storage", capacity=1000000)]
    # Add filesystem and transfer_manager attributes
    device.filesystem = Mock(spec=FileSystem)
    device.transfer_manager = Mock(spec=TransferManager)
    return device


def test_connect_command_success(runner, mock_device_manager, mock_device):
    mock_device_manager.return_value.get_connected_devices.return_value = [mock_device]

    result = runner.invoke(cli, ["connect"])

    assert result.exit_code == 0
    assert "Connected to Test Device" in result.output
    assert "Internal Storage" in result.output


def test_connect_command_no_devices(runner, mock_device_manager):
    mock_device_manager.return_value.get_connected_devices.return_value = []

    result = runner.invoke(cli, ["connect"])

    assert result.exit_code != 0
    assert "No devices found" in result.output


def test_list_command(runner, mock_device_manager, mock_device):
    # Mock filesystem
    files = [
        FileInfo("photo.jpg", "/DCIM/photo.jpg", FileType.IMAGE, 1024),
        FileInfo("video.mp4", "/DCIM/video.mp4", FileType.VIDEO, 2048),
    ]

    with patch("amtt.cli.commands.get_current_device") as mock_get_device:
        mock_get_device.return_value = mock_device
        mock_device.filesystem.list_files.return_value = files

        result = runner.invoke(cli, ["list", "/DCIM"])

        assert result.exit_code == 0
        assert "photo.jpg" in result.output
        assert "video.mp4" in result.output
        assert "1.0 KB" in result.output
        assert "2.0 KB" in result.output


def test_list_command_empty(runner, mock_device_manager, mock_device):
    with patch("amtt.cli.commands.get_current_device") as mock_get_device:
        mock_get_device.return_value = mock_device
        mock_device.filesystem.list_files.return_value = []

        result = runner.invoke(cli, ["list", "/empty"])

        assert result.exit_code == 0
        assert "Directory is empty" in result.output


def test_list_command_error(runner, mock_device_manager, mock_device):
    with patch("amtt.cli.commands.get_current_device") as mock_get_device:
        mock_get_device.return_value = mock_device
        mock_device.filesystem.list_files.side_effect = Exception("Access denied")

        result = runner.invoke(cli, ["list", "/error"])

        assert result.exit_code != 0
        assert "Failed to list files" in result.output


def test_transfer_command(runner, mock_device_manager, mock_device):
    # Mock files and transfer
    file_info = FileInfo("photo.jpg", "/DCIM/photo.jpg", FileType.IMAGE, 1024)
    transfer_result = TransferResult(
        source=file_info, destination=Path("/dest/photo.jpg"), success=True
    )

    with patch("amtt.cli.commands.get_current_device") as mock_get_device:
        mock_get_device.return_value = mock_device
        mock_device.filesystem.get_file_info.return_value = file_info
        mock_device.transfer_manager.transfer_file.return_value = transfer_result

        result = runner.invoke(
            cli, ["transfer", "/DCIM/photo.jpg", "/dest", "--verify"]
        )

        assert result.exit_code == 0
        assert "Successfully transferred" in result.output
        mock_device.transfer_manager.transfer_file.assert_called_with(
            file_info,
            Path("/dest"),
            organization=ANY,
            verify=True,
            duplicate_strategy="rename",
            progress_callback=ANY,
            delete_source=False,
        )


def test_transfer_command_error(runner, mock_device_manager, mock_device):
    # Mock transfer error
    file_info = FileInfo("photo.jpg", "/DCIM/photo.jpg", FileType.IMAGE, 1024)
    transfer_result = TransferResult(
        source=file_info,
        destination=Path("/dest/photo.jpg"),
        success=False,
        error="Transfer failed",
    )

    with patch("amtt.cli.commands.get_current_device") as mock_get_device:
        mock_get_device.return_value = mock_device
        mock_device.filesystem.get_file_info.return_value = file_info
        mock_device.transfer_manager.transfer_file.return_value = transfer_result

        result = runner.invoke(cli, ["transfer", "/DCIM/photo.jpg", "/dest"])

        assert result.exit_code != 0
        assert "Failed to transfer" in result.output


def test_transfer_with_organization(runner, mock_device_manager, mock_device):
    file_info = FileInfo(
        "photo.jpg",
        "/DCIM/photo.jpg",
        FileType.IMAGE,
        1024,
        modified_date=datetime(2024, 3, 20),
    )
    transfer_result = TransferResult(
        source=file_info, destination=Path("/dest/2024/03/20/photo.jpg"), success=True
    )

    with patch("amtt.cli.commands.get_current_device") as mock_get_device:
        mock_get_device.return_value = mock_device
        mock_device.filesystem.get_file_info.return_value = file_info
        mock_device.transfer_manager.transfer_file.return_value = transfer_result

        result = runner.invoke(
            cli, ["transfer", "/DCIM/photo.jpg", "/dest", "--organize", "date"]
        )

        assert result.exit_code == 0
        assert "Successfully transferred" in result.output
        mock_device.transfer_manager.transfer_file.assert_called_with(
            file_info,
            Path("/dest"),
            organization=ANY,
            verify=False,
            duplicate_strategy="rename",
            progress_callback=ANY,
            delete_source=False,
        )


def test_transfer_with_delete(runner, mock_device_manager, mock_device):
    file_info = FileInfo("photo.jpg", "/DCIM/photo.jpg", FileType.IMAGE, 1024)
    transfer_result = TransferResult(
        source=file_info, destination=Path("/dest/photo.jpg"), success=True
    )

    with patch("amtt.cli.commands.get_current_device") as mock_get_device:
        mock_get_device.return_value = mock_device
        mock_device.filesystem.get_file_info.return_value = file_info
        mock_device.transfer_manager.transfer_file.return_value = transfer_result

        result = runner.invoke(
            cli, ["transfer", "/DCIM/photo.jpg", "/dest", "--delete-source"]
        )

        assert result.exit_code == 0
        assert "Successfully transferred" in result.output
        mock_device.transfer_manager.transfer_file.assert_called_with(
            file_info,
            Path("/dest"),
            organization=ANY,
            verify=False,
            duplicate_strategy="rename",
            progress_callback=ANY,
            delete_source=True,
        )


def test_batch_transfer_command(runner, mock_device_manager, mock_device):
    # Mock multiple files
    files = [
        FileInfo(f"photo{i}.jpg", f"/DCIM/photo{i}.jpg", FileType.IMAGE, 1024)
        for i in range(3)
    ]
    transfer_results = [
        TransferResult(source=f, destination=Path(f"/dest/{f.name}"), success=True)
        for f in files
    ]

    with patch("amtt.cli.commands.get_current_device") as mock_get_device:
        mock_get_device.return_value = mock_device
        mock_device.filesystem.list_files.return_value = files
        mock_device.transfer_manager.batch_transfer.return_value = transfer_results

        # Provide 'y' as input for the confirmation prompt
        result = runner.invoke(
            cli, ["transfer", "/DCIM/*.jpg", "/dest", "--batch"], input="y\n"
        )

        assert result.exit_code == 0
        assert "Successfully transferred 3 files" in result.output


def test_batch_transfer_no_matches(runner, mock_device_manager, mock_device):
    with patch("amtt.cli.commands.get_current_device") as mock_get_device:
        mock_get_device.return_value = mock_device
        mock_device.filesystem.list_files.return_value = []

        result = runner.invoke(cli, ["transfer", "/DCIM/*.jpg", "/dest", "--batch"])

        assert result.exit_code != 0
        assert "No files match pattern" in result.output


def test_batch_transfer_cancelled(runner, mock_device_manager, mock_device):
    files = [
        FileInfo(f"photo{i}.jpg", f"/DCIM/photo{i}.jpg", FileType.IMAGE, 1024)
        for i in range(3)
    ]

    with patch("amtt.cli.commands.get_current_device") as mock_get_device:
        mock_get_device.return_value = mock_device
        mock_device.filesystem.list_files.return_value = files

        # Provide 'n' as input to cancel the transfer
        result = runner.invoke(
            cli, ["transfer", "/DCIM/*.jpg", "/dest", "--batch"], input="n\n"
        )

        assert result.exit_code == 0
        assert not mock_device.transfer_manager.batch_transfer.called


def test_connect_multiple_devices(runner, mock_device_manager):
    device1 = Mock(spec=Device)
    device1.name = "Device 1"
    device1.serial = "123"
    device1.storage_info = [StorageInfo(id=1, name="Storage 1", capacity=1000)]

    device2 = Mock(spec=Device)
    device2.name = "Device 2"
    device2.serial = "456"
    device2.storage_info = [StorageInfo(id=1, name="Storage 2", capacity=2000)]

    devices = [device1, device2]
    mock_device_manager.return_value.get_connected_devices.return_value = devices

    # Select first device
    result = runner.invoke(cli, ["connect"], input="1\n")

    assert result.exit_code == 0
    assert "Multiple devices found" in result.output
    assert "Device 1" in result.output
    assert "Device 2" in result.output
    assert "Connected to Device 1" in result.output


def test_format_size():
    """Test size formatting function"""
    assert format_size(500) == "500.0 B"
    assert format_size(1024) == "1.0 KB"
    assert format_size(1024 * 1024) == "1.0 MB"
    assert format_size(1024 * 1024 * 1024) == "1.0 GB"
    assert format_size(1024 * 1024 * 1024 * 1024) == "1.0 TB"


def test_format_progress():
    """Test progress formatting function"""
    progress = TransferProgress(
        filename="test.jpg",
        bytes_transferred=512000,
        total_bytes=1024000,
        percentage=50.0,
        speed_bps=1024 * 1024,  # 1MB/s
        eta_seconds=10.5,
    )
    result = format_progress(progress)
    assert "test.jpg" in result
    assert "50.0%" in result
    assert "500.0 KB/1000.0 KB" in result  # Check the actual size format
