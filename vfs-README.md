# Crypton — Linux Virtual Filesystem (VFS)

Crypton's VFS module provides a FUSE-based filesystem bridge for POSIX-compatible operating systems, including Linux. It allows a local or remote storage backend to be mounted as a directory and accessed through ordinary filesystem operations.

In Crypton, the VFS backend connects Linux filesystem operations to the remote storage API, allowing users to browse, open, create, edit, and move remote files through their normal applications.

The implementation includes chunk-based caching, persistent SQLite metadata, synchronization journaling, periodic backing-store refreshes, conditional writes, and recovery handling for unsuccessful file commits.

## Core Components

### BackingStore

The `BackingStore` class defines the interface between the filesystem and its underlying storage system.

A backing store may represent a local directory, a remote server, or another storage implementation. The VFS calls its methods to retrieve metadata, list directories, read files, upload changes, and perform filesystem operations.

Core methods include:

- `initialize()` — Prepare the backing store for use.
- `listdir(path)` — List directory contents.
- `stat(path)` — Return file or directory metadata as a `BackingStat`.
- `open_read(path)` — Open a readable file-like stream.
- `write_file_from_local(source, destination)` — Write a local file to the backing store.
- `make_directory(path)` — Create a directory.
- `lexists(path)` — Check whether a path exists.
- `delete(path, is_directory)` — Delete a file or directory.
- `move(source, destination)` — Move or replace a path.

Optional methods provide file hashing, POSIX metadata, metadata updates, conditional writes, and filesystem statistics.

### StorageVFS

The `StorageVFS` class implements the FUSE filesystem operations by inheriting from `fuse.Operations`.

It translates system calls into backing-store operations and manages:

- File and directory metadata.
- Directory listings and path normalization.
- File reads, writes, truncation, and creation.
- Open file handles and per-file working copies.
- Commit and conflict handling.
- Cache invalidation and synchronization journaling.
- Background refresh of remote file state.

### CacheManager

The `CacheManager` handles chunk-based read caching.

Instead of downloading an entire remote file for every read, it retrieves the required chunks and stores them locally. Cached chunks are associated with their backing path, chunk index, and file-version metadata.

The cache manager uses a SQLite database to track cached chunks, including their filenames, sizes, versions, and last-access times.

### SyncJournal

The `SyncJournal` maintains a persistent record of filesystem operations that may need recovery.

It uses SQLite with write-ahead logging (WAL) and full synchronous mode for its journal database. Pending operations can be replayed when the filesystem starts again.

The journal also tracks file hashes, version tokens, and scheduled refresh checks.

## Requirements

### Operating System

- Linux or another POSIX-compatible operating system supported by the installed FUSE implementation.
- Windows is explicitly unsupported and raises a `RuntimeError` during module initialization.

### System Dependencies

Install the system FUSE library and utilities required by your distribution.

On Ubuntu or Debian-based distributions, the appropriate FUSE package depends on your operating-system version and FUSE setup.

### Python Dependencies

- `fusepy` — Python interface to FUSE.
- `blake3` — File-content hashing and verification.
- Python's built-in `sqlite3` module — Persistent cache metadata and synchronization journal.
- Python's standard filesystem, threading, and utility modules.

The module also requires the system-level FUSE library. Installing `fusepy` alone does not guarantee that the mount will work.

## Usage

### 1. Run the Standalone Example

Running `vfs.py` directly starts a local, disk-backed demonstration filesystem:

```bash
python vfs.py
```

By default, the example uses these paths relative to the current working directory:

| Path | Purpose |
|---|---|
| `./storage` | Backing directory containing the actual files. |
| `./mount` | Directory where FUSE mounts the filesystem. |
| `./cache` | Cached file chunks and temporary working files. |
| `./cache_meta.db` | SQLite database containing chunk-cache metadata. |
| `./sync_journal.db` | Persistent operation journal and file-hash state. |

The standalone example uses `LocalStorageBackend`, which stores files on disk under `./storage`. It is **not an in-memory filesystem**.

After mounting, open another terminal and interact with `./mount` as you would with an ordinary directory. Files created there are stored in the backing directory.

Stop the program with Ctrl+C. Files in the backing directory persist after shutdown, while cached data and temporary working files have their own cleanup and recovery behavior.

### 2. Mount a Custom Storage Backend

To mount a different backend, implement the `BackingStore` interface and pass an instance to `main()`.

For example, Crypton's Linux client supplies its remote-storage object to the VFS mount function:

```python
from vfs import main

# "storage" is an initialized-compatible backing store,
# such as Crypton's LinuxRemoteStorage instance.
main(
    backing_store=storage,
    mount_dir="/mnt/crypton",
)
```

The backing store must implement the methods required by the VFS operations it supports. It should also provide the expected metadata and error behavior for correct filesystem integration.

The mount directory is created automatically if it does not exist. Ensure that the current user has the required permissions and that the mount point is suitable for FUSE.

### 3. Configure the Cache and Journal

The `main()` function accepts optional configuration parameters:

```python
from vfs import main

main(
    backing_store=storage,
    mount_dir="/mnt/crypton",
    cache_dir="./cache",
    db_path="./cache_meta.db",
    journal_path="./sync_journal.db",
    chunk_size=16 * 1024 * 1024,
    cache_ttl=120,
    refresh_interval=5,
)
```

| Parameter | Default | Description |
|---|---|---|
| `cache_dir` | `./cache` | Directory for cached chunks and working files. |
| `db_path` | `./cache_meta.db` | SQLite chunk-cache metadata database. |
| `journal_path` | `./sync_journal.db` | SQLite operation journal and file-hash database. |
| `chunk_size` | 16 MiB | Size of each cached read chunk. |
| `cache_ttl` | 120 seconds | Maximum chunk-cache inactivity period before expiration. |
| `refresh_interval` | 5 seconds | Interval used by the background backing-store refresh worker. |

Keep the cache database, journal database, cache files, and recovery directory in appropriate locations. These paths are relative to the process's working directory unless an absolute path is supplied.

## Chunk-Based Caching

The VFS defines the following default settings:

```python
CHUNK_SIZE = 16 * 1024 * 1024
CACHE_TTL = 60 * 2
CACHE_SWEEP_INTERVAL = 1
```

When an application requests part of a file, `StorageVFS` determines which chunks contain the requested byte range and obtains the necessary data through `CacheManager`.

The cache manager:

1. Calculates the chunk indexes required by a read.
2. Checks whether valid cached chunks are available.
3. Verifies cached chunk metadata against the file's version.
4. Retrieves missing or invalidated data from the backing store.
5. Stores the retrieved chunks locally.
6. Updates their last-access timestamps.

Cached chunks are expired after 120 seconds without access by default. A background cleanup worker checks for expired chunks approximately once per second.

This expiration policy applies to the managed chunk cache. It does not mean every file stored in the cache directory is automatically removed after 120 seconds: open-file working copies and recovery files are managed separately.

### Cache Invalidation

Cached data is invalidated when the VFS detects that the backing file has changed, or when relevant filesystem mutations invalidate cached paths.

The background refresh process tracks backing-file versions and, when supported by the backend, content hashes. It spreads eligible file checks across refresh cycles to avoid hashing every file on every pass.

A detected change causes the relevant cached chunks to be removed so subsequent reads can retrieve current backing-store data.

Version tokens are based on metadata such as file type, size, creation time, and modification time. They are useful for change detection but are not cryptographic proof that file contents have remained identical.

## File Reads and Writes

### Reading Files

Read operations are served from the managed chunk cache when possible. Otherwise, the VFS reads the corresponding byte ranges from the backing store and caches them.

This makes repeated and partial reads more efficient, especially for large remote files.

The default FUSE configuration uses direct I/O, so the VFS-managed chunk cache is distinct from the kernel's normal file-data page cache.

### Writing Files

Writes are staged in temporary working files inside the cache directory rather than being immediately applied to the backing store with each individual write.

When a file is written, the VFS:

1. Checks the file's version against its recorded baseline.
2. Creates a local working copy of the backing file when needed.
3. Applies writes or truncation to that working copy.
4. Calculates a BLAKE3 digest for the completed working file.
5. Records the pending write in the synchronization journal.
6. Attempts a conditional write to the backing store.
7. Verifies the resulting file size and updates cache and version state.

The VFS attempts to commit dirty data during flush, synchronization, and file release operations.

For Crypton's remote backend, the conditional-write path uses the server's transactional VFS upload protocol when available. Other backing stores can implement their own conditional-write behavior.

**Important:** Successful local writes do not imply that the remote commit has already succeeded. A commit can fail because of a network error, a version conflict, or a backing-store error.

### Concurrent Modification Detection

Each open file tracks a baseline version. Before committing modified contents, the VFS checks whether the backing file still matches that version.

When a change is detected, the VFS can return a busy/conflict error instead of overwriting newer data.

Conditional-write support allows a backing store to enforce this check more directly. The provided default `BackingStore` implementation does not itself provide an atomic conditional write, so the fallback version check depends on the backend's behavior and concurrency guarantees.

## Synchronization Journal and Recovery

The synchronization journal records operations that may need to be completed or reconciled after an interrupted operation.

The journal stores pending writes, directory creation, deletion, and move operations. It also maintains file-hash and version state used by the background refresh mechanism.

During startup, `main()` initializes the backing store, cache manager, and journal, then attempts to replay pending operations before mounting the filesystem.

### Failed Write Recovery

If a file cannot be committed safely, the VFS attempts to preserve the modified working copy rather than silently discarding it.

Recovery files are saved under:

```text
./cache/recovery/
```

They use filenames that include the original basename, a timestamp, a unique suffix, and the ` .conflict` suffix.

For example:

```text
cache/recovery/report.pdf.1791849600.a1b2c3d4.conflict
```

These files contain local file data that could not be committed. Review them manually before attempting to merge or upload their contents.

The exact recovery location depends on the configured cache directory.

### Journal Replay

On startup, journal replay attempts to reconcile pending operations with the current backing store.

For pending writes, it checks whether the destination already matches the staged file, attempts a conditional write where applicable, and verifies the resulting content. Failed writes that cannot be safely replayed may be preserved as recovery files.

Other failed journal operations may remain pending for a future replay attempt.

**Note:** The journal is not a general-purpose version-control system. It does not guarantee conflict-free merging of simultaneous edits or provide unlimited historical file versions.

## Path Handling and Filesystem Semantics

FUSE paths usually begin with a slash, such as `/documents/report.pdf`. The helper `clean_backend_path()` converts these into normalized backend-relative paths.

It:

- Rejects null bytes.
- Removes leading slashes.
- Rejects path components equal to `..`.
- Removes redundant empty and current-directory components.

This provides consistent path handling for the storage abstraction.

The local demonstration backend performs additional path containment checks and rejects symlinks. Other custom backends must implement suitable containment and link-handling protections themselves.

### Directory Operations

The VFS maps common operating-system operations to backing-store methods, including:

- `getattr` — Retrieve filesystem metadata.
- `readdir` — List directory contents.
- `open` and `read` — Open and read files.
- `create` and `write` — Create and modify files.
- `flush` and `fsync` — Attempt to commit pending modifications.
- `release` — Close a file handle and finish its commit/cleanup handling.
- `truncate` — Change a file's size.
- `mkdir` — Create a directory.
- `unlink` and `rmdir` — Remove files and directories.
- `rename` — Move or replace paths.
- `statfs` — Retrieve filesystem capacity information.

The VFS filters common temporary-file names from directory listings and from its background recursive file scan.

### Metadata Limitations

Metadata behavior depends on the backing store.

The current `chmod()` and `chown()` handlers validate that a path exists but do not actually change permissions or ownership. Timestamp updates through `utimens()` depend on the backend's `set_metadata()` implementation.

Do not assume that every POSIX metadata operation is fully supported by every remote storage backend.

Symlink operations are optional and require explicit `symlink()` and `readlink()` support from the backing store. Otherwise, they return an unsupported-operation error.

## Security Considerations

### Local Cache Protection

The chunk cache and working files contain the data read from the backing store. For a remote Crypton backend, this means cached chunks and staged modifications can contain plaintext file content after the network layer has decrypted it.

The VFS does not automatically encrypt these local cache files at rest.

Protect the cache directory, databases, working files, and recovery directory with appropriate filesystem permissions and OS-level disk encryption when necessary. Avoid placing them in directories accessible to untrusted users.

### Backing-Store Trust

The VFS delegates storage and authorization to its backing store. When used with Crypton, the server remains part of the trusted storage environment and receives decrypted application data through the networking layer.

The VFS's local path normalization does not replace authorization checks, server-side path containment, or operating-system isolation.

### Integrity and Conflict Checks

BLAKE3 hashes are used to detect content differences and verify staged writes. Version tokens help detect concurrent changes, and conditional writes can reject stale updates.

These mechanisms improve integrity and consistency, but they do not by themselves provide file authenticity, digital signatures, or automatic merging of conflicting edits.

## Troubleshooting

### FUSE Mount Fails

- Verify that the OS-level FUSE libraries are installed.
- Confirm that `fusepy` is installed in the active Python environment.
- Ensure that the current user is allowed to create and access the mount point.
- Inspect the error output from the FUSE mount and the backing store.

### Remote Reads Fail

- Confirm that the backing store can connect to the remote server.
- Verify the requested path and file metadata.
- Check server logs for errors or version changes.
- Ensure that the local cache directory is writable.

### Writes Fail or Report Conflicts

- Check the backing store's connection and permissions.
- Look for concurrent changes to the destination file.
- Review the synchronization journal and mount logs.
- Inspect the recovery directory for preserved modifications.

### The Cache Uses Too Much Disk Space

- Review the configured cache directory.
- Verify that the cache cleanup worker is running.
- Check whether space is occupied by working files, temporary files, or recovery files rather than expired cached chunks.
- Remove recovery files only after confirming their contents are no longer needed.

### Files Do Not Reflect External Changes Immediately

The VFS refreshes backing-store state periodically. The default refresh interval is five seconds, but the detection time depends on the number of files, the scheduling of hash checks, and the metadata or hash capabilities of the backing store.
