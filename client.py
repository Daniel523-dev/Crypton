import json, os, sys, getpass, traceback, time, errno, blake3
CHUNK_SIZE = 12 * 1024 * 1024
if sys.platform == "win32":
    import winfuse3 as mount_backend
    import msvcrt
    PLATFORM = "windows"
elif sys.platform.startswith("linux"):
    import vfs as mount_backend
    import errno
    import select
    import termios
    import tty
    PLATFORM = "linux"
else:raise RuntimeError(f"Unsupported platform:{sys.platform}")
def get_optional_input(text, timeout=15):
    if not sys.stdin.isatty() or not sys.stdout.isatty():return None
    value = []
    cursor = 0
    start = time.monotonic()
    print(text, end="", flush=True)
    def redraw():
        print("\r" + text + "".join(value) + "\x1b[K", end="", flush=True)
        print(f"\r{text}{''.join(value[:cursor])}", end="", flush=True)
    def insert(char):
        nonlocal cursor
        value.insert(cursor, char)
        cursor += 1
        redraw()
    def backspace():
        nonlocal cursor
        if cursor > 0:
            cursor -= 1
            value.pop(cursor)
            redraw()
    def delete():
        if cursor < len(value):
            value.pop(cursor)
            redraw()
    def move_left():
        nonlocal cursor
        if cursor > 0:
            cursor -= 1
            redraw()
    def move_right():
        nonlocal cursor
        if cursor < len(value):
            cursor += 1
            redraw()
    def move_home():
        nonlocal cursor
        cursor = 0
        redraw()
    def move_end():
        nonlocal cursor
        cursor = len(value)
        redraw()
    if os.name == "nt":
        import msvcrt
        while time.monotonic() - start < timeout:
            if not msvcrt.kbhit():
                time.sleep(0.01)
                continue
            char = msvcrt.getwch()
            if char in ("\r", "\n"):
                print()
                return "".join(value) or None
            if char == "\x03":raise KeyboardInterrupt
            if char in ("\x00", "\xe0"):
                key = msvcrt.getwch()
                if key == "K":move_left()
                elif key == "M":move_right()
                elif key == "G":move_home()
                elif key == "O":move_end()
                elif key == "S":delete()
                continue
            if char == "\b":backspace()
            elif char == "\x1b":continue
            else:insert(char)
        print()
        return None
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while time.monotonic() - start < timeout:
            remaining = timeout - (time.monotonic() - start)
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                print()
                return None
            char = os.read(fd, 1)
            if char in (b"\r", b"\n"):
                print()
                return "".join(value) or None
            if char == b"\x03":raise KeyboardInterrupt
            if char in (b"\x7f", b"\x08"):
                backspace()
                continue
            if char == b"\x1b":
                ready, _, _ = select.select([fd], [], [], 0.03)
                if not ready:continue
                seq = os.read(fd, 1)
                if seq == b"[":
                    ready, _, _ = select.select([fd], [], [], 0.03)
                    if not ready:continue
                    key = os.read(fd, 1)
                    if key == b"D":move_left()
                    elif key == b"C":move_right()
                    elif key == b"H":move_home()
                    elif key == b"F":move_end()
                    elif key == b"3":
                        ready, _, _ = select.select([fd], [], [], 0.03)
                        if ready and os.read(fd, 1) == b"~":delete()
                continue
            if char[0] < 128:insert(char.decode())
            else:
                expected = (2 if char[0] & 0xE0 == 0xC0 else 3 if char[0] & 0xF0 == 0xE0 else 4 if char[0] & 0xF8 == 0xF0 else 1)
                raw = char
                for _ in range(expected - 1):
                    ready, _, _ = select.select([fd], [], [], 0.05)
                    if not ready:break
                    raw += os.read(fd, 1)
                decoded = raw.decode("utf-8", errors="replace")
                for c in decoded:insert(c)
        print()
        return None
    finally:termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
def make_packet(meta, payload=b""):
    h = json.dumps(meta, separators=(",", ":")).encode()
    return len(h).to_bytes(4, "big") + h + payload
def parse_packet(data):
    if len(data) < 4:raise ValueError("Invalid response data")
    n = int.from_bytes(data[:4], "big")
    if len(data) < 4 + n:raise ValueError("Incomplete packet header")
    return json.loads(data[4:4+n].decode()), data[4+n:]
class RemoteReader:
    def __init__(self, storage, key, size):self.storage, self.key, self.size, self.offset = storage, key, size, 0
    def __enter__(self):return self
    def __exit__(self, *args):self.close()
    def read(self, size=-1):
        if self.offset >= self.size:return b""
        size = self.size - self.offset if size < 0 else min(size, self.size - self.offset)
        out = bytearray()
        while len(out) < size:
            n = min(CHUNK_SIZE, size - len(out))
            chunk = self.storage.read_chunk(self.key, self.offset, n)
            if not chunk:break
            out.extend(chunk)
            self.offset += len(chunk)
        return bytes(out)
    def seek(self, offset, whence=0):
        if whence == 0:pos = offset
        elif whence == 1:pos = self.offset + offset
        elif whence == 2:pos = self.size + offset
        else:raise ValueError("Invalid whence")
        if pos < 0:raise ValueError("Negative seek position")
        self.offset = pos
        return pos
    def tell(self):return self.offset
    def close(self):pass
class RemoteStorage:
    def __init__(self, host="127.0.0.1", port=9000, key_path="./auth_key", password=None, auth_key_password_callback=None):
        if not os.path.exists(key_path):raise FileNotFoundError(f"Key file not found:{key_path}")
        if not password:password = getpass.getpass("Client password:")
        import network
        try:self.client = network.TCPClient(host=host,port=port,password=password,auth_key=key_path,auth_key_password_callback=auth_key_password_callback)
        except Exception as e:traceback.print_exception(e);raise OSError
        self.lock = __import__("threading").Lock()
        self.callbacks = {"read":None, "write":None, "delete":None, "mkdir":None}
    def initialize(self):pass
    def describe(self):return "RemoteStorage"
    def on(self, event, callback):
        if event in self.callbacks:self.callbacks[event] = callback
    def _request(self, meta, timeout=10):
        with self.lock:
            eid = self.client.send(make_packet(meta))
            try:res = self.client.recv(eid, timeout)
            except Exception as e:return {"status":"error", "message":str(e)}
        if not res:return {"status":"error", "message":"Request timeout"}
        try:return parse_packet(res)[0]
        except Exception as e:return {"status":"error", "message":str(e)}
    def exists(self, key):return self._request({"cmd":"info", "path":key}).get("status") == "ok"
    def is_dir(self, key):
        key = key.strip("/")
        if not key:return True
        r = self._request({"cmd":"info", "path":key})
        return r.get("status") == "ok" and r.get("is_dir", False)
    def get_size(self, key):
        r = self._request({"cmd":"info", "path":key})
        return r.get("size", 0) if r.get("status") == "ok" else 0
    def stat(self, key):
        r = self._request({"cmd":"info", "path":key})
        if r.get("status") != "ok":raise FileNotFoundError(key)
        size, mtime = r.get("size", 0), r.get("mtime", 0)
        is_dir = r.get("is_dir", False)
        if PLATFORM == "windows":return mount_backend.BackingStat(is_directory=is_dir,size=size,creation_time=mtime,access_time=mtime,modified_time=mtime,)
        return {"size":size, "mtime":mtime}
    def rename(self, src_key, dst_key):return self._request({"cmd":"move","src_path":src_key,"dst_path":dst_key,}).get("status") == "ok"
    def copy(self, src_key, dst_key):return self._request({"cmd":"copy","src_path":src_key,"dst_path":dst_key,}).get("status") == "ok"
    def write_chunk(self, key, offset, chunk):
        if self.callbacks["write"]:self.callbacks["write"](key, chunk)
        req = make_packet({"cmd":"upload_chunk", "path":key, "offset":offset},chunk,)
        with self.lock:
            eid = self.client.send(req)
            res = self.client.recv(eid, 60)
        if not res:return False
        try:return parse_packet(res)[0].get("status") == "ok"
        except Exception:return False
    def read_chunk(self, key, offset, length=CHUNK_SIZE):
        if self.callbacks["read"]:self.callbacks["read"](key)
        req = make_packet({"cmd":"download_chunk","path":key,"offset":offset,"length":length,})
        with self.lock:
            eid = self.client.send(req)
            res = self.client.recv(eid, 60)
        return res[1:] if res and res[:1] == b"\x00" else b""
    def read(self, key):
        if self.callbacks["read"]:self.callbacks["read"](key)
        size = self.get_size(key)
        out = bytearray()
        for offset in range(0, size, CHUNK_SIZE):
            chunk = self.read_chunk(key,offset,min(CHUNK_SIZE, size - offset),)
            if not chunk:break
            out.extend(chunk)
        return bytes(out)
    def truncate(self, key, size):
        if isinstance(size, bool) or not isinstance(size, int) or size < 0:raise ValueError("Truncate size must be a non-negative integer")
        r = self._request({"cmd":"truncate","path":key,"size":size,})
        if r.get("status") != "ok":raise OSError(r.get("message", f"Failed to truncate remote file:{key!r}"))
        return r.get("size", size)
    def delete(self, key, is_directory=None):
        if self.callbacks["delete"]:self.callbacks["delete"](key)
        self._request({"cmd":"delete", "path":key})
    def mkdir(self, key):
        if self.callbacks["mkdir"]:self.callbacks["mkdir"](key)
        self._request({"cmd":"mkdir", "path":key})
    def listdir(self, rel_path):
        r = self._request({"cmd":"list", "path":rel_path}, 60)
        if r.get("status") != "ok":raise OSError(r.get("message", "Directory listing failed"))
        return [x["name"] for x in r.get("items", [])]
    def list_keys(self):
        keys = []
        def walk(path):
            r = self._request({"cmd":"list", "path":path}, 60)
            if r.get("status") != "ok":return
            for item in r.get("items", []):
                p = f"{path}/{item['name']}" if path else item["name"]
                if item.get("is_dir"):walk(p)
                else:keys.append(p)
        walk("")
        return keys
    def get_hash(self, key):
        req = make_packet({"cmd":"get_hash", "path":key})
        with self.lock:
            eid = self.client.send(req)
            res = self.client.recv(eid, 60)
        if not res or res[:1] != b"\x00":return None
        return res[1:]
    def open_read(self, relative_path):return RemoteReader(self, relative_path, self.get_size(relative_path))
    def write_file_from_local(self, source_path, relative_path):
        offset = 0
        with open(source_path, "rb") as f:
            while chunk := f.read(CHUNK_SIZE):
                if not self.write_chunk(relative_path, offset, chunk):raise IOError("Failed to upload file chunk")
                offset += len(chunk)
        if offset == 0:
            if not self.write_chunk(relative_path, 0, b""):raise IOError("Failed to create empty remote file")
        self.truncate(relative_path, offset)
    def make_directory(self, relative_path):self.mkdir(relative_path)
    def lexists(self, relative_path):return self.exists(relative_path)
    def move(self, source_relative_path, destination_relative_path):
        if not self.rename(source_relative_path, destination_relative_path):raise OSError(f"Failed to move {source_relative_path!r} -> {destination_relative_path!r}")
class LinuxRemoteStorage(RemoteStorage):
    def _vfs_request(self, meta, payload=b"", timeout=60):
        packet = make_packet(meta, payload)
        with self.lock:
            eid = self.client.send(packet)
            try:response = self.client.recv(eid, timeout)
            except Exception as exc:raise OSError(f"SFTP request {meta.get('cmd')!r} failed:{exc}") from exc
        if not response:raise TimeoutError(f"SFTP request {meta.get('cmd')!r} timed out")
        try:result, extra_payload = parse_packet(response)
        except Exception as exc:raise OSError(f"Invalid SFTP response for {meta.get('cmd')!r}:{exc}") from exc
        if extra_payload:raise OSError(f"Unexpected payload in {meta.get('cmd')!r} response")
        if not isinstance(result, dict):raise OSError("Invalid SFTP response metadata")
        return result
    @staticmethod
    def _raise_vfs_response(response, path=None):
        message = str(response.get("message", "Remote operation failed"))
        code = response.get("code")
        if response.get("status") == "conflict" or code == "version_mismatch":raise BlockingIOError(errno.EBUSY, message, path)
        if code in ("not_found", errno.ENOENT, "ENOENT"):raise FileNotFoundError(errno.ENOENT, message, path)
        if code in ("exists", errno.EEXIST, "EEXIST"):raise FileExistsError(errno.EEXIST, message, path)
        if isinstance(code, int) and not isinstance(code, bool):raise OSError(code, message, path)
        raise OSError(errno.EIO, message, path)
    def _vfs_ok(self, meta, payload=b"", timeout=60, path=None):
        response = self._vfs_request(meta, payload, timeout)
        if response.get("status") != "ok":self._raise_vfs_response(response, path)
        return response
    def stat(self, key):
        response = self._vfs_request({"cmd":"vfs_stat", "path":key}, timeout=30)
        if response.get("status") != "ok":self._raise_vfs_response(response, key)
        try:return mount_backend.BackingStat(is_directory=bool(response["is_directory"]),size=int(response["size"]),creation_time=float(response["creation_time"]),access_time=float(response["access_time"]),modified_time=float(response["modified_time"]),)
        except (KeyError, TypeError, ValueError) as exc:raise OSError(f"Incomplete vfs_stat response for {key!r}") from exc
    def exists(self, key):
        try:
            self.stat(key)
            return True
        except FileNotFoundError:return False
    def lexists(self, relative_path):return self.exists(relative_path)
    def is_dir(self, key):return self.stat(key).is_directory
    def get_size(self, key):return self.stat(key).size
    def listdir(self, rel_path):
        response = self._vfs_ok({"cmd":"vfs_list", "path":rel_path}, timeout=60, path=rel_path)
        return [item["name"] for item in response.get("items", [])]
    def open_read(self, relative_path):
        st = self.stat(relative_path)
        if st.is_directory:raise IsADirectoryError(relative_path)
        return RemoteReader(self, relative_path, st.size)
    def get_posix_metadata(self, relative_path):
        response = self._vfs_request({"cmd":"vfs_posix_metadata", "path":relative_path}, timeout=30)
        if response.get("status") != "ok":self._raise_vfs_response(response, relative_path)
        return {key:value for key, value in response.items() if key.startswith("st_")}
    def set_metadata(self, *args, **kwargs):return True
    def statfs(self, relative_path=""):
        response = self._vfs_request({"cmd":"vfs_statfs", "path":relative_path}, timeout=30)
        if response.get("status") != "ok":self._raise_vfs_response(response, relative_path)
        return {key:value for key, value in response.items() if key.startswith("f_")}
    def make_directory(self, relative_path):
        if self.callbacks["mkdir"]:self.callbacks["mkdir"](relative_path)
        self._vfs_ok({"cmd":"vfs_mkdir", "path":relative_path},timeout=30,path=relative_path,)
    def delete(self, relative_path, is_directory):
        if self.callbacks["delete"]:self.callbacks["delete"](relative_path)
        self._vfs_ok({"cmd":"vfs_delete","path":relative_path,"is_directory":bool(is_directory),}, timeout=30, path=relative_path)
    def move(self, source_relative_path, destination_relative_path):
        response = self._vfs_request({"cmd":"vfs_move","src_path":source_relative_path,"dst_path":destination_relative_path,}, timeout=60)
        if response.get("status") != "ok":self._raise_vfs_response(response, source_relative_path)
    @staticmethod
    def _hash_hex(path):
        hasher = blake3.blake3()
        with open(path, "rb") as stream:
            for block in iter(lambda:stream.read(4 * 1024 * 1024), b""):hasher.update(block)
        return hasher.digest(64).hex()
    def _transactional_write(self, source_path, relative_path, expected_version=None):
        size = os.path.getsize(source_path)
        target_hash_hex = self._hash_hex(source_path)
        begin_meta = {"cmd":"vfs_begin_upload","path":relative_path,"size":size,"target_hash_hex":target_hash_hex,}
        if expected_version is not None:begin_meta["expected_version"] = expected_version
        begin = self._vfs_request(begin_meta, timeout=60)
        if begin.get("status") == "conflict" or begin.get("code") == "version_mismatch":return False
        if begin.get("status") != "ok":self._raise_vfs_response(begin, relative_path)
        upload_id = begin.get("upload_id")
        if not isinstance(upload_id, str) or not upload_id:raise OSError("Server did not return an upload ID")
        completed = False
        try:
            offset = 0
            with open(source_path, "rb") as stream:
                while True:
                    chunk = stream.read(CHUNK_SIZE)
                    if not chunk:break
                    if self.callbacks["write"]:self.callbacks["write"](relative_path, chunk)
                    self._vfs_ok({"cmd":"vfs_upload_chunk","upload_id":upload_id,"offset":offset,}, payload=chunk, timeout=60, path=relative_path)
                    offset += len(chunk)
            if size == 0 and self.callbacks["write"]:self.callbacks["write"](relative_path, b"")
            commit = self._vfs_request({"cmd":"vfs_commit_upload","upload_id":upload_id,}, timeout=120)
            if commit.get("status") == "conflict" or commit.get("code") == "version_mismatch":
                completed = True
                return False
            if commit.get("status") != "ok":self._raise_vfs_response(commit, relative_path)
            if commit.get("hash") != target_hash_hex:raise OSError("Server committed a different file hash")
            if int(commit.get("size", -1)) != size:raise OSError("Server committed an unexpected file size")
            completed = True
            return True
        finally:
            if not completed:
                try:self._vfs_request({"cmd":"vfs_abort_upload","upload_id":upload_id,}, timeout=15)
                except Exception:pass
    def write_file_from_local(self, source_path, relative_path):
        if not self._transactional_write(source_path, relative_path):
            raise BlockingIOError(errno.EBUSY,"Backing file changed while uploading",relative_path,)
    def write_file_from_local_if_unchanged(self, source_path, relative_path, expected_version):return self._transactional_write(source_path, relative_path, expected_version=expected_version)
def auth_key_password_callback():return getpass.getpass('Auth Key Password:')
if __name__ == "__main__":
    key_path = sys.argv[1] if len(sys.argv) > 1 else "./auth_key"
    TPM=False
    try:import TPM_client;TPM=True
    except:pass
    password=None
    ip = ''
    if TPM:
        try:
            c=TPM_client.TPMClient()
            password=c.get_bytes('SFTP client password')['value'].decode("ascii")
        except ConnectionError:print('Failed to connect to TPM server. Is TPM.exe running?')
        except:pass
    if TPM:
        try:ip = c.get_bytes("SFTP client host IP")["value"].decode("ascii")
        except:ip = ""
    ip = get_optional_input(f"Host IP [{ip}]:").strip() or ip
    if not ip:raise RuntimeError("Host IP required")
    retry=True
    retrys=10
    while retry and retrys>0:
        retrys-=1
        retry=False
        if password==None:password = getpass.getpass("Client password:")
        storage_class = RemoteStorage if PLATFORM == "windows" else LinuxRemoteStorage
        try:storage = storage_class(host=ip,key_path=key_path,password=password,auth_key_password_callback=auth_key_password_callback)
        except OSError:password=None;retry=True
    if retrys==0 and retry:raise RuntimeError('Setup Error')
    if TPM:
        try:c.create_bytes('SFTP client password',password.encode('ascii'))
        except:pass
        try:c.create_bytes("SFTP client host IP", ip.encode("ascii"))
        except:pass
    storage.on("write",lambda key, data:print(f"[WRITE] {key} ({len(data)} bytes) {time.time()}"),)
    storage.on("read",lambda key:print(f"[READ] {key}"),)
    storage.on("delete",lambda key:print(f"[DELETE] {key}"),)
    mount_point = os.path.expanduser("~/mount")
    os.makedirs(mount_point, exist_ok=True)
    if PLATFORM == "windows":
        print(f"[*] Starting WinFUSE at {mount_point}...")
        try:mount_backend.main(storage, mount_point)
        except KeyboardInterrupt:print("\n[*] WinFUSE stopped.")
    else:
        print(f"[*] Mounting FUSE at {mount_point}...")
        try:mount_backend.main(storage, mount_point)
        except KeyboardInterrupt:print("\n[*] FUSE stopped.")
        except Exception as e:print(f"[!] FUSE mount error:{e}")
