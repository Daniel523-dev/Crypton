# Crypton Setup Guide

This guide covers the dependencies and native extension required by the current source, running the server and client, enrolling clients with TOTP, and protecting local state. Crypton can run the server and client on Windows or Linux in any combination.

## 1. Requirements

### Python packages

Install the common runtime packages into the Python environment used to run Crypton:

```bash
python -m pip install cryptography argon2-cffi blake3 zxcvbn pyotp
```

On Linux, use `python3` if that is the name of your Python interpreter. Keep the project modules `Encryption.py`, `network.py`, `server.py`, `client.py`, and `util.py` together unless you adjust their imports.

`network.py` imports a compiled extension named `backend`. `backend.cpp` is its source. The extension must be built for the same operating system, Python version, and CPU architecture as the interpreter. Build requirements include `pybind11`, a C++17-capable compiler, and Python development headers.

### Mount dependencies

The mount layer is platform-specific and is not fully contained in the files covered by this guide.

- **Windows:** `client.py` imports `winfuse3`. Install the dependencies required by that backend, including WinFsp where its current integration requires it. See [`winfuse3-README.md`](winfuse3-README.md).
- **Linux:** `client.py` imports `vfs`. Install the Python FUSE binding and system FUSE packages required by the project's VFS integration. See [`vfs-README.md`](vfs-README.md).

The `backend` networking extension is required even when you use the Python storage API without mounting a drive.

## 2. Build the `backend` extension (If you are using python 3.14, you may download backend.cp314-win_amd64.pyd instead)

Install the build dependency:

```bash
python -m pip install pybind11 setuptools
```

On Linux, install a C++ compiler and the Python development headers using your distribution's package manager. From the directory containing `backend.cpp`, run:

```bash
c++ -O3 -Wall -shared -std=c++17 -fPIC -pthread \
  $(python3 -m pybind11 --includes) backend.cpp \
  -o "backend$(python3-config --extension-suffix)"
```

The output filename must begin with `backend` and end with the extension suffix reported by the same Python interpreter used to run Crypton. Confirm that the extension can be imported:

```bash
python -c "import backend; print(backend.__doc__)"
```

For Windows or other build environments, use the MSVC C++ build tools and `pybind11` with the same Python environment that will run Crypton. A cross-platform setuptools recipe and the extension's exported API are documented in [`backend-README.md`](backend-README.md).

## 3. Start the server

Run from the Crypton directory so that relative files such as `server_salt.bin` and `./keys` resolve consistently:

```bash
python server.py
```

The command-line launcher asks for the server password. It also asks briefly whether to set up a new administrator TOTP. On first startup, or when a new TOTP setup is requested, Crypton prints a Base32 administrator TOTP secret and clears the console after a short delay.

1. Add that secret to a trusted authenticator app immediately.
2. Keep the secret offline and private; it grants access to the administrator login flow.
3. Confirm the printed listening address. The command-line launcher tries to discover a local interface address and falls back to `127.0.0.1` if discovery fails.
4. Allow inbound TCP port `9000` only from intended clients through the host/network firewall.

The default server shared directory is `~/Shared`. It is created if needed. To choose another location, edit `SHARED_DIR` in `server.py`; the current `FileServer` constructor does not expose a shared-directory parameter.

The server also uses these relative paths by default:

- `./server_salt.bin` — server password salt; keep it with the associated encrypted key material.
- `./keys/` — server-side client identity keys.
- `./ADMIN - TOTP.bin` — encrypted administrator TOTP secret.
- `./BOOTSTRAP - TOTP.bin` — encrypted bootstrap TOTP secret when bootstrap enrollment has been configured.

Run the server from the same working directory on subsequent starts, or explicitly plan and manage these relative paths before relocating it.

## 4. Configure and enroll the first client

The current implementation uses TOTP-based bootstrap enrollment. It does **not** use the older administrator ZIP bootstrap archive described by outdated documentation.

### 4.1 Configure bootstrap TOTP as an administrator

1. Start `python client.py ./auth_key` on a machine that can reach the server.
2. At `Authenticate as admin? [y/N]:`, enter `y`.
3. Enter the server host/IP and the current administrator TOTP code from your authenticator app.
4. In the admin console, use the bootstrap TOTP setup option to generate a new secret. Add the displayed secret to an authenticator app, then verify it with a current code when prompted.
5. Enable bootstrap enrollment in the admin console.
6. Communicate the bootstrap TOTP secret or enrollment code to the intended new client through a trusted channel.

The administrator TOTP and bootstrap TOTP serve different purposes. Do not distribute the administrator secret to ordinary clients.

### 4.2 Enroll a new client

On the client machine, ensure the intended identity path does not already contain a client identity file. Run:

```bash
python client.py ./auth_key
```

Choose normal (non-admin) mode, enter the server address and a strong client password, then enter the current code from the bootstrap authenticator when asked for `Auth Key Security Code`. After successful enrollment, the client stores its encrypted identity material at the selected path. That file is no longer an empty/nonexistent path; keep it private and back it up securely.

If `./auth_key` already exists, the client attempts normal authentication with that identity file and the client password instead of starting first-time bootstrap.

### 4.3 Disable bootstrap enrollment

After the intended client or clients are enrolled, log back in through admin mode and disable bootstrap enrollment. Keep bootstrap disabled except during a planned enrollment window. Treat the bootstrap TOTP as a privileged onboarding credential.

## 5. Start the client and mount storage

Run the client in the same working directory as its identity file:

```bash
python client.py ./auth_key
```

The program prompts for normal/admin mode, server address, and (in normal mode) the client password. The mounted directory is `~/mount` on both Windows and Linux.

- On Windows, the client starts the `winfuse3` integration and uses Windows Cloud Files API behavior for remote file hydration.
- On Linux, the client starts the FUSE-based `vfs` integration. Its cache and synchronization behavior is covered in [`vfs-README.md`](vfs-README.md).

On Linux, the default VFS metadata/cache files may be created under the client's current working directory, including `cache/`, `cache_meta.db`, and `sync_journal.db`. Preserve journal, working, and recovery files until you have verified that no local changes remain uncommitted. Keep the working directory consistent across launches.

## 6. Use the Python API without a mount

```python
from client import RemoteStorage

storage = RemoteStorage(
    host="192.0.2.10",  # Replace with your server address.
    port=9000,
    key_path="./auth_key",
    password=None,      # Prompts for the client password.
)

print(storage.listdir("/"))
storage.write_file_from_local("./example.pdf", "/example.pdf")
with storage.open_read("/example.pdf") as remote_file:
    data = remote_file.read(1024)
```

The API uses `key_path` for the enrolled client identity. The optional `auth_key_code_callback` argument can supply the bootstrap TOTP code programmatically when first enrolling a new client.

## 7. Backups, revocation, and maintenance

Back up these items securely:

- `server_salt.bin`, the server key directory, and the encrypted TOTP state files.
- Each client's identity file and its associated client password managed separately.
- Files in the shared directory.
- Linux cache journals, working files, or recovery files that may contain changes not yet committed to the server.

To revoke a client, use the administrator tools to deauthorize its stored identity. To stop a client that is currently connected, use the disconnect action as well. Deauthorization alone removes the persistent identity keys but should not be treated as immediate session termination.

## 8. Security considerations

- Use strong, unique server and client passwords. The networking module checks password strength with `zxcvbn`.
- Protect server identity files, salt files, TOTP secrets, client identity files, and backup copies with strict operating-system permissions.
- The custom Crypton protocol encrypts application messages in transit, but it is not a drop-in replacement for TLS and has not been established as independently audited or formally verified.
- Files saved by `server.py` in the shared directory are plaintext at rest unless the operating system or storage device provides encryption. The server can read file contents.
- Local hydrated/cache files may contain plaintext. Do not delete from a mounted directory just to clear the cache; it may delete the remote file.
- Do not expose the listening TCP port to untrusted networks before reviewing the protocol and deployment threat model.

## 9. Optional Psudo-TPM integration

Crypton can optionally integrate with [Psudo-TPM](https://github.com/Daniel523-dev/Psudo-TPM) for saved connection details and password autofill. It is separate from Crypton and is not required for normal operation. The current integration relies on Windows DPAPI; do not treat it as a supported Linux credential store.

Follow Psudo-TPM's own release instructions for `TPM.exe`, `TPM_client.py`, and its dependencies. Start the TPM service on each machine where its local integration will be used. Client and server integrations operate independently.

## 10. Troubleshooting

**`ModuleNotFoundError: backend`** — Build `backend.cpp` for the active Python interpreter. Check the extension filename and that it is in the import path.

**`ModuleNotFoundError` for `pyotp`, `zxcvbn`, `cryptography`, `argon2`, or `blake3`** — Install runtime packages into the same interpreter environment used to launch Crypton.

**Client cannot connect** — Confirm the server is running on TCP port `9000`, verify the address shown by the server, and check firewall/routing rules.

**Bootstrap fails** — Confirm bootstrap enrollment is enabled, that a bootstrap TOTP secret has been configured and verified, and that the code is current. Make sure the target identity path is absent for first enrollment.

**Normal authentication fails** — Check that the selected identity file and client password match. Confirm the client has not been deauthorized and the server salt/state files have not been replaced or restored inconsistently.

**Mount fails** — Install the correct platform mount dependencies and check the terminal output. Review [`vfs-README.md`](vfs-README.md) or [`winfuse3-README.md`](winfuse3-README.md).
