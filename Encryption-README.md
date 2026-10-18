# `Encryption.py` — Cryptographic Utilities

`Encryption.py` provides Python wrappers for hashing, key derivation, symmetric encryption, key agreement, digital signatures, and X.509 certificate helpers. The application networking code uses only part of this module; using a helper here does not mean the running TCP protocol uses TLS.

## Requirements

Install the Python packages:

```bash
python -m pip install cryptography argon2-cffi blake3
```

The project-local `util.py` module is also imported. `blake3` is used when installed; otherwise `HASH` falls back to SHA-3/SHAKE hashing. `basic_kdf` uses BLAKE3 when available and an HKDF-SHA-512 path when it is not, so the fallback behavior is not byte-for-byte compatible with the BLAKE3 path. Use the same environment/configuration on both sides when deriving keys.

## API overview

| Function | Purpose |
|---|---|
| `HASH(data, l=32, hex=False)` | Hash bytes and return a digest or hexadecimal text. Uses BLAKE3 when installed. |
| `basic_kdf(master, salt, length=32)` | Lightweight deterministic derivation helper. It is not a password-hardening KDF. |
| `kdf(password, salt, level=5)` | Argon2id key derivation using the configured level. |
| `kdf_fast(password, salt)` / `kdf_slow(password, salt)` | Convenience wrappers for Argon2id levels 0 and 10. |
| `encrypt(data, key)` / `decrypt(blob, key)` | AES-CTR encryption/decryption; provides no authentication by itself. |
| `encryptGCM(data, key, aad=None)` / `decryptGCM(blob, key, aad=None)` | AES-GCM authenticated encryption/decryption. AAD must match during decryption. |
| `gen_chacha20()` | Generates a 32-byte ChaCha20 key. |
| `encrypt_chacha(data, key, auth=True)` / `decrypt_chacha(blob, key, auth=True)` | ChaCha20-Poly1305 when `auth=True`; raw ChaCha20 stream encryption when `auth=False`. |
| `gen_x25519(overkill=False)` / `shared_secret(private, public)` | X25519 key generation/shared secret; `overkill=True` selects X448. |
| `gen_ed25519(overkill=False)` / `ed25519_sign(private, data)` / `ed25519_verify(public, blob)` | Ed25519 signatures; `overkill=True` selects Ed448 for key generation. |
| `generate_tls(...)` | Writes a self-signed ECDSA P-256 TLS certificate and its private key. |
| `gen_CA(...)` | Generates CA key/certificate files. Review the implementation before using it in a production PKI. |

## Hashing and key derivation

```python
import os
import Encryption as enc

payload = b"sample data"
digest_hex = enc.HASH(payload, l=32, hex=True)

salt = os.urandom(16)
# Argon2id; kdf_fast is a convenience level, not a recommendation for every use.
key = enc.kdf_fast(b"a user-supplied password", salt)
assert len(digest_hex) == 64
```

Use unique random salts for password-derived keys and store the salt with the protected ciphertext or credential material. Choose KDF cost based on the threat model and deployment performance, not the helper name alone.

## Authenticated symmetric encryption (AES-GCM)

```python
import os
import Encryption as enc

master_key = os.urandom(32)
plaintext = b"Sensitive information"
associated_data = b"record:123"

ciphertext = enc.encryptGCM(plaintext, master_key, aad=associated_data)
recovered = enc.decryptGCM(ciphertext, master_key, aad=associated_data)
assert recovered == plaintext
```

The actual function signatures are `encryptGCM(data, key, aad=None)` and `decryptGCM(encrypted, key, aad=None)`. They do **not** accept a `secure_kdf=True` parameter. Internally, the functions create a random salt and nonce, derive a subkey with `basic_kdf`, and store the nonce and salt alongside the AEAD ciphertext. The same `aad` value must be supplied when decrypting or authentication will fail.

## Key exchange

```python
import Encryption as enc

alice_private, alice_public = enc.gen_x25519()
bob_private, bob_public = enc.gen_x25519()

alice_secret = enc.shared_secret(alice_private, bob_public)
bob_secret = enc.shared_secret(bob_private, alice_public)
assert alice_secret == bob_secret
```

Set `overkill=True` to select X448 in `gen_x25519`. Keep private keys private and use each shared secret only in a protocol that has appropriate authentication and key separation.

## Digital signatures

```python
import Encryption as enc

private_key, public_key = enc.gen_ed25519()
message = b"Data to be signed"
signed_blob = enc.ed25519_sign(private_key, message)
verified_message = enc.ed25519_verify(public_key, signed_blob)
assert verified_message == message
```

The current helper serializes the signature followed by the original message. Do not parse that combined format using an assumed fixed signature length without accounting for the selected algorithm: Ed25519 uses a 64-byte signature and Ed448 uses a 114-byte signature.

## Certificate generation

```python
import Encryption as enc

enc.generate_tls(
    cert_path="cert.pem",
    key_path="key.pem",
    common_name="localhost",
    san_dns=["localhost"],
    valid_days=365,
)
```

This helper creates a self-signed certificate; clients will not automatically trust it. The key is written unencrypted, so protect the file using filesystem permissions and encrypted storage. The supplied `network.py`/`backend.cpp` transport does not use this certificate helper; generating a certificate does not turn Crypton's custom protocol into TLS.

## Security notes

- **Prefer authenticated encryption.** `encrypt()`/`decrypt()` use AES-CTR without an authentication tag. They do not detect ciphertext tampering. `encrypt_chacha(..., auth=False)` is also unauthenticated. Add an independently designed authentication scheme only if you understand the associated risks; otherwise use the AEAD functions.
- **Do not use `basic_kdf` to harden weak passwords.** Use `kdf`, `kdf_fast`, or `kdf_slow` with random salts when password-hardening is required.
- **Keep nonces and salts in their expected formats.** Do not modify the ciphertext layout or reuse nonce/key combinations with AEAD algorithms.
- **Review fallback behavior.** Installing or removing `blake3` changes `HASH` and `basic_kdf` behavior in this implementation. Do not silently mix output from different paths for stored keys or protocol values.
- **This is a utility module, not a security audit.** Review the code and have the complete protocol assessed before relying on it for high-risk data.
