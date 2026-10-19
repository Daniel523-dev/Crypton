# Crypton — Self-Hosted Remote Storage

Crypton is a cross-platform, self-hosted file-storage project for Windows and Linux. It provides a native mount experience, a Python storage API, chunked transfers, and a custom TCP protocol that encrypts application messages in transit.

> **Security scope:** Crypton is not end-to-end encrypted storage in the strict sense. The server decrypts requests and stores file contents in its shared directory as ordinary files. The supplied server does not encrypt those files at rest. Transport encryption and encrypted authentication material do not protect server-side plaintext from a server administrator or a compromised server.

## Features

- **Native filesystem access:** Windows integration through `winfuse3` and the Windows Cloud Files API; Linux integration through the FUSE-based `vfs` backend.
- **Python API:** Read, upload, list, rename, copy, truncate, and delete remote files without mounting a drive.
- **Chunked I/O:** Standard file transfers use 12 MiB chunks; the Linux VFS has a separate transactional upload flow.
- **Encrypted network messages:** `network.py` uses X448-based key agreement and AES-GCM-protected messages through the native C++ TCP extension in `backend.cpp`.
- **Credential protection:** Client identity material and server authorization keys are encrypted at rest using password-derived keys.
- **Administrator tools:** An admin console supports user and connection management, client disconnection, and time-based one-time-password (TOTP) enrollment controls.

## Quick start
> [!IMPORTANT]
> ### **Before exploring Crypton, read `network-README.md` and examine `network.py` and `backend.cpp`!**

Start with [`SETUP.md`](SETUP.md) for dependency installation, compiling the native backend, server startup, and first-client enrollment.

At a high level:

1. Install the Python dependencies and build the `backend` extension from `backend.cpp`.
2. Start the server with `python server.py` and securely record the administrator TOTP secret shown during initial setup.
3. Use the client admin console to configure and enable a bootstrap TOTP for first-time client enrollment.
4. Start a client with `python client.py ./auth_key`, complete enrollment, and keep the resulting client identity file private.
5. Disable bootstrap enrollment when you have finished adding clients.

The default server storage directory is `~/Shared`. The command-line client mounts remote storage at `~/mount`. Both paths are relative to the current user's home directory; see the component docs for platform-specific behavior.

## Documentation

| Document | Contents |
|---|---|
| [`SETUP.md`](SETUP.md) | Installation, native extension build, server/client startup, enrollment, backups, troubleshooting |
| [`server-README.md`](server-README.md) | Server configuration, storage behavior, administration, upload protocol |
| [`client-README.md`](client-README.md) | Client mount, Python storage API, caching, callbacks |
| [`network-README.md`](network-README.md) | Authentication flow, protocol behavior, `TCPServer` and `TCPClient` APIs |
| [`backend-README.md`](backend-README.md) | C++/pybind11 TCP extension, exported classes, build instructions and limits |
| [`Encryption-README.md`](Encryption-README.md) | Encryption helpers, key derivation, hashing, key exchange, signatures, certificate helpers |
| [`vfs-README.md`](vfs-README.md) | Linux FUSE mount and VFS cache/synchronization behavior |
| [`winfuse-README.md`](winfuse-README.md) | Windows mount integration and Cloud Files API behavior |

## Architecture

- `server.py` implements the filesystem command handler and writes files under the configured shared directory.
- `client.py` exposes `RemoteStorage` and platform-specific mount adapters.
- `network.py` implements enrollment, TOTP-based administrator/bootstrap authentication, session-key setup, and encrypted message handling.
- `Encryption.py` provides cryptographic helpers used by the networking code and may also be used independently.
- `backend.cpp` builds the importable Python extension named `backend`; it implements the native TCP transport, framing, queues, callbacks, and connection lifecycle.
- `util.py` is a project-local helper module required by the Python cryptography/networking code.

The native extension is a runtime dependency: `network.py` imports `backend`. Mounting also needs the platform-specific integration and its dependencies. See [`backend-README.md`](backend-README.md), [`vfs-README.md`](vfs-README.md), and [`winfuse-README.md`](winfuse-README.md).

## Security and operational notes

- Network messages are encrypted and authenticated by the Crypton protocol, but the custom protocol has not been shown here to have an independent security audit or formal verification.
- The live networking path uses the custom TCP protocol; the certificate helper in `Encryption.py` is completely unused in this project.
- Server-side files in `~/Shared` are plaintext at rest unless the host provides disk/file encryption. Linux cache, working, and recovery files can also contain plaintext; Windows-hydrated files may consume local disk space.
- Use strong, unique passwords and protect `server_salt.bin`, the server key directory, TOTP state files, and client identity files. Back these up securely.
- Removing a client's server-side identity keys prevents future authentications. It does not necessarily terminate an already-authenticated session; use the admin console's disconnect action when immediate disconnection is required.
- Do not delete files from a mounted directory just to reclaim local cache space. A delete may affect the remote file itself. Use the supported cache-management procedure for the relevant mount backend.
- Optional autofill integration is provided by the separate [Psudo-TPM project](https://github.com/Daniel523-dev/Psudo-TPM). It is not required for core Crypton operation.

## License

Crypton is released under the GNU General Public License v3.0 (GPL-3.0). See [`LICENSE`](LICENSE) for the full terms.
