"""
Fuzz harness over the signature-encoding boundary — apex hardening of T5/Q2.

Randomized but SEEDED (reproducible) fuzzing of the deterministic-Falcon verifier:
  1. No MUTATION of a valid sigma ever verifies (bit-flips, truncation, extension, splices).
  2. Random garbage of any length never verifies AND never crashes the verifier.

This complements the fixed rejection matrix (test_signature_kat / test_inscription) with breadth.
Lib-gated and fixture-gated (skips cleanly without FALCON_DET1024_LIB or an unpopulated fixture).
The seed is fixed so a failure is exactly reproducible. Run: cd sdk && pytest tests -v
"""

import ctypes
import json
import os
import random

import pytest

from trelyan_pq import build_message, falcon

_FIX_PATH = os.path.join(os.path.dirname(__file__), "vectors", "det1024_kat.json")
with open(_FIX_PATH, "r", encoding="utf-8") as _f:
    _FIX = json.load(_f)

FUZZ_SEED = 1469      # fixed -> reproducible failures
FUZZ_ITERS = 300


def _populated() -> bool:
    return bool(_FIX.get("pubkey_hex") and _FIX.get("vectors"))


def _lib_available() -> bool:
    try:
        _pk, buf = falcon.default_signer()._keygen_into_buffer()
        ctypes.memset(ctypes.addressof(buf), 0, falcon.PRIVKEY_SIZE)
        return True
    except Exception:
        return False


requires = pytest.mark.skipif(
    not (_populated() and _lib_available()),
    reason="needs FALCON_DET1024_LIB + a populated det1024_kat.json",
)


def _vector0():
    v = _FIX["vectors"][0]
    pubkey = bytes.fromhex(_FIX["pubkey_hex"])
    m = build_message(v["app_id"], v["cell_id"],
                      bytes.fromhex(v["artifact_hash_hex"]), bytes.fromhex(v["genesis_hash_hex"]))
    good = bytes.fromhex(v["sig_hex"])
    return pubkey, m, good


@requires
def test_fuzz_mutated_signatures_never_verify():
    signer = falcon.FalconDet1024()
    pubkey, m, good = _vector0()
    assert signer.verify(good, pubkey, m)                          # baseline: the real sigma verifies
    rnd = random.Random(FUZZ_SEED)
    checked = 0
    for _ in range(FUZZ_ITERS):
        b = bytearray(good)
        mode = rnd.randrange(4)
        if mode == 0:                                              # flip 1-4 random bits
            for _ in range(rnd.randint(1, 4)):
                b[rnd.randrange(len(b))] ^= (1 << rnd.randrange(8))
        elif mode == 1:                                            # truncate
            b = b[:rnd.randrange(0, len(b))]
        elif mode == 2:                                            # extend with random bytes
            b += bytes(rnd.randrange(256) for _ in range(rnd.randint(1, 200)))
        else:                                                      # splice random bytes over a region
            i = rnd.randrange(len(b)); n = rnd.randint(1, len(b) - i)
            b[i:i + n] = bytes(rnd.randrange(256) for _ in range(n))
        mutant = bytes(b)
        if mutant == good:                                         # astronomically unlikely; stay exact
            continue
        assert not signer.verify(mutant, pubkey, m), f"a mutated sigma verified (mode {mode})"
        checked += 1
    assert checked > FUZZ_ITERS // 2                               # the fuzzer actually exercised mutants


@requires
def test_fuzz_random_garbage_never_verifies_or_crashes():
    signer = falcon.FalconDet1024()
    pubkey, m, _good = _vector0()
    rnd = random.Random(FUZZ_SEED ^ 0xABCD)
    for _ in range(FUZZ_ITERS):
        blob = bytes(rnd.randrange(256) for _ in range(rnd.randrange(0, 1500)))
        assert signer.verify(blob, pubkey, m) is False            # must reject, must not raise


@requires
def test_length_boundary_corpus_rejected():
    """Exact length-boundary corpus around the 1423-byte compressed-sig cap (the auditor will look
    for this): well-headed (0xBA, salt 0x00) but wrong-content blobs at 1422 / 1423 / 1424 and at
    len(good)±1 must all be rejected without crashing — so rejection isn't only a length gate."""
    signer = falcon.FalconDet1024()
    pubkey, m, good = _vector0()
    for n in (1422, 1423, 1424, len(good) - 1, len(good) + 1):
        blob = bytes([0xBA, 0x00]) + bytes(max(0, n - 2))         # correct header+salt, zero body
        assert signer.verify(blob, pubkey, m) is False
