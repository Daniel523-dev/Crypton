import json, os, sys, getpass, traceback, time
CHUNK_SIZE = 12 * 1024 * 1024
if sys.platform == "win32":
    import winfuse3 as mount_backend
    PLATFORM = "windows"
elif sys.platform.startswith("linux"):
    import vfs as mount_backend
    PLATFORM = "linux"
else:raise RuntimeError(f"Unsupported platform: {sys.platform}")
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
        if not os.path.exists(key_path):raise FileNotFoundError(f"Key file not found: {key_path}")
        if not password:password = getpass.getpass("Client password: ")
        import network
        try:self.client = network.TCPClient(host=host,port=port,password=password,auth_key=key_path,auth_key_password_callback=auth_key_password_callback)
        except Exception as e:traceback.print_exception(e);raise OSError
        self.lock = __import__("threading").Lock()
        self.callbacks = {"read": None, "write": None, "delete": None, "mkdir": None}
    def initialize(self):pass
    def describe(self):return "RemoteStorage"
    def on(self, event, callback):
        if event in self.callbacks:self.callbacks[event] = callback
    def _request(self, meta, timeout=10):
        with self.lock:
            eid = self.client.send(make_packet(meta))
            try:res = self.client.recv(eid, timeout)
            except Exception as e:return {"status": "error", "message": str(e)}
        if not res:return {"status": "error", "message": "Request timeout"}
        try:return parse_packet(res)[0]
        except Exception as e:return {"status": "error", "message": str(e)}
    def exists(self, key):return self._request({"cmd": "info", "path": key}).get("status") == "ok"
    def is_dir(self, key):
        key = key.strip("/")
        if not key:return True
        r = self._request({"cmd": "info", "path": key})
        return r.get("status") == "ok" and r.get("is_dir", False)
    def get_size(self, key):
        r = self._request({"cmd": "info", "path": key})
        return r.get("size", 0) if r.get("status") == "ok" else 0
    def stat(self, key):
        r = self._request({"cmd": "info", "path": key})
        if r.get("status") != "ok":raise FileNotFoundError(key)
        size, mtime = r.get("size", 0), r.get("mtime", 0)
        is_dir = r.get("is_dir", False)
        if PLATFORM == "windows":return mount_backend.BackingStat(is_directory=is_dir,size=size,creation_time=mtime,access_time=mtime,modified_time=mtime,)
        return {"size": size, "mtime": mtime}
    def rename(self, src_key, dst_key):return self._request({"cmd": "move","src_path": src_key,"dst_path": dst_key,}).get("status") == "ok"
    def copy(self, src_key, dst_key):return self._request({"cmd": "copy","src_path": src_key,"dst_path": dst_key,}).get("status") == "ok"
    def write_chunk(self, key, offset, chunk):
        if self.callbacks["write"]:self.callbacks["write"](key, chunk)
        req = make_packet({"cmd": "upload_chunk", "path": key, "offset": offset},chunk,)
        with self.lock:
            eid = self.client.send(req)
            res = self.client.recv(eid, 60)
        if not res:return False
        try:return parse_packet(res)[0].get("status") == "ok"
        except Exception:return False
    def read_chunk(self, key, offset, length=CHUNK_SIZE):
        if self.callbacks["read"]:self.callbacks["read"](key)
        req = make_packet({"cmd": "download_chunk","path": key,"offset": offset,"length": length,})
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
    def write(self, key, content):
        if not content:
            self.write_chunk(key, 0, b"")
            return
        for offset in range(0, len(content), CHUNK_SIZE):
            if not self.write_chunk(key,offset,content[offset:offset + CHUNK_SIZE],):raise IOError("Failed to upload file chunk")
    def delete(self, key, is_directory=None):
        if self.callbacks["delete"]:self.callbacks["delete"](key)
        self._request({"cmd": "delete", "path": key})
    def mkdir(self, key):
        if self.callbacks["mkdir"]:self.callbacks["mkdir"](key)
        self._request({"cmd": "mkdir", "path": key})
    def listdir(self, rel_path):
        r = self._request({"cmd": "list", "path": rel_path}, 60)
        if r.get("status") != "ok":raise OSError(r.get("message", "Directory listing failed"))
        return [x["name"] for x in r.get("items", [])]
    def list_keys(self):
        keys = []
        def walk(path):
            r = self._request({"cmd": "list", "path": path}, 60)
            if r.get("status") != "ok":return
            for item in r.get("items", []):
                p = f"{path}/{item['name']}" if path else item["name"]
                if item.get("is_dir"):walk(p)
                else:keys.append(p)
        walk("")
        return keys
    def get_hash(self, key):
        req = make_packet({"cmd": "get_hash", "path": key})
        with self.lock:
            eid = self.client.send(req)
            res = self.client.recv(eid, 60)
        if not res or res[:1] != b"\x00":return None
        return res[1:].hex()
    def open_read(self, relative_path):return RemoteReader(self, relative_path, self.get_size(relative_path))
    def write_file_from_local(self, source_path, relative_path):
        offset = 0
        with open(source_path, "rb") as f:
            while chunk := f.read(CHUNK_SIZE):
                if not self.write_chunk(relative_path, offset, chunk):raise IOError("Failed to upload file chunk")
                offset += len(chunk)
        if offset == 0:self.write_chunk(relative_path, 0, b"")
    def make_directory(self, relative_path):self.mkdir(relative_path)
    def lexists(self, relative_path):return self.exists(relative_path)
    def move(self, source_relative_path, destination_relative_path):
        if not self.rename(source_relative_path, destination_relative_path):raise OSError(f"Failed to move {source_relative_path!r} -> {destination_relative_path!r}")
def auth_key_password_callback():return getpass.getpass('Auth Key Password: ')
if __name__ == "__main__":
    key_path = sys.argv[1] if len(sys.argv) > 1 else "./auth_key"
    TPM=False
    try:import TPM_client;TPM=True
    except:pass
    password=None
    if TPM:
        try:
            c=TPM_client.TPMClient()
            password=c.get_bytes('SFTP client password')['value'].decode("ascii")
        except ConnectionError:print('Failed to connect to TPM server. Is TPM.exe running?')
        except:pass
    if TPM:
        try:ip = c.get_bytes("SFTP client host IP")["value"].decode("ascii")
        except:ip = ""
    ip = input(f"Host IP [{ip}]: ").strip() or ip
    if not ip:raise RuntimeError("Host IP required")
    retry=True
    retrys=10
    while retry and retrys>0:
        retrys-=1
        retry=False
        if password==None:password = getpass.getpass("Client password: ")
        try:storage = RemoteStorage(host=ip,key_path=key_path,password=password,auth_key_password_callback=auth_key_password_callback)
        except OSError:password=None;retry=True
    if retrys==0 and retry:raise RuntimeError('Setup Error')
    if TPM:
        try:c.create_bytes('SFTP client password',password.encode('ascii'))
        except:pass
        try: c.create_bytes("SFTP client host IP", ip.encode("ascii"))
        except: pass
    storage.on("write",lambda key, data: print(f"[WRITE] {key} ({len(data)} bytes) {time.time()}"),)
    storage.on("read",lambda key: print(f"[READ] {key}"),)
    storage.on("delete",lambda key: print(f"[DELETE] {key}"),)
    mount_point = r"C:\Users\murphy2607\mount" if PLATFORM == "windows" else "/mnt/remote-storage"
    os.makedirs(mount_point, exist_ok=True)
    if PLATFORM == "windows":
        print(f"[*] Starting WinFUSE at {mount_point}...")
        try:mount_backend.main(storage, mount_point)
        except KeyboardInterrupt:print("\n[*] WinFUSE stopped.")
    else:
        print(f"[*] Mounting FUSE at {mount_point}...")
        try:mount_backend.FUSE(mount_backend.StorageFUSE(storage),mount_point,nothreads=True,foreground=True,)
        except KeyboardInterrupt:print("\n[*] FUSE stopped.")
        except Exception as e:print(f"[!] FUSE mount error: {e}")