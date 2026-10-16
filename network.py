import os, hmac, zipfile, threading, traceback, base64, io, pyotp, backend, Encryption, util, subprocess, time
from zxcvbn import zxcvbn
try:Encryption.decryptGCM(b"X" * 100, b"X" * 100)
except Exception as e:DecryptionError = type(e)
SALT_SIZE = 64
STD_TIMEOUT = 5.0
MAX_TIMEOUT = 60
EID_SIZE = 8
class ProtocolError(Exception):pass
def _new_eid():return os.urandom(EID_SIZE)
def _derive_at_rest_key(password, salt_or_path):
    if not password:raise ValueError("Password cannot be empty.")
    result = zxcvbn(password)
    guesses_log10 = result.get("guesses_log10", 0)
    if guesses_log10 <= 9:raise ValueError(f"Password too weak (log10 guesses:{guesses_log10:.2f}). Must be > 8.")
    if isinstance(salt_or_path, bytes):
        salt = salt_or_path
        if len(salt) != SALT_SIZE:raise ValueError(f"Salt must be exactly {SALT_SIZE} bytes.")
    else:
        salt_file = os.fspath(salt_or_path)
        if os.path.exists(salt_file):
            with open(salt_file, "rb") as f:salt = f.read()
            if len(salt) != SALT_SIZE:raise ValueError(f"Salt file must contain exactly {SALT_SIZE} bytes.")
        else:
            salt = os.urandom(SALT_SIZE)
            with open(salt_file, "wb") as f:f.write(salt)
    return Encryption.kdf_slow(password.encode("utf-8"), salt)
def validate_auth_keys(directory, at_rest_key):
    os.makedirs(directory, exist_ok=True)
    for filename in os.listdir(directory):
        path = os.path.join(directory, filename)
        if (os.path.isfile(path) and not filename.endswith((".prv", ".pub"))):os.remove(path)
    stems = {os.path.splitext(filename)[0] for filename in os.listdir(directory) if filename.endswith((".prv", ".pub"))}
    pairs = []
    for stem in stems:
        prv = os.path.join(directory, stem + ".prv")
        pub = os.path.join(directory, stem + ".pub")
        if os.path.isfile(prv) and os.path.isfile(pub):
            try:
                with open(prv, "rb") as f:p_bytes = Encryption.decryptGCM(f.read(), at_rest_key)
                with open(pub, "rb") as f:b_bytes = Encryption.decryptGCM(f.read(), at_rest_key)
                init_key = Encryption.gen_x25519(True)
                if Encryption.shared_secret(init_key[0], b_bytes) == Encryption.shared_secret(p_bytes, init_key[1]):
                    pairs.append((prv, pub))
                    continue
            except DecryptionError:raise
            except Exception:pass
        for path in (prv, pub):
            if os.path.exists(path):os.remove(path)
    return pairs
class TCPServer:
    def __init__(self, host, port, password, newTOTP=False, enable_bootstrap=False, auth_key_dir="./keys", on_exchange=None, simult_handshakes=4, simult_exchanges=4):
        self.auth_key_dir = auth_key_dir
        self.on_exchange = on_exchange
        self.newTOTP = newTOTP
        self.last_bootstrap=0
        self.enable_bootstrap = enable_bootstrap
        self.admin_ed = None
        self.at_rest_key = _derive_at_rest_key(password, "./server_salt.bin")
        validate_auth_keys(self.auth_key_dir, self.at_rest_key)
        totp_path = "./TOTP.bin"
        if self.newTOTP or not os.path.exists(totp_path):
            totp_secret_bytes = os.urandom(20)
            base32_secret = base64.b32encode(totp_secret_bytes).decode("utf-8")
            encrypted_totp = Encryption.encryptGCM(totp_secret_bytes, self.at_rest_key)
            with open(totp_path, "wb") as f:f.write(encrypted_totp)
            print(f"--- NEW TOTP SECRET (Base32): {base32_secret} ---")
            print("Console will be cleared in 30 seconds for security.")
            def clear_console():
                try:subprocess.run('cls' if os.name == 'nt' else 'clear',shell=True)
                except Exception:pass
            threading.Timer(30.0, clear_console).start()
        else:
            with open(totp_path, "rb") as f:totp_secret_bytes = Encryption.decryptGCM(f.read(), self.at_rest_key)
            base32_secret = base64.b32encode(totp_secret_bytes).decode("utf-8")
        self.totp = pyotp.TOTP(base32_secret)
        self._lock = threading.RLock()
        self._backend = backend.Server(host, port, handshake_worker=self._hs_worker, on_exchange=self._backend_on_exchange, simult_handshakes=simult_handshakes, simult_exchanges=simult_exchanges)
        self._keys = {}
        self._counters = {}
        self._backend.start()
    def start(self):self._backend.start()
    def _send_handshake(self, temp_cid, data):self._backend.send_handshake(temp_cid, data)
    def _recv_handshake(self, temp_cid, timeout=STD_TIMEOUT):return self._backend.recv_handshake(temp_cid, timeout=timeout)
    def _hs_worker(self, temp_cid):
        is_bootstrap = False
        try:
            client_temp_pub = self._recv_handshake(temp_cid, timeout=STD_TIMEOUT)
            if client_temp_pub is None:raise ProtocolError("Handshake timed out")
            if client_temp_pub.startswith(b"REQ_KEY"):
                if not self.enable_bootstrap:raise ProtocolError("Bootstrap authentication is disabled")
                if time.time()-self.last_bootstrap<45:raise ProtocolError("Bootstrap authentication is on cooldown")
                is_bootstrap = True
                client_init_pub = client_temp_pub[7:]
            else:client_init_pub = client_temp_pub
            init_key = Encryption.gen_x25519(True)
            tss = Encryption.shared_secret(init_key[0], client_init_pub)
            if is_bootstrap:
                nonce = os.urandom(32)
                self._send_handshake(temp_cid, init_key[1] + nonce)
                encrypted_totp = self._recv_handshake(temp_cid, timeout=4 * STD_TIMEOUT)
                if encrypted_totp is None:raise ProtocolError("Timed out waiting for TOTP code")
                hashed_totp = Encryption.decryptGCM(encrypted_totp, tss)
                current_time = time.time()
                totp_code = None
                for offset in range(-1, 2):
                    candidate = self.totp.at(current_time + offset * 30)
                    candidate_hash = Encryption.basic_kdf(util.str_to_bytes(candidate), b"")
                    if hmac.compare_digest(candidate_hash, hashed_totp):
                        totp_code = candidate
                        break
                if totp_code is None:raise ProtocolError("Invalid TOTP code")
                self.last_bootstrap=time.time()
                self.admin_ed = Encryption.gen_ed25519(True)
                salt = os.urandom(SALT_SIZE)
                key = Encryption.kdf(util.str_to_bytes(totp_code), salt, 5)
                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w") as zf:
                    zf.writestr("admin.prv", Encryption.encryptGCM(self.admin_ed[0], key))
                    zf.writestr("admin.pub", Encryption.encryptGCM(self.admin_ed[1], key))
                    zf.writestr("salt.bin", salt)
                admin_zip_bytes = zip_buffer.getvalue()
                self._send_handshake(temp_cid, Encryption.encryptGCM(admin_zip_bytes, tss))
                admin_proof = self._recv_handshake(temp_cid, timeout=2 * STD_TIMEOUT)
                if admin_proof is None:raise ProtocolError("Timed out waiting for admin proof")
                verified = Encryption.ed25519_verify(self.admin_ed[1], admin_proof)
                if Encryption.decryptGCM(verified, tss) != nonce:raise ProtocolError("Bad Admin Sig")
                prv_b, pub_b = Encryption.gen_x25519(True)
                self._send_handshake(temp_cid, Encryption.ed25519_sign(self.admin_ed[0], Encryption.encryptGCM(pub_b, tss)))
                key_ack = self._recv_handshake(temp_cid, timeout=STD_TIMEOUT)
                if key_ack is None:raise ProtocolError("Timed out waiting for auth-key ACK")
                key_ack = Encryption.decryptGCM(Encryption.ed25519_verify(self.admin_ed[1], key_ack), tss)
                if key_ack == b"0":raise ProtocolError("Client rejected auth key")
                if key_ack != b"1":raise ProtocolError("Invalid auth key ACK")
                fid = os.urandom(64).hex()
                prv = os.path.join(self.auth_key_dir, fid + ".prv")
                pub = os.path.join(self.auth_key_dir, fid + ".pub")
                with open(prv, "wb") as f:f.write(Encryption.encryptGCM(prv_b, self.at_rest_key))
                with open(pub, "wb") as f:f.write(Encryption.encryptGCM(pub_b, self.at_rest_key))
            else:self._send_handshake(temp_cid, init_key[1])
            encrypted_hash = self._recv_handshake(temp_cid, timeout=2 * STD_TIMEOUT)
            if encrypted_hash is None:raise ProtocolError("Timed out waiting for auth identity")
            _hash = Encryption.decryptGCM(encrypted_hash, tss)
            auth_file = ""
            for filename in os.listdir(self.auth_key_dir):
                if not filename.endswith(".pub"):continue
                auth_path = os.path.join(self.auth_key_dir, filename)
                with open(auth_path, "rb") as f:encrypted_pub = f.read()
                pub_key = Encryption.decryptGCM(encrypted_pub, self.at_rest_key)
                if hmac.compare_digest(_hash, Encryption.basic_kdf(pub_key, b"", 6)):
                    auth_file = auth_path
                    break
            if not auth_file:raise ProtocolError("Auth Denied")
            with open(auth_file[:-4] + ".prv", "rb") as f:raw_prv = Encryption.decryptGCM(f.read(), self.at_rest_key)
            encrypted_client_key = self._recv_handshake(temp_cid, timeout=STD_TIMEOUT)
            if encrypted_client_key is None:raise ProtocolError("Timed out waiting for client key")
            ekey = Encryption.kdf_fast(Encryption.shared_secret(raw_prv, Encryption.decryptGCM(encrypted_client_key, tss)), tss)
            sc, rc = 1, 0
            def send_enc(data):
                nonlocal sc
                ctr = sc.to_bytes(8, "big")
                sc += 1
                self._send_handshake(temp_cid, ctr + Encryption.encryptGCM(data, ekey, aad=ctr + b"1"))
            def recv_enc():
                nonlocal rc
                payload = self._recv_handshake(temp_cid, timeout=STD_TIMEOUT)
                if payload is None:raise ProtocolError("Timed out waiting for encrypted handshake")
                ctr = payload[:8]
                counter = int.from_bytes(ctr, "big")
                if counter <= rc:raise ProtocolError("Counter Error")
                rc = counter
                return Encryption.decryptGCM(payload[8:], ekey, aad=ctr + b"0")
            auth_test_key = Encryption.gen_ed25519(True)
            send_enc(auth_test_key[1])
            pub = recv_enc()
            def send_signed_enc(data):
                nonlocal sc
                ctr = sc.to_bytes(8, "big")
                sc += 1
                encrypted = Encryption.encryptGCM(data, ekey, aad=ctr + b"1")
                self._send_handshake(temp_cid, ctr + Encryption.ed25519_sign(auth_test_key[0], encrypted))
            def recv_signed_enc():
                nonlocal rc
                payload = self._recv_handshake(temp_cid, timeout=STD_TIMEOUT)
                if payload is None:raise ProtocolError("Timed out waiting for signed handshake")
                ctr = payload[:8]
                counter = int.from_bytes(ctr, "big")
                if counter <= rc:raise ProtocolError("Counter Error")
                rc = counter
                encrypted = Encryption.ed25519_verify(pub, payload[8:])
                return Encryption.decryptGCM(encrypted, ekey, aad=ctr + b"0")
            nonce = os.urandom(256)
            send_enc(nonce)
            if recv_signed_enc() != nonce:raise ProtocolError("Bad Sig")
            client_nonce = recv_enc()
            send_signed_enc(client_nonce)
            with self._lock:
                self._keys[_hash] = ekey
                self._counters[_hash] = [sc, rc]
                self._backend.auth_finished(temp_cid, _hash)
        except Exception as exc:traceback.print_exception(exc)
    def _backend_on_exchange(self, cid, eid):
        try:
            data = self.recv(cid, eid=eid, timeout=STD_TIMEOUT)
            if data is None:return
            if self.on_exchange is not None:self.on_exchange(self, eid, data, cid)
        except Exception:traceback.print_exc()
    def send(self, payload, eid=None, client_id=None):
        if eid is not None and (not isinstance(eid, bytes) or len(eid) != EID_SIZE):raise ValueError("eid must be exactly 8 bytes")
        with self._lock:
            if client_id is None:raise ValueError("client_id is required when starting a server exchange")
            if client_id not in self._keys:raise ProtocolError("Client is not authenticated")
            ekey = self._keys[client_id]
            sc, rc = self._counters[client_id]
            self._counters[client_id][0] += 1
        if eid is None:eid = _new_eid()
        ctr = sc.to_bytes(8, "big")
        encrypted = ctr + Encryption.encryptGCM(payload, ekey, aad=eid + ctr + b"1")
        return self._backend.send(encrypted, client_id, eid=eid)
    def recv(self, client_id, eid, timeout=MAX_TIMEOUT):
        if not isinstance(eid, bytes) or len(eid) != EID_SIZE:raise ValueError("eid must be exactly 8 bytes")
        with self._lock:
            if client_id not in self._keys:raise ProtocolError("Client is not authenticated")
            ekey = self._keys[client_id]
        raw = self._backend.recv(client_id, eid=eid, timeout=min(timeout, MAX_TIMEOUT))
        if raw is None:return None
        ctr = raw[:8]
        counter = int.from_bytes(ctr, "big")
        with self._lock:
            sc, rc = self._counters[client_id]
            if counter <= rc:raise ProtocolError("Counter Error")
            self._counters[client_id][1] = counter
        return Encryption.decryptGCM(raw[8:], ekey, aad=eid + ctr + b"0")
    def close_client(self, client_id):
        try:self._backend.close_client(client_id)
        finally:
            with self._lock:
                self._keys.pop(client_id, None)
                self._counters.pop(client_id, None)
    def set_backpressure(self, client_id, enabled=True):self._backend.set_backpressure(client_id, enabled)
    def close(self):
        self._backend.stop()
        with self._lock:
            self._keys.clear()
            self._counters.clear()
class TCPClient:
    def __init__(self, host, port, password, auth_key="./auth_key", auth_key_code_callback=None, on_exchange=None, simult_exchanges=4):
        self.on_exchange = on_exchange
        self._lock = threading.RLock()
        self.sc = 1
        self.rc = 0
        self.ekey = None
        self.at_rest_key = None
        self._backend = backend.Client(host, port, on_exchange=self._backend_on_exchange, simult_exchanges=simult_exchanges)
        try:self._authenticate(password, auth_key, auth_key_code_callback)
        except Exception:
            self.close()
            raise
    def _send_handshake(self, payload):self._backend.send_handshake(payload)
    def _recv_handshake(self, timeout=STD_TIMEOUT):return self._backend.recv_handshake(timeout=timeout)
    def _authenticate(self, password, auth_key, auth_key_code_callback):
        is_bootstrap = not os.path.exists(auth_key)
        init_key = Encryption.gen_x25519(True)
        if is_bootstrap:
            if auth_key_code_callback is None:raise ValueError("auth_key_code_callback is required for bootstrap")
            self._send_handshake(b"REQ_KEY" + init_key[1])
            response = self._recv_handshake(timeout=STD_TIMEOUT)
            if response is None:raise ProtocolError("Handshake timed out")
            server_init_pub = response[:len(init_key[1])]
            nonce = response[len(init_key[1]):]
            tss = Encryption.shared_secret(init_key[0], server_init_pub)
            totp_code = auth_key_code_callback()
            self._send_handshake(Encryption.encryptGCM(Encryption.basic_kdf(totp_code.encode("utf-8"),b''), tss))
            encrypted_admin_zip = self._recv_handshake(timeout=2 * STD_TIMEOUT)
            if encrypted_admin_zip is None:raise ProtocolError("Timed out waiting for admin zip")
            admin_zip_bytes = Encryption.decryptGCM(encrypted_admin_zip, tss)
            with zipfile.ZipFile(io.BytesIO(admin_zip_bytes), "r") as zf:
                for filename in ("admin.prv", "admin.pub", "salt.bin"):
                    if zf.getinfo(filename).file_size > 1024 * 1024:raise MemoryError(f"File {filename} exceeds safety limits.")
                admin_prv_enc = zf.read("admin.prv")
                admin_pub_enc = zf.read("admin.pub")
                salt = zf.read("salt.bin")
            key = Encryption.kdf(util.str_to_bytes(totp_code), salt, 5)
            admin_prv = Encryption.decryptGCM(admin_prv_enc, key)
            admin_pub = Encryption.decryptGCM(admin_pub_enc, key)
            self._send_handshake(Encryption.ed25519_sign(admin_prv, Encryption.encryptGCM(nonce, tss)))
            signed_auth_pub = self._recv_handshake(timeout=STD_TIMEOUT)
            if signed_auth_pub is None:raise ProtocolError("Handshake timed out")
            auth_pub = Encryption.decryptGCM(Encryption.ed25519_verify(admin_pub, signed_auth_pub), tss)
            if not auth_pub:
                signed_nack = Encryption.ed25519_sign(admin_prv, Encryption.encryptGCM(b"0", tss))
                self._send_handshake(signed_nack)
                raise ProtocolError("Invalid Server Auth Key")
            signed_ack = Encryption.ed25519_sign(admin_prv, Encryption.encryptGCM(b"1", tss))
            self._send_handshake(signed_ack)
            salt_rest = os.urandom(SALT_SIZE)
            self.at_rest_key = _derive_at_rest_key(password, salt_rest)
            with open(auth_key, "wb") as f:
                f.write(salt_rest)
                f.write(Encryption.encryptGCM(auth_pub, self.at_rest_key))
            pub_key = auth_pub
        else:
            self._send_handshake(init_key[1])
            server_init_pub = self._recv_handshake(timeout=STD_TIMEOUT)
            if server_init_pub is None:raise ProtocolError("Handshake timed out")
            tss = Encryption.shared_secret(init_key[0], server_init_pub)
            with open(auth_key, "rb") as f:
                salt = f.read(SALT_SIZE)
                encrypted_pub = f.read()
            if len(salt) != SALT_SIZE:raise ProtocolError("Invalid auth_key: missing salt")
            if not encrypted_pub:raise ProtocolError("Invalid auth_key: missing key data")
            self.at_rest_key = _derive_at_rest_key(password, salt)
            pub_key = Encryption.decryptGCM(encrypted_pub, self.at_rest_key)
        self._send_handshake(Encryption.encryptGCM(Encryption.basic_kdf(pub_key, b"", 6), tss))
        keys = Encryption.gen_x25519(True)
        self._send_handshake(Encryption.encryptGCM(keys[1], tss))
        self.ekey = Encryption.kdf_fast(Encryption.shared_secret(keys[0], pub_key), tss)
        def _send_enc(payload):
            ctr = self.sc.to_bytes(8, "big")
            self.sc += 1
            self._send_handshake(ctr + Encryption.encryptGCM(payload, self.ekey, aad=ctr + b"0"))
        def _recv_enc(raw_payload):
            ctr = raw_payload[:8]
            counter = int.from_bytes(ctr, "big")
            if counter <= self.rc:raise ProtocolError("Counter Error")
            self.rc = counter
            return Encryption.decryptGCM(raw_payload[8:], self.ekey, aad=ctr + b"1")
        auth_test_key = Encryption.gen_ed25519(True)
        raw = self._recv_handshake(timeout=STD_TIMEOUT)
        if raw is None:raise ProtocolError("Handshake timed out")
        pub = _recv_enc(raw)
        _send_enc(auth_test_key[1])
        def send_signed_enc(data):
            ctr = self.sc.to_bytes(8, "big")
            self.sc += 1
            encrypted = Encryption.encryptGCM(data, self.ekey, aad=ctr + b"0")
            self._send_handshake(ctr + Encryption.ed25519_sign(auth_test_key[0], encrypted))
        def recv_signed_enc():
            payload = self._recv_handshake(timeout=STD_TIMEOUT)
            if payload is None:raise ProtocolError("Handshake timed out")
            ctr = payload[:8]
            counter = int.from_bytes(ctr, "big")
            if counter <= self.rc:raise ProtocolError("Counter Error")
            self.rc = counter
            encrypted = Encryption.ed25519_verify(pub, payload[8:])
            return Encryption.decryptGCM(encrypted, self.ekey, aad=ctr + b"1")
        raw = self._recv_handshake(timeout=STD_TIMEOUT)
        if raw is None:raise ProtocolError("Handshake timed out")
        nonce = _recv_enc(raw)
        send_signed_enc(nonce)
        client_nonce = os.urandom(256)
        _send_enc(client_nonce)
        if recv_signed_enc() != client_nonce:raise ProtocolError("Bad Sig")
        self._backend.auth_finished()
    def send(self, payload, eid=None):
        if eid is not None and (not isinstance(eid, bytes) or len(eid) != EID_SIZE):raise ValueError("eid must be exactly 8 bytes")
        with self._lock:
            if self.ekey is None:raise ProtocolError("Client is not authenticated")
            if eid is None:eid = _new_eid()
            ctr = self.sc.to_bytes(8, "big")
            encrypted = ctr + Encryption.encryptGCM(payload, self.ekey, aad=eid + ctr + b"0")
            self.sc += 1
            return self._backend.send(encrypted, eid=eid)
    def recv(self, eid, timeout=MAX_TIMEOUT):
        if not isinstance(eid, bytes) or len(eid) != EID_SIZE:raise ValueError("eid must be exactly 8 bytes")
        with self._lock:
            if self.ekey is None:raise ProtocolError("Client is not authenticated")
            ekey = self.ekey
        effective_timeout = None if timeout is None else min(timeout, MAX_TIMEOUT)
        raw = self._backend.recv(eid, timeout=effective_timeout)
        if raw is None:return None
        if len(raw) < 8:raise ProtocolError("Invalid encrypted response: missing counter")
        ctr = raw[:8]
        counter = int.from_bytes(ctr, "big")
        with self._lock:
            if counter <= self.rc:raise ProtocolError("Counter Error")
            self.rc = counter
        return Encryption.decryptGCM(raw[8:], ekey, aad=eid + ctr + b"1")
    def _backend_on_exchange(self, eid):
        try:
            data = self.recv(eid, timeout=STD_TIMEOUT)
            if data is None:return
            if self.on_exchange is not None:self.on_exchange(self, eid, data)
        except Exception:traceback.print_exc()
    def set_backpressure(self, enabled=True):self._backend.set_backpressure(enabled)
    def close(self):
        backend_client = getattr(self, "_backend", None)
        try:
            if backend_client is not None:backend_client.close()
        finally:
            lock = getattr(self, "_lock", None)
            if lock is not None:
                with lock:
                    self.ekey = None
                    self.at_rest_key = None
                    self.sc = 1
                    self.rc = 0
