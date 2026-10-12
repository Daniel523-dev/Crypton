# Secure Networking Module

A message-exchange-based networking library that abstracts encryption, authentication, key management, and message framing over TCP sockets using ZeroMQ. Designed for secure, asynchronous-style communication, it allows developers to focus on application logic without manually managing cryptographic primitives or socket buffers.

## Core Features

* **Exchange-Based Routing (`eid`):** Messages are tracked using Exchange IDs (`eid`), allowing multiple requests and responses to be routed over a single TCP connection.
* **End-to-End Encryption:** Application messages are encrypted and authenticated transparently. The application layer does not need to handle session keys, nonces, or ciphertexts directly.
* **Event-Driven Server Hooks:** Server logic can be separated through an `on_exchange` callback, invoked when a new authenticated exchange is received.
* **Automated Key Provisioning:** First-time client connections can use an administrator key archive (`auth_key`) to authenticate the server and provision a long-term client identity key.
* **Encrypted Key Storage:** Long-term authentication keys are encrypted at rest using AES-GCM and a password-derived key.
* **Password Strength Validation:** Built-in `zxcvbn` integration checks password strength before deriving at-rest encryption keys.
* **Replay Protection:** Message counters help detect repeated or out-of-order encrypted messages.
* **Queue Limits:** A maximum buffered payload size of 256 MiB helps limit memory exhaustion from excessive queued data.

## Security Model

The module uses multiple cryptographic mechanisms to protect communications and stored identity keys.

### In Transit

* **X25519:** Establishes shared secrets using Diffie–Hellman key exchange.
* **Ed25519:** Signs handshake messages to authenticate key exchange steps and help prevent man-in-the-middle attacks.
* **AES-GCM:** Provides authenticated encryption for application payloads and relevant handshake data.
* **Message Counters:** Monotonically increasing counters help reject replayed or out-of-order encrypted messages.
* **Exchange IDs:** Associate messages with the appropriate request/response exchange.

### At Rest

* **AES-GCM:** Encrypts long-term authentication key material before writing it to disk.
* **Password-Based Key Derivation:** Passwords are processed through the module's `Encryption.kdf_slow` implementation using unique salts.
* **Password Strength Checks:** The `zxcvbn` estimator rejects passwords that do not meet the implementation's configured strength threshold.
* **Separate Administrator Credentials:** The bootstrap archive is protected by a separate administrator password.

**Important:** The actual algorithms in the supplied implementation are X25519 and Ed25519, not X448 and Ed448. The strength of the overall security also depends on the implementations in `Encryption.py`, key handling, protocol details, and operational practices. The presence of these primitives alone does not constitute a formal security audit.

## Installation / Requirements

Install the following Python dependencies:

* `pyzmq` — ZeroMQ bindings for TCP transport and socket management.
* `zxcvbn` — Password strength estimation.
* `cryptography` — Required if used by the underlying `Encryption.py` implementation.
* `argon2-cffi` — Required if `Encryption.kdf_slow` uses Argon2.
* `blake3` — Required if used by the underlying encryption or hashing utilities.
* `numpy` — Required if imported by `util.py` or other helper modules.

The last three dependencies are based on the helper modules and are not directly imported by `network.py`. Ensure they are installed according to the actual implementations of `Encryption.py` and `util.py`.

The module also requires the local `Encryption.py` and `util.py` files.

## Usage Example

### 1. Server Setup

The server listens for incoming client connections and can dispatch authenticated messages through the `on_exchange` callback.

The server requires:
* A password for protecting stored authentication keys.
* An administrator password for generating the initial bootstrap archive.
* An authentication key directory for storing server-side identity keys.

```python
from network import TCPServer

def handle_message(server, eid, data, client_id):
    print(f"Received: {data.decode('utf-8')}")

    # Reply using the same Exchange ID and client identity.
    server.send(
        b"Message acknowledged!",
        eid=eid,
        client_id=client_id
    )

server = TCPServer(
    host="127.0.0.1",
    port=8888,
    password="Use-A-Strong-Unique-Server-Password!",
    auth_key_password="Use-A-Separate-Strong-Admin-Password!",
    auth_key_dir="./server_keys",
    salt_file="./server_salt.bin",
    on_exchange=handle_message
)
```

The server generates an administrator key archive at `./server_keys/auth_key` when a sufficiently strong administrator password is accepted. Distribute this archive securely to authorized clients for their initial enrollment.

**Note:** Keep the administrator password separate from the server's at-rest password. The example credentials are placeholders; use unique secrets in real deployments.

### 2. Client Setup

On its first run, the client uses the administrator archive to authenticate the bootstrap exchange and provision its long-term authentication key.

After successful provisioning, the archive path is replaced with an encrypted client identity key file. Subsequent connections use this cached key instead of repeating the bootstrap process.

```python
from getpass import getpass
from network import TCPClient

client = TCPClient(
    host="127.0.0.1",
    port=8888,
    password=getpass("Client key-storage password: "),
    auth_key="./client_auth.zip",
    auth_key_password_callback=lambda: getpass(
        "Administrator archive password: "
    )
)

# Send a message and obtain its Exchange ID.
eid = client.send(b"Hello secure world!")

# Wait for the response associated with this exchange.
response = client.recv(eid, timeout=5.0)

if response is not None:
    print(f"Server replied: {response.decode('utf-8')}")

client.close()
```

**Important:** `auth_key_password_callback` is used when the supplied `auth_key` is a ZIP archive. Once provisioning replaces the archive with the client's encrypted identity-key file, the callback is no longer needed for that file.

The callback must return the password used to protect the administrator archive.

### 3. Server Receive Without a Callback

If `on_exchange` is not supplied, incoming application messages are placed in the server's receive queue. They can be retrieved using `recv()`.

```python
from network import TCPServer

server = TCPServer(
    host="127.0.0.1",
    port=8888,
    password="Use-A-Strong-Unique-Server-Password!",
    auth_key_password="Use-A-Separate-Strong-Admin-Password!",
    auth_key_dir="./server_keys"
)

try:
    eid, data, client_id = server.recv(timeout=5.0)
    print(f"Received from {client_id}: {data!r}")

    server.send(
        b"Message acknowledged!",
        eid=eid,
        client_id=client_id
    )
finally:
    server.close()
```

The server's `recv()` method returns a tuple containing the exchange ID, payload, and client identity.

## API Overview

### TCPServer

`TCPServer(host, port, password, auth_key_password, auth_key_dir="./keys", salt_file="./server_salt.bin", on_exchange=None)`

* `host` — Interface address to bind to.
* `port` — TCP port to listen on.
* `password` — Password used to derive the at-rest encryption key.
* `auth_key_password` — Password used to protect the administrator bootstrap archive.
* `auth_key_dir` — Directory for server authentication key material and the administrator archive.
* `salt_file` — File containing the salt used for server at-rest key derivation.
* `on_exchange` — Optional callback with signature `(server, eid, data, client_id)`.

Methods:

* `send(payload, eid=None, client_id=None)` — Queue an encrypted response or message for a client. When an exchange ID is supplied, it is used to route the message to the associated client.
* `recv(timeout=60.0)` — Retrieve the next queued message as `(eid, data, client_id)`. This method is intended for use when no callback is configured.
* `close()` — Stop the server I/O loop and close its socket.

### TCPClient

`TCPClient(host, port, password, auth_key="./auth_key", auth_key_password_callback=None)`

* `host` — Server hostname or IP address.
* `port` — Server TCP port.
* `password` — Password used to derive the at-rest encryption key for the client identity key.
* `auth_key` — Path to the administrator ZIP archive during initial provisioning or the cached client identity-key file afterward.
* `auth_key_password_callback` — Callable that returns the administrator archive password during initial provisioning.

Methods:

* `send(payload, eid=None)` — Send an encrypted message and return its exchange ID. If no ID is supplied, a random ID is generated.
* `recv(eid, timeout=60.0)` — Wait for a response associated with the given exchange ID.
* `close()` — Stop the client's I/O loop and close its socket.

The client `recv()` method returns the decrypted response payload or `None` if no matching pending exchange exists. A timeout can raise `queue.Empty`; handle this exception when implementing timeout-sensitive application logic.

## Architecture Notes

### Queue Management

The implementation defines `MAX_QUEUE_BYTES` as 256 MiB. The server tracks buffered payload sizes per client, while the client tracks its overall buffered payload size.

Excessive buffering can trigger client disconnection or stop the client I/O loop. Applications should still implement appropriate backpressure, message-size limits, and error handling for their workload.

### Threading

Both `TCPServer` and `TCPClient` use background I/O threads and thread-safe queues for socket operations.

* `send()` queues outgoing messages.
* `recv()` waits for queued responses or messages.
* The server's `on_exchange` callback is invoked from the server I/O loop, so lengthy callback work can delay further I/O processing.

For production applications, keep callbacks short and delegate expensive work to an application-managed worker queue.

### Exchange Lifecycle

Exchange IDs associate requests with responses. The implementation maintains exchange activity timestamps and periodically removes entries that have been inactive for approximately 60 seconds.

Clients should treat exchange IDs as opaque byte strings and avoid reusing an ID while a previous exchange is still pending.

### Authentication and Bootstrap

During initial provisioning, the client uses the administrator archive to verify the bootstrap exchange and obtain its long-term authentication key. The client then saves the provisioned key in encrypted form.

Protect the administrator archive and its password carefully. Anyone who obtains the required bootstrap credentials may be able to enroll a client, subject to the protocol's authentication checks.

### Operational Security

* Use different, strong passwords for server key storage, client key storage, and administrator bootstrap credentials.
* Distribute bootstrap archives through a trusted, authenticated channel.
* Restrict access to key directories and salt files.
* Do not commit private keys, bootstrap archives, passwords, or generated credentials to version control.
* Handle exceptions from socket operations, callbacks, and receive timeouts.
* Test reconnection, shutdown, malformed messages, and authentication failures before production deployment.
* Review the implementation for denial-of-service risks and consider formal security testing before relying on it for sensitive traffic.

## Source Repository

The `network.py` implementation was reused from my networking repository:
```
https://github.com/Daniel523-dev/Networking/
```
