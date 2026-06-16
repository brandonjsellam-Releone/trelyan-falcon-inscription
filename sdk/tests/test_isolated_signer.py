"""
Tests for keygen_sign_seal_isolated — the short-lived isolated signing worker (containment hardening).

The private key's whole lifetime is confined to a subprocess that exits; the parent receives only the
public key + signature. Lib-gated (needs FALCON_DET1024_LIB); the tripwire path is pure-Python.

Run:  cd sdk && pytest tests -v
"""

import ctypes
import json
import os
import subprocess
import sys

import pytest

from trelyan_pq import (
    SealResult,
    InMemorySealStore,
    JsonFileSealStore,
    CellAlreadySealed,
    SealVerificationError,
    keygen_sign_seal_isolated,
    sha512_256,
)
from trelyan_pq import falcon

ART = sha512_256(b"trelyan isolated-signer artifact")
GENESIS = bytes(32)
APP_ID = 763809096


def _lib_available() -> bool:
    try:
        _pk, buf = falcon.default_signer()._keygen_into_buffer()
        ctypes.memset(ctypes.addressof(buf), 0, falcon.PRIVKEY_SIZE)
        return True
    except Exception:
        return False


requires_lib = pytest.mark.skipif(not _lib_available(), reason="FALCON_DET1024_LIB not built/set")


# --- pure-Python: the parent-side tripwire fires before spawning any worker -----------------------
def test_isolated_presealed_cell_raises_before_spawn(tmp_path):
    store = JsonFileSealStore(tmp_path / "sealed.json")
    store.record(9)
    with pytest.raises(CellAlreadySealed):
        keygen_sign_seal_isolated(APP_ID, 9, ART, GENESIS, store=store)


# --- lib-gated: real isolated keygen+sign --------------------------------------------------------
@requires_lib
def test_isolated_seal_produces_verifying_signature():
    store = InMemorySealStore()
    result = keygen_sign_seal_isolated(APP_ID, 21, ART, GENESIS, store=store)
    assert isinstance(result, SealResult)
    assert len(result.pubkey) == 1793 and result.pubkey[0] == 0x0A
    assert result.signature[0] == 0xBA
    verifier = falcon.FalconDet1024()
    assert verifier.verify_inscription(result.signature, result.pubkey, APP_ID, 21, ART, GENESIS)
    assert store.is_sealed(21)


@requires_lib
def test_isolated_second_seal_raises():
    store = InMemorySealStore()
    keygen_sign_seal_isolated(APP_ID, 22, ART, GENESIS, store=store)
    with pytest.raises(CellAlreadySealed):
        keygen_sign_seal_isolated(APP_ID, 22, ART, GENESIS, store=store)


@requires_lib
def test_isolated_result_has_no_private_key():
    store = InMemorySealStore()
    result = keygen_sign_seal_isolated(APP_ID, 23, ART, GENESIS, store=store)
    assert not hasattr(result, "privkey") and not hasattr(result, "private_key")


@requires_lib
def test_isolated_require_locked_fails_closed_when_mlockall_unavailable():
    """Fail-closed (DeepSeek/OpenAI seats): with require_locked=True the worker refuses to keygen
    unless mlockall pinned all pages. Where mlockall is unavailable (Windows) it must REFUSE rather
    than sign on swappable memory; the cell is not consumed. On POSIX mlockall usually succeeds, so
    the refusal is only asserted on win32."""
    if sys.platform != "win32":
        pytest.skip("mlockall is typically available on POSIX, so the fail-closed refusal is not observable here")
    store = InMemorySealStore()
    with pytest.raises(SealVerificationError):
        keygen_sign_seal_isolated(APP_ID, 25, ART, GENESIS, store=store, require_locked=True)
    assert not store.is_sealed(25)


@requires_lib
def test_worker_stdout_carries_only_public_values():
    """The containment property, checked at the boundary: the worker's stdout (everything that
    crosses back to the parent) contains ONLY the public key + signature — never the private key.
    The committed privkey length is 2305 B (4610 hex chars); assert no such field is present."""
    req = json.dumps({"app_id": APP_ID, "cell_id": 24,
                      "artifact_hash": ART.hex(), "genesis_hash": GENESIS.hex()}).encode()
    proc = subprocess.run([sys.executable, "-m", "trelyan_pq._seal_worker"],
                          input=req, capture_output=True, timeout=120, env=os.environ.copy())
    assert proc.returncode == 0, proc.stderr.decode()
    out = json.loads(proc.stdout.decode())
    # only public values + the auditable protections report cross the boundary — no private-key field
    assert set(out.keys()) == {"ok", "pubkey", "signature", "protections"}
    assert out["ok"] is True
    assert len(out["pubkey"]) == 1793 * 2                         # public key, hex
    # a 2305-byte private key would be 4610 hex chars; ensure nothing that size leaked
    assert all(len(v) != falcon.PRIVKEY_SIZE * 2 for v in out.values() if isinstance(v, str))
    assert set(out["protections"]) >= {"mlockall", "no_core_dump", "no_ptrace", "platform"}
