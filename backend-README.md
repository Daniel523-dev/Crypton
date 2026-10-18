# Native TCP Backend (`backend.cpp`)

`backend.cpp` builds the Python extension module named `backend`. The extension implements Crypton's native TCP transport: socket creation, framed reads/writes, connection tracking, handshake and authenticated message queues, exchange-ID routing, callback dispatch, backpressure controls, and connection shutdown.

`network.py` imports this module directly, so the extension is a runtime dependency for both the server and the client. This backend uses native TCP sockets; it is not the ZeroMQ backend described in older documentation.

## Requirements

- A C++17-capable compiler.
- Python development headers matching the Python interpreter that will import the extension.
- `pybind11` and `setuptools` installed in that same Python environment.
- On Windows, MSVC C++ build tools and the Windows SDK; on Linux, a standard C++ compiler and development headers.

Install the Python build tools:

```bash
python -m pip install pybind11 setuptools
```

## Build on Linux

From the directory that contains `backend.cpp`, run:

```bash
c++ -O3 -Wall -shared -std=c++17 -fPIC -pthread \
  $(python3 -m pybind11 --includes) backend.cpp \
  -o "backend$(python3-config --extension-suffix)"
```

Run the command with the same Python version used by Crypton. On systems where multiple Python installations are present, use their matching `python3` and `python3-config` commands.

Verify the build:

```bash
python -c "import backend; print(backend.__doc__)"
```

## Build with setuptools (including Windows)

For a Windows build, open a developer command prompt configured for the appropriate Visual Studio C++ toolchain. Save the following as `setup_backend.py` next to `backend.cpp`:

```python
import os
from setuptools import Extension, setup
import pybind11

if os.name == "nt":
    compile_args = ["/std:c++17", "/O2"]
else:
    compile_args = ["-std=c++17", "-O3"]

setup(
    name="crypton-backend",
    version="0.1.0",
    ext_modules=[
        Extension(
            "backend",
            ["backend.cpp"],
            include_dirs=[pybind11.get_include()],
            language="c++",
            extra_compile_args=compile_args,
        )
    ],
)
```

Then run:

```bash
python setup_backend.py build_ext --inplace
python -c "import backend; print(backend.__doc__)"
```

If the build fails, verify the compiler, Python headers, and `pybind11` are using the same architecture and interpreter. The generated file must be importable as `backend` from the directory where Crypton is launched.

## Exported module values

The module docstring is `Networking v2.0 queued TCP backend (resource-hardened)`. It exposes these constants:

| Constant | Current value | Meaning |
|---|---:|---|
| `MAX_UNAUTH_PAYLOAD` | 65,535 bytes | Maximum unauthenticated/handshake payload. |
| `MAX_AUTH_PAYLOAD` | 33,554,431 bytes | Maximum authenticated payload accepted by framing. |
| `QUEUE_LIMIT` | 8 | Queue limit used by the backend. |

The implementation also defines internal connection, buffer, worker-pool, and callback limits. Those values are implementation safeguards, not a promise of a specific client count or throughput.

## `backend.Server`

The Python constructor is:

```python
backend.Server(
    host,
    port,
    handshake_worker=None,
    on_exchange=None,
    simult_handshakes=4,
    simult_exchanges=4,
)
```

`handshake_worker` is called for a newly accepted unauthenticated connection and is responsible for performing the application-level handshake. `on_exchange` handles the notification for a received authenticated exchange. The native backend moves socket handling and queued callback work to its I/O/worker threads.

Exported methods and properties include:

| Member | Description |
|---|---|
| `start()` / `stop()` | Start or stop the listener and I/O loop. |
| `send(data, cid, eid=None)` | Queue a payload for an authenticated client ID, optionally associated with an exchange ID. |
| `recv(cid, eid, timeout=None)` | Wait for a matching exchange payload for a client. |
| `send_handshake(temp_cid, data)` | Send an unauthenticated handshake payload. |
| `recv_handshake(temp_cid, timeout=None)` | Receive a handshake payload before authentication. |
| `auth_finished(temp_cid, new_cid, confirmation_payload=None)` | Mark a connection authenticated and bind its final client ID. |
| `is_authed(...)` | Query the backend authentication state. |
| `close_client(client_id)` | Close a particular client connection. |
| `set_backpressure(client_id, enabled)` | Enable or disable backpressure for a connection. |
| `MAGIC1`, `MAGIC2` | Read-only framing markers generated/held by the backend. |

The exact method signatures are defined in the `PYBIND11_MODULE` block at the bottom of `backend.cpp`; keep this document aligned with that block when the source changes.

## `backend.Client`

The Python constructor is:

```python
backend.Client(host, port, on_exchange=None, simult_exchanges=4)
```

Exported methods/properties include:

- `send(data, eid=None)` and `recv(eid, timeout=None)` for queued application payloads.
- `send_handshake(data)` and `recv_handshake(timeout=None)` for pre-authentication messages.
- `auth_finished()` to switch the connection to authenticated mode after `network.py` completes its handshake.
- `close()` to close the connection and stop the I/O loop.
- Read-only `is_authed`, `cid`, `MAGIC1`, and `MAGIC2` properties.
- `set_backpressure(enabled)` to toggle outgoing transport backpressure.

The C++ extension transports bytes and routes them by connection/exchange IDs. Cryptographic key negotiation, AES-GCM processing, counters, and client enrollment logic live in `network.py`, not in `backend.cpp`.

## Operational notes

- Do not import/use the backend's raw send APIs as a substitute for the authentication/encryption layer in `network.py`.
- Callback code should be bounded, exception-safe, and designed for threaded invocation. Avoid blocking indefinitely in callbacks because doing so can reduce throughput.
- The backend's queue, payload, peer, and connection limits are resource controls, not a defense that makes a publicly exposed listener safe by itself.
- The native backend is part of a custom protocol. Review its framing and lifecycle code together with `network.py`; a successful compile or passing smoke test is not a security audit.
