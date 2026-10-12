# Crypton — Remote File Storage Server

The Crypton server is the storage backend for the Crypton self-hosted file storage ecosystem. It provides authenticated, encrypted network communication, a sandboxed shared directory, a JSON-based filesystem command protocol, chunked file transfers, and transactional uploads for the Linux VFS client.

Crypton supports Windows and Linux clients regardless of the server's operating system. Clients can access remote files through native filesystem integrations or use the Python storage API directly.

The server uses Crypton's custom networking and authentication module rather than SSH or conventional file-transfer protocols.

## Core Features

- **Sandboxed Storage:** Remote filesystem operations are confined to the configured shared directory using canonical path resolution and containment checks.
- **Cross-Platform Operation:** The server supports Windows and Linux, with clients communicating through Crypton's custom networking layer.
- **Chunked File Transfers:** Standard downloads and uploads use a default chunk size of 12 MiB, allowing files to be transferred incrementally.
- **Transactional VFS Uploads:** The Linux VFS protocol supports temporary upload files, chunk-range tracking, file-size and BLAKE3 hash verification, conflict detection, and atomic replacement.
- **Concurrent-Modification Detection:** VFS uploads can use expected-version tokens to prevent overwriting a file that changed during the operation.
- **Filesystem Metadata:** Provides file information, timestamps, directory listings, POSIX-style metadata, and filesystem capacity information.
- **File Management:** Supports listing, creating directories, moving, copying, deleting, truncating, downloading, and uploading files.
- **Encrypted Network Transport:** Application payloads are protected by the Crypton networking layer.
- **Protected Authentication Keys:** Server-side authentication key material is encrypted at rest using a password-derived key.

## Requirements

Install the Python dependencies required by the project:

- `pyzmq` — ZeroMQ-based network communication.
- `cryptography` — Cryptographic primitives used by the encryption module.
- `argon2-cffi` — Required if the encryption module uses Argon2 for key derivation.
- `zxcvbn` — Password strength estimation.
- `blake3` — File hashing and transactional upload integrity verification.

The server also requires the project's local `network.py`, `Encryption.py`, and `util.py` modules, along with their dependencies.

Install the dependencies for the actual versions of these modules before starting the server.

## Setup and Installation

### 1. Shared Directory

The server uses the following default shared directory:

```python
SHARED_DIR = os.path.expanduser("~/Shared")
```

The directory is created automatically if it does not exist.

On Linux, this normally resolves to:

```text
/home/your-user/Shared
```

On Windows, it resolves relative to the account's home directory.

**Changing the storage location:** Edit `SHARED_DIR` in `server.py` before starting the server. The current `FileServer` constructor does not accept a shared-directory parameter.

Files stored in this directory are the actual server-side files. The server does not automatically encrypt their contents at rest; use appropriate filesystem permissions, full-disk encryption, or another storage-encryption mechanism if that protection is required.

### 2. Running the Server

Run the server directly:

```bash
python server.py
```

The command-line entry point attempts to discover a local interface address by opening a UDP socket toward an external address. If discovery fails, it falls back to `127.0.0.1`.

The program prompts for the server's key-storage password and then optionally requests an administrator authentication-key password.

Example:

```text
Server password:
Auth key password:
[*] File Server active on tcp://192.0.2.10:9000 | Serving: /home/user/Shared
```

The displayed IP address and shared-directory path depend on the machine's configuration.

The server password is required. The administrator archive password is optional; if a sufficiently strong password is accepted, the networking module generates the administrator bootstrap archive used to enroll new clients.

The optional password prompt has a timeout. If no password is entered, the administrator archive is not provisioned for that startup.

**Network access:** The selected address must be reachable by the intended clients. Check the host firewall and network configuration if connections fail. Binding to `127.0.0.1` makes the service accessible only through the local machine.

### 3. Programmatic Setup

The server can also be embedded in another Python application:

```python
import time
from server import FileServer

server = FileServer(
    host="127.0.0.1",
    port=9000,
    password="Use-A-Strong-Unique-Server-Password!",
    auth_key_password="Use-A-Separate-Strong-Admin-Password!",
    key_dir="./keys",
    salt_file="./server_salt.bin",
)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Shutting down Crypton server...")
finally:
    server.server.close()
```

The example binds to the loopback interface. Use an appropriate interface address when serving other machines.

The `FileServer` instance wraps the networking server, which runs its own background I/O thread. Shutdown is performed through `server.server.close()` in the current implementation.

### Constructor Reference

The constructor is:

`FileServer(host="127.0.0.1", port=9000, password=None, auth_key_password=None, key_dir="./keys", salt_file="./server_salt.bin")`

| Parameter | Description |
|---|---|
| `host` | Network interface address to bind to. |
| `port` | TCP port; defaults to 9000. |
| `password` | Required password used to derive the server's at-rest authentication-key encryption key. |
| `auth_key_password` | Optional administrator bootstrap archive password. |
| `key_dir` | Directory containing server authentication key material. |
| `salt_file` | Path to the salt file used for deriving the server's at-rest encryption key. |

The shared directory is configured separately through `SHARED_DIR` in the source code.

The salt file must be preserved alongside the protected authentication material. Losing or replacing it can prevent the original at-rest key from being derived.

## Protocol Structure

Crypton's storage client encodes application requests using a custom binary packet format before passing them to the encrypted networking layer.

The packet structure is:

1. **Header Length — 4 bytes:** A big-endian integer specifying the length of the JSON metadata.
2. **Metadata — variable length:** A UTF-8 encoded JSON object containing the command and its arguments.
3. **Payload — variable length:** Optional binary data, primarily used for file transfers.

The metadata generally includes fields such as `cmd` and `path`, with additional fields for offsets, lengths, destination paths, and upload identifiers.

The packet is transmitted as an application payload over Crypton's encrypted network connection. The networking layer uses ZeroMQ for transport and routing.

### Request and Response Behavior

Most filesystem commands return JSON metadata encoded in the packet format.

The `download_chunk` and `get_hash` commands instead return binary responses with a leading status byte:

- `0x00` indicates success, followed by the returned data.
- `0x01` indicates failure, followed by an error message.

The client must interpret these response formats appropriately.

## Supported Commands

### Standard Filesystem Commands

| Command | Purpose |
|---|---|
| `list` | Lists directory entries, including names, sizes, and directory indicators. |
| `info` | Returns path information, file size, chunk size, and total download chunks. |
| `download_chunk` | Reads file data from a requested byte offset. |
| `upload_chunk` | Writes a binary payload at a specified file offset. |
| `get_hash` | Computes and returns a BLAKE3 digest for a file or requested byte range. |
| `truncate` | Changes the length of an existing regular file. |
| `mkdir` | Creates a directory, including missing parent directories. |
| `move` | Moves a file or directory. |
| `copy` | Copies a file or directory. |
| `delete` | Deletes a file or recursively removes a directory tree. |

Standard uploads write directly to the destination file at the requested offset. They are not transactional: a failed or interrupted transfer can leave a partially updated file.

The standard `move`, `copy`, and `delete` operations have different semantics from their VFS counterparts, particularly for directory replacement and deletion.

### VFS Filesystem Commands

The VFS protocol provides additional filesystem operations for the Linux FUSE backend.

| Command | Purpose |
|---|---|
| `vfs_list` | Lists supported filesystem entries while filtering common temporary-file names. |
| `vfs_stat` | Returns file or directory information, timestamps, size, version token, and related metadata. |
| `vfs_posix_metadata` | Returns POSIX-style metadata fields. |
| `vfs_statfs` | Returns filesystem capacity and related statistics. |
| `vfs_mkdir` | Creates a directory and reports an error if the path already exists. |
| `vfs_delete` | Deletes a file or an empty directory, checking the expected path type when supplied. |
| `vfs_move` | Moves or replaces a path subject to source/destination type and directory constraints. |
| `vfs_begin_upload` | Creates a temporary file and begins a transactional upload session. |
| `vfs_upload_chunk` | Writes a chunk into an upload session at a specified offset. |
| `vfs_commit_upload` | Verifies and commits the completed upload. |
| `vfs_abort_upload` | Cancels an upload session and removes its temporary file. |

VFS operations return structured error responses, including error codes for conditions such as missing paths, existing paths, and version conflicts.

## Chunked Transfers

The server defines these constants:

```python
CHUNK_SIZE = 12 * 1024 * 1024
IO_CHUNK_SIZE = 16 * 1024 * 1024
VFS_MAX_UPLOAD_CHUNK = 64 * 1024 * 1024
```

- `CHUNK_SIZE` — Default chunk size for the standard transfer protocol.
- `IO_CHUNK_SIZE` — Maximum block size used by the standard hash operation when reading file data.
- `VFS_MAX_UPLOAD_CHUNK` — Maximum accepted payload size for a single VFS upload-chunk request.

The VFS upload protocol permits chunks up to 64 MiB, independently of the standard 12 MiB client chunk size.

Chunked transfers avoid requiring clients to request an entire large file in one operation. However, chunk sizes alone do not guarantee a strict memory limit: actual resource usage depends on payload size, concurrency, buffering, and application behavior.

## Transactional VFS Uploads

The VFS upload implementation is designed to avoid exposing incomplete uploads as the final destination file.

### Upload Process

1. **Begin upload:** The client specifies the destination path, expected file size, and target BLAKE3 digest.
2. **Create temporary file:** The server creates a temporary file in the destination directory and sizes it to the declared file length.
3. **Upload chunks:** The client sends data with offsets. The server verifies the upload identifier, client ownership, offset, and chunk-size limit.
4. **Track ranges:** Successfully received byte ranges are recorded so the server can verify that the declared file contents have been completely uploaded.
5. **Verify content:** The server verifies the final file size and, when a target hash was provided, compares the computed BLAKE3 digest with the expected digest.
6. **Check for conflicts:** The destination's version token is checked again before replacement.
7. **Commit:** If verification succeeds and the destination has not changed, the temporary file replaces the destination using `os.replace()`.
8. **Clean up:** The server removes the completed upload session and its temporary file reference.

The temporary file is created in the destination directory so the final replacement can generally be performed on the same filesystem.

### Version Tokens and Conflict Detection

The server constructs version tokens using attributes such as:

- Whether the path is a directory.
- File size.
- Creation time.
- Modification time.

The client can submit an `expected_version` when beginning an upload. If the destination no longer matches the expected version, the server returns a conflict instead of proceeding.

Even without an explicitly supplied expected version, the transactional upload captures the destination's starting version and checks it again at commit time. This helps prevent an upload from silently replacing a file that changed while the transfer was in progress.

Version tokens are based on filesystem metadata rather than a guaranteed content-unique identifier, so they should not be treated as a cryptographic proof that the destination contents have remained identical.

### Session Lifetime and Cleanup

Incomplete upload sessions are removed after approximately one hour without activity when the server performs its VFS upload-expiration checks.

Temporary uploads are held in the server's in-memory session table. They are not a persistent, restart-resumable upload database; restarting the server loses the session metadata, even if a temporary file remains on disk.

The VFS directory-listing command filters common temporary-file names, including the server's upload temporary files.

## Sandboxed Filesystem Access

The server uses `safe_path()` to resolve requested paths relative to the shared directory.

The function:

1. Resolves the shared directory to its canonical path.
2. Resolves the requested target.
3. Compares the resolved paths using `os.path.commonpath()`.
4. Rejects the target when its resolved path falls outside the shared directory.

This helps prevent directory traversal through paths such as `../secret.txt` and paths that resolve outside the shared directory.

**Important:** Path checks are not a substitute for OS-level isolation. Filesystem links, concurrent path changes, platform-specific path semantics, and race conditions must also be considered when evaluating the server's security. Use appropriate filesystem permissions and avoid exposing the service to untrusted networks without a thorough security review.

### File and Directory Behavior

The standard and VFS protocols have intentionally different filesystem semantics.

- Standard `mkdir` creates parent directories as needed.
- VFS `vfs_mkdir` requires the requested directory not to exist.
- Standard `delete` recursively removes directories.
- VFS `vfs_delete` removes only empty directories.
- Standard `move` and `copy` can create missing destination parents.
- VFS `vfs_move` requires the destination parent to exist and uses replacement semantics with source/destination type checks.
- Standard `upload_chunk` writes directly into the destination file.
- VFS uploads stage the new contents in a temporary file and commit after verification.

Applications using VFS operations should handle filesystem errors rather than assuming all operations succeed.

## Security and Architecture Notes

### Network Encryption

Crypton's networking module authenticates clients and protects application payloads during transmission using authenticated encryption.

The storage server receives decrypted application payloads before processing filesystem commands. Consequently, the server is part of the trust boundary: an administrator or process with sufficient server privileges can access the stored file contents.

### Encryption at Rest

The networking module protects authentication key material stored in its key directory using password-derived encryption keys.

This protection does **not** automatically encrypt files stored in `SHARED_DIR`. Uploaded documents and other shared files are written as ordinary filesystem content. To protect server-side data at rest, use OS-level access controls, full-disk encryption, or another suitable storage-encryption layer.

### File Integrity

Crypton's network layer authenticates encrypted messages in transit. This protects message confidentiality and detects unauthorized modifications to authenticated ciphertext.

For VFS transactional uploads, the server additionally calculates a BLAKE3 digest and compares it with the expected digest supplied by the client. This helps detect incomplete or corrupted uploaded content, assuming the client supplies the correct expected hash.

BLAKE3 is a cryptographic hash function, not a digital signature. Hash verification does not independently establish who created a file or whether its contents are trustworthy.

### Resource Management

The server uses locks to coordinate VFS mutations and upload-session operations. Incomplete uploads can occupy disk space until they are aborted or expire.

The networking module also maintains its own queue accounting. Its configured queue limit does not represent a strict process-wide RAM limit.

For deployments handling large files or multiple concurrent clients:

- Monitor available disk space.
- Account for temporary upload files.
- Restrict inbound network access.
- Handle operation timeouts and error responses.
- Test behavior under interrupted transfers and concurrent modifications.
- Review message-size and resource-exhaustion risks.

### Administrator Bootstrap Credentials

The networking layer generates an administrator bootstrap archive when a sufficiently strong administrator password is accepted.

Treat the archive and its password as sensitive credentials. Distribute enrollment archives through a trusted channel and protect the key directory with restrictive filesystem permissions.

Client enrollment and access revocation are handled by the networking/authentication layer, not by the shared-directory filesystem API.

Under the current authentication behavior, deleting a client's authorization key material takes effect for that client when it restarts; it should not be treated as immediate termination of an established session.

## Troubleshooting

### The Server Does Not Start

- Verify that the required Python modules and dependencies are installed.
- Ensure the server password is supplied.
- Check that the configured port is available.
- Verify that the salt file and authentication-key directory can be created or accessed.

### Clients Cannot Connect

- Check the displayed server IP address and port.
- Ensure the client is using an address reachable from its network.
- Review host firewall rules and any intervening network restrictions.
- Verify the client credentials and bootstrap enrollment state.

### Uploads Fail or Report Conflicts

- Confirm the destination directory exists for VFS uploads.
- Check available disk space for the temporary upload file.
- Check whether the destination was modified during the transfer.
- Verify the expected hash, declared size, and chunk offsets.
- Retry only after handling any previous failed or conflicting upload.

### Files Appear to Be Missing

- Confirm that the client and server are using the expected shared directory.
- Check whether a file has been placed in a temporary upload state.
- Review server-side logs and filesystem permissions.
- Verify that the requested path resolves within the shared directory.

## License

Crypton is released under the **GNU General Public License v3.0 (GPL-3.0)**.

See the `LICENSE` file in the repository for the full license text and information about your rights and obligations when using or modifying this software.
