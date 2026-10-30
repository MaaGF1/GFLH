# tools/crypto_box.py
#
# Dependency-free encrypted containers (standard library only).
#
# Construction (encrypt-then-MAC):
#   key   = PBKDF2-HMAC-SHA256(passphrase, salt, 600000 iterations)
#   ek/mk = HKDF-Expand(key, info="enc"/"mac")
#   ks    = HMAC-SHA256(ek, nonce || counter_be32) concatenated  # used as keystream
#   ct    = plaintext XOR ks
#   tag   = HMAC-SHA256(mk, header || salt || nonce || ct)[:16]
#
# This is not a replacement for a general-purpose crypto library. It exists for one
# purpose only: to move the "recipe" out of static source. The goal is to raise the bar
# to "you must dump memory at runtime", not to resist cryptanalysis.

import hashlib
import hmac
import os
import struct

MAGIC = b"GFLM1"          # passphrase container
MAGIC_FP = b"GFLM2"       # module-fingerprint container (no passphrase prompt)
SALT_LEN = 16
NONCE_LEN = 16
TAG_LEN = 16
ITERS = 600000


def _hkdf_expand(key, info, length=32):
    out, prev, i = b"", b"", 1
    while len(out) < length:
        prev = hmac.new(key, prev + info + bytes([i]), hashlib.sha256).digest()
        out += prev
        i += 1
    return out[:length]


def _keys(password, salt):
    base = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERS, dklen=32)
    return _hkdf_expand(base, b"enc"), _hkdf_expand(base, b"mac")


def _keystream(ek, nonce, length):
    out, counter = bytearray(), 0
    while len(out) < length:
        out += hmac.new(ek, nonce + struct.pack(">I", counter), hashlib.sha256).digest()
        counter += 1
    return bytes(out[:length])


def seal(plaintext: bytes, password: str) -> bytes:
    salt = os.urandom(SALT_LEN)
    nonce = os.urandom(NONCE_LEN)
    ek, mk = _keys(password, salt)
    ks = _keystream(ek, nonce, len(plaintext))
    ct = bytes(a ^ b for a, b in zip(plaintext, ks))
    tag = hmac.new(mk, MAGIC + salt + nonce + ct, hashlib.sha256).digest()[:TAG_LEN]
    return MAGIC + salt + nonce + ct + tag


def open_sealed(blob: bytes, password: str) -> bytes:
    if len(blob) < len(MAGIC) + SALT_LEN + NONCE_LEN + TAG_LEN:
        raise ValueError("container is too short")
    if blob[:len(MAGIC)] != MAGIC:
        raise ValueError("not a passphrase container")
    off = len(MAGIC)
    salt = blob[off:off + SALT_LEN]; off += SALT_LEN
    nonce = blob[off:off + NONCE_LEN]; off += NONCE_LEN
    ct = blob[off:-TAG_LEN]
    tag = blob[-TAG_LEN:]

    ek, mk = _keys(password, salt)
    expect = hmac.new(mk, MAGIC + salt + nonce + ct, hashlib.sha256).digest()[:TAG_LEN]
    if not hmac.compare_digest(tag, expect):
        raise ValueError("wrong passphrase, or the file has been modified")

    ks = _keystream(ek, nonce, len(ct))
    return bytes(a ^ b for a, b in zip(ct, ks))


# ---------------------------------------------------------------- fingerprint container
#
# Used by "no passphrase" mode: the key does not come from a passphrase but from the
# target module's PE fingerprint (DOS header 0x40 bytes + COFF header 20 bytes). Those
# two regions are identical in the file on disk and in the mapped image, so the build
# machine can read the file while the runtime reads memory and still derive the same key.
# The package therefore contains no key bytes; decrypting requires the matching game build.

def derive_key(seed: bytes) -> bytes:
    return hashlib.sha256(b"GFLM-fp-v1" + seed).digest()


def _fp_mats(key):
    return _hkdf_expand(key, b"enc"), _hkdf_expand(key, b"mac")


def seal_keyed(plaintext: bytes, key: bytes) -> bytes:
    nonce = os.urandom(NONCE_LEN)
    ek, mk = _fp_mats(key)
    ks = _keystream(ek, nonce, len(plaintext))
    ct = bytes(a ^ b for a, b in zip(plaintext, ks))
    tag = hmac.new(mk, MAGIC_FP + nonce + ct, hashlib.sha256).digest()[:TAG_LEN]
    return MAGIC_FP + nonce + ct + tag


def open_keyed(blob: bytes, key: bytes) -> bytes:
    if len(blob) < len(MAGIC_FP) + NONCE_LEN + TAG_LEN:
        raise ValueError("container is too short")
    if blob[:len(MAGIC_FP)] != MAGIC_FP:
        raise ValueError("not a fingerprint container")
    off = len(MAGIC_FP)
    nonce = blob[off:off + NONCE_LEN]; off += NONCE_LEN
    ct = blob[off:-TAG_LEN]
    tag = blob[-TAG_LEN:]

    ek, mk = _fp_mats(key)
    expect = hmac.new(mk, MAGIC_FP + nonce + ct, hashlib.sha256).digest()[:TAG_LEN]
    if not hmac.compare_digest(tag, expect):
        raise ValueError("fingerprint mismatch (different game build), or the file has been modified")

    ks = _keystream(ek, nonce, len(ct))
    return bytes(a ^ b for a, b in zip(ct, ks))


def pe_fingerprint(data: bytes) -> bytes:
    """DOS header + COFF header: identical in file and memory, and carries TimeDateStamp."""
    if len(data) < 0x40:
        raise ValueError("PE data is too short")
    e = int.from_bytes(data[0x3C:0x40], "little")
    if e <= 0 or e + 24 > len(data):
        raise ValueError("illegal PE header offset")
    return bytes(data[0:0x40]) + bytes(data[e + 4:e + 24])


def pe_fingerprint_file(path: str) -> bytes:
    with open(path, "rb") as f:
        head = f.read(0x1000)
    return pe_fingerprint(head)


def pe_size_of_image_file(path: str) -> int:
    """SizeOfImage (OptionalHeader+56): equals the mapped module size, used as a second version check."""
    with open(path, "rb") as f:
        head = f.read(0x1000)
    e = int.from_bytes(head[0x3C:0x40], "little")
    return int.from_bytes(head[e + 24 + 56:e + 24 + 60], "little")
