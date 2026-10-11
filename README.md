# Secure Encrypted SFTP

Welcome to the Secure File Transfer project. This repository contains a complete, end-to-end encrypted remote file storage ecosystem. It allows you to host a secure file server and mount it on client machines (Windows and Linux) as a native local drive. Files are encrypted and decrypted on the fly in memory, ensuring that your data remains secure both in transit and at rest.

## Setup and Installation

For detailed instructions on setting up, installing, and configuring the project, please refer to the `SETUP.md` file in the root directory of this repository. Follow the instructions in that document to prepare the environment and get the system running.

## Project Structure & Documentation

The project is broken down into several modular components. For detailed instructions on how to use, configure, or develop each piece, please refer to their respective README files:

* **Server Component** (`server-README.md`): Instructions for running and configuring the secure remote storage backend.
* **Client Component** (`client-README.md`): Guide for using the Python client API and mounting the remote server as a local drive.
* **Cryptography** (`Encryption-README.md`): Overview of the cryptographic backbone (Argon2, AES-GCM, ChaCha20, X25519/Ed25519) securing the entire ecosystem.
* **Networking** (`network-README.md`): Explanation of the custom TCP packet framing and streaming protocol used for zero-knowledge data transfer.
* **Linux Mount** (`vfs-README.md`): Details on the POSIX-compliant FUSE bridge for Unix-like systems.
* **Windows Mount** (`winfuse-README.md`): Details on the Windows virtual drive integration, which is powered by the Windows Cloud Files API (`cfAPI`) rather than traditional FUSE.

## Windows SFTP Client Cache Management

The Windows SFTP client relies on the Windows Cloud Files API (`cfAPI`) to integrate remote files with the local filesystem. When the client reads from or writes to a file, Windows may cache the file's contents locally, causing the file to occupy disk space on the client machine.

To remove these cached files and reclaim disk space:

1. **Stop the Windows SFTP client** to ensure that no files are actively being accessed or modified.
2. **Navigate to the mount directory** used by the Windows SFTP client.
3. **Delete the cached files** from the mount directory to remove the locally stored file contents.

**Note:** Only delete files when the client is stopped and you are certain they are cached files that can be safely removed. Ensure that any local changes have been synchronized with the remote server before deleting files to avoid losing data.

## Optional: TPM Autofill Integration

Optional autofill functionality is provided by the separate Psudo-TPM repository, available at:

```url
https://github.com/Daniel523-dev/Psudo-TPM
```

This component is not included in this repository and must be obtained separately.

To enable autofill, download `TPM.exe` from the most recent release in the Psudo-TPM repository and download `TPM_client.py`. Place both `TPM.exe` and `TPM_client.py` in the current working directory on the machines where the integration will be used.

**Starting the TPM program:**

* **Server:** The server administrator must manually start `TPM.exe` on the server machine to enable server-side TPM autofill functionality.
* **Client:** Each user must manually start `TPM.exe` on their own computer to enable client-side TPM autofill functionality.

**Independent operation:** The server and client TPM integrations operate independently of each other. Whether the server runs Psudo-TPM does not affect the client's ability to use its own Psudo-TPM integration, and whether the client runs Psudo-TPM does not affect the server's ability to use its own integration. Each side can enable or disable its TPM functionality independently.

The TPM integration is entirely optional and is not required for the core encrypted file storage, network communication, or drive-mounting functionality.

## License

This software is released under the **GNU General Public License v3.0 (GPL-3.0)**.

Please see the `LICENSE` file for the full text of the license, your rights, and your obligations when using or modifying this software.
