# Crypton — Secure Encrypted Remote Storage

Crypton is a cross-platform, end-to-end encrypted, self-hosted file storage ecosystem that provides a OneDrive-like experience from the client's perspective while keeping infrastructure under your control. Run the server and clients on Windows or Linux in any combination, and mount remote storage as a native local drive.

Crypton supports asynchronous uploads, transparent file hydration through the Windows Cloud Files API (cfAPI), and FUSE-based Linux mounting with chunked caching. Files are encrypted and decrypted on the fly in memory, while authentication keys are protected with password-based encryption at rest. Crypton uses a custom authentication and networking protocol built on standard cryptographic primitives rather than SSH or conventional file-transfer protocols.

## Setup and Installation

For detailed instructions on setting up, installing, and configuring Crypton, refer to the `SETUP.md` file in the root directory of this repository. Follow the instructions in that document to prepare the environment and get the system running.

## Project Structure & Documentation

Crypton is organized into several modular components. For detailed instructions on using, configuring, or developing each component, refer to its respective README file:

* **Server Component** (`server-README.md`): Instructions for running and configuring the remote storage server.
* **Client Component** (`client-README.md`): Guide to the Python client API and mounting remote storage as a native local drive.
* **Cryptography** (`Encryption-README.md`): Overview of the cryptographic components, including Argon2id, AES-GCM, X448, Ed448, and BLAKE3.
* **Networking** (`network-README.md`): Explanation of the custom network packet framing, streaming protocol, and communication mechanisms.
* **Linux Mount** (`vfs-README.md`): Details on the FUSE-based Linux filesystem integration and chunked caching.
* **Windows Mount** (`winfuse-README.md`): Details on the Windows virtual drive integration using the Windows Cloud Files API (cfAPI) for features such as transparent file hydration.

## Windows Client Cache Management

The Windows Crypton client uses the Windows Cloud Files API (cfAPI) to integrate remote files with the local filesystem. Files can appear in the mounted directory without their complete contents being stored locally. When files are accessed, Windows may hydrate them by downloading their contents, which can cause local disk usage to increase.

To reclaim disk space, use the cache-management procedures documented by the project, where available. Avoid deleting files directly from the mounted directory unless you are certain the operation is safe and intended: doing so may delete files or affect synchronization rather than simply remove cached data.

Before performing cache cleanup:

1. **Stop the Crypton client** to prevent files from being actively accessed or modified.
2. **Identify the cached data** using the project's supported cache-management procedures.
3. **Verify synchronization** to ensure local changes have been uploaded before removing any cached contents.

**Note:** The correct cleanup procedure depends on how the file is represented and managed by cfAPI. Do not assume that deleting a file from the mounted directory is equivalent to dehydrat­ing it.

## Client Access Revocation

Crypton stores client authorization material in files on the server. Access for a client can be revoked by deleting its corresponding authorization file.

**Important:** Revocation takes effect when the affected client restarts. Do not treat deleting the file as an immediate termination of an already established session.

## Optional: TPM Autofill Integration

Optional autofill functionality is provided by the separate Psudo-TPM repository:

https://github.com/Daniel523-dev/Psudo-TPM

This component is not included in Crypton and must be obtained separately.

To enable autofill, download `TPM.exe` from the latest release in the Psudo-TPM repository and obtain `TPM_client.py`. Place both files in the current working directory on each machine where the integration will be used.

### Starting the TPM Program

* **Server:** The server administrator must manually start `TPM.exe` on the server machine to enable server-side TPM autofill functionality.
* **Client:** Each user must manually start `TPM.exe` on their own computer to enable client-side TPM autofill functionality.

### Independent Operation

The server and client TPM integrations operate independently. Whether the server runs Psudo-TPM does not affect the client's ability to use its own integration, and whether the client runs Psudo-TPM does not affect the server's integration.

Each side can enable or disable its TPM functionality independently.

The TPM integration is entirely optional and is not required for Crypton's core encrypted storage, network communication, authentication, or drive-mounting functionality.

## License

Crypton is released under the **GNU General Public License v3.0 (GPL-3.0)**.

See the `LICENSE` file for the full license text and information about your rights and obligations when using or modifying this software.
