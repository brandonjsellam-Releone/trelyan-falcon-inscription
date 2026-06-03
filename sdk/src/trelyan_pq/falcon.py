"""
trelyan_pq.falcon — Deterministic Falcon-1024 signer in the EXACT encoding Algorand's native
`falcon_verify` opcode accepts: deterministic, COMPRESSED, header byte 0xBA.

Why this module exists: generic liboqs / pqcrypto Falcon does NOT interoperate with the AVM
opcode (randomized signatures, wrong header) and gets rejected on-chain. This is a thin,
audited-shape ctypes wrapper over the `algorand/falcon` C library — the same code path
Algorand uses — exposing keygen / sign / verify.

Build the shared library once and point FALCON_DET1024_LIB at it:

    git clone https://github.com/algorand/falcon && cd falcon
    cc -O3 -fPIC -shared -o libfalcondet1024.so \\
        codec.c common.c falcon.c fft.c fpr.c keygen.c rng.c shake.c sign.c vrfy.c deterministic.c
    export FALCON_DET1024_LIB="$PWD/libfalcondet1024.so"   # .dylib on macOS, .dll on Windows

(If the link errors on a missing symbol, add the .c that defines it; if it errors on a
duplicate main(), you included a test file — drop it.)

Sign the RAW message M from `trelyan_pq.message.build_message()` — do NOT pre-hash it.
"""

from __future__ import annotations

import ctypes
import os
from typing import Optional, Tuple

from .message import PUBKEY_LEN, SIG_COMPRESSED_MAXSIZE, DET_COMPRESSED_HEADER

__all__ = [
    "FalconDet1024",
    "PRIVKEY_SIZE",
    "PUBKEY_SIZE",
    "CURRENT_SALT_VERSION",
    "keygen",
    "sign",
    "verify",
    "sign_inscription",
    "verify_inscription",
    "default_signer",
]

PUBKEY_SIZE = PUBKEY_LEN          # 1793
PRIVKEY_SIZE = 2305              # FALCON_PRIVKEY_SIZE(10)
CURRENT_SALT_VERSION = 0

_DEFAULT_LIB_PATH = os.environ.get("FALCON_DET1024_LIB", "./libfalcondet1024.so")


class _Shake256Context(ctypes.Structure):
    # typedef struct { uint64_t opaque_contents[26]; } shake256_context;  (falcon.h)
    _fields_ = [("opaque_contents", ctypes.c_uint64 * 26)]


def _bind(lib: ctypes.CDLL) -> ctypes.CDLL:
    lib.shake256_init_prng_from_system.argtypes = [ctypes.POINTER(_Shake256Context)]
    lib.shake256_init_prng_from_system.restype = ctypes.c_int
    lib.falcon_det1024_keygen.argtypes = [
        ctypes.POINTER(_Shake256Context), ctypes.c_char_p, ctypes.c_char_p,
    ]
    lib.falcon_det1024_keygen.restype = ctypes.c_int
    lib.falcon_det1024_sign_compressed.argtypes = [
        ctypes.c_char_p, ctypes.POINTER(ctypes.c_size_t),
        ctypes.c_char_p, ctypes.c_char_p, ctypes.c_size_t,
    ]
    lib.falcon_det1024_sign_compressed.restype = ctypes.c_int
    lib.falcon_det1024_verify_compressed.argtypes = [
        ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_size_t,
    ]
    lib.falcon_det1024_verify_compressed.restype = ctypes.c_int
    return lib


def _load(lib_path: str) -> ctypes.CDLL:
    try:
        return _bind(ctypes.CDLL(lib_path))
    except OSError as e:
        raise RuntimeError(
            f"Could not load the Falcon shared library at {lib_path!r}. Build it (see this "
            f"module's docstring) and set FALCON_DET1024_LIB to its path. Underlying error: {e}"
        ) from e


class FalconDet1024:
    """Deterministic Falcon-1024 keygen / sign / verify, bound to the algorand/falcon C library.

    The library is loaded lazily on first use, so importing this module never fails even if the
    shared object isn't built yet.
    """

    def __init__(self, lib_path: Optional[str] = None) -> None:
        self.lib_path = lib_path or _DEFAULT_LIB_PATH
        self._lib: Optional[ctypes.CDLL] = None

    def _lib_ref(self) -> ctypes.CDLL:
        if self._lib is None:
            self._lib = _load(self.lib_path)
        return self._lib

    def keygen(self) -> Tuple[bytes, bytes]:
        """Return (pubkey[1793], privkey[2305]) for Deterministic Falcon-1024."""
        lib = self._lib_ref()
        rng = _Shake256Context()
        if lib.shake256_init_prng_from_system(ctypes.byref(rng)) != 0:
            raise RuntimeError("shake256_init_prng_from_system failed (no OS RNG?)")
        privkey = ctypes.create_string_buffer(PRIVKEY_SIZE)
        pubkey = ctypes.create_string_buffer(PUBKEY_SIZE)
        rc = lib.falcon_det1024_keygen(ctypes.byref(rng), privkey, pubkey)
        if rc != 0:
            raise RuntimeError(f"falcon_det1024_keygen failed (rc={rc})")
        return pubkey.raw[:PUBKEY_SIZE], privkey.raw[:PRIVKEY_SIZE]

    def sign(self, privkey: bytes, message: bytes) -> bytes:
        """Sign the RAW message M (low-level; prefer sign_inscription()). Do NOT pre-hash M.

        Returns the compressed signature `falcon_verify` expects (first byte 0xBA).
        """
        if len(privkey) != PRIVKEY_SIZE:
            raise ValueError(f"privkey must be {PRIVKEY_SIZE} bytes, got {len(privkey)}")
        lib = self._lib_ref()
        sig = ctypes.create_string_buffer(SIG_COMPRESSED_MAXSIZE)
        sig_len = ctypes.c_size_t(SIG_COMPRESSED_MAXSIZE)
        rc = lib.falcon_det1024_sign_compressed(sig, ctypes.byref(sig_len), privkey, message, len(message))
        if rc != 0:
            raise RuntimeError(f"falcon_det1024_sign_compressed failed (rc={rc})")
        out = sig.raw[: sig_len.value]
        if not out or out[0] != DET_COMPRESSED_HEADER:
            raise AssertionError(
                f"unexpected header byte {out[0]:#04x} (expected {DET_COMPRESSED_HEADER:#04x}); "
                f"the bytes would be rejected on-chain"
            )
        return out

    def verify(self, sig: bytes, pubkey: bytes, message: bytes) -> bool:
        """Local round-trip check mirroring the on-chain falcon_verify. True iff valid."""
        lib = self._lib_ref()
        return lib.falcon_det1024_verify_compressed(sig, len(sig), pubkey, message, len(message)) == 0

    # --- inscription-bound convenience (preferred over raw sign/verify) ----------------------
    def sign_inscription(self, privkey: bytes, app_id: int, cell_id: int,
                         artifact_hash: bytes, genesis_hash: bytes) -> bytes:
        """Build the domain-separated message M (binds app_id, cell_id, artifact, network) and
        sign it. Preferred over raw sign(): the binding makes the signature non-replayable across
        apps/cells/networks."""
        from .message import build_message
        return self.sign(privkey, build_message(app_id, cell_id, artifact_hash, genesis_hash))

    def verify_inscription(self, sig: bytes, pubkey: bytes, app_id: int, cell_id: int,
                           artifact_hash: bytes, genesis_hash: bytes) -> bool:
        """Verify `sig` against the reconstructed inscription message M for these parameters."""
        from .message import build_message
        return self.verify(sig, pubkey, build_message(app_id, cell_id, artifact_hash, genesis_hash))


# --- module-level convenience over a shared default instance ---------------------------------
_default: Optional[FalconDet1024] = None


def default_signer() -> FalconDet1024:
    global _default
    if _default is None:
        _default = FalconDet1024()
    return _default


def keygen() -> Tuple[bytes, bytes]:
    return default_signer().keygen()


def sign(privkey: bytes, message: bytes) -> bytes:
    return default_signer().sign(privkey, message)


def verify(sig: bytes, pubkey: bytes, message: bytes) -> bool:
    return default_signer().verify(sig, pubkey, message)


def sign_inscription(privkey: bytes, app_id: int, cell_id: int,
                     artifact_hash: bytes, genesis_hash: bytes) -> bytes:
    return default_signer().sign_inscription(privkey, app_id, cell_id, artifact_hash, genesis_hash)


def verify_inscription(sig: bytes, pubkey: bytes, app_id: int, cell_id: int,
                       artifact_hash: bytes, genesis_hash: bytes) -> bool:
    return default_signer().verify_inscription(sig, pubkey, app_id, cell_id, artifact_hash, genesis_hash)
