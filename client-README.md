# Crypton Client

`client.py` is the user-facing client for the Crypton storage server. It supports a native mount on Windows and Linux, plus a Python API for direct remote file operations.

> **Data handling:** Network messages are encrypted in transit, but the server writes ordinary plaintext files in its shared directory. Windows-hydrated and Linux-cached files may also exist as local plaintext.

## Requirements

The client requires the common Crypton Python dependencies and the compiled `backend` extension. See [`SETUP.md`](SETUP.md) and [`backend-README.md`](backend-README.md).

The mount implementation depends on the platform:

- **Windows:** `winfuse3` and its filesystem dependencies. The client integrates with Windows Cloud Files API (cfAPI) for on-demand hydration.
- **Linux:** the project's `vfs` module and compatible FUSE packages. The VFS adds local chunk caching and transactional upload behavior.

The current entry point supports Windows and Linux; other operating systems raise a runtime error.

## Start the client

Run the client from the directory where you want its identity file and relative application state to live:

```bash
python client.py ./auth_key
```

The identity path is optional and defaults to `./auth_key`. At startup the client asks whether to authenticate as an administrator and then prompts for the server host/IP. Normal mode also requests a client password. During first-time enrollment, it requests an `Auth Key Security Code` from the bootstrap TOTP configured by an administrator.

If the identity file does not exist, the client attempts bootstrap enrollment. If it already exists, it is treated as the encrypted identity file for normal authentication. Keep the identity file private and back it up securely.

The mount point in the current source is `~/mount` on both platforms.

## First-time enrollment

First-time enrollment must be enabled by a server administrator. The administrator signs in using the administrator TOTP, configures and verifies a separate bootstrap TOTP, and enables bootstrap enrollment temporarily. The new client then uses a current bootstrap TOTP code to obtain and save its client identity. The administrator should disable bootstrap enrollment when enrollment is complete.

Do not share the administrator TOTP secret with ordinary clients. For full instructions, see [the setup guide](SETUP.md#4-configure-and-enroll-the-first-client) and [`network-README.md`](network-README.md).

## Python API

The `RemoteStorage` class works without mounting a drive:

```python
from client import RemoteStorage

storage = RemoteStorage(
    host="192.0.2.10",  # Replace with your server's address.
    port=9000,
    key_path="./auth_key",
    password=None,      # Prompts interactively.
)

print(storage.listdir("/"))
storage.write_file_from_local("./local_document.pdf", "/remote_document.pdf")

with storage.open_read("/remote_document.pdf") as remote_file:
    remote_file.seek(1024)
    sample = remote_file.read(512)

print(storage.get_size("/remote_document.pdf"))
```

The constructor is:

```python
RemoteStorage(
    host="127.0.0.1",
    port=9000,
    key_path="./auth_key",
    password=None,
    auth_key_code_callback=None,
)
```

`auth_key_code_callback` is a callable used to obtain the bootstrap security code when enrolling a new client. It is not a password callback for an administrator ZIP archive; the current protocol no longer uses that archive flow.

## Common `RemoteStorage` methods

| Method | Purpose |
|---|---|
| `read(path)` | Read a remote file into memory. |
| `read_chunk(path, offset, length=CHUNK_SIZE)` | Read a portion of a file. |
| `write_chunk(path, offset, data)` | Write a data chunk at the requested offset. |
| `write_file_from_local(source, destination)` | Upload a local file in chunks using the standard upload command. |
| `open_read(path)` | Return a `RemoteReader` with `read`, `seek`, and `tell`. |
| `listdir(path)` / `list_keys()` | List entries or recursively enumerate remote files. |
| `exists(path)` / `is_dir(path)` | Query path existence or directory status. |
| `get_size(path)` / `get_hash(path)` | Retrieve size or server-computed hash information. |
| `mkdir(path)` / `make_directory(path)` | Create a remote directory. |
| `delete(path)` | Delete a remote path. This operation affects the server-side file. |
| `rename(source, destination)` / `move(source, destination)` | Move or rename a remote path. |
| `copy(source, destination)` | Copy a remote path. |
| `truncate(path, size)` | Change a remote file's length. |
| `on(event, callback)` | Register callbacks for `read`, `write`, `delete`, or `mkdir`. |

Some behaviors differ between the generic API and the Linux mount integration. The Linux `LinuxRemoteStorage` mount adapter uses additional VFS commands for metadata, cache handling, and transactional uploads. Do not assume the generic `write_file_from_local` method has the same transaction semantics as a mounted Linux VFS write.

The standard `info` response provides the file/directory and modification-time fields used by `RemoteStorage.is_dir()` and `RemoteStorage.stat()`, along with size and chunk information. The Linux VFS-specific metadata commands remain a separate interface with additional filesystem attributes.

## Mount behavior and caching

### Windows

The Windows backend uses cfAPI to represent remote files in the local filesystem and hydrate contents when applications access them. Hydration may use local disk space. Deleting a mounted file may delete the remote file instead of only removing a local cached copy; use a supported cache-management procedure to reclaim space.

### Linux

The Linux backend uses FUSE and the Crypton VFS. It uses chunk caching and a synchronization journal, and its mount upload workflow supports integrity checks and expected-version conflicts. The cache and journal paths are relative to the current working directory in the current implementation, so consistently launch the client from the intended directory. Preserve recovery files and journals until all writes are known to be committed.

## Event callbacks

```python
storage.on("read", lambda path: print("read", path))
storage.on("write", lambda path, chunk: print("write", path, len(chunk)))
storage.on("delete", lambda path: print("delete", path))
storage.on("mkdir", lambda path: print("mkdir", path))
```

Callbacks are useful for diagnostics and application-level logging. They are not a substitute for server authorization, auditing, or error handling.

## Administration and revocation

Run `client.py` and select admin mode to access the administrator console. Administrative functions include listing users/connections, configuring bootstrap TOTP, enabling/disabling bootstrap enrollment, renaming a stored client, deauthorizing a client, and disconnecting a live connection.

Deauthorizing a client removes its persistent server-side identity key files. An already-connected session may continue until it is separately disconnected or ends; use the disconnect action when immediate termination is intended.

## Security notes

- Use strong, unique client passwords and protect the client identity file.
- The server can access plaintext contents of stored files. Encrypt the server's disk/volume if protection at rest is required.
- Do not expose the service to untrusted networks without reviewing the custom protocol's threat model.
- Avoid deleting contents of a mount to clear cache; it may be a real remote deletion.

## Troubleshooting

**Cannot connect:** Check the host/IP, TCP port `9000`, server process, firewall, and client identity.

**Bootstrap rejected:** Confirm that bootstrap TOTP was configured and verified by an administrator, bootstrap mode is enabled, the code is current, and the identity path does not already exist.

**Normal login rejected:** Verify the identity file and client password and check whether the administrator deauthorized the client.

**Mount does not start:** Verify the relevant `winfuse3` or `vfs` dependencies and inspect the terminal output. See [`SETUP.md`](SETUP.md).
