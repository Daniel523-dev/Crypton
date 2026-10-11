# WinFUSE

A Python-based Windows Cloud Files API filesystem provider with an application-controlled backing store.

WinFUSE exposes a normal Windows filesystem mount through the Windows Cloud Files API (CfAPI). Files and directories appear in the mounted location as placeholders, while the actual data is provided by an application-defined `BackingStore` implementation.

The project can be used as a standalone program backed by a local `./storage` directory, or imported as a Python module and backed by anything the application wants.

## How It Works

```text
Windows Explorer
       │
       ▼
CfAPI Mount Directory
       │
       ▼
WinFUSE Provider
       │
       ├── Placeholder Data
       │
       └── File Contents
              │
              ▼
         BackingStore
              │
      ┌───────┼────────┐
      ▼       ▼        ▼
   Local    Database  Remote
    Disk              Storage
```

The Cloud Files mount and the backing storage are intentionally separate.

The mount must be located outside any other cloud-sync provider's sync root. The Python program itself can be stored elsewhere, including inside OneDrive.

## Features

* Windows Cloud Files API integration
* Placeholder-based filesystem namespace
* On-demand file hydration
* Application-controlled backing storage
* Recursive initial namespace population
* File creation and modification synchronization
* File deletion synchronization
* File and directory move synchronization
* Standalone local filesystem backend
* Importable Python module
* No requirement for backing data to exist on the local filesystem

## Requirements

* Windows
* Python 3
* `watchdog`
* Windows Cloud Files API (`cldapi.dll`)

Install the Python dependency with:

```powershell
pip install watchdog
```

The program must be run on Windows because it uses Windows Cloud Files API functions directly.

## Standalone Usage

Running the module directly uses the included local filesystem backend.

The default layout is:

```text
.
├── cfapi_mirror.py
├── storage\
└── mount\
```

Run it with:

```powershell
python cfapi_mirror.py
```

The local backend maps:

```text
./storage
```

to:

```text
./mount
```

For example:

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

The file in `mount` is a Cloud Files placeholder until Windows requests its contents. At that point, WinFUSE asks the backing store for the requested data and supplies it through CfAPI.

## Using WinFUSE as a Module

When imported, WinFUSE does not choose or create a backing store.

The application provides one:

```python
import cfapi_mirror

class MyBackend(cfapi_mirror.BackingStore):
    def initialize(self):
        ...

    def listdir(self, path):
        ...

    def stat(self, path):
        ...

    def open_read(self, path):
        ...

    def write_file_from_local(self, source_path, path):
        ...

    def make_directory(self, path):
        ...

    def lexists(self, path):
        ...

    def delete(self, path, is_directory):
        ...

    def move(self, source, destination):
        ...

backend = MyBackend()

cfapi_mirror.main(
    r"C:\MyMount",
    backend,
)
```

The application controls both:

1. Where the Windows mount is created.
2. Where and how the actual file data is stored.

## BackingStore

`BackingStore` is the interface between WinFUSE and the application's storage system.

Paths passed to the backend are logical relative paths using `/` as the separator:

```text
Music
Music/Albums
Music/Albums/song.flac
```

The backend decides how those paths are represented.

For example, a backend could store data in:

* A normal filesystem
* A database
* Object storage
* A network filesystem
* A custom storage engine
* An encrypted storage layer
* Any combination of the above

### Required Methods

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

    def describe(self):
        ...
```

### `stat()`

Returns a `BackingStat` object containing the metadata needed to create Cloud Files placeholders:

```python
BackingStat(
    is_directory=True,
    size=0,
    creation_time=...,
    access_time=...,
    modified_time=...,
)
```

### `open_read()`

Returns a binary file-like object supporting at least:

```python
seek(offset)
read(length)
```

This is used by the `FETCH_DATA` callback to retrieve file contents.

### `write_file_from_local()`

Receives the physical Windows path of a file that was created or modified in the mount and the logical backing path where it should be stored.

```python
write_file_from_local(
    r"C:\MyMount\Music\song.flac",
    "Music/song.flac",
)
```

The backend is responsible for copying, uploading, encrypting, or otherwise storing the data.

## Mount Directory

The mount directory is supplied to `main()`:

```python
cfapi_mirror.main(
    r"C:\MyMount",
    backend,
)
```

It is independent of the backing store.

For example:

```text
C:\MyMount
```

could be backed by:

```text
Remote object storage
```

while the Python application itself could live at:

```text
C:\Users\Dan\OneDrive\WinFUSE\
```

The mount directory should not be placed inside another cloud provider's sync root.

## OneDrive and Other Cloud Storage

The Python application itself can be stored in OneDrive.

For example:

```text
OneDrive\
└── WinFUSE\
    ├── cfapi_mirror.py
    └── app.py

C:\CloudMount\
└── ...
```

This is different from placing the CfAPI mount inside OneDrive.

The application code can be stored in OneDrive as long as the actual CfAPI mount is located somewhere outside the OneDrive sync root.

The same principle applies to other filesystem synchronization providers.

## Current CfAPI Design

The provider currently:

* Registers a Cloud Files sync root.
* Creates the initial placeholder namespace before connecting callbacks.
* Uses `FETCH_DATA` to hydrate files.
* Uses a full hydration policy.
* Creates the complete initial namespace during startup.
* Uses Watchdog to monitor changes made through the mounted filesystem.
* Synchronizes those changes into the application-provided backing store.

The Cloud Files API layer is intentionally kept separate from the backing storage layer.

## Project Philosophy

The most important design goal is separation of responsibilities.

WinFUSE handles:

```text
Windows filesystem
       ↓
Cloud Files API
       ↓
placeholder/hydration behavior
```

The application handles:

```text
logical path
       ↓
BackingStore
       ↓
actual data
```

This makes the provider reusable without requiring the provider itself to understand the application's storage system.

## Warning

This project directly interfaces with Windows Cloud Files API using Python `ctypes`.

That means small changes to native structures, callback definitions, buffer handling, or API parameters can cause failures that are difficult to diagnose.

The existing CfAPI implementation should be treated carefully.

In other words:

```text
IT WORKS.

DO NOT TOUCH THE BLACK MAGIC.
```
## winfuse3.py was reused from my winFUSE repository
```url
https://github.com/Daniel523-dev/winFUSE/
```

## License

WinFUSE is licensed under the GNU General Public License v3.0.

See the [LICENSE](LICENSE) file for the complete license text.

Copyright © 2026 Daniel523-dev.
