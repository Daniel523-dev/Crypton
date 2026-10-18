# Crypton Server (`server.py`)

The Crypton server provides the remote filesystem command handler and writes file data beneath a shared directory. It relies on `network.py` for TOTP-based authentication and encrypted application messages, and on the compiled `backend` extension for TCP I/O.

> **Important:** The server decrypts requests before processing them and stores file content as ordinary files. The current implementation does not encrypt the shared directory at rest, so the server administrator and anyone who can read the server filesystem can access file contents.

## Requirements

Install the core Python dependencies and build `backend.cpp` into an importable extension named `backend`:

```bash
python -m pip install cryptography argon2-cffi blake3 zxcvbn pyotp pybind11 setuptools
```

`Encryption.py`, `network.py`, `server.py`, `util.py`, and the compiled `backend` module must be available. See [`SETUP.md`](SETUP.md) and [`backend-README.md`](backend-README.md).

## Storage and paths

The default shared directory is configured in `server.py`:

```python
SHARED_DIR = os.path.expanduser("~/Shared")
```

The server creates this directory if it is missing. `FileServer` does not currently accept a shared-directory argument; edit `SHARED_DIR` in the source to use another location.

By default, the server also uses relative paths in its current working directory:

- `./server_salt.bin` — salt used to derive the server at-rest key.
- `./keys/` — encrypted server-side client identity key files (`.prv` and `.pub`).
- `./ADMIN - TOTP.bin` — encrypted administrator TOTP secret.
- `./BOOTSTRAP - TOTP.bin` — encrypted bootstrap TOTP secret after it has been configured.

Run the server from the same working directory on subsequent launches and protect the files above. Do not move or restore the salt separately from the encrypted material it protects. The current key-validation routine expects `.prv`/`.pub` pairs in `./keys` and removes unexpected ordinary files or invalid/incomplete key pairs from that directory at startup; do not store unrelated files there.

## Run the server

```bash
python server.py
```

The command-line entry point attempts to determine a local interface address and defaults to `127.0.0.1` if detection fails. It prompts for the server password, and briefly asks whether to set up a new administrator TOTP. On first startup, the server creates an administrator TOTP if one does not already exist and prints the Base32 secret to the console.

Add the secret to an authenticator app before the console clears. The client admin console uses the current generated TOTP code to authenticate administrators. Use the printed address and TCP port `9000` when connecting from clients; check firewall/routing rules if remote clients cannot reach it.

The programmatic constructor currently exposed by `server.py` is:

```python
FileServer(host="127.0.0.1", port=9000, password=None, **kwargs)
```

Example:

```python
from server import FileServer

server = FileServer(
    host="0.0.0.0",  # Bind to all interfaces only if this exposure is intended.
    port=9000,
    password="a strong unique server password",
    auth_key_dir="./keys",
)
try:
    input("Server running; press Enter to stop.\n")
finally:
    server.server.close()
```

Binding to `0.0.0.0` exposes the listener on all network interfaces. Use a specific interface address and appropriate firewall restrictions for real deployments.

## Administrator access and client enrollment

The current source uses administrator and bootstrap TOTP credentials, not the older ZIP bootstrap archive documented in historical versions.

1. Start `client.py` and choose administrator mode.
2. Enter the server address and current administrator TOTP code.
3. In the administrator console, create a bootstrap TOTP secret, add it to an authenticator app, and verify a current code.
4. Enable bootstrap enrollment only while authorized clients are being added.
5. The new client uses a previously unused identity file path and the current bootstrap TOTP code to enroll.
6. Disable bootstrap enrollment when done.

The bootstrap TOTP is separate from the administrator TOTP and the client password. Do not distribute the administrator secret to ordinary users.

The admin console can list users and connections, rename client identities, deauthorize clients, and disconnect active sessions. Deauthorization deletes persistent identity key files; it does not necessarily close an already-established session. Use the disconnect operation when immediate session termination is required.

## Filesystem protocol

`server.py` accepts JSON metadata with optional binary payloads. The packet helper serializes a four-byte big-endian metadata length, JSON metadata, and then any payload bytes. Filesystem commands include:

| Command family | Examples |
|---|---|
| Basic metadata and transfer | `list`, `info`, `download_chunk`, `upload_chunk`, `get_hash`, `truncate` |
| Standard file operations | `mkdir`, `move`, `copy`, `delete` |
| Linux VFS metadata | `vfs_stat`, `vfs_list`, `vfs_statfs`, `vfs_posix_metadata` |
| Linux VFS upload | `vfs_begin_upload`, `vfs_upload_chunk`, `vfs_commit_upload`, `vfs_abort_upload` |
| Administration | `admin_list_connections`, `admin_list_users`, bootstrap TOTP status/setup/enable/disable and client-management commands |

Standard uploads write directly to the destination file at byte offsets; an interrupted transfer can leave a partially updated file. The standard `info` response includes file/directory status and modification time alongside size, chunk size, and chunk count, supporting the generic `RemoteStorage` metadata methods. The Linux VFS upload path uses a temporary file, completeness/size/hash checks, commit/abort operations, and optional expected-version checks to detect conflicting updates.

The standard chunk size is 12 MiB. The server also defines a 16 MiB I/O chunk constant and a 64 MiB maximum for an individual VFS upload chunk. These implementation defaults are not a general throughput guarantee.

## Filesystem boundary and security

The `safe_path()` helper resolves requested paths relative to the shared directory and rejects paths whose resolved location falls outside it. This helps protect against straightforward path traversal, but it is not a substitute for operating-system isolation. Symlinks, concurrent path changes, race conditions, and platform-specific filesystem semantics should be considered in a security review.

Additional deployment protections:

- Store `~/Shared` on an encrypted volume if server-side at-rest confidentiality is needed.
- Apply restrictive permissions to `~/Shared`, `./keys`, `server_salt.bin`, and TOTP state files.
- Use strong unique passwords and protect administrator/bootstrap TOTP secrets.
- Keep the listener behind a firewall and avoid exposing it to untrusted networks without an independent protocol assessment.
- Back up stored files and Crypton's key/salt/TOTP state securely. Confirm restore procedures before relying on backups.

## Troubleshooting

**Server does not start:** Check Python dependencies, that `backend` imports, that the chosen port is free, and that the current directory permits creation/read access for the salt/key/TOTP files.

**Client cannot reach the server:** Confirm the displayed bind address, port `9000`, firewall, and routing. A loopback bind only permits connections from the same machine.

**Admin login fails:** Confirm the server's administrator TOTP secret is in the authenticator app and device time is correct. Resetting the secret invalidates previously configured authenticator entries.

**Client bootstrap fails:** Bootstrap TOTP must be configured and verified, enrollment must be enabled, the code must be current, and the new identity path must not already exist.

**A deauthorized client still works:** Persistent deauthorization does not automatically guarantee termination of an already-open session. Disconnect the active connection separately.
