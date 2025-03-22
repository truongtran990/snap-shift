import hashlib
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest

from amtt.core.filesystem import FileInfo, FileType
from amtt.core.transfer import (
    OrganizationStrategy,
    TransferManager,
    TransferProgress,
)


@pytest.fixture
def mock_device():
    device = Mock()
    device._mtp_device = Mock()
    return device


@pytest.fixture
def mock_filesystem():
    return Mock()


@pytest.fixture
def transfer_manager(mock_device, mock_filesystem):
    return TransferManager(mock_device, mock_filesystem)


def test_transfer_single_file_success(
    transfer_manager, mock_device, mock_filesystem, tmp_path
):
    # Setup test data
    source_file = FileInfo(
        name="test.jpg",
        path="/DCIM/test.jpg",
        type=FileType.IMAGE,
        size=1024,
        modified_date=datetime.now(),
        id=1,
    )

    # Mock file content and hash
    file_content = b"test file content"
    file_hash = hashlib.sha256(file_content).hexdigest()

    # Setup mocks
    mock_device._mtp_device.get_file_content.return_value = file_content

    # Perform transfer
    dest_path = tmp_path / "photos"
    result = transfer_manager.transfer_file(source_file, dest_path, verify=True)

    # Verify transfer
    assert result.success
    assert result.destination == dest_path / "test.jpg"
    assert result.source == source_file
    assert result.hash == file_hash

    # Verify file was written correctly
    assert (dest_path / "test.jpg").read_bytes() == file_content


def test_transfer_with_organization(
    transfer_manager, mock_device, mock_filesystem, tmp_path
):
    # Setup test data
    source_file = FileInfo(
        name="test.jpg",
        path="/DCIM/test.jpg",
        type=FileType.IMAGE,
        size=1024,
        modified_date=datetime(2024, 3, 20),
        id=1,
    )

    # Mock file content
    mock_device._mtp_device.get_file_content.return_value = b"test content"

    # Test date-based organization
    result = transfer_manager.transfer_file(
        source_file, tmp_path, organization=OrganizationStrategy.BY_DATE
    )

    expected_path = tmp_path / "2024" / "03" / "20" / "test.jpg"
    assert result.destination == expected_path
    assert expected_path.exists()


def test_transfer_with_duplicate_handling(
    transfer_manager, mock_device, mock_filesystem, tmp_path
):
    source_file = FileInfo(
        name="test.jpg",
        path="/DCIM/test.jpg",
        type=FileType.IMAGE,
        size=1024,
        modified_date=datetime.now(),
        id=1,
    )

    # Create existing file
    dest_dir = tmp_path / "photos"
    dest_dir.mkdir()
    (dest_dir / "test.jpg").write_bytes(b"existing content")

    # Mock new file content
    mock_device._mtp_device.get_file_content.return_value = b"new content"

    # Test rename strategy
    result = transfer_manager.transfer_file(
        source_file, dest_dir, duplicate_strategy="rename"
    )

    assert "test_1.jpg" in result.destination.name
    assert (dest_dir / "test.jpg").exists()  # Original remains
    assert result.destination.exists()  # New file created with different name


def test_transfer_error_handling(
    transfer_manager, mock_device, mock_filesystem, tmp_path
):
    source_file = FileInfo(
        name="test.jpg", path="/DCIM/test.jpg", type=FileType.IMAGE, size=1024, id=1
    )

    # Simulate MTP error
    mock_device._mtp_device.get_file_content.side_effect = Exception("MTP Error")

    result = transfer_manager.transfer_file(source_file, tmp_path, verify=True)
    assert not result.success
    assert "MTP Error" in result.error


def test_batch_transfer(transfer_manager, mock_device, mock_filesystem, tmp_path):
    files = [
        FileInfo(
            name=f"test{i}.jpg",
            path=f"/DCIM/test{i}.jpg",
            type=FileType.IMAGE,
            size=1024,
            id=i,
        )
        for i in range(3)
    ]

    # Mock file content
    mock_device._mtp_device.get_file_content.return_value = b"test content"

    # Perform batch transfer
    results = transfer_manager.batch_transfer(files, tmp_path)

    assert len(results) == 3
    assert all(r.success for r in results)
    assert len(list(tmp_path.glob("*.jpg"))) == 3


def test_transfer_progress_callback(
    transfer_manager, mock_device, mock_filesystem, tmp_path
):
    source_file = FileInfo(
        name="test.jpg", path="/DCIM/test.jpg", type=FileType.IMAGE, size=1024, id=1
    )

    progress_updates = []

    def progress_callback(progress: TransferProgress):
        progress_updates.append(progress)

    # Mock large file content
    mock_device._mtp_device.get_file_content.return_value = b"x" * 1024

    # Perform transfer with progress tracking
    transfer_manager.transfer_file(
        source_file, tmp_path, progress_callback=progress_callback
    )

    assert len(progress_updates) > 0
    assert progress_updates[-1].percentage == 100
    assert progress_updates[-1].bytes_transferred == 1024


def test_organize_by_type(transfer_manager):
    """Test organizing files by type"""
    # Test different file types
    file_types = [
        (FileType.IMAGE, "test.jpg", "Images"),
        (FileType.VIDEO, "test.mp4", "Videos"),
        (FileType.AUDIO, "test.mp3", "Audio"),
        (FileType.DOCUMENT, "test.pdf", "Documents"),
        (FileType.OTHER, "test.xyz", "Other"),
    ]

    for file_type, filename, expected_dir in file_types:
        file_info = FileInfo(filename, f"/DCIM/{filename}", file_type, 1024)
        dest_path = transfer_manager._get_organized_path(
            file_info, Path("/dest"), OrganizationStrategy.BY_TYPE
        )
        assert str(dest_path) == f"/dest/{expected_dir}"
