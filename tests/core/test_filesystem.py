from datetime import datetime
from unittest.mock import Mock

import pytest

from amtt.core.filesystem import FileSystem, FileSystemError, FileType


@pytest.fixture
def mock_device():
    device = Mock()
    device._mtp_device = Mock()
    return device


@pytest.fixture
def filesystem(mock_device):
    return FileSystem(mock_device)


def test_list_files_success(filesystem, mock_device):
    mock_device._mtp_device.get_files_and_folders.return_value = [
        {
            "filename": "photo.jpg",
            "filesize": 1024,
            "modificationdate": "2024-03-20 10:00:00",
            "filetype": "image/jpeg",
            "id": 1,
        },
        {"filename": "videos", "filetype": "folder", "id": 2},
    ]

    files = filesystem.list_files("/DCIM/Camera")

    assert len(files) == 2

    # Check file properties
    photo = next(f for f in files if f.name == "photo.jpg")
    assert photo.type == FileType.IMAGE
    assert photo.size == 1024
    assert isinstance(photo.modified_date, datetime)
    assert photo.path == "/DCIM/Camera/photo.jpg"

    # Check folder properties
    folder = next(f for f in files if f.name == "videos")
    assert folder.type == FileType.FOLDER
    assert folder.path == "/DCIM/Camera/videos"


def test_list_files_empty_directory(filesystem, mock_device):
    mock_device._mtp_device.get_files_and_folders.return_value = []

    files = filesystem.list_files("/empty/dir")
    assert len(files) == 0


def test_list_files_error(filesystem, mock_device):
    mock_device._mtp_device.get_files_and_folders.side_effect = Exception("MTP Error")

    with pytest.raises(FileSystemError) as exc_info:
        filesystem.list_files("/some/path")
    assert "Failed to list files" in str(exc_info.value)


def test_file_type_detection(filesystem, mock_device):
    mock_device._mtp_device.get_files_and_folders.return_value = [
        {"filename": "test.jpg", "filetype": "image/jpeg", "id": 1},
        {"filename": "test.mp4", "filetype": "video/mp4", "id": 2},
        {"filename": "test.mp3", "filetype": "audio/mpeg", "id": 3},
        {"filename": "test.txt", "filetype": "text/plain", "id": 4},
        {"filename": "test.unknown", "filetype": "application/octet-stream", "id": 5},
    ]

    files = filesystem.list_files("/test")
    file_types = {f.name: f.type for f in files}

    assert file_types["test.jpg"] == FileType.IMAGE
    assert file_types["test.mp4"] == FileType.VIDEO
    assert file_types["test.mp3"] == FileType.AUDIO
    assert file_types["test.txt"] == FileType.DOCUMENT
    assert file_types["test.unknown"] == FileType.OTHER


def test_get_file_info(filesystem, mock_device):
    mock_device._mtp_device.get_file_info.return_value = {
        "filename": "photo.jpg",
        "filesize": 1024,
        "modificationdate": "2024-03-20 10:00:00",
        "filetype": "image/jpeg",
        "id": 1,
    }

    file_info = filesystem.get_file_info("/DCIM/Camera/photo.jpg")

    assert file_info.name == "photo.jpg"
    assert file_info.size == 1024
    assert file_info.type == FileType.IMAGE
    assert file_info.path == "/DCIM/Camera/photo.jpg"
    assert isinstance(file_info.modified_date, datetime)


def test_get_file_info_not_found(filesystem, mock_device):
    mock_device._mtp_device.get_file_info.side_effect = Exception("File not found")

    with pytest.raises(FileSystemError) as exc_info:
        filesystem.get_file_info("/nonexistent/file.jpg")
    assert "File not found" in str(exc_info.value)


def test_create_directory_success(filesystem, mock_device):
    filesystem.create_directory("/new/dir")
    mock_device._mtp_device.create_folder.assert_called_with("/new/dir")


def test_create_directory_error(filesystem, mock_device):
    mock_device._mtp_device.create_folder.side_effect = Exception("Failed to create")

    with pytest.raises(FileSystemError) as exc_info:
        filesystem.create_directory("/new/dir")
    assert "Failed to create directory" in str(exc_info.value)


def test_delete_file_success(filesystem, mock_device):
    filesystem.delete_file("/test/file.jpg")
    mock_device._mtp_device.delete_object.assert_called_with("/test/file.jpg")


def test_delete_file_error(filesystem, mock_device):
    mock_device._mtp_device.delete_object.side_effect = Exception("Failed to delete")

    with pytest.raises(FileSystemError) as exc_info:
        filesystem.delete_file("/test/file.jpg")
    assert "Failed to delete" in str(exc_info.value)


def test_file_type_detection_edge_cases(filesystem, mock_device):
    # Test unknown MIME type
    mock_device._mtp_device.get_files_and_folders.return_value = [
        {"filename": "test.xyz", "filetype": "application/x-unknown", "id": 1}
    ]

    files = filesystem.list_files("/test")
    assert files[0].type == FileType.OTHER

    # Test document MIME types
    doc_types = [
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ]

    for mime_type in doc_types:
        mock_device._mtp_device.get_files_and_folders.return_value = [
            {"filename": "test.doc", "filetype": mime_type, "id": 1}
        ]
        files = filesystem.list_files("/test")
        assert files[0].type == FileType.DOCUMENT


def test_parse_file_info_invalid_date(filesystem, mock_device):
    mock_device._mtp_device.get_files_and_folders.return_value = [
        {
            "filename": "test.jpg",
            "filetype": "image/jpeg",
            "filesize": 1024,
            "modificationdate": "invalid-date",
            "id": 1,
        }
    ]

    files = filesystem.list_files("/test")
    assert files[0].modified_date is None
