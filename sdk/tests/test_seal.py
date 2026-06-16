"""
Tests for trelyan_pq.seal — sign-once-destroy (T1).

Two tiers:
  * Pure-Python (no Falcon C lib needed): the tripwire fires before any keygen, the stores behave,
    and SealResult exposes no private key. These run everywhere, including CI without the lib.
  * Lib-gated (skipif FALCON_DET1024_LIB is unbuilt/unset): real keygen/sign — the private-key
    buffer reads all-zero after seal, the signature self-verifies with header 0xBA, a second seal
    of the same cell raises, and a bad-build signature fails closed without consuming the cell.

Run:  cd sdk && pytest tests -v
"""

import ctypes
import dataclasses

import pytest

from trelyan_pq import (
    SealResult,
    JsonFileSealStore,
    InMemorySealStore,
    CellAlreadySealed,
    SealVerificationError,
    keygen_sign_seal,
    sha512_256,
)
from trelyan_pq import falcon


# --- lib availability gate ---------------------------------------------------------------------
def _lib_available() -> bool:
    """True iff the Deterministic Falcon-1024 shared lib loads and keygens (exercises it for real)."""
    try:
        _pk, buf = falcon.default_signer()._keygen_into_buffer()
        ctypes.memset(ctypes.addressof(buf), 0, falcon.PRIVKEY_SIZE)  # don't leave a stray key around
        return True
    except Exception:
        return False


requires_lib = pytest.mark.skipif(
    not _lib_available(),
    reason="FALCON_DET1024_LIB not built/set — skipping lib-backed seal tests",
)

# Fixed, network-agnostic seal inputs reused across tests.
ART = sha512_256(b"trelyan T1 seal artifact")
GENESIS = bytes(32)
APP_ID = 763809096  # the TestNet app id (not load-bearing for these off-chain tests)


# --- spies that wrap a real signer (let tests observe the wiped buffer / force a bad build) -----
class _CapturingSigner:
    """Pass-through signer that captures the private-key buffer so a test can read it post-seal."""

    def __init__(self, inner):
        self._inner = inner
        self.captured = None

    def _keygen_into_buffer(self):
        pubkey, buf = self._inner._keygen_into_buffer()
        self.captured = buf
        return pubkey, buf

    def sign(self, privkey, message):
        return self._inner.sign(privkey, message)

    def verify_inscription(self, *args, **kwargs):
        return self._inner.verify_inscription(*args, **kwargs)


class _TamperingSigner(_CapturingSigner):
    """Like _CapturingSigner but corrupts the signature body so self-verification fails."""

    def sign(self, privkey, message):
        sig = bytearray(self._inner.sign(privkey, message))
        sig[20] ^= 0xFF  # flip a body byte; header (sig[0]) stays 0xBA so we exercise verify, not the header check
        return bytes(sig)


# ============================ pure-Python (no C lib needed) ============================

def test_sealresult_has_no_private_key_field():
    names = {f.name for f in dataclasses.fields(SealResult)}
    assert names == {"pubkey", "signature", "cell_id"}
    assert "privkey" not in names and "private_key" not in names


def test_inmemory_store_roundtrip():
    s = InMemorySealStore()
    assert not s.is_sealed(7)
    s.record(7)
    assert s.is_sealed(7)


def test_page_lock_helpers_roundtrip():
    """Apex hardening: the mlock/VirtualLock page-pin helpers are best-effort (return a bool, never
    raise) and the buffer still wipes to all-zero. On a normal host _lock_pages returns True."""
    buf = ctypes.create_string_buffer(falcon.PRIVKEY_SIZE)
    locked = falcon._lock_pages(buf)
    assert isinstance(locked, bool)                       # best-effort: True on most hosts
    ctypes.memset(ctypes.addressof(buf), 0, falcon.PRIVKEY_SIZE)
    falcon._unlock_pages(buf)                             # must not raise
    assert buf.raw == b"\x00" * falcon.PRIVKEY_SIZE


def test_jsonfile_store_roundtrip_and_persists(tmp_path):
    p = tmp_path / "sealed.json"
    s = JsonFileSealStore(p)
    assert not s.is_sealed(42)
    s.record(42)
    assert s.is_sealed(42)
    # a fresh instance over the same file sees the record (durable, survives "restart")
    assert JsonFileSealStore(p).is_sealed(42)


def test_presealed_cell_raises_before_any_keygen(tmp_path):
    """The tripwire must fire before keygen, so this holds even when the C lib is absent."""
    store = JsonFileSealStore(tmp_path / "sealed.json")
    store.record(5)
    with pytest.raises(CellAlreadySealed):
        keygen_sign_seal(APP_ID, 5, ART, GENESIS, store=store)


# ============================ lib-gated (real keygen / sign) ============================

@requires_lib
def test_seal_wipes_private_key_buffer():
    store = InMemorySealStore()
    spy = _CapturingSigner(falcon.default_signer())
    result = keygen_sign_seal(APP_ID, 11, ART, GENESIS, store=store, signer=spy)
    # the private-key buffer must read all-zero after the seal returns
    assert spy.captured is not None
    assert spy.captured.raw == b"\x00" * falcon.PRIVKEY_SIZE
    assert isinstance(result, SealResult)


@requires_lib
def test_seal_signature_verifies_and_has_0xBA_header():
    store = InMemorySealStore()
    result = keygen_sign_seal(APP_ID, 12, ART, GENESIS, store=store)
    assert len(result.pubkey) == 1793 and result.pubkey[0] == 0x0A   # logn=10 public-key header
    assert result.signature[0] == 0xBA                                # deterministic compressed header
    # an INDEPENDENT verifier accepts the returned (sig, pubkey) for these exact inscription params
    verifier = falcon.FalconDet1024()
    assert verifier.verify_inscription(result.signature, result.pubkey, APP_ID, 12, ART, GENESIS)


@requires_lib
def test_second_seal_of_same_cell_raises():
    store = InMemorySealStore()
    keygen_sign_seal(APP_ID, 13, ART, GENESIS, store=store)
    assert store.is_sealed(13)
    with pytest.raises(CellAlreadySealed):
        keygen_sign_seal(APP_ID, 13, ART, GENESIS, store=store)


@requires_lib
def test_bad_build_fails_closed_without_consuming_cell():
    """A signature that fails self-verification raises SealVerificationError, still wipes the key,
    and does NOT record the cell (retry allowed once the build is fixed)."""
    store = InMemorySealStore()
    tamper = _TamperingSigner(falcon.default_signer())
    with pytest.raises(SealVerificationError):
        keygen_sign_seal(APP_ID, 14, ART, GENESIS, store=store, signer=tamper)
    assert not store.is_sealed(14)                              # cell not consumed
    assert tamper.captured.raw == b"\x00" * falcon.PRIVKEY_SIZE  # key still wiped on the failure path
