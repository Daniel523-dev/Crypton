# Crypton Setup Guide

This guide covers installing and configuring Crypton, running the server and clients, authorizing new clients, configuring optional Psudo-TPM password autofill, managing storage locations, and understanding important security considerations.

Crypton is a cross-platform, self-hosted remote storage ecosystem with a OneDrive-like client experience. It supports Windows and Linux clients, encrypted network communication, native filesystem mounting, chunked file transfers, Windows Cloud Files API (cfAPI) integration, and Linux FUSE-based storage with local caching.

## Table of Contents

- [1. Requirements](#1-requirements)
- [2. Server Setup](#2-server-setup)
- [3. Client Setup](#3-client-setup)
- [4. Authorizing a Client](#4-authorizing-a-client)
- [5. Storage Locations](#5-storage-locations)
- [6. Client Revocation](#6-client-revocation)
- [7. Optional Psudo-TPM Integration](#7-optional-psudo-tpm-integration)
- [8. Security Considerations](#8-security-considerations)
- [9. Performance and Scalability](#9-performance-and-scalability)
- [10. Troubleshooting](#10-troubleshooting)

---

## 1. Requirements

Crypton supports running the server and client on Windows or Linux in any combination.

For example, a Windows client can connect to a Linux server, and a Linux client can connect to a Windows server.

### 1.1 Python

Install a compatible version of Python on each machine. Ensure Python and pip are available from a terminal.

On Windows, the commands below use `python`. On Linux, use `python3` if required by your distribution.

### 1.2 Server Dependencies

Install the required Python packages:

```shell
python -m pip install cryptography argon2-cffi numpy pyzmq blake3 zxcvbn
```

The server also requires these project modules:

- `Encryption.py`
- `network.py`
- `server.py`
- `util.py`

Keep the files together in the server's installation directory unless you have adjusted the imports.

### 1.3 Windows Client Dependencies

Install the Python packages required by the client and its Windows mount integration:

```shell
python -m pip install watchdog pyzmq zxcvbn cryptography argon2-cffi blake3 numpy
```

The Windows client imports the `winfuse3` mount backend, which integrates with the Windows Cloud Files API (cfAPI).

Install and configure the Windows filesystem dependencies required by that backend, including WinFsp where applicable. Make sure the matching `winfuse3` module is present and its required dependencies are installed.

### 1.4 Linux Client Dependencies

Install the Python packages:

```shell
python3 -m pip install fusepy pyzmq zxcvbn cryptography argon2-cffi blake3 numpy
```

The Linux client also requires the system FUSE library supported by the installed `fusepy` version.

Install the appropriate FUSE package for your Linux distribution and configure permissions as necessary. The exact system package depends on your distribution and FUSE version.

The client requires these project modules:

- `Encryption.py`
- `network.py`
- `client.py`
- `util.py`
- `vfs.py`

### 1.5 Obtain the Project Files

Download or clone the Crypton repository and place the required modules in the appropriate server or client directory.

Keep the installation directory consistent when starting the application. Several default paths, including the client mount point and Linux cache locations, are relative to the current working directory.

---

## 2. Server Setup

The Crypton server provides remote filesystem access and manages client authentication through the networking module.

### 2.1 Configure the Shared Directory

The server's default shared directory is configured in `server.py`:

```python
SHARED_DIR = os.path.expanduser("~/Shared")
```

The directory is created automatically if it does not exist.

On Linux, this normally resolves to:

```text
/home/your-user/Shared
```

On Windows, it resolves relative to the home directory of the account running the server.

The current `FileServer` constructor does not accept a shared-directory parameter. To use another location, change `SHARED_DIR` in `server.py` before starting the server.

**Important:** This is the directory containing the actual server-side files. The networking layer protects data in transit, but files stored here are not automatically encrypted at rest by the supplied `server.py` implementation. See [Section 8: Security Considerations](#8-security-considerations).

### 2.2 Start the Server

Open a terminal in the server installation directory and run:

```shell
python server.py
```

On Linux, use:

```shell
python3 server.py
```

The server prompts for the master server password:

```text
Server password:
```

It may then prompt for the administrator authentication-key password:

```text
Auth key password:
```

The server prints its listening address and shared directory when initialization succeeds. For example:

```text
[*] File Server active on tcp://192.0.2.10:9000 | Serving: /home/user/Shared
```

The IP address depends on the machine's network configuration. The example address above is illustrative.

The current command-line launcher attempts to discover a local network address and falls back to the loopback address if discovery fails. Verify the printed address before attempting to connect from another machine.

If the server binds to `127.0.0.1`, remote machines cannot connect through that loopback address. Adjust the host configuration if necessary.

### 2.3 Configure the Master Server Password

Use a strong, unique password when prompted for the master server password.

This password is used to derive the encryption key that protects server-side authentication key material at rest. It is distinct from the administrator authentication-key password.

The server also creates or loads a salt file used during key derivation. The default location is:

```text
./server_salt.bin
```

Keep this file safe and available. Losing or replacing it can prevent the original at-rest encryption key from being derived.

### 2.4 Configure the Administrator Authentication-Key Password

The administrator authentication-key password controls the generation of the bootstrap archive used to enroll new clients.

Use a separate, strong password.

This prompt is optional at startup, but **client enrollment requires an administrator bootstrap archive**. If the password is omitted, times out, or fails the configured validation, the server may start without enabling new-client enrollment.

The default bootstrap archive location is:

```text
./keys/auth_key
```

The archive is generated by the networking module when an acceptable administrator password is supplied.

The archive password is distinct from:

- The master server password.
- A client's master key-storage password.
- The password used by unrelated accounts or services.

See [Section 4: Authorizing a Client](#4-authorizing-a-client) for the enrollment procedure.

### 2.5 Server Key and Salt Storage

By default, the networking module uses:

```text
./keys/
./server_salt.bin
```

The key directory contains server-side authentication key material and the administrator bootstrap archive. The salt file supports server at-rest key derivation.

These paths are relative to the server process's current working directory unless configured otherwise.

Restrict access to this directory and the salt file. Back them up securely, and do not commit private keys, archives, salts, or credentials to version control.

### 2.6 Keep the Server Running

The server performs network communication in background I/O threads. When running from the command line, leave the server process running while clients access the storage.

Press Ctrl+C to shut it down cleanly.

If using the server programmatically, close the underlying networking server when the application exits:

```python
server.server.close()
```

---

## 3. Client Setup

The client provides the interface to remote storage. It can mount the storage as a native filesystem or expose storage operations through its Python API.

### 3.1 Platform-Specific Mounting

**Windows**

The Windows client uses the `winfuse3` mount backend and the Windows Cloud Files API (cfAPI). This supports the representation of remote files in the local filesystem and on-demand file hydration.

Install the required Windows filesystem dependencies before launching the client.

**Linux**

The Linux client uses the `vfs` module and FUSE. The VFS provides chunk-based local caching, working files for edits, a synchronization journal, and recovery handling for failed commits.

Install the required FUSE libraries and verify that the current user has suitable permissions.

### 3.2 Start the Client

Place the required client modules in the client installation directory and run:

```shell
python client.py ./auth_key
```

On Linux:

```shell
python3 client.py ./auth_key
```

The authentication-key path is optional. If omitted, the client defaults to:

```text
./auth_key
```

The supplied file initially needs to be the administrator bootstrap archive distributed by the server administrator.

During startup, the client requests the host IP address and client password if these values were not obtained through the optional TPM integration.

When the supplied authentication file is an administrator ZIP archive, the client also requests the archive password.

The client uses the following credentials for different purposes:

| Credential | Purpose |
|---|---|
| Master client password | Derives the at-rest encryption key used to protect the client's stored identity key. |
| Administrator authentication-key password | Unlocks the administrator bootstrap archive during initial enrollment. |
| Server address | Identifies the server to connect to. |

Do not reuse the server password as the client password or the administrator archive password.

### 3.3 Initial Mount Point

The current client creates a directory named:

```text
./mount
```

This is the default mount point on both Windows and Linux. It is relative to the current working directory.

The client creates the directory if it does not exist, then starts the platform-specific mount backend.

If the mount fails, check the mount dependencies, filesystem permissions, and terminal output.

### 3.4 Windows Client Behavior

The Windows client uses cfAPI integration to make remote files available through the local filesystem.

Depending on the file and the mount implementation, a file may appear locally before all of its contents have been downloaded. Accessing the file can trigger hydration and increase local disk usage.

Avoid deleting files from the mounted directory merely to reclaim cached space. Deleting a file may delete the remote file itself rather than only its locally hydrated contents.

Use the appropriate cache-management behavior supported by the mount integration.

### 3.5 Linux Client Behavior

The Linux client mounts remote storage through FUSE and the Crypton VFS implementation.

The VFS uses local chunk caching and persistent SQLite databases to manage cached data and synchronization state.

By default, the VFS uses these paths relative to the client's current working directory:

```text
./cache/
./cache_meta.db
./sync_journal.db
```

The cache directory can contain cached chunks, temporary working files, and recovery files. The databases track cached data and operations that may need to be retried or reconciled.

**Important:** Keep the working directory consistent between client launches. If you launch the client from a different directory, the relative cache and journal paths may resolve somewhere else.

Do not remove the journal, working files, or recovery files indiscriminately. They may contain information required to recover changes that have not yet been committed.

### 3.6 Python API

A mounted drive is not required for every client operation. The Python client exposes a `RemoteStorage` API for direct remote access.

For example:

```python
from client import RemoteStorage, auth_key_password_callback

storage = RemoteStorage(
    host="192.0.2.10",
    port=9000,
    key_path="./auth_key",
    password="Use-A-Strong-Unique-Client-Password!",
    auth_key_password_callback=auth_key_password_callback,
)

print(storage.listdir("/"))
```

Replace the example address and credentials with your actual configuration.

For additional API methods and usage examples, see `client-README.md`.

---

## 4. Authorizing a Client

Initial enrollment is a coordinated process between the server administrator and the client user.

The administrator supplies a bootstrap archive protected by a separate password. During enrollment, the client and server execute the authentication handshake and provision a long-term client identity key.

### 4.1 Server Administrator: Prepare the Bootstrap Archive

1. Start the server with a suitable administrator authentication-key password.
2. Confirm that the server has initialized successfully and generated its bootstrap archive.
3. Locate the archive:

   ```text
   ./keys/auth_key
   ```

4. Make a copy of the archive for the client.
5. Transfer the archive to the client user through a trusted channel.
6. Communicate the corresponding archive password through a separate, trusted channel.

Do not send the archive and its password together through an untrusted channel.

### 4.2 Client User: Install the Bootstrap Archive

1. Obtain the archive and its password from the administrator.
2. Place a copy of the archive in the client working directory.
3. Name the copy `auth_key`, or supply a different path when launching the client.
4. Ensure that the file is the current archive issued by the administrator.

For example:

```shell
python client.py ./auth_key
```

On Linux:

```shell
python3 client.py ./auth_key
```

The client password and administrator archive password are entered separately.

### 4.3 Complete Enrollment

During bootstrapping, the client uses the administrator signing credentials in the archive to authenticate the enrollment exchange.

If enrollment succeeds, the client receives its long-term identity key material and protects it using the client password.

**Important:** The client overwrites the local `auth_key` file during successful provisioning. Its contents change from the administrator ZIP archive to the client's encrypted identity-key file.

Use a client-specific copy of the bootstrap archive rather than treating the server's archive as a reusable client identity file.

### 4.4 Bootstrap Archive Rotation

The bootstrap archive has a short lifecycle.

- The server generates an archive during startup when an acceptable administrator archive password is provided.
- The server regenerates its administrator signing credentials and archive after a bootstrap attempt.
- Restarting the server also replaces the archive.
- A second client should not rely on an archive that has already been used in a bootstrap attempt.
- If enrollment fails, obtain the current archive from the administrator before trying again.

An archive may therefore become invalid before a client uses it if another enrollment attempt occurs or the server restarts.

Coordinate enrollment so that clients receive the current archive and do not race to use the same one.

The archive password can remain the same across rotations, but each newly generated archive contains new administrator signing credentials and a new salt.

### 4.5 After Enrollment

After successful enrollment, the client should retain its newly provisioned identity-key file at the configured authentication-key path.

Subsequent connections use this identity file rather than repeating the administrator bootstrap procedure.

Keep this file secure. It contains encrypted identity material, and its confidentiality depends on the at-rest password and the security of the client machine.

Each client should maintain its own identity file. Do not distribute one client's provisioned identity file as the bootstrap archive for other clients.

---

## 5. Storage Locations

The following table lists the default locations used by the supplied implementation.

| Component | Default Location | Purpose |
|---|---|---|
| Server shared files | `~/Shared` | Files stored on the server. |
| Server authentication keys | `./keys/` | Server-side client key material and bootstrap archive. |
| Server salt | `./server_salt.bin` | Salt for server at-rest key derivation. |
| Client identity file | `./auth_key` | Client's encrypted identity key after enrollment. |
| Client mount point | `./mount` | Native filesystem mount point on Windows or Linux. |
| Linux chunk cache | `./cache/` | Cached chunks, working files, and recovery files. |
| Linux cache metadata | `./cache_meta.db` | SQLite metadata for cached chunks. |
| Linux synchronization journal | `./sync_journal.db` | Pending filesystem operations and file-hash state. |

Paths beginning with `./` are relative to the process's current working directory.

The server's shared directory is different: it is defined by `SHARED_DIR` in `server.py` and expanded relative to the home directory of the account running the server.

### 5.1 Backups

Back up important configuration and key material securely.

In particular, protect:

- The server's key directory.
- The server salt file.
- Client identity-key files.
- Any data stored in the shared directory.
- Linux cache recovery files that contain unsynchronized changes.

Avoid copying temporary cache contents unnecessarily, but verify that no needed recovery data is lost before cleaning up a cache directory.

---

## 6. Client Revocation

Client authorization is managed by the networking layer.

The server stores provisioned client identity key material in the configured authentication-key directory. These files are separate from the administrator bootstrap archive.

To revoke a client, identify its server-side identity key files and remove the associated authorization material. Remove both members of the corresponding key pair when cleaning up the identity.

**Important:** Removing authorization files prevents the client from successfully authenticating again, but it does not necessarily terminate an already-established connection immediately.

Under the current behavior, the revocation becomes effective for a client when it disconnects and attempts to authenticate again, such as after a client restart. Do not treat file deletion as an immediate session-termination mechanism.

Take care to identify the correct client identity before deleting key material. Removing the wrong files can revoke the wrong client.

For additional information about the authentication implementation, see `network-README.md`.

---

## 7. Optional Psudo-TPM Integration

Psudo-TPM provides optional password autofill and connection-information storage.

Repository:

https://github.com/Daniel523-dev/Psudo-TPM

This integration is not required for normal Crypton operation.

### 7.1 Platform Support

Psudo-TPM relies on Windows DPAPI and is intended for Windows. Do not rely on it as a supported Linux credential-storage integration.

### 7.2 Install Psudo-TPM

Download the following from the Psudo-TPM repository:

- `TPM.exe` — the latest release.
- `TPM_client.py` — the corresponding Python module.

Place both files in the same directory as the server or client files where the integration will be used.

Install the additional dependencies required by Psudo-TPM:

```shell
python -m pip install zstandard pywin32
```

Follow the Psudo-TPM project's own instructions if its current release specifies additional setup requirements.

### 7.3 Start TPM.exe

If the optional integration is enabled, start `TPM.exe` before launching the Crypton server or client.

The TPM process must be available whenever the relevant server or client process needs to retrieve stored credentials.

The current Crypton entry points attempt to import `TPM_client` and retrieve previously stored values when the module is available. If the TPM service cannot be reached, the program may fall back to interactive entry.

The server and client integrations operate independently. Enabling TPM on one machine does not enable it on the other.

### 7.4 Stored Values

The current integration can store values such as:

- The server password.
- The client password.
- The client host IP address.

The administrator bootstrap archive password remains a separate credential used during initial enrollment.

TPM autofill is optional and is not required for encrypted networking, client authorization, storage access, or filesystem mounting.

---

## 8. Security Considerations

### 8.1 Passwords and Key Storage

Use strong, unique passwords for server key storage, client key storage, and administrator bootstrap access.

Crypton's networking module derives at-rest encryption keys from passwords and salts. Protect those passwords and retain the corresponding salt files.

Password strength estimation is implemented using `zxcvbn`. Passwords that do not meet the implementation's configured strength requirements may be rejected.

### 8.2 Transport Encryption and Stored Files

Crypton encrypts application payloads in transit and protects authentication key material at rest.

However, the supplied server implementation decrypts network messages before processing filesystem commands and writing files into the shared directory.

Consequently:

- The server can access the plaintext contents of files it stores.
- Files in `~/Shared` are not automatically encrypted at rest by the server application.
- Linux cache chunks, working files, and recovery files may contain plaintext file contents.
- Windows files that have been hydrated may occupy local disk space as accessible file content.

For additional protection, use operating-system access controls and disk encryption on both server and client machines.

Do not assume that network encryption alone protects files against someone who gains access to the server's filesystem or a running client.

### 8.3 Secure Client Enrollment

- Distribute bootstrap archives through a trusted, authenticated channel.
- Send the administrator archive password separately.
- Use only the current archive supplied by the administrator.
- Coordinate enrollment to prevent multiple clients from racing to use one archive.
- Treat client identity files as sensitive, even though their key material is encrypted.
- Remove the correct server-side client authorization material when revoking access.

### 8.4 Network Exposure

Restrict access to the server to the networks and clients that require it.

- Configure the host firewall appropriately.
- Avoid exposing the server directly to untrusted networks without a security review.
- Protect the key directory and salt file with restrictive filesystem permissions.
- Monitor server logs and handle unexpected disconnects or authentication failures.
- Test authentication, reconnection, and recovery behavior before relying on the system for sensitive data.

### 8.5 File and Cache Management

Do not delete files from a mounted directory just to reclaim local cache space. A delete operation may affect the remote file itself.

On Linux, working files and recovery files can contain modifications that have not been committed to the backing store. Preserve them until you have confirmed that they are no longer needed.

---

## 9. Performance and Scalability

Crypton uses chunked transfers, background network I/O, caching, and transactional uploads to support large files and concurrent filesystem activity.

The default transfer chunk size for the client is 12 MiB. The Linux VFS defaults to 16 MiB cache chunks, and its transactional upload path supports chunks up to the server's configured 64 MiB maximum.

Actual throughput and client capacity depend on:

- CPU performance and available memory.
- Network bandwidth and latency.
- Number of active clients.
- File sizes and access patterns.
- Cache hit rates and available disk space.
- Server filesystem performance.
- Concurrent reads, writes, uploads, and metadata operations.

The networking implementation defines a 256 MiB payload-buffer accounting limit, but this is not a strict process-wide memory limit.

There is no reliable universal client-count guarantee based solely on the protocol's exchange-ID or cryptographic identifier sizes. Determine practical capacity by benchmarking the actual deployment under realistic workloads.

---

## 10. Troubleshooting

### 10.1 The Server Does Not Start

- Verify that Python and the required dependencies are installed.
- Ensure the server password meets the configured strength requirements.
- Check that the port is available.
- Confirm that the key directory and salt file can be created or accessed.
- Inspect the terminal output for initialization errors.

### 10.2 The Client Cannot Connect

- Verify that the server is running.
- Confirm that the host IP address and port are correct.
- Ensure the server's listening address is reachable from the client.
- Check host firewall and network restrictions.
- Verify that the client has valid authorization material.

### 10.3 Authentication Fails

- Confirm that the correct client identity file or current administrator archive was supplied.
- Verify the corresponding password.
- If enrolling a new client, obtain the current bootstrap archive from the administrator.
- Check whether another client attempted enrollment or the server restarted after the archive was distributed.
- If the client identity was revoked, contact the administrator for authorization.

### 10.4 The Mount Fails

**Windows**

- Verify that the `winfuse3` module and required filesystem dependencies are installed.
- Confirm that WinFsp and the Windows Cloud Files API integration are configured correctly.
- Check that the intended mount point is accessible.

**Linux**

- Verify that `fusepy` and the compatible system FUSE library are installed.
- Check FUSE permissions and mount-point ownership.
- Inspect the terminal output for VFS or backing-store errors.

### 10.5 Files Fail to Upload

- Check the server connection and available disk space.
- Verify that the destination directory exists.
- Check for concurrent modifications and version-conflict errors.
- Inspect the Linux VFS journal and recovery directory for uncommitted changes.
- Retry only after determining whether a prior operation partially completed or left recoverable data.

### 10.6 Cached Files Use Too Much Disk Space

- Check the configured cache directory.
- Allow the Linux cache manager to expire inactive chunks.
- Check whether disk usage comes from cached chunks, working files, or recovery files.
- Use the supported platform-specific cache-management procedures.
- Do not blindly remove contents from the mount directory.

---

## Setup Complete

Setup is complete when:

1. The server is running with its storage directory and key material configured.
2. The client has received valid authorization credentials.
3. The client has successfully completed initial enrollment.
4. The client can connect to the server.
5. The client can access remote storage through its configured mount point or Python API.

Psudo-TPM is optional and is not required for Crypton's core networking, authentication, storage, or filesystem mounting functionality.
