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

## Contributing

**Contributions of any kind are welcome!** You don't need to be a cryptography expert, know the entire codebase, or write code to help improve Crypton.

Crypton is a self-hosted remote-storage project for Windows and Linux. I welcome outside feedback, testing, security reviews, bug reports, documentation improvements, and code contributions.

### How you can help

- **🔒 Review security and cryptography.** Examine the networking protocol, authentication flow, key handling, encryption implementation, and threat model. Question assumptions, identify potential weaknesses, and suggest improvements. Independent review is especially valuable.
- **🐛 Report bugs.** Try Crypton on your system, find unexpected behavior, and open an issue with steps to reproduce it. Small edge cases are worth reporting, too.
- **🧪 Test on different systems.** Help test Windows and Linux setups, file transfers, large files, interrupted connections, concurrent operations, mounting, caching, and recovery behavior.
- **📖 Improve documentation.** Clarify installation instructions, explain confusing parts of the architecture, improve examples, or document problems you encountered.
- **💡 Suggest ideas.** Open an issue to propose a feature, discuss a design decision, ask a question, or point out something that could be simpler or safer.
- **💻 Contribute code and tests.** Fix a bug, add a regression test, improve error handling, or help with maintainability. Small, focused pull requests are appreciated.

### Reporting issues

For ordinary bugs and suggestions, [open a GitHub issue](https://github.com/Daniel523-dev/Crypton/issues/new). Include your operating system, relevant dependency versions, steps to reproduce the problem, and the expected versus actual behavior. Remove passwords, keys, authentication files, and other sensitive information from logs or examples.

For security vulnerabilities, please use the repository's private vulnerability-reporting channel rather than publishing exploitable details in a public issue.

### A note on security

Crypton's security deserves careful independent scrutiny. As documented in the README, the server currently decrypts requests and stores file contents as ordinary files, and the custom network protocol has not been independently audited or formally verified in the documentation.

Please review the documented security assumptions and limitations before relying on Crypton for sensitive data. Security findings, questions, and constructive criticism are welcome.

### Getting started

You do not need to submit a pull request to contribute. An issue describing a bug, a question about the threat model, a test result from a different operating system, or a suggestion for improving the project can all be valuable contributions. This project is designed to work on windows and linux, macOS is unsupported.

Not sure whether something is worth reporting? Please open an issue and explain what you found.

Thank you for taking the time to help make Crypton better!

## License

Crypton is released under the GNU General Public License v3.0 (GPL-3.0). See [`LICENSE`](LICENSE) for the full terms.
