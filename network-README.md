# Crypton — Secure Networking Module

Crypton's networking module provides encrypted message exchange over TCP using ZeroMQ. It handles the custom authentication handshake, session-key establishment, encrypted message transport, exchange-based routing, and background socket processing.

The module separates network transport from application logic. It supports multiple exchange IDs over a connection, an optional server-side message callback, queued message handling, password-protected credential files, and administrator-controlled enrollment for new clients.

Crypton uses a custom protocol built on cryptographic primitives rather than SSH or a conventional file-transfer protocol. This document covers the behavior of `network.py`; it does not document the project's broader application protocol or installation requirements.

## Core Features

- **Exchange-based routing:** Messages are associated with exchange IDs (`eid`) so requests and responses can be routed over a persistent client connection.
- **Authenticated encryption:** Application payloads are protected using AES-GCM through the project's encryption helpers.
- **Two-part key establishment:** The handshake combines a temporary Diffie–Hellman shared secret with a second shared secret involving the server-side key pair assigned to the client's bearer credential.
- **Administrator-controlled enrollment:** A new client can use the administrator bootstrap archive to authenticate an enrollment exchange and receive its client-specific bearer credential.
- **Encrypted credential storage:** Server-side key pairs, the client's saved credential, and administrator signing-key material are encrypted at rest using password-derived keys.
- **Password-strength checks:** Password strength is estimated when deriving at-rest encryption keys.
- **Replay checks:** Monotonically increasing counters help reject duplicate or older messages within an established session.
- **Background I/O:** Dedicated I/O threads and queues separate socket handling from most application-level work.
- **Payload accounting:** The implementation tracks queued payload bytes and defines a 256 MiB accounting threshold to help limit excessive buffering.
- **Opaque application payloads:** This layer transports bytes and leaves application message formats to higher-level components.

## Security Model

The networking layer aims to provide confidentiality and integrity for application messages, authenticate clients through a secret bearer credential, and establish a fresh session key for each connection. Its security depends on the cryptographic helper implementations, key storage, random-number generation, correct protocol use, and operational handling of credentials. The custom protocol has not been established as formally verified or independently audited merely by using established primitives.

### Algorithms used by the networking handshake

The calls in `network.py` use the helpers `Encryption.gen_x25519(True)` and `Encryption.gen_ed25519(True)`. In the supplied `Encryption` implementation, the `True` mode selects **X448** and **Ed448**, respectively. The helper names therefore do not literally describe the algorithms used by this networking configuration.

- **X448:** Creates shared secrets through Diffie–Hellman key agreement.
- **Ed448:** Signs selected bootstrap and session-confirmation messages.
- **Argon2id:** Derives at-rest keys and the handshake's session-root material using the configured parameters in the encryption helpers.
- **AES-GCM:** Encrypts and authenticates handshake and application payloads.
- **Counters and authenticated associated data (AAD):** Protect message metadata and help detect reused or older records.

### Normal handshake overview

For a previously enrolled client, the handshake proceeds conceptually as follows:

1. The client and server exchange fresh X448 public keys and independently derive a temporary shared secret (`tss`). The initial ephemeral public-key exchange is not independently authenticated.
2. The client derives a compact identifier from its saved bearer public key and sends that identifier encrypted under `tss`. The server uses the identifier to locate the corresponding stored server-side key pair.
3. The client generates another ephemeral X448 key pair and sends its public key protected under `tss`.
4. The client calculates a shared secret using its new ephemeral private key and the saved bearer public key. The server calculates the matching secret using the corresponding stored private key and the client's ephemeral public key.
5. Both sides combine that second shared secret with `tss` through the configured KDF to derive the session-root material.
6. The peers exchange temporary Ed448 signing public keys inside the encrypted handshake and perform signed nonce challenges to confirm participation in the new session.
7. After the handshake succeeds, application messages use AES-GCM with per-message random salts and IVs. Counters, exchange IDs where applicable, and direction markers are authenticated as additional data.

The two shared secrets have different roles: `tss` protects the early handshake messages, while the second exchange ties the session derivation to the server-side key pair associated with the client's credential. The combined construction is intended to prevent an intermediary that establishes a different temporary secret with each endpoint from transparently completing the rest of the handshake. This is a description of the intended design, not a formal security proof.

### Client credential model

The client's saved credential is deliberately a **secret bearer credential**. During enrollment, the server creates an X448 key pair and retains both key components encrypted at rest. The client receives the corresponding public key and stores it encrypted under the client's key-storage password. Although this is mathematically a public key, Crypton intentionally treats the saved copy as secret authorization material.

Possession of the decrypted bearer public key allows a client to derive the credential identifier and participate in the session-key exchange. Someone who obtains the decrypted credential may therefore be able to impersonate its holder; the server does not verify a separate, persistent client private key in the normal handshake. The local password protects the stored file, but it is not independently sent to or verified by the server during normal authentication.

The credential identifier is derived with a requested length of six bytes, making it a compact 48-bit lookup value. It is an index into the server's credential store, not the bearer credential itself. Identifier collisions are possible, so this namespace is intended for the project's expected deployment scale rather than an arbitrarily large population.

### Bootstrap and enrollment

The administrator bootstrap archive contains Ed448 signing-key material protected by a password-derived key. During initial enrollment:

1. The client loads the archive and decrypts the administrator signing keys using the supplied archive password.
2. Client and server establish a temporary X448 shared secret.
3. The server sends a random nonce. The client signs the encrypted nonce using the administrator private key, and the server verifies the signature and nonce.
4. The server generates a new X448 key pair for this client's bearer credential and sends the public key in a signed, encrypted message.
5. The client verifies the signature, accepts the key, and sends a signed acknowledgement.
6. The server stores the associated X448 key pair encrypted with its at-rest key. The client stores the public-key credential encrypted with its own at-rest key.
7. The connection proceeds through the normal session-key establishment and confirmation steps.

The administrator signing keys authorize enrollment; they are not the application session key. The temporary Ed448 keys used later in the normal handshake are session-confirmation keys, not persistent client identities.

**Bootstrap archive rotation is intentional.** After a bootstrap attempt that enters the bootstrap path, the server regenerates its administrator signing key and rewrites the archive, including after an unsuccessful attempt. This is a deliberate availability trade-off in the current design: handshake workers are serialized, pending handshakes are queued, and established sessions retain their already-derived session keys. However, failed bootstrap attempts can invalidate a previously distributed archive and delay legitimate enrollment until the current archive is distributed. Disabling bootstrapping prevents the `REQ_KEY` path from being accepted and avoids this bootstrap-specific rotation. It does not eliminate all resource costs from unauthenticated handshake attempts.

Distribute the current bootstrap archive only through a trusted, authenticated channel. Keep the archive password separate from the server's at-rest password and the client's key-storage password.

### In transit

- **Authenticated encryption:** AES-GCM is used to protect message confidentiality and detect changes to the ciphertext or authenticated metadata.
- **Per-message material:** The encryption helper prepends a random 12-byte IV and 32-byte salt to each encrypted record. The salt is used to derive a per-message AES key from the session-root material.
- **Direction markers:** Client-to-server and server-to-client records use different direction markers in AAD so that a record cannot simply be copied unchanged into the opposite direction.
- **Counters:** Each side maintains increasing message counters. A counter must be greater than the last accepted counter; it does not have to be exactly the next integer. This permits gaps while rejecting duplicate or older counters.
- **Exchange IDs:** Application exchange IDs are included in AAD and are used for message routing. The server suppresses repeated incoming messages associated with an already-seen exchange ID while that ID remains in its duplicate-tracking set.
- **Challenge-response:** Random nonces and temporary Ed448 signatures provide explicit confirmation that the peer can participate in the newly established encrypted session.

The initial ephemeral X448 public keys are sent before the session root exists and are not independently authenticated at that point. The later exchange involving the enrolled server key and the key-confirmation messages are intended to bind the completed session to the stored credential. An active intermediary may still disrupt handshakes, observe exposed protocol metadata such as the compact credential identifier if it can interpose on the initial exchange, or cause availability problems.

### At rest

- The server's stored credential key pairs are encrypted using the server at-rest key.
- The client's bearer credential is encrypted using the client's key-storage password and its stored salt.
- The administrator signing-key material in the bootstrap archive is encrypted using a key derived from the separate administrator archive password.
- Argon2id and random salts make offline password guessing more expensive, but the protection still depends on password quality and safeguarding the passwords and files.

The server decrypts application messages before forwarding them to `on_exchange` or placing them in its receive queue. This is not a zero-knowledge design: the server can access application plaintext.

## Usage

### 1. Server setup with a callback

The optional `on_exchange` callback is called with `(server, eid, data, client_id)` when an incoming application message is accepted for an exchange.

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

The server creates the administrator bootstrap archive at `./server_keys/auth_key` when the supplied administrator password passes its configured validation. Transfer the current archive securely to authorized clients that need initial enrollment.

Use different passwords for server key storage and administrator bootstrap access. Never commit generated keys, archives, passwords, or secret material to version control.

### 2. Client setup

A new client uses the administrator archive to authenticate enrollment. After enrollment, the same path is replaced by the encrypted client bearer-credential file.

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
    response = client.recv(eid, timeout=5.0)

    if response is not None:
        print(f"Server replied: {response!r}")
finally:
    client.close()
```

Replace the example address with the actual server address. The networking interface transports bytes. Encode textual messages with UTF-8 when needed and decode received payloads only when their format is known. Production applications should handle `queue.Empty` and other expected communication errors.

The `auth_key_password_callback` is used to obtain the administrator archive password while the supplied file is a ZIP archive. It is not a replacement for the client's separate key-storage password.

### 3. Receive messages without a callback

If `on_exchange` is omitted, incoming application messages are placed in the server receive queue and can be retrieved with `recv()`.

```python
import queue
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

The server `recv()` method returns a tuple in this order:

- `eid` — exchange identifier.
- `data` — decrypted application payload.
- `client_id` — the authenticated bearer-credential identifier.

The method may raise `queue.Empty` when no message arrives before the timeout.

### 4. Exchange IDs

The client generates a random 64-byte exchange ID when `send()` is called without one.

```python
eid = client.send(b"Request payload")
response = client.recv(eid, timeout=10.0)
```

Applications may supply an explicit byte-string exchange ID. Treat IDs as opaque values and do not reuse an ID while an earlier exchange is pending. The server tracks seen IDs to avoid dispatching duplicate requests; a request using a seen ID may be ignored while that ID remains in the tracking set.

The server can reply through the same exchange by supplying `eid` to `server.send()`. The authenticated client identifier may also be supplied explicitly using `client_id`.

## API Overview

### `TCPServer`

Constructor:

```python
TCPServer(
    host,
    port,
    password,
    auth_key_password,
    auth_key_dir="./keys",
    salt_file="./server_salt.bin",
    on_exchange=None,
)
```

| Parameter | Description |
|---|---|
| `host` | Interface address on which the server listens. |
| `port` | TCP port for incoming connections. |
| `password` | Password used to derive the server at-rest encryption key. |
| `auth_key_password` | Password used to protect the administrator bootstrap archive. |
| `auth_key_dir` | Directory for server credential keys and the administrator archive. |
| `salt_file` | File containing the server at-rest key-derivation salt. |
| `on_exchange` | Optional callback with signature `(server, eid, data, client_id)`. |

The salt file is created if it does not exist. Preserve it alongside the protected key material: losing or replacing it can prevent the original at-rest key from being derived.

Methods:

- `send(payload, eid=None, client_id=None)` — Queue an encrypted message for a client. An exchange ID can route a response to its associated client; an authenticated client identifier can be supplied explicitly.
- `recv(timeout=60.0)` — Retrieve the next queued application message as `(eid, data, client_id)`. Intended for use when no callback is configured.
- `close()` — Stop the server I/O loop and close its ZeroMQ socket.

The server `send()` method does not return a delivery confirmation. A queued message should not be assumed to have been received or processed successfully.

### `TCPClient`

Constructor:

```python
TCPClient(
    host,
    port,
    password,
    auth_key="./auth_key",
    auth_key_password_callback=None,
)
```

| Parameter | Description |
|---|---|
| `host` | Server hostname or IP address. |
| `port` | Server TCP port. |
| `password` | Password used to derive the client's at-rest encryption key. |
| `auth_key` | Administrator ZIP archive during enrollment or the encrypted client bearer-credential file afterward. |
| `auth_key_password_callback` | Callable returning the administrator archive password during initial enrollment. |

Methods:

- `send(payload, eid=None)` — Send an encrypted application payload and return its exchange ID.
- `recv(eid, timeout=60.0)` — Wait for a response associated with the specified exchange ID.
- `close()` — Stop the client's I/O loop and close its ZeroMQ socket.

The client `recv()` method returns the decrypted response payload or `None` when no matching pending exchange exists. Waiting for an existing exchange may raise `queue.Empty` on timeout. Applications should also handle connection-related failures.

## Architecture Notes

### Transport and message framing

The networking layer uses a ZeroMQ `ROUTER` socket on the server and a `DEALER` socket on the client, communicating over TCP. ZeroMQ provides transport-level message framing and routing. The module exchanges multipart messages containing routing information, an exchange ID, and a payload.

This module does not itself define a four-byte JSON length-prefix packet format. Higher-level components may encode metadata and binary payloads before passing them to this layer. For example, a storage client may use a four-byte big-endian metadata length followed by JSON metadata and an optional binary payload; that is an application-level envelope carried inside the encrypted networking payload.

### Background I/O and callbacks

Both `TCPServer` and `TCPClient` use background I/O threads and queues. Calls to `send()` queue outgoing data, while `recv()` retrieves queued incoming messages or responses.

The server's `on_exchange` callback executes inside the server I/O loop. A slow callback can delay additional server-side I/O processing. Keep callbacks short and delegate expensive operations to an application-managed worker queue when appropriate.

### Queue management and denial of service

The module defines `MAX_QUEUE_BYTES` as 256 MiB. The server tracks payload-byte accounting per connection identity, while the client tracks buffered received payload bytes across its queues. Exceeding the relevant accounting threshold can result in a connection being killed or the client's I/O loop stopping.

This is payload accounting, not a strict process-wide memory limit. In particular, the pending handshake-task queue is not globally bounded, and queued handshake payload accounting is not equivalent to measuring total Python memory use. Applications should consider message-size limits, backpressure, timeouts, and resource-exhaustion risks.

Handshake workers are serialized, and pending handshakes are queued. This limits concurrent handshake-worker execution but also means a handshake backlog can delay later attempts. Established sessions retain their derived session keys during bootstrap-key rotation, although heavy network traffic or callback work can still affect overall responsiveness.

### Message counters and replay detection

Established sessions use monotonically increasing counters for encrypted messages. Counters are authenticated as part of the associated data, and received values are checked against the previously observed counter. A counter that is reused or decreases is rejected; gaps are allowed.

Exchange IDs have separate duplicate and activity tracking. Inactive exchange-tracking entries are periodically cleaned up after approximately 60 seconds. This lifecycle is distinct from the session message counters.

### Credential revocation

The server keeps the enrolled key pair for each bearer credential in its credential directory. Removing a credential's key files prevents the corresponding stored key pair from being selected for a future handshake. It should not be treated as immediate termination of an already established session, whose session key is already held in memory; disconnecting an active session requires separate handling.

### Operational security

- Use strong, unique passwords for server key storage, client key storage, and administrator bootstrap access.
- Protect administrator archives and transfer them through trusted channels.
- Restrict access to credential directories and salt files.
- Back up protected key material and its associated salt files securely.
- Never commit private keys, bootstrap archives, passwords, or generated credentials to version control.
- Handle communication timeouts, queue exhaustion, callback errors, malformed input, and connection failures.
- Keep application callbacks short to avoid blocking the server I/O loop.
- Test reconnection, shutdown, authentication failure, malformed input, and resource exhaustion.
- Obtain an independent security review before relying on the custom protocol for highly sensitive workloads.
