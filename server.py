import json, os, shutil, time, network, getpass, sys, traceback, socket
SHARED_DIR = os.path.expanduser("~/Shared")
CHUNK_SIZE = 12 * 1024 * 1024
if os.name == "nt":
    import msvcrt
else:
    import select
    import termios
    import tty
def get_optional_password(text, timeout=15):
    if not sys.stdin.isatty() or not sys.stdout.isatty():return None
    if os.name == "nt":
        print(text, end="", flush=True)
        password = ""
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if msvcrt.kbhit():
                char = msvcrt.getwch()
                if char in ("\r", "\n"):
                    print()
                    return password or None
                elif char == "\x03":raise KeyboardInterrupt
                elif char == "\b":password = password[:-1]
                else:password += char
            time.sleep(0.05)
        print()
        return None
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        print(text, end="", flush=True)
        password = ""
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            remaining = timeout - (time.monotonic() - start)
            ready, _, _ = select.select([fd], [], [], remaining)
            if not ready:
                print()
                return None
            char = os.read(fd, 1).decode("utf-8", errors="ignore")
            if char in ("\r", "\n"):
                print()
                return password or None
            elif char == "\x03":raise KeyboardInterrupt
            elif char in ("\x7f", "\b"):password = password[:-1]
            else:password += char
        print()
        return None
    finally:termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
def safe_path(base_dir, req_path):
    """Ensure the requested path stays strictly inside the shared directory."""
    base = os.path.realpath(base_dir)
    target = os.path.realpath(os.path.join(base, str(req_path).lstrip("/\\")))
    try:
        if os.path.commonpath((base, target)) != base:raise PermissionError("Access denied: path outside shared directory")
    except ValueError:raise PermissionError("Access denied: path outside shared directory")
    return target
def make_packet(meta: dict, payload: bytes = b"") -> bytes:
    meta_bytes = json.dumps(meta, separators=(",", ":")).encode("utf-8")
    return len(meta_bytes).to_bytes(4, byteorder="big") + meta_bytes + payload
class FileServer:
    def __init__(self, host="127.0.0.1", port=9000, password=None, auth_key_password=None, key_dir="./keys",salt_file="./server_salt.bin"):
        if not password:raise ValueError("Server password is required.")
        self.shared_dir = SHARED_DIR
        os.makedirs(self.shared_dir, exist_ok=True)
        try:
            self.server = network.TCPServer(host=host,port=port,password=password,auth_key_password=auth_key_password,auth_key_dir=key_dir,salt_file=salt_file,on_exchange=self.handle_exchange,)
        except Exception as e:traceback.print_exception(e);raise OSError
        print(f"[*] File Server active on tcp://{host}:{port} | Serving: {self.shared_dir}")
    def handle_exchange(self, server_inst, eid, data, cid):
        try:
            if len(data) < 4:return
            header_len = int.from_bytes(data[:4], "big")
            if header_len < 2 or 4 + header_len > len(data):raise ValueError("Invalid packet header")
            meta = json.loads(data[4:4 + header_len].decode("utf-8"))
            payload = data[4 + header_len:]
            cmd = meta.get("cmd")
            if cmd == "list":
                rel_path = meta.get("path", "")
                target = safe_path(self.shared_dir, rel_path)
                if not os.path.exists(target):resp = make_packet({"status": "error","message": "Directory does not exist",})
                elif not os.path.isdir(target):resp = make_packet({"status": "error","message": "Path is not a directory",})
                else:
                    items = []
                    for entry in sorted(os.listdir(target)):
                        full = os.path.join(target, entry)
                        is_dir = os.path.isdir(full)
                        size = 0 if is_dir else os.path.getsize(full)
                        items.append({"name": entry,"is_dir": is_dir,"size": size,})
                    resp = make_packet({"status": "ok","items": items,})
                server_inst.send(resp,eid=eid,client_id=cid,)
            elif cmd == "info":
                rel_path = meta.get("path", "")
                target = safe_path(self.shared_dir, rel_path)
                if not os.path.exists(target):resp = make_packet({"status": "error","message": "Path does not exist",})
                else:
                    is_file = os.path.isfile(target)
                    size = os.path.getsize(target) if is_file else 0
                    total_chunks = ((size + CHUNK_SIZE - 1) // CHUNK_SIZE if is_file else 0)
                    resp = make_packet({"status": "ok","path": rel_path,"is_file": is_file,"size": size,"chunk_size": CHUNK_SIZE,"total_chunks": total_chunks,})
                server_inst.send(resp,eid=eid,client_id=cid,)
            elif cmd == "download_chunk":
                rel_path = meta.get("path", "")
                target = safe_path(self.shared_dir, rel_path)
                offset = meta.get("offset",meta.get("chunk_idx", 0) * CHUNK_SIZE,)
                length = meta.get("length", CHUNK_SIZE)
                if not os.path.isfile(target):resp = b"\x01File not found"
                else:
                    with open(target, "rb") as f:
                        f.seek(offset)
                        chunk = f.read(length)
                    resp = b"\x00" + chunk
                server_inst.send(resp,eid=eid,client_id=cid,)
            elif cmd == "upload_chunk":
                rel_path = meta.get("path", "")
                target = safe_path(self.shared_dir, rel_path)
                offset = meta.get("offset",meta.get("chunk_idx", 0) * CHUNK_SIZE,)
                os.makedirs(os.path.dirname(target), exist_ok=True)
                mode = "r+b" if os.path.exists(target) else "w+b"
                with open(target, mode) as f:
                    f.seek(offset)
                    f.write(payload)
                    f.flush()
                resp = make_packet({"status": "ok",})
                server_inst.send(resp,eid=eid,client_id=cid,)
            elif cmd == "move":
                src_target = safe_path(self.shared_dir,meta.get("src_path", ""),)
                dst_target = safe_path(self.shared_dir,meta.get("dst_path", ""),)
                if not os.path.exists(src_target):resp = make_packet({"status": "error","message": "Source path does not exist",})
                else:
                    os.makedirs(os.path.dirname(dst_target),exist_ok=True,)
                    shutil.move(src_target, dst_target)
                    resp = make_packet({"status": "ok",})
                server_inst.send(resp,eid=eid,client_id=cid,)
            elif cmd == "copy":
                src_target = safe_path(self.shared_dir,meta.get("src_path", ""),)
                dst_target = safe_path(self.shared_dir,meta.get("dst_path", ""),)
                if not os.path.exists(src_target):resp = make_packet({"status": "error","message": "Source path does not exist",})
                else:
                    os.makedirs(os.path.dirname(dst_target),exist_ok=True,)
                    if os.path.isdir(src_target):shutil.copytree(src_target,dst_target,dirs_exist_ok=True,)
                    else:shutil.copy2(src_target,dst_target,)
                    resp = make_packet({"status": "ok",})
                server_inst.send(resp,eid=eid,client_id=cid,)
            elif cmd == "delete":
                target = safe_path(self.shared_dir,meta.get("path", ""),)
                if not os.path.exists(target):resp = make_packet({"status": "error","message": "Path does not exist",})
                else:
                    if os.path.isdir(target):shutil.rmtree(target)
                    else:os.remove(target)
                    resp = make_packet({"status": "ok",})
                server_inst.send(resp,eid=eid,client_id=cid,)
            elif cmd == "mkdir":
                target = safe_path(self.shared_dir,meta.get("path", ""),)
                os.makedirs(target, exist_ok=True)
                resp = make_packet({"status": "ok",})
                server_inst.send(resp,eid=eid,client_id=cid,)
            else:
                resp = make_packet({"status": "error","message": f"Unknown command: {cmd!r}",})
                server_inst.send(resp,eid=eid,client_id=cid,)
        except Exception as e:
            try:
                resp = make_packet({"status": "error","message": str(e),})
                server_inst.send(resp,eid=eid,client_id=cid,)
            except Exception:pass
if __name__ == "__main__":
    IP="127.0.0.1"
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            IP = s.getsockname()[0]
    except:pass
    TPM=False
    try:import TPM_client;TPM=True
    except:pass
    password=None
    if TPM:
        try:
            c=TPM_client.TPMClient()
            password=c.get_bytes('SFTP server password')['value'].decode("ascii")
        except ConnectionError:print('Failed to connect to TPM server. Is TPM.exe running?')
        except:pass
    retry=True
    retrys=10
    while retry and retrys>0:
        retrys-=1
        retry=False
        if password == None:password = getpass.getpass("Server password: ")
        auth_key_password = get_optional_password("Auth key password: ")
        if auth_key_password==None:auth_key_password=''
        if not isinstance(password,str):raise TypeError('password must be a string')
        if not isinstance(auth_key_password,str):raise TypeError('auth_key_password must be a string')
        try:
            srv = FileServer(IP,password=password,auth_key_password=auth_key_password)
        except OSError:
            retry=True
            password=None
    if retrys==0 and retry:raise RuntimeError('Setup Error')
    if TPM:
        try:c.create_bytes('SFTP server password',password.encode('ascii'))
        except:pass
    try:
        while True:time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Shutting down...")
        srv.server.close()