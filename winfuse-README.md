# WinFUSE — Windows Cloud Files API Provider

WinFUSE is a Python-based filesystem provider built on the Windows Cloud Files API (cfAPI). It exposes files and directories through a registered Windows synchronization root, allowing remote or locally backed storage to appear in the Windows filesystem as placeholders.

File contents are provided by an application-defined `BackingStore` implementation. When Windows requests file data, WinFUSE retrieves it from the backing store and supplies it through the Cloud Files API.

WinFUSE is used by Crypton's Windows client to provide a OneDrive-like file access experience backed by Crypton's encrypted remote storage system.

The provider and backing store are deliberately separate. WinFUSE handles Windows filesystem integration, placeholder creation, hydration, and synchronization events, while the application controls how actual file contents are stored and retrieved.

## How It Works

```text
Windows Explorer and Applications
                 |
                 v
       Windows Cloud Files API
                 |
                 v
        WinFUSE Provider
          |           |
          v           v
    Placeholders   Hydration Requests
          |           |
          +-----+-----+
                |
                v
           BackingStore
                |
       +--------+---------+
       |        |         |
       v        v         v
    Local     Database   Remote
    Storage              Storage
```

The mount directory and backing storage are separate.

The mount directory must be outside any other cloud-sync provider's synchronization root. The Python application itself can be stored elsewhere, including in OneDrive, provided the actual WinFUSE mount is outside that provider's sync root.

## Features

- **Windows Cloud Files API Integration:** Registers a Windows synchronization root and connects to Cloud Files callbacks.
- **Placeholder-Based Namespace:** Creates placeholders representing files and directories in the backing store.
- **On-Demand Hydration:** Retrieves remote file contents when Windows requests them.
- **Chunked Data Transfer:** Fetches file data in chunks of up to 12 MiB.
- **Application-Controlled Storage:** Uses a configurable backing-store interface rather than requiring data to reside on the local filesystem.
- **Namespace Refresh:** Periodically reconciles the mounted directory with the backing store.
- **Filesystem Change Monitoring:** Uses Watchdog to detect file and directory operations in the mount.
- **Bidirectional Synchronization Logic:** Propagates supported local changes to the backing store and can refresh changed backing files when compatible hash support is provided.
- **Persistent Synchronization Journal:** Records pending operations in SQLite to support recovery after interruptions.
- **Standalone Local Backend:** Includes a disk-backed example for testing the provider independently of Crypton.
- **Reusable Python Module:** Allows applications to supply their own storage implementation.

## Requirements

- Windows with support for the Windows Cloud Files API.
- Python 3.
- The `watchdog` Python package.
- The Windows Cloud Files API library, `cldapi.dll`, available on the system.
- The required Windows native APIs and filesystem permissions.

Install the Python dependency:

```powershell
python -m pip install watchdog
```

WinFUSE directly interfaces with Windows native APIs using Python `ctypes`. It is not a FUSE-based Windows implementation, despite the project name.

The current implementation is Windows-only. Importing it on a non-Windows platform fails because it loads Windows system libraries directly.

## Standalone Usage

Running `winfuse3.py` directly uses the included local filesystem backend.

```powershell
python winfuse3.py
```

The default layout is:

```text
.
├── winfuse3.py
├── storage\
├── mount\
└── sync_journal.db
```

All paths are relative to the process's current working directory unless otherwise configured in the source.

The local backend maps:

```text
.\storage\
```

to:

```text
.\mount\
```

For example, a file stored at:

```text
storage\
└── Music\
    └── song.flac
```

appears in the mounted filesystem as:

```text
mount\
└── Music\
    └── song.flac
```

The file in the mount is represented by a Cloud Files placeholder. Windows requests its contents when the file is accessed, and WinFUSE retrieves the data from the backing store.

The actual file is stored under `.\storage\\` in the standalone example. Files in the mount should be treated as part of the synchronized filesystem, not as an independent disposable cache.

## Using WinFUSE as a Python Module

When imported, WinFUSE does not select the storage backend automatically. The application supplies a compatible `BackingStore` instance.

For example:

```python
import winfuse3

class MyBackend(winfuse3.BackingStore):
    def initialize(self):
        ...

    def listdir(self, relative_path):
        ...

    def stat(self, relative_path):
        ...

    def open_read(self, relative_path):
        ...

    def write_file_from_local(self, source_path, relative_path):
        ...

    def make_directory(self, relative_path):
        ...

    def lexists(self, relative_path):
        ...

    def delete(self, relative_path, is_directory):
        ...

    def move(self, source_relative_path, destination_relative_path):
        ...

backend = MyBackend()

# main() takes the backing store first and mount directory second.
winfuse3.main(
    backend,
    r"C:\MyMount",
)
```

The application controls:

1. Where the Windows synchronization root is registered.
2. Where and how the actual file contents are stored.
3. How file metadata is retrieved.
4. How changes are written back to the backing store.

The `main()` function initializes the backend and synchronization journal, registers the sync root, populates the namespace, connects the Cloud Files callback, and starts filesystem monitoring and refresh processing.

## BackingStore

`BackingStore` defines the interface between WinFUSE and the application's storage system.

Paths passed to the backend are logical relative paths using forward slashes:

```text
Music
Music/Albums
Music/Albums/song.flac
```

The backend decides how these paths map to its actual storage.

Possible implementations include:

- A regular filesystem.
- A database.
- Object storage.
- A network filesystem.
- A remote encrypted storage service.
- A custom storage engine.
- Another application-managed storage layer.

### Required Methods

The current base class provides the following interface:

```python
class BackingStore:
    def initialize(self):
        ...

    def listdir(self, relative_path):
        ...

    def stat(self, relative_path):
        ...

    def open_read(self, relative_path):
        ...

    def write_file_from_local(self, source_path, relative_path):
        ...

    def make_directory(self, relative_path):
        ...

    def lexists(self, relative_path):
        ...

    def delete(self, relative_path, is_directory):
        ...

    def move(self, source_relative_path, destination_relative_path):
        ...

    def get_hash(self, relative_path):
        return None

    def describe(self):
        return type(self).__name__
```

The primary filesystem methods must be implemented by a custom backend. `get_hash()` is optional at the interface level, but it is important for detecting changes to existing file contents in the background.

### BackingStat

The `stat()` method returns a `BackingStat` instance containing the metadata needed to create and update Windows placeholders.

```python
winfuse3.BackingStat(
    is_directory=False,
    size=1024,
    creation_time=0.0,
    access_time=0.0,
    modified_time=0.0,
)
```

The timestamps are Unix timestamps expressed in seconds. The provider converts them to Windows FILETIME values when constructing placeholder metadata.

For directories, the size is normally zero.

### open_read()

The `open_read()` method returns a binary file-like object that supports at least:

```python
stream.seek(offset)
data = stream.read(length)
```

WinFUSE uses this interface to satisfy `FETCH_DATA` callbacks. The returned stream must provide the requested bytes, or the operation may fail.

### write_file_from_local()

The `write_file_from_local()` method receives the physical Windows path of a file in the mount and its logical backing path.

```python
backend.write_file_from_local(
    r"C:\MyMount\Music\song.flac",
    "Music/song.flac",
)
```

The backend is responsible for copying, uploading, encrypting, or otherwise storing the file contents.

The provider may retry writes when files are still changing. Backends should handle repeated calls safely and should not assume that each invocation corresponds to a unique user action.

### get_hash()

The optional `get_hash()` method returns a digest for a backing file. WinFUSE uses hash information to track content changes and compare local contents with the backing store.

If the backend inherits the default implementation, which returns `None`, hash-based content reconciliation is disabled. Namespace refresh can still discover new or missing paths, but external modifications to the contents of existing backing files cannot be reliably detected through this mechanism.

**Hash compatibility matters:** The current provider computes local file hashes using SHA-256 and represents them as hexadecimal strings. A custom backend's `get_hash()` must return a compatible digest representation for direct comparisons to work correctly.

## Mount Directory

The mount directory is provided to `main()`:

```python
winfuse3.main(
    backend,
    r"C:\MyMount",
)
```

It is independent of the backing store.

For example:

```text
C:\MyMount
```

could be backed by remote storage, while the application itself lives at:

```text
C:\Users\your-user\OneDrive\WinFUSE\
```

The application directory and the mounted synchronization root serve different purposes.

**Do not place the actual WinFUSE mount directory inside another cloud provider's sync root.** Nesting one synchronization provider inside another can cause recursive synchronization, conflicting placeholder handling, or unexpected data behavior.

The same rule applies to OneDrive and other cloud synchronization providers.

## OneDrive and Other Cloud Storage

The WinFUSE application code can be stored in OneDrive.

For example:

```text
OneDrive\
└── WinFUSE\
    ├── winfuse3.py
    └── app.py

C:\CloudMount\
└── ...
```

Here, OneDrive synchronizes the application files, while WinFUSE registers a separate mount at `C:\CloudMount\\`.

This is different from placing the WinFUSE mount inside OneDrive itself.

## Cloud Files API Implementation

### Sync Root Registration

WinFUSE registers the configured mount directory using `CfRegisterSyncRoot()` and connects the provider through `CfConnectSyncRoot()`.

The current implementation configures full hydration and an always-full population policy. It creates placeholders recursively for the initial backing-store namespace rather than waiting to discover all entries as individual directories are opened.

### Placeholder Creation

During namespace population, WinFUSE enumerates the backing store and creates Windows placeholders for its entries.

Placeholder metadata includes attributes, file size, timestamps, and a file identity derived from the logical backing path.

The provider filters common temporary-file names while enumerating the namespace.

### File Hydration

When Windows requests file data, the provider receives a `FETCH_DATA` callback.

The implementation:

1. Resolves the callback's Windows path to a logical backing path.
2. Determines the requested byte range.
3. Aligns transfer boundaries as necessary for the Cloud Files API.
4. Reads the corresponding data from the backing store.
5. Transfers the data to Windows using `CfExecute()`.

The default fetch chunk size is:

```python
FETCH_CHUNK_SIZE = 12 * 1024 * 1024
```

Hydration is performed in a background worker thread. If a request fails, the provider attempts to complete it with a Cloud Files failure status.

### Local Filesystem Changes

WinFUSE uses Watchdog to monitor the mounted directory for supported filesystem events:

- File creation.
- File modification.
- File deletion.
- File and directory movement.

These events are translated into corresponding backing-store operations.

The implementation uses an internal-event tracking mechanism to help distinguish provider-driven filesystem changes from user changes. File writes are retried when the file is still changing, and the synchronization journal records operations that may need recovery.

This is a best-effort synchronization mechanism, not a guarantee that every filesystem event is delivered exactly once.

### Remote Namespace Refresh

The provider periodically reconciles the mounted namespace with the backing store. The default refresh interval is five seconds.

It can create placeholders for new backing-store entries and remove stale entries from the mount when appropriate.

Remote changes to the contents of existing files require compatible `get_hash()` support from the backing store. The provider uses hash-based refresh checks to identify changed content and update placeholders.

The refresh mechanism spreads eligible hash checks across successive cycles and adjusts the interval for files that remain unchanged. Consequently, remote content updates may take longer than a single refresh interval to be detected.

## Synchronization Journal and Recovery

WinFUSE stores its synchronization journal in:

```text
.\sync_journal.db
```

The path is defined by `JOURNAL_PATH` in `winfuse3.py` and is relative to the process's current working directory.

The journal tracks pending write, directory creation, delete, and move operations, along with file-hash state used by refresh logic.

When the provider starts, it attempts to replay pending operations before normal synchronization begins. Operations that fail during replay may remain pending for a future attempt.

The journal is persistent, but its presence does not guarantee conflict-free synchronization. If using a remote backing store, provide suitable retry behavior, consistent metadata, and safe handling of conflicting modifications.

The current Windows provider's journal is not an automatic version-history system and does not guarantee recovery of every change after a process crash.

## Important Implementation Notes

- The provider relies on direct Windows API calls through `ctypes`.
- Native callback structures, structure sizes, HRESULT handling, and buffer management are sensitive to implementation errors.
- The provider uses Watchdog and periodic refreshes to synchronize changes.
- Hash-based file-content refresh requires a backend with compatible `get_hash()` behavior.
- The standalone backend is a local disk implementation; remote-storage integration is supplied by the application.
- The mount's placeholder behavior and local disk usage depend on Windows Cloud Files API policies and the state of each file.
- Cache, journal, and working paths should be kept consistent between program launches.

The Cloud Files API implementation should be modified carefully. Small changes to native structures, callback definitions, memory handling, or API parameters may cause failures that are difficult to diagnose.

```text
IT WORKS.
DO NOT TOUCH THE BLACK MAGIC.
```
