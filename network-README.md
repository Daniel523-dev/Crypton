# Crypton — Secure Networking Module

Crypton's networking module provides authenticated, encrypted message exchange over TCP using ZeroMQ. It handles client authentication, cryptographic key establishment, encrypted message transport, exchange-based routing, and background socket processing.

The module is designed to separate network communication from application logic. It supports multiple exchanges over a single connection, server-side message callbacks, queued message handling, password-protected authentication keys, and an administrator-controlled client enrollment process.

Crypton uses a custom authentication protocol built on standard cryptographic primitives rather than SSH or conventional file-transfer protocols.

## Core Features

- **Exchange-Based Routing:** Messages are associated with exchange IDs (`eid`), allowing requests and responses to be routed over persistent client connections.
- **Authenticated Encryption:** Application payloads are encrypted and authenticated using AES-GCM.
- **Cryptographic Handshake:** Establishes session keys using ephemeral Diffie–Hellman key exchange and authenticates selected handshake messages with digital signatures.
- **Administrator-Controlled Enrollment:** New clients can use an administrator bootstrap archive to authenticate the provisioning exchange and receive a long-term client identity.
- **Encrypted Key Storage:** Server-side client key pairs, client identity files, and administrator signing keys are protected with password-derived encryption keys.
- **Password Strength Validation:** Uses `zxcvbn` to estimate password strength when deriving at-rest encryption keys.
- **Replay Detection:** Monotonically increasing message counters help reject replayed or out-of-order messages.
- **Background I/O:** Dedicated I/O threads and queues separate socket processing from most application-level operations.
- **Queue Limits:** The implementation defines a 256 MiB payload-buffer accounting limit to help control excessive buffering.
- **Custom Application Payloads:** The networking layer transports opaque byte payloads, allowing higher-level components to implement their own message formats.

## Security Model

Crypton combines asymmetric key exchange, digital signatures, authenticated encryption, and password-based key derivation.

### In Transit

- **X448:** Establishes shared secrets using ephemeral Diffie–Hellman key exchange.
- **Ed448:** Signs selected handshake messages to authenticate important key-exchange steps.
- **AES-GCM:** Protects application messages and handshake data with authenticated encryption.
- **Message Counters:** Monotonically increasing counters help detect reused or older messages within an established session.
- **Authenticated Associated Data:** Exchange identifiers, counters, and direction markers are incorporated into AES-GCM authentication data where applicable.
- **Exchange IDs:** Associate messages with their corresponding exchanges and support response routing.

The current implementation calls the project's `Encryption.gen_x25519(True)` and `Encryption.gen_ed25519(True)` helpers. In the supplied Encryption module, the enabled `True` mode selects X448 and Ed448, respectively; the helper names are therefore not the literal algorithms used in this configuration.

### At Rest

- **AES-GCM:** Encrypts stored authentication key material.
- **Password-Based Key Derivation:** The `Encryption.kdf_slow` helper derives keys using a unique salt.
- **Password Strength Checks:** The `zxcvbn` estimator enforces a configured minimum strength for at-rest key-storage passwords.
- **Separate Credentials:** The server's at-rest password is distinct from the administrator bootstrap archive password.
- **Client Key Protection:** The client's stored identity file contains a salt and encrypted identity-key material, protected using its client key-storage password.

The cryptographic security of the complete system also depends on the implementation of `Encryption.py`, random-number generation, key handling, protocol behavior, and operational practices. Use of strong cryptographic primitives alone does not establish that a custom protocol is secure or formally audited.

**Important distinction:** This networking layer decrypts messages on the server before delivering them to the application callback or receive queue. Its transport encryption should not be interpreted as a zero-knowledge architecture in which the server cannot access application plaintext.

## Installation and Requirements

Install the Python dependencies required by the project:

- `pyzmq` — ZeroMQ bindings for TCP transport and socket management.
- `zxcvbn` — Password strength estimation.
- `cryptography` — Cryptographic primitives used by the Encryption module.
- `argon2-cffi` — Required by the Encryption module's Argon2-based key derivation.
- `blake3` — Required if enabled by the project's encryption or hashing implementation.

The module also requires the local `Encryption.py` and `util.py` files.

Some dependencies are transitive dependencies of these helper modules rather than direct imports in `network.py`. Install the dependencies specified by the project and its actual helper implementations.

## Usage

### 1. Server Setup

The server accepts client connections and can deliver authenticated application messages through the optional `on_exchange` callback.

The server requires:

- A password for protecting stored authentication key material.
- An administrator bootstrap password for generating the initial enrollment archive.
- An authentication-key directory for server-side identity keys.
- A TCP interface address and port.

Example:

```python
import time
from network import TCPServer

def handle_message(server, eid, data, client_id):
    print(f"Received from {client_id}: {data!r}")

    # Reply to the same exchange and authenticated client.
    server.send(
        b"Message acknowledged!",
        eid=eid,
        client_id=client_id,
    )

server = TCPServer(
    host="127.0.0.1",
    port=8888,
    password="Use-A-Strong-Unique-Server-Password!",
    auth_key_password="Use-A-Separate-Strong-Admin-Password!",
    auth_key_dir="./server_keys",
    salt_file="./server_salt.bin",
    on_exchange=handle_message,
)

try:
    # Keep the process alive while the I/O thread handles connections.
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Shutting down Crypton networking server.")
finally:
    server.close()
```

The server generates the administrator bootstrap archive at `./server_keys/auth_key` when the administrator password passes its configured validation.

Distribute the current archive securely to authorized clients that need initial enrollment. The archive contains the administrator signing key material and its salt; the protected key material must be unlocked using the administrator archive password.

**Credential separation:** Use different passwords for server key storage and administrator bootstrap access. Never commit generated keys, archives, passwords, or secret material to version control.

### 2. Client Setup

A new client uses the administrator archive to authenticate the enrollment exchange and obtain its long-term identity key material.

Example:

```python
from getpass import getpass
from network import TCPClient

client = TCPClient(
    host="127.0.0.1",
    port=8888,
    password=getpass("Client key-storage password: "),
    auth_key="./client_auth",
    auth_key_password_callback=lambda: getpass(
        "Administrator archive password: "
    ),
)

try:
    # Send an application message and receive its exchange ID.
    eid = client.send(b"Hello, Crypton!")

    try:
        response = client.recv(eid, timeout=5.0)
    except Exception:
        # Production applications should handle queue.Empty
        # and other expected communication errors separately.
        raise

    if response is not None:
        print(f"Server replied: {response!r}")
finally:
    client.close()
```

Replace the example address with the actual server address.

The example deliberately uses byte strings because the networking interface transports byte payloads. Encode textual messages with UTF-8 when needed and decode received payloads only when their format is known.

#### Bootstrap Archive Behavior

During initial enrollment:

1. The client loads the administrator archive and unlocks its protected signing keys.
2. The client and server exchange ephemeral public keys and establish a shared secret.
3. The client proves possession of the administrator signing key by signing the expected handshake data.
4. The server supplies its new client identity public key in an authenticated, signed response.
5. The client saves the identity material in encrypted form, using its client key-storage password.
6. The server stores the associated client key pair encrypted with its server at-rest key.

After enrollment, the path supplied through `auth_key` contains the client's encrypted identity-key file rather than the original ZIP archive.

The server also regenerates its administrator signing key and bootstrap archive after a bootstrap attempt. The archive is therefore rotated during enrollment; use the current archive when registering additional clients. Transfer bootstrap archives only through a trusted, authenticated channel.

The callback `auth_key_password_callback` is used to obtain the administrator archive password while the supplied file is a ZIP archive. It is not a replacement for the client's separate key-storage password.

### 3. Receive Messages Without a Callback

If `on_exchange` is omitted, incoming application messages are placed in the server's receive queue and can be retrieved with `recv()`.

```python
import queue
import time
from network import TCPServer

server = TCPServer(
    host="127.0.0.1",
    port=8888,
    password="Use-A-Strong-Unique-Server-Password!",
    auth_key_password="Use-A-Separate-Strong-Admin-Password!",
    auth_key_dir="./server_keys",
)

try:
    while True:
        try:
            eid, data, client_id = server.recv(timeout=5.0)
        except queue.Empty:
            continue

        print(f"Received from {client_id}: {data!r}")

        server.send(
            b"Message acknowledged!",
            eid=eid,
            client_id=client_id,
        )
except KeyboardInterrupt:
    pass
finally:
    server.close()
```

The server's `recv()` method returns a tuple in the following order:

- `eid` — Exchange identifier.
- `data` — Decrypted application payload.
- `client_id` — Authenticated client identity identifier.

The receive method may raise `queue.Empty` when no message becomes available before the timeout.

### 4. Using Explicit Exchange IDs

The client generates a random exchange ID automatically when `send()` is called without one.

```python
eid = client.send(b"Request payload")

response = client.recv(eid, timeout=10.0)
```

Applications can also supply an explicit byte-string exchange ID to `send()`. Treat IDs as opaque identifiers and avoid reusing an ID while an earlier exchange is pending.

The server can reply through the same exchange by supplying `eid` to `server.send()`. The authenticated client identity may also be provided explicitly through `client_id`.

## API Overview

### TCPServer

Constructor:

`TCPServer(host, port, password, auth_key_password, auth_key_dir="./keys", salt_file="./server_salt.bin", on_exchange=None)`

| Parameter | Description |
|---|---|
| `host` | Interface address on which the server listens. |
| `port` | TCP port for incoming connections. |
| `password` | Password used to derive the server at-rest encryption key. |
| `auth_key_password` | Password used to protect the administrator bootstrap archive. |
| `auth_key_dir` | Directory for server authentication keys and the administrator archive. |
| `salt_file` | File containing the server at-rest key derivation salt. |
| `on_exchange` | Optional callback with signature `(server, eid, data, client_id)`. |

The salt file is created when it does not exist. Preserve it alongside the protected key material: losing or replacing it can prevent the original at-rest key from being derived.

Methods:

- `send(payload, eid=None, client_id=None)` — Queue an encrypted message for a client. An exchange ID can be used to route a response to its associated client; an authenticated client identity can be supplied explicitly.
- `recv(timeout=60.0)` — Retrieve the next queued application message as `(eid, data, client_id)`. Intended for use when no callback is configured.
- `close()` — Stop the server I/O loop and close its ZeroMQ socket.

The server's `send()` method does not return a delivery confirmation. Applications should not assume that a queued message was received or processed successfully.

### TCPClient

Constructor:

`TCPClient(host, port, password, auth_key="./auth_key", auth_key_password_callback=None)`

| Parameter | Description |
|---|---|
| `host` | Server hostname or IP address. |
| `port` | Server TCP port. |
| `password` | Password used to derive the client's at-rest encryption key. |
| `auth_key` | Administrator ZIP archive during enrollment or the encrypted client identity file afterward. |
| `auth_key_password_callback` | Callable returning the administrator archive password during initial enrollment. |

Methods:

- `send(payload, eid=None)` — Send an encrypted application payload and return its exchange ID.
- `recv(eid, timeout=60.0)` — Wait for a response associated with the specified exchange ID.
- `close()` — Stop the client's I/O loop and close its ZeroMQ socket.

The client `recv()` method returns the decrypted response payload or `None` when no matching pending exchange exists. A timeout can raise `queue.Empty`. Applications should explicitly handle this exception and any connection-related failures.

## Architecture Notes

### Transport and Message Framing

The networking layer uses ZeroMQ's `ROUTER` socket on the server and `DEALER` socket on the client, communicating over TCP.

ZeroMQ handles transport-level message framing and routing. The module exchanges multipart messages containing routing information, an exchange identifier, and a payload.

The networking module does not itself define a four-byte JSON length-prefix packet format. Higher-level components, such as the Crypton storage client, may encode their application metadata and binary payloads before passing them to this layer.

For example, the storage client uses a four-byte big-endian metadata length, JSON metadata, and an optional binary payload. This is an application-level envelope carried inside the encrypted networking payload.

### Background I/O and Threading

Both `TCPServer` and `TCPClient` use background I/O threads and thread-safe queues.

- `send()` queues outgoing data for transmission.
- `recv()` retrieves responses or messages from queues.
- Socket processing occurs in the background I/O thread.
- The server's `on_exchange` callback executes within the server I/O loop.

**Callback warning:** A slow callback can delay further server-side I/O processing. Keep callbacks short and delegate expensive operations to an application-managed worker queue when appropriate.

### Queue Management

The module defines `MAX_QUEUE_BYTES` as 256 MiB.

The server tracks buffered payload sizes per client, while the client tracks buffered received payload bytes across its queues. Exceeding the configured accounting limit can result in a client being disconnected or its I/O loop stopping.

This is payload-buffer accounting, not a strict process-wide memory limit. It does not guarantee that total memory usage will remain below 256 MiB. Applications should still consider message-size limits, backpressure, timeouts, and resource-exhaustion risks.

### Message Counters and Replay Detection

Established sessions use monotonically increasing counters for encrypted messages. Counters are authenticated as part of the encrypted message's associated data, and received counters are checked against the previously observed value.

A counter that is reused or does not increase is rejected. This helps detect replayed or out-of-order messages within the active session.

Exchange IDs have their own lifecycle tracking. Inactive exchange tracking entries are periodically cleaned up after approximately 60 seconds.

### Authentication and Client Enrollment

The administrator bootstrap archive allows a new client to authenticate the initial enrollment exchange. Once enrollment succeeds, the server retains the new client's encrypted identity key pair, and the client retains its encrypted identity-key material.

The administrator archive's signing keys are regenerated following a bootstrap attempt. This rotates the bootstrap credentials, while existing provisioned client identities are managed separately.

Deleting a client's authorization key files from the server removes the stored identity material for that client. Under the current overall Crypton behavior, this revocation takes effect for the affected client when it restarts; it should not be treated as immediate termination of an already established session.

### Operational Security

- Use strong, unique passwords for server key storage, client key storage, and administrator bootstrap credentials.
- Protect administrator archives and transfer them through trusted channels.
- Restrict access to key directories and salt files.
- Back up protected key material and its associated salt files securely.
- Never commit private keys, bootstrap archives, passwords, or generated credentials to version control.
- Catch and handle communication timeouts, queue exhaustion, callback errors, and connection failures.
- Keep application callbacks short to avoid blocking the server I/O loop.
- Test reconnection, shutdown, authentication failure, malformed input, and resource exhaustion.
- Obtain an independent security review before relying on the custom authentication protocol for highly sensitive workloads.

## Source Repository

The networking implementation originated in my networking repository:

https://github.com/Daniel523-dev/Networking/

Crypton's networking module is integrated with the storage client's application protocol and the project's encryption utilities.
