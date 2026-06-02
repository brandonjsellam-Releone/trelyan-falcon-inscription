"""
falcon_det1024.py — off-chain Deterministic Falcon-1024 signer for TRELYAN inscriptions.

This produces signatures in EXACTLY the format Algorand's `falcon_verify` opcode accepts:
Deterministic Falcon-1024, COMPRESSED encoding (header byte 0xBA + 1-byte salt version).
See FALCON_ENCODING_2026-06-01.md for why generic liboqs/pqcrypto Falcon does NOT work here.

It is a thin ctypes wrapper over the `algorand/falcon` C library, exposing the three calls the
audit test needs: keygen(), sign_compressed(privkey, data), verify_compressed(sig, pubkey, data).

--------------------------------------------------------------------------------------------------
BUILD THE SHARED LIBRARY (one-time, on your machine — the sandbox VM here can't compile it):

    git clone https://github.com/algorand/falcon
    cd falcon
    # Compile ALL library .c sources into one shared object. Include every .c EXCEPT
    # test/benchmark mains (e.g. exclude test_falcon.c / speed.c / nist KAT harnesses).
    # The deterministic API lives in deterministic.c and depends on the core sources:
    cc -O3 -fPIC -shared -o libfalcondet1024.so \
        codec.c common.c falcon.c fft.c fpr.c keygen.c rng.c shake.c sign.c vrfy.c deterministic.c
    #   (file list can vary by repo revision — if the link errors on a missing symbol,
    #    add the .c that defines it; if it errors on a duplicate main(), you included a test file.)
    export FALCON_DET1024_LIB="$PWD/libfalcondet1024.so"

Then:  python falcon_det1024.py        # runs the self-test (keygen -> sign -> verify round trip)

On macOS the output is libfalcondet1024.dylib (same cc command); on Windows build a .dll and set
FALCON_DET1024_LIB to its path.
--------------------------------------------------------------------------------------------------
"""

import ctypes
import os

# ---- constants for Falcon-1024 (logn=10), from algorand/falcon falcon.h / deterministic.h ----
LOGN = 10
PUBKEY_SIZE = 1793                       # FALCON_PUBKEY_SIZE(10)  — matches contract PUBKEY_LEN
PRIVKEY_SIZE = 2305                      # FALCON_PRIVKEY_SIZE(10)
SIG_COMPRESSED_MAXSIZE = 1423            # det = FALCON_SIG_COMPRESSED_MAXSIZE(10)(=1462) - 40 + 1
DET_COMPRESSED_HEADER = 0xBA             # 0x3A | 0x80  (deterministic compressed)
CURRENT_SALT_VERSION = 0

_LIB_PATH = os.environ.get("FALCON_DET1024_LIB", "./libfalcondet1024.so")


class _Shake256Context(ctypes.Structure):
    # typedef struct { uint64_t opaque_contents[26]; } shake256_context;  (falcon.h) -> 208 bytes
    _fields_ = [("opaque_contents", ctypes.c_uint64 * 26)]


def _load():
    try:
        lib = ctypes.CDLL(_LIB_PATH)
    except OSError as e:
        raise RuntimeError(
            f"Could not load Falcon shared library at {_LIB_PATH!r}. Build it (see this file's "
            f"header) and set FALCON_DET1024_LIB to its path. Underlying error: {e}"
        )
    lib.shake256_init_prng_from_system.argtypes = [ctypes.POINTER(_Shake256Context)]
    lib.shake256_init_prng_from_system.restype = ctypes.c_int
    lib.falcon_det1024_keygen.argtypes = [ctypes.POINTER(_Shake256Context), ctypes.c_char_p, ctypes.c_char_p]
    lib.falcon_det1024_keygen.restype = ctypes.c_int
    lib.falcon_det1024_sign_compressed.argtypes = [
        ctypes.c_char_p, ctypes.POINTER(ctypes.c_size_t), ctypes.c_char_p, ctypes.c_char_p, ctypes.c_size_t,
    ]
    lib.falcon_det1024_sign_compressed.restype = ctypes.c_int
    lib.falcon_det1024_verify_compressed.argtypes = [
        ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_size_t,
    ]
    lib.falcon_det1024_verify_compressed.restype = ctypes.c_int
    return lib


_lib = None
def _libref():
    global _lib
    if _lib is None:
        _lib = _load()
    return _lib


def keygen():
    """Return (pubkey: bytes[1793], privkey: bytes[2305]) for Deterministic Falcon-1024."""
    lib = _libref()
    rng = _Shake256Context()
    if lib.shake256_init_prng_from_system(ctypes.byref(rng)) != 0:
        raise RuntimeError("shake256_init_prng_from_system failed (no OS RNG?)")
    privkey = ctypes.create_string_buffer(PRIVKEY_SIZE)
    pubkey = ctypes.create_string_buffer(PUBKEY_SIZE)
    rc = lib.falcon_det1024_keygen(ctypes.byref(rng), privkey, pubkey)
    if rc != 0:
        raise RuntimeError(f"falcon_det1024_keygen failed (rc={rc})")
    return pubkey.raw[:PUBKEY_SIZE], privkey.raw[:PRIVKEY_SIZE]


def sign_compressed(privkey: bytes, data: bytes) -> bytes:
    """
    Deterministically sign `data` (the RAW message M the contract rebuilds — do NOT pre-hash).
    Returns the compressed signature `falcon_verify` expects (first byte 0xBA).
    """
    if len(privkey) != PRIVKEY_SIZE:
        raise ValueError(f"privkey must be {PRIVKEY_SIZE} bytes, got {len(privkey)}")
    lib = _libref()
    sig = ctypes.create_string_buffer(SIG_COMPRESSED_MAXSIZE)
    sig_len = ctypes.c_size_t(SIG_COMPRESSED_MAXSIZE)
    rc = lib.falcon_det1024_sign_compressed(sig, ctypes.byref(sig_len), privkey, data, len(data))
    if rc != 0:
        raise RuntimeError(f"falcon_det1024_sign_compressed failed (rc={rc})")
    out = sig.raw[:sig_len.value]
    if out[0] != DET_COMPRESSED_HEADER:
        raise AssertionError(f"unexpected header byte {out[0]:#04x}; expected {DET_COMPRESSED_HEADER:#04x}")
    return out


def verify_compressed(sig: bytes, pubkey: bytes, data: bytes) -> bool:
    """Local round-trip check (mirrors the on-chain falcon_verify). True iff valid."""
    lib = _libref()
    return lib.falcon_det1024_verify_compressed(sig, len(sig), pubkey, data, len(data)) == 0


# ---- message reconstruction MUST mirror inscription.py::_build_message (spec §4) ----
DOMAIN_TAG = b"TRELYAN-INSCRIPTION-v1"

def build_message(app_id: int, cell_id: int, artifact_hash: bytes, genesis_hash: bytes) -> bytes:
    """M = DOMAIN_TAG ‖ app_id(8, big) ‖ cell_id(8, big) ‖ artifact_hash(32) ‖ genesis_hash(32)."""
    if len(artifact_hash) != 32:
        raise ValueError("artifact_hash must be 32 bytes (sha512_256)")
    if len(genesis_hash) != 32:
        raise ValueError("genesis_hash must be 32 bytes")
    return (
        DOMAIN_TAG
        + app_id.to_bytes(8, "big")
        + cell_id.to_bytes(8, "big")
        + artifact_hash
        + genesis_hash
    )


if __name__ == "__main__":
    import hashlib

    print(f"Loading Falcon lib from: {_LIB_PATH}")
    pk, sk = keygen()
    print(f"pubkey  {len(pk)} B (expect {PUBKEY_SIZE})")
    print(f"privkey {len(sk)} B (expect {PRIVKEY_SIZE})")
    assert len(pk) == PUBKEY_SIZE and len(sk) == PRIVKEY_SIZE

    # A realistic message: pretend app_id/cell_id/genesis are known; artifact_hash = sha512_256(blob).
    art = hashlib.new("sha512_256", b"hello, after Q-Day").digest()
    genesis = bytes(32)  # in a real test, the network genesis hash (Global.genesis_hash)
    M = build_message(app_id=1001, cell_id=1, artifact_hash=art, genesis_hash=genesis)

    sig = sign_compressed(sk, M)
    print(f"sig     {len(sig)} B (<= {SIG_COMPRESSED_MAXSIZE}), header {sig[0]:#04x} (expect 0xba), "
          f"salt_version {sig[1]}")
    assert sig[0] == DET_COMPRESSED_HEADER and sig[1] == CURRENT_SALT_VERSION

    assert verify_compressed(sig, pk, M), "valid signature rejected — encoding/build mismatch!"
    tampered = bytearray(sig); tampered[20] ^= 0xFF
    assert not verify_compressed(bytes(tampered), pk, M), "tampered signature accepted — bad!"
    print("OK: keygen -> sign -> verify round trip passes; tamper rejected. "
          "These exact bytes are what falcon_verify expects on-chain.")
