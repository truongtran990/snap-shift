from unittest.mock import Mock, patch

import pytest

from amtt.core.device import Device, DeviceConnectionError, DeviceManager, StorageInfo


@pytest.fixture
def mock_mtp():
    with patch("amtt.core.device.pymtp.MTP") as mock_mtp:
        yield mock_mtp


@pytest.fixture
def device_manager():
    return DeviceManager()


def test_device_connection_success(mock_mtp, device_manager):
    # Mock device detection
    mock_device = Mock()
    mock_device.get_devicename.return_value = "Test Android Device"
    mock_device.get_serialnumber.return_value = "123456789"
    mock_device.get_storage.return_value = [(1, "Internal Storage", 1000000)]
    mock_mtp.return_value.detect_devices.return_value = [mock_device]

    # Test connection
    devices = device_manager.get_connected_devices()
    assert len(devices) == 1
    device = devices[0]

    assert isinstance(device, Device)
    assert device.name == "Test Android Device"
    assert device.serial == "123456789"
    assert device.storage_info[0].id == 1
    assert device.storage_info[0].name == "Internal Storage"
    assert device.storage_info[0].capacity == 1000000


def test_device_connection_no_devices(mock_mtp, device_manager):
    mock_mtp.return_value.detect_devices.return_value = []

    with pytest.raises(DeviceConnectionError) as exc_info:
        device_manager.get_connected_devices()
    assert "No Android devices found" in str(exc_info.value)


def test_device_connection_error(mock_mtp, device_manager):
    mock_mtp.return_value.detect_devices.side_effect = Exception("MTP Error")

    with pytest.raises(DeviceConnectionError) as exc_info:
        device_manager.get_connected_devices()
    assert "Failed to connect to device" in str(exc_info.value)


def test_device_storage_info(mock_mtp, device_manager):
    mock_device = Mock()
    mock_device.get_storage.return_value = [
        (1, "Internal Storage", 1000000),
        (2, "SD Card", 2000000),
    ]
    mock_mtp.return_value.detect_devices.return_value = [mock_device]

    devices = device_manager.get_connected_devices()
    device = devices[0]

    assert len(device.storage_info) == 2
    assert device.storage_info[0].id == 1
    assert device.storage_info[0].name == "Internal Storage"
    assert device.storage_info[1].id == 2
    assert device.storage_info[1].name == "SD Card"


def test_device_validation():
    # Test missing name
    with pytest.raises(ValueError) as exc_info:
        Device(
            name="",
            serial="123",
            storage_info=[StorageInfo(id=1, name="Storage", capacity=1000)],
            _mtp_device=Mock(),
        )
    assert "must have both name and serial number" in str(exc_info.value)

    # Test missing serial
    with pytest.raises(ValueError) as exc_info:
        Device(
            name="Test Device",
            serial="",
            storage_info=[StorageInfo(id=1, name="Storage", capacity=1000)],
            _mtp_device=Mock(),
        )
    assert "must have both name and serial number" in str(exc_info.value)

    # Test no storage
    with pytest.raises(ValueError) as exc_info:
        Device(name="Test Device", serial="123", storage_info=[], _mtp_device=Mock())
    assert "must have at least one storage unit" in str(exc_info.value)


def test_device_manager_disconnect(mock_mtp):
    device_manager = DeviceManager()
    device_manager._mtp = mock_mtp
    device_manager._connected_devices = [Mock()]

    device_manager.disconnect_all()

    assert mock_mtp.disconnect.called
    assert not device_manager._connected_devices
    assert device_manager._mtp is None
