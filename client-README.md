# Crypton — Cross-Platform Storage Client

The Crypton client is the client-side component of the Crypton self-hosted, end-to-end encrypted remote storage ecosystem. From the user's perspective, it provides a OneDrive-like experience while allowing remote files to be accessed through a native local drive on Windows or Linux.

Crypton supports Windows Cloud Files API (cfAPI) integration for transparent file hydration and FUSE-based filesystem mounting on Linux. It includes a Python API for direct remote storage operations, chunked file transfers, caching, and event callbacks. File data is encrypted and decrypted in memory as part of the Crypton security architecture.

## Core Features

- **Native Drive Integration:** Access remote files through your operating system's file manager. Open, create, edit, move, and delete files using familiar filesystem workflows.
- **Cross-Platform Support:** Supports Windows and Linux clients, independently of the server's operating system.
- **Windows Cloud Files API:** Uses the `winfuse3` mount backend to integrate remote files with Windows through cfAPI, including on-demand file hydration.
- **Linux FUSE Mounting:** Uses the `vfs` mount backend to expose remote storage through a Linux filesystem interface, with chunked caching.
- **Chunked File Transfers:** Transfers file data in chunks of up to 12 MiB, allowing large files to be processed without loading the entire file into memory at once.
- **Upload Integrity and Conflict Detection:** The Linux VFS upload path supports transactional uploads, BLAKE3 hash verification, size verification, and optional expected-version checks to detect conflicting modifications.
- **Asynchronous Upload Support:** The mount integration supports upload workflows designed to keep file operations responsive while data is transferred.
- **Python Storage API:** Provides direct access to remote files and directories without requiring a mounted drive.
- **Remote File Reader:** The `RemoteReader` class provides a file-like interface with `read()`, `seek()`, and `tell()` operations.
- **Event Callbacks:** Use `storage.on(...)` to observe read, write, delete, and directory-creation operations.
- **Memory-Based Encryption:** File data is handled through the project's encryption architecture, with encryption and decryption performed in memory.

## Requirements

### Windows

- Python and the dependencies required by Crypton.
- The `winfuse3` module.
- The underlying Windows filesystem driver and dependencies required by the mount backend, including WinFsp where applicable.
- The Crypton client modules, including `network.py` and the required encryption modules.

### Linux

- Python and the dependencies required by Crypton.
- The `vfs` module.
- The system-level FUSE libraries and packages required by the mount backend.
- The Crypton client modules, including `network.py` and the required encryption modules.
- The `blake3` Python package for the Linux client's file hashing functionality.

Install and configure the platform-specific dependencies before running the client. Refer to the project's setup documentation for installation details.

## Usage

### 1. Mount the Remote Drive

Run `client.py` with the path to the client authentication key:

```bash
python client.py ./path/to/auth_key
```

The authentication key path is optional. If omitted, the client defaults to `./auth_key`.

During startup, the client may prompt for:

- **Host IP:** The IP address of the Crypton server.
- **Client Password:** The password used to authenticate the client.
- **Authentication Key Password:** The password needed to decrypt the protected authentication key.

If the optional TPM integration is configured, the client can attempt to retrieve the saved host address and client password.

The client creates a local `./mount` directory if it does not exist and starts the platform-appropriate mount backend.

Example startup output:

```text
Host IP [192.0.2.10]:
Client password:
Auth Key Password:
[*] Starting WinFUSE at ./mount...
```

The displayed mount message depends on the operating system. On Linux, the client starts the FUSE mount instead.

**Mount point:** The default is `./mount`, relative to the current working directory on both Windows and Linux. Ensure the location is appropriate for your operating system and configured mount backend.

Once mounted, use the drive as you would a normal local filesystem. File access and hydration behavior depend on the platform's mount integration.

### 2. Use the Python API

The `RemoteStorage` class provides direct access to remote storage without requiring a mounted drive.

```python
from client import RemoteStorage, auth_key_password_callback

# Initialize the storage connection.
# Omitting password prompts for the client password.
storage = RemoteStorage(
    host="192.0.2.10",
    port=9000,
    key_path="./auth_key",
    auth_key_password_callback=auth_key_password_callback,
)

# Upload a local file to remote storage.
storage.write_file_from_local(
    "./local_document.pdf",
    "/remote_document.pdf",
)

# Read a remote file into memory.
data = storage.read("/remote_document.pdf")

# Read a remote file through the file-like interface.
with storage.open_read("/remote_document.pdf") as remote_file:
    remote_file.seek(1024)  # Skip the first 1 KiB.
    chunk = remote_file.read(512)  # Read the next 512 bytes.

# List directory contents.
print("Files:", storage.listdir("/"))

# Check whether a remote path exists.
print(storage.exists("/remote_document.pdf"))

# Query the remote file size.
print(storage.get_size("/remote_document.pdf"))
```

The example uses a documentation-only IP address; replace it with your server's actual address.

The client password and the authentication-key password serve different purposes. The first authenticates the client to the server, while the second unlocks the protected authentication key when required.

### 3. File Operations

The storage API provides methods for common remote filesystem operations.

| Method | Purpose |
|---|---|
| `read(path)` | Read a remote file into memory. |
| `read_chunk(path, offset, length)` | Retrieve a portion of a remote file. |
| `write_chunk(path, offset, data)` | Write a chunk of file data. |
| `write_file_from_local(source, destination)` | Upload a local file in chunks. |
| `open_read(path)` | Open a file-like remote reader. |
| `listdir(path)` | List the contents of a directory. |
| `exists(path)` | Check whether a remote path exists. |
| `is_dir(path)` | Check whether a path is a directory. |
| `get_size(path)` | Retrieve a remote file's size. |
| `mkdir(path)` | Create a remote directory. |
| `delete(path)` | Delete a remote path. |
| `rename(source, destination)` | Rename or move a remote path. |
| `copy(source, destination)` | Copy a remote path. |
| `truncate(path, size)` | Change a remote file's length. |
| `get_hash(path)` | Retrieve the server-provided file hash. |
| `move(source, destination)` | Move a remote path, raising an error on failure. |

Some operations have platform-specific implementations. The Linux mount backend uses additional VFS-specific operations for filesystem metadata, directory access, and transactional file uploads.

### 4. RemoteReader

The `RemoteReader` class provides a file-like interface for reading remote data.

```python
with storage.open_read("/large_file.bin") as remote_file:
    print("File size:", remote_file.size)

    # Read the first 1 MiB.
    first_chunk = remote_file.read(1024 * 1024)

    # Seek to a specific position.
    remote_file.seek(4096)

    # Read from the new position.
    data = remote_file.read(1024)

    # Inspect the current read position.
    print("Position:", remote_file.tell())
```

The reader retrieves file contents in chunks rather than requiring a single request for the entire file. Its interface supports seeking from the beginning, current position, or end of the file.

### 5. Event Callbacks

Register callbacks to observe storage operations:

```python
storage.on(
    "read",
    lambda path: print(f"[READ] {path}"),
)

storage.on(
    "write",
    lambda path, data: print(
        f"[WRITE] {path} ({len(data)} bytes)"
    ),
)

storage.on(
    "delete",
    lambda path: print(f"[DELETE] {path}"),
)

storage.on(
    "mkdir",
    lambda path: print(f"[MKDIR] {path}"),
)
```

Supported event names are `read`, `write`, `delete`, and `mkdir`. A write callback receives the path and the chunk of data being written. Read callbacks receive the path.

Callbacks can be useful for logging, diagnostics, and application-level monitoring. They should not be treated as a substitute for server-side authorization or security auditing.

## Under the Hood

### Networking and Packet Framing

The client communicates with the server through Crypton's custom networking implementation. The packet helpers `make_packet()` and `parse_packet()` encode and decode messages using a four-byte length prefix for JSON metadata followed by any binary payload.

The client delegates network communication and cryptographic processing to the project's networking and encryption modules.

### Thread Safety

The storage implementation uses a `threading.Lock` to serialize access to the network client's send/receive operations. This helps prevent concurrent requests from interfering with one another when multiple filesystem operations occur close together.

### Chunked Transfers

The shared `CHUNK_SIZE` is 12 MiB. Chunked processing allows large files to be transferred incrementally.

For Linux VFS writes, the client supports a transactional upload process:

1. Calculate the local file's size and BLAKE3 hash.
2. Request an upload session from the server.
3. Upload file chunks with their respective offsets.
4. Commit the completed upload.
5. Verify the server-reported hash and file size.
6. Abort the upload when an unsuccessful operation leaves a transaction unfinished.

The optional expected-version parameter enables conditional uploads. If the server reports a version conflict, the client can reject the write instead of silently overwriting a concurrent change.

### Caching and Hydration

On Windows, the cfAPI integration allows remote files to be represented in the local filesystem and hydrated when their contents are accessed. Hydrated data can occupy local disk space.

On Linux, the FUSE integration provides filesystem access through the `vfs` backend, which supports chunked caching.

Caching is an implementation detail of the mount backends. Do not assume that deleting a file from the mounted directory merely clears its cached content; it can instead delete the remote file. Use the appropriate platform-specific cache-management procedure.

### Encryption and Data Handling

Crypton uses its encryption and networking components to protect communications and file data. Authentication keys are protected with password-based encryption at rest.

The exact confidentiality guarantees depend on the complete implementation, key handling, and runtime environment. Files that are hydrated or cached locally may exist as accessible local filesystem content while in use; end-to-end encryption does not by itself mean cached files remain encrypted on the client disk.

## Client Access Revocation

Client authorization is managed by the server. Deleting the authorization file associated with a client revokes its authorization for subsequent authentication.

**Important:** Under the current behavior, deleting the file takes effect when the affected client restarts. It should not be treated as immediate termination of an existing session.

## Optional TPM Autofill Integration

Crypton can optionally integrate with the separate Psudo-TPM project to retrieve saved connection information and the client password.

Repository:

https://github.com/Daniel523-dev/Psudo-TPM

This integration is not required for normal client operation. See the main project README and the Psudo-TPM documentation for setup instructions.

## Troubleshooting

**The client cannot connect to the server**

- Verify the server's IP address and listening port.
- Confirm that network access to the server is permitted.
- Check that the client password and authentication key are correct.
- Verify that the authentication key can be decrypted using its password.

**The mount fails to start**

- Confirm that the required Windows or Linux mount dependencies are installed.
- Verify that the mount directory is suitable for the platform-specific backend.
- Check the terminal output for mount errors and dependency issues.

**A remote file cannot be read or written**

- Confirm that the client has valid authorization.
- Check the server logs and network connection.
- On Linux, inspect any version-conflict or transactional upload errors before retrying a write.

**Local disk usage increases**

- Windows cfAPI hydration may store file content locally.
- Linux caching may also use local disk space.
- Use the supported cache-management process for the appropriate platform rather than deleting files blindly from the mounted directory.

## License

Crypton is released under the **GNU General Public License v3.0 (GPL-3.0)**.

See the `LICENSE` file in the repository for the full license text and information about your rights and obligations when using or modifying this software.
