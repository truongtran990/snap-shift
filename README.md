# Android Media Transfer Tool (AMTT)

## Project Overview

AMTT is a Python-based command-line application designed to efficiently transfer media files (images, videos, and audio recordings) from Android devices to Linux systems via USB connection. The application provides options to selectively move files, verify transfer integrity, and organize content, allowing users to free up storage space on their mobile devices.

This README serves as a comprehensive specification for developing the AMTT application according to the requirements below.

## Target Users & Use Cases

- General computer users with basic command-line knowledge
- Users who have accumulated substantial media on Android devices
- Primary use case: Efficient backup and organization of media files to free up phone storage

## Technical Requirements

- **Python version**: 3.10
- **Connection protocol**: Media Transfer Protocol (MTP) exclusively via USB connection
- **Supported file types**:
  - Images: JPG, JPEG, PNG, GIF, HEIC, WEBP
  - Videos: MP4, MOV, 3GP, MKV, WEBM
  - Audio: MP3, WAV, AAC, OGG, FLAC
  - Documents (optional): PDF, DOCX, TXT
- **Device compatibility**: Android 8.0 (Oreo) and higher
- **Verification**: SHA-256 hash verification of transferred files

## Functional Requirements

### Device Connection Management
- Automatic detection of connected Android devices
- Handling of multiple connected devices
- Display of device information (model, storage capacity, available space)

### File System Navigation
- Browse Android device directory structure
- List files with essential metadata (size, date, type)
- Support for custom path entry and navigation shortcuts

### File Selection
- Select individual files
- Select directories recursively
- Selection by file patterns and wildcards

### Transfer Operations
- Copy files (leaving originals intact)
- Move files (delete originals after successful transfer)
- Resume interrupted transfers when possible
- Pause and cancel ongoing transfers

### Organization Options
- Organize by date (YYYY/MM/DD folder structure)
- Organize by media type (Images/Videos/Audio)
- Preserve original folder structure
- Custom organization using templates

### Batch Processing
- Queue multiple transfer operations
- Define default behaviors for recurring operations

### Filtering Capabilities
- Filter by date range (creation or modification date)
- Filter by file type/extension
- Filter by file size (minimum/maximum)
- Filter by filename pattern

### Duplicate Handling
- Detection methods: filename, content hash, or both
- Options: skip, rename, overwrite, prompt user

### Progress Tracking
- Real-time transfer speed display
- Estimated time remaining
- File count and size progress
- Transfer history logging

### Error Handling
- Recovery mechanisms for disconnected devices
- Retry options for failed transfers
- Detailed error logging

## User Interface

The application must implement a command-line interface (CLI) with text-based progress indicators, following this command structure:

```
amtt [global_options] command [command_options]

Commands:
  connect     - Connect to device
  list        - List files/folders on device
  select      - Select files for transfer
  transfer    - Initiate transfer operation
  configure   - Update configuration
  help        - Display help information
```

### User Workflow
1. Connect Android device via USB
2. Launch application with `amtt connect`
3. Browse device with `amtt list [path]`
4. Select files with `amtt select [patterns]`
5. Set destination with `amtt destination [path]`
6. Execute transfer with `amtt transfer [--move]`
7. Review results and confirm deletion (if applicable)

## Architecture & Implementation

### Component Breakdown
1. **Device Connection Module**
   - MTP protocol handlers
   - Device detection and authorization
   - Storage enumeration

2. **File System Interface**
   - Directory traversal
   - File metadata collection
   - Permission handling

3. **Transfer Engine**
   - Queue management
   - Chunked file transfer
   - Verification services
   - Error recovery

4. **Organization Manager**
   - Path resolution
   - Directory creation
   - Metadata extraction
   - Template parsing

5. **CLI Interface**
   - Command parser
   - Display formatting
   - User input handling
   - Progress visualization

### File Transfer Process Flow
1. Enumerate selected files and calculate total size
2. Create destination directory structure
3. For each file:
   - Create transfer buffer and read source file
   - Write to destination file
   - Calculate checksum of destination file
   - Verify against source
   - If move operation and verification successful, delete source
4. Generate transfer report

## Dependencies & Libraries

### Core Dependencies
- pymtp: Python bindings for libMTP
- tqdm: Progress bar functionality
- click: Command-line interface framework
- pyusb: USB communication
- hashlib: File hashing and verification

### Optional Dependencies
- pillow: Image metadata extraction and thumbnail generation
- pydantic: Configuration and data validation
- colorama: Terminal color support
- ffmpeg-python: Video metadata extraction

## Configuration

### User Configuration Options
- Default destination directory
- Organization templates
- Transfer behavior preferences
- Verification strictness
- Duplicate handling policy

### Configuration Storage
- Config file in `~/.config/amtt/config.yaml`
- Command-line overrides
- Per-device settings profiles

## Installation & Requirements

### System Requirements
- Linux with libmtp and development headers
- Python 3.10+
- USB debugging enabled on Android device
- Sufficient storage space on destination system

### Installation Method
```bash
# Via pip
pip install android-media-transfer-tool

# Required system dependencies (Ubuntu/Debian)
sudo apt install libmtp-dev python3-dev

# Post-installation setup
amtt setup
```

## Usage Guide

### Basic Commands

1. **Connect to Device**
   ```bash
   # List available devices
   amtt connect
   ```

2. **List Files**
   ```bash
   # List files in a directory
   amtt list /DCIM/Camera
   
   # List all files recursively
   amtt list /DCIM --recursive
   ```

3. **Transfer Files**
   ```bash
   # Transfer a single file
   amtt transfer /DCIM/photo.jpg /destination/path

   # Transfer with file verification
   amtt transfer /DCIM/photo.jpg /destination/path --verify

   # Transfer and delete source after successful transfer
   amtt transfer /DCIM/photo.jpg /destination/path --delete-source
   ```

4. **Batch Transfer**
   ```bash
   # Transfer multiple files using pattern matching
   amtt transfer "/DCIM/*.jpg" /destination/path --batch

   # Transfer all media files from a directory
   amtt transfer /DCIM /destination/path --batch
   ```

### Organization Options

1. **Organize by Date**
   ```bash
   # Creates YYYY/MM/DD folder structure
   amtt transfer /DCIM/photo.jpg /destination --organize date
   ```

2. **Organize by Type**
   ```bash
   # Organizes into Images/Videos/Audio folders
   amtt transfer /DCIM/photo.jpg /destination --organize type
   ```

3. **Combined Organization**
   ```bash
   # Combines both date and type organization
   amtt transfer /DCIM/photo.jpg /destination --organize both
   ```

### Duplicate Handling

```bash
# Skip existing files
amtt transfer /DCIM/photo.jpg /destination --duplicate skip

# Rename duplicates
amtt transfer /DCIM/photo.jpg /destination --duplicate rename

# Overwrite existing files
amtt transfer /DCIM/photo.jpg /destination --duplicate overwrite
```

### Progress Tracking

```bash
# Show detailed progress
amtt transfer /DCIM/photo.jpg /destination --verbose
```

## Common Use Cases

1. **Backup Camera Photos**
   ```bash
   # Organize photos by date and verify transfer
   amtt transfer "/DCIM/Camera/*.jpg" ~/Pictures/Phone --batch --organize date --verify
   ```

2. **Move Videos to External Drive**
   ```bash
   # Transfer videos and remove from device
   amtt transfer "/DCIM/Camera/*.mp4" /media/external --batch --delete-source
   ```

3. **Quick Device Cleanup**
   ```bash
   # List large files
   amtt list /DCIM --sort size

   # Transfer and organize by type
   amtt transfer /DCIM /backup/path --batch --organize type
   ```

## Troubleshooting

1. **Device Not Detected**
   - Ensure USB debugging is enabled on your Android device
   - Try disconnecting and reconnecting the USB cable
   - Check if the device is mounted properly

2. **Transfer Errors**
   - Use the `--verify` flag to ensure file integrity
   - Check available space on destination
   - Ensure proper read/write permissions

3. **Performance Issues**
   - Avoid transferring too many files at once
   - Use a high-quality USB cable
   - Close other applications using the device

## Error Messages

Common error messages and their solutions:

- `No devices found`: Check USB connection and device authorization
- `Failed to connect to device`: Ensure USB debugging is enabled
- `Permission denied`: Check file system permissions
- `No files match pattern`: Verify the file pattern is correct
- `Transfer failed`: Check storage space and retry with `--verify`

## Best Practices

1. **Before Transfer**
   - Check available space on destination
   - Use `--verify` for important files
   - Review files with `list` command

2. **During Transfer**
   - Keep device connected and screen on
   - Avoid using device during transfer
   - Monitor progress with `--verbose`

3. **After Transfer**
   - Verify transferred files
   - Check transfer logs
   - Safely disconnect device

## Documentation

The application should include:
- User documentation (installation, quick start, commands, troubleshooting)
- Developer documentation (architecture overview, API docs)

## Limitations & Constraints

- No support for wireless transfers
- No automatic photo/video editing
- No real-time synchronization
- Possible limitations with certain Android OEM implementations
- Requires USB debugging enabled on some devices

## Project Structure

The application should follow a modular structure:

```
amtt/
├── __init__.py
├── cli/
│   ├── __init__.py
│   ├── commands.py
│   └── display.py
├── core/
│   ├── __init__.py
│   ├── device.py
│   ├── transfer.py
│   └── verification.py
├── utils/
│   ├── __init__.py
│   ├── filesystem.py
│   └── organization.py
├── config/
│   ├── __init__.py
│   └── settings.py
└── main.py
```

## Development Instructions

This README serves as a comprehensive specification for developing the AMTT application. The implementation should strictly follow these requirements, focusing first on core functionality (device connection, file listing, basic transfers) before moving to more advanced features.

---

**Note to Developers**: Please follow this specification strictly when implementing the Android Media Transfer Tool application. The primary goal is to create a reliable, efficient command-line utility that allows users to transfer and organize media files from Android devices to Linux systems via USB/MTP connection. 