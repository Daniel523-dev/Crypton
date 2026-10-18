# Crypton Networking Module (`network.py`)

`network.py` implements Crypton's custom TCP authentication and message layer. It handles administrator and client authentication, TOTP-based bootstrap enrollment, session-key setup, authenticated message encryption, exchange IDs, and routing callbacks. It delegates socket I/O, framing, connection queues, and worker pools to the native Python extension built from [`backend.cpp`](backend.cpp).

**Transport note:** The current source uses the native `backend` TCP extension. It does not use ZeroMQ, despite older documentation that described `pyzmq`. The protocol is custom and should not be treated as TLS or as independently audited merely because it uses standard cryptographic primitives.

## Dependencies

Runtime dependencies include:

```bash
python -m pip install cryptography argon2-cffi blake3 zxcvbn pyotp
```

The local `Encryption.py` and `util.py` modules and the compiled `backend` extension are required. See [`backend-README.md`](backend-README.md) for compiling the extension.

## Authentication and enrollment

The current implementation uses TOTP codes rather than a ZIP-based administrator bootstrap archive.

- **Server password:** Used to derive the server's at-rest key for protected authorization/TOTP material. A salt is stored in `./server_salt.bin`.
- **Administrator TOTP:** Allows access to the client-side administrator console. On first server startup, or after an explicit reset, the server prints a Base32 secret. Import it into an authenticator app and keep it private.
- **Bootstrap TOTP:** A separate TOTP secret that the administrator configures and verifies in the admin console. It must be enabled before a new client can enroll.
- **Client password:** Protects the client's stored identity material at rest. It is distinct from both TOTP secrets.
- **Client identity file:** A new client starts with a path that does not yet exist (default `./auth_key`). After successful bootstrap it stores encrypted identity material at that path. A future connection uses that file for normal authentication.

Recommended enrollment sequence:

1. Log in to admin mode with the administrator TOTP.
2. Generate and verify the bootstrap TOTP using the admin console.
3. Enable bootstrap enrollment only for the planned enrollment window.
4. On the new client, use a new identity path and provide a current bootstrap TOTP code when prompted.
5. Disable bootstrap enrollment after the authorized client has enrolled.

Do not distribute the administrator TOTP secret to regular clients.

## Cryptographic flow (high-level)

The networking implementation calls `Encryption.gen_x25519(True)` for its handshake key pairs; in `Encryption.py`, this selects X448. It derives session material from the key agreement and applies AES-GCM to handshake/application payloads. Message counters and authenticated associated data bind encrypted payloads to their exchange and direction, and the implementation rejects non-increasing counters.

This is a summary of the code, not a security proof. The protocol is custom, the complete handshake should be independently reviewed, and the implementation does not become TLS through use of AES-GCM or through the separate certificate helper in `Encryption.py`.

## Message exchange

Exchange IDs are exactly 8 bytes. A client can create an exchange and wait for the matching response:

```python
from network import TCPClient

client = TCPClient(
    host="127.0.0.1",
    port=9000,
    password="a strong client password",
    auth_key="./auth_key",
)
try:
    eid = client.send(b"Hello, Crypton")
    response = client.recv(eid, timeout=5.0)
    if response is not None:
        print(response)
finally:
    client.close()
```

This example assumes that `./auth_key` is an already-enrolled identity file. For first-time enrollment, pass an `auth_key_code_callback` to provide the current bootstrap TOTP code. Use interactive prompts rather than hard-coded passwords in real applications.

Callbacks receive application payloads after the networking layer has decrypted them. Keep callback code short, handle errors, and avoid assuming that a queued send means the remote application processed the message.

## `TCPServer` API

The current constructor signature is:

```python
TCPServer(
    host,
    port,
    password,
    newTOTP=False,
    auth_key_dir="./keys",
    on_exchange=None,
    simult_handshakes=4,
    simult_exchanges=4,
)
```

| Parameter | Meaning |
|---|---|
| `host`, `port` | TCP interface address and port. |
| `password` | Required password used to derive the server at-rest key. |
| `newTOTP` | When true, generates a new administrator TOTP secret. |
| `auth_key_dir` | Directory holding server-side client identity key pairs. |
| `on_exchange` | Optional callback `(server, eid, data, client_id)` for incoming application messages. |
| `simult_handshakes`, `simult_exchanges` | Worker concurrency settings passed to the native extension. |

Useful methods:

- `send(payload, eid=None, client_id=None)` — queue an encrypted message for an authenticated client. `client_id` is required.
- `recv(client_id, eid, timeout=60)` — wait for a specific exchange on a client connection.
- `close_client(client_id)` — close the session and clear in-memory state for that client.
- `set_backpressure(client_id, enabled=True)` — toggle transport backpressure for a client.
- `close()` — stop the server's native I/O backend.

The server generates and persists TOTP material in relative files including `ADMIN - TOTP.bin` and, after configuration, `BOOTSTRAP - TOTP.bin`. Preserve these files with the matching `server_salt.bin` and key directory.

## `TCPClient` API

Current constructor:

```python
TCPClient(
    host,
    port,
    password,
    auth_key="./auth_key",
    admin_auth_code=None,
    auth_key_code_callback=None,
    on_exchange=None,
    simult_exchanges=4,
)
```

| Parameter | Meaning |
|---|---|
| `host`, `port` | Server hostname/IP and TCP port. |
| `password` | Client password for at-rest key derivation. |
| `auth_key` | Existing encrypted client identity file, or a new path for enrollment. |
| `admin_auth_code` | Current administrator TOTP code when connecting as admin. |
| `auth_key_code_callback` | Callback that returns the current bootstrap TOTP code during first enrollment. |
| `on_exchange` | Optional client callback `(client, eid, payload)` for incoming exchanges. |
| `simult_exchanges` | Worker concurrency setting passed to the native extension. |

Methods include `send(payload, eid=None)`, `recv(eid, timeout=60)`, `set_backpressure(enabled=True)`, and `close()`. `recv()` returns the decrypted payload or `None`; it may raise for timeout or connection/protocol errors.

## Operations and security

- Use random, unique passwords and store secrets in an approved secret manager or protected local storage.
- Back up the server salt, server key directory, TOTP state files, and client identity files together as needed. Replacing a salt without matching encrypted material may make existing keys unusable.
- Deauthorizing a client removes its persistent server identity keys. Existing sessions need to be disconnected separately if immediate termination is required.
- Application payloads are plaintext inside both client and server processes. The server stores file bytes as ordinary files; enable disk encryption and operating-system access controls where at-rest protection is required.
- Check the full implementation and threat model before exposing the listener to untrusted networks. The protocol is custom and has not been demonstrated here to have undergone an independent security audit.
