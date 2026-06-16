"""
Signature-level KAT for Deterministic Falcon-1024 (T2).

Two tiers, mirroring test_seal.py:
  * Fixture integrity (pure-Python, no C lib): once the fixture is populated, verify the committed
    vectors are internally consistent — each message equals build_message(...), each recorded
    sig hash equals sha512_256(sig), headers/sizes are well-formed. Catches a corrupted/edited
    fixture even with no lib. Skips while the fixture is unpopulated.
  * Byte-identity (lib-gated, skipif FALCON_DET1024_LIB unset): re-sign each committed message with
    the committed private key and assert the produced compressed signature is BYTE-IDENTICAL to the
    committed golden (full bytes + sha512_256), plus a negative check (a one-byte-flipped golden must
    NOT match and must fail verification).

Scope / honest framing of the byte-identity claim (reviewer Q11/Q7):
  - Byte-identity across ubuntu/macos/windows is REGRESSION EVIDENCE that the pinned signer is
    reproducible — NOT a general Falcon portability proof. It holds because the pinned source
    (config.h) pins the EMULATED fixed-point FP backend (FALCON_FPEMU=1, FALCON_FPNATIVE=0), whose
    uint64 integer arithmetic is bit-exact across compilers; this is guaranteed by the pinned-tree
    digest and checked explicitly by ci/verify_pinned_digest.py. Native FP (FALCON_FPNATIVE) or
    unsafe optimization (-ffast-math, FMA, x87 extended precision) would break it — and per config.h's
    own CRITICAL SECURITY WARNING, signing non-determinism is a catastrophic forgery risk. These are
    TRELYAN-pinned regression vectors for the Algorand deterministic variant, NOT NIST FIPS-206 KATs
    (FN-DSA is draft, unpublished). The header byte 0xBA is the Algorand deterministic-compressed
    header (0x3A | 0x80), not standard Falcon 0x3A.

The committed keypair is a PUBLIC TEST VECTOR — not a secret, bound to no cell, never used on-chain.

Populate the fixture once on a machine with the pinned lib (built from the pinned source, whose
config.h already pins FALCON_FPEMU=1):
    FALCON_DET1024_LIB=/path/to/libfalcondet1024.so python tests/vectors/gen_det1024_kat.py

Run:  cd sdk && pytest tests -v   (CI sets TRELYAN_REQUIRE_KAT=1 to fail if still unpopulated)
"""

import ctypes
import json
import os

import pytest


from trelyan_pq import build_message, sha512_256
from trelyan_pq import falcon

_FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "vectors", "det1024_kat.json")
PINNED_DETERMINISTIC_C_SHA512_256 = "601390dc53521fc1b00eb962ea63d64c2d65bfe774450cf4ec59a3478e0a54a4"


def _load():
    with open(_FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


_FIX = _load()


def _populated() -> bool:
    return bool(_FIX.get("pubkey_hex") and _FIX.get("privkey_hex") and _FIX.get("vectors"))


def _lib_available() -> bool:
    try:
        _pk, buf = falcon.default_signer()._keygen_into_buffer()
        ctypes.memset(ctypes.addressof(buf), 0, falcon.PRIVKEY_SIZE)
        return True
    except Exception:
        return False


requires_fixture = pytest.mark.skipif(
    not _populated(),
    reason="det1024_kat.json is unpopulated — run tests/vectors/gen_det1024_kat.py on a lib machine and commit",
)
requires_lib = pytest.mark.skipif(
    not _lib_available(),
    reason="FALCON_DET1024_LIB not built/set — skipping byte-identity KAT",
)


# --- always runs, even unpopulated: the pin in the fixture must match the pinned build ----------
def test_fixture_pins_the_expected_deterministic_c_digest():
    assert _FIX.get("deterministic_c_sha512_256") == PINNED_DETERMINISTIC_C_SHA512_256
    assert _FIX.get("pinned_commit") == "ce15e75bceb372867daf6b8e81918ab6978686eb"


# --- always runs: the committed keypair must be unmistakably labeled a non-secret test vector ----
def test_fixture_is_labeled_a_public_test_vector():
    sec = (_FIX.get("_security") or "").upper()
    assert "TEST" in sec and ("NOT SECRET" in sec or "NOT A SECRET" in sec), \
        "the KAT fixture must declare its keypair a non-secret PUBLIC TEST VECTOR"


def test_kat_private_key_does_not_leak_into_source():
    """Guardrail (8-seat council): the committed test-only KAT private key must live ONLY in the
    fixture — never hardcoded into source — so an operational code path can never pick it up. Fails
    the build if those key bytes appear in any SDK .py source file."""
    if not _populated():
        pytest.skip("fixture unpopulated")
    sk_hex = _FIX["privkey_hex"]
    src_root = os.path.join(os.path.dirname(__file__), "..", "src")
    leaks = []
    for root, _dirs, files in os.walk(src_root):
        for fn in files:
            if fn.endswith(".py"):
                p = os.path.join(root, fn)
                with open(p, "r", encoding="utf-8", errors="ignore") as fh:
                    if sk_hex in fh.read():
                        leaks.append(os.path.relpath(p, src_root))
    assert not leaks, f"KAT private key bytes leaked into SDK source: {leaks}"


# --- CI guard: fail (don't skip) if the fixture is still the unpopulated sentinel ---------------
def test_fixture_is_populated_when_required():
    if os.environ.get("TRELYAN_REQUIRE_KAT") != "1":
        pytest.skip("set TRELYAN_REQUIRE_KAT=1 (CI does) to require a populated KAT fixture")
    assert _populated(), (
        "det1024_kat.json is still the unpopulated sentinel — generate it on a lib machine "
        "(python tests/vectors/gen_det1024_kat.py) and commit before this job can pass"
    )


# --- pure-Python fixture integrity (no lib): runs once the fixture is populated ------------------
@requires_fixture
def test_committed_vectors_are_internally_consistent():
    pubkey = bytes.fromhex(_FIX["pubkey_hex"])
    privkey = bytes.fromhex(_FIX["privkey_hex"])
    assert len(pubkey) == 1793 and pubkey[0] == 0x0A     # Falcon-1024 pubkey, logn=10 header
    assert len(privkey) == 2305                           # Falcon-1024 privkey
    assert _FIX["vectors"], "fixture marked populated but has no vectors"
    for v in _FIX["vectors"]:
        art = bytes.fromhex(v["artifact_hash_hex"])
        genesis = bytes.fromhex(v["genesis_hash_hex"])
        m = build_message(v["app_id"], v["cell_id"], art, genesis)
        assert m.hex() == v["message_hex"], f"{v['name']}: message != build_message()"
        sig = bytes.fromhex(v["sig_hex"])
        assert sig[0] == 0xBA, f"{v['name']}: sig header != 0xBA"
        assert sig[1] == 0x00, f"{v['name']}: salt-version != 0x00"
        assert len(sig) == v["sig_len"] <= 1423, f"{v['name']}: sig length"
        assert sha512_256(sig).hex() == v["sig_sha512_256"], f"{v['name']}: sig hash mismatch"


# --- lib-gated byte-identity: the actual build-divergence control --------------------------------
@requires_fixture
@requires_lib
def test_signatures_are_byte_identical_to_golden():
    signer = falcon.FalconDet1024()
    pubkey = bytes.fromhex(_FIX["pubkey_hex"])
    privkey = bytes.fromhex(_FIX["privkey_hex"])
    for v in _FIX["vectors"]:
        art = bytes.fromhex(v["artifact_hash_hex"])
        genesis = bytes.fromhex(v["genesis_hash_hex"])
        m = build_message(v["app_id"], v["cell_id"], art, genesis)
        sig = signer.sign(privkey, m)
        golden = bytes.fromhex(v["sig_hex"])
        assert sig == golden, f"{v['name']}: sigma NOT byte-identical to golden (build divergence!)"
        assert sha512_256(sig).hex() == v["sig_sha512_256"]
        assert signer.verify(sig, pubkey, m), f"{v['name']}: golden sigma fails verify"
        # negative check: flipping one byte of the golden must break both equality and verification
        corrupt = bytearray(golden)
        corrupt[len(corrupt) // 2] ^= 0xFF
        corrupt = bytes(corrupt)
        assert sig != corrupt, f"{v['name']}: corrupted golden unexpectedly equal"
        assert not signer.verify(corrupt, pubkey, m), f"{v['name']}: corrupted sigma still verifies"


@requires_fixture
@requires_lib
def test_sdk_encoding_rejection_matrix():
    """T5/Q2 (off-chain half): the malformed-signature rejection matrix mirrored in the SDK verifier,
    so the same cases an auditor checks on-chain are checked off-chain too. One positive accept plus
    five rejections: wrong header / truncated / over-long / tampered salt-version / valid-but-wrong-M.
    (A fuzzing harness over these is a noted follow-up, out of scope here.)"""
    signer = falcon.FalconDet1024()
    pubkey = bytes.fromhex(_FIX["pubkey_hex"])
    v = _FIX["vectors"][0]
    art = bytes.fromhex(v["artifact_hash_hex"])
    genesis = bytes.fromhex(v["genesis_hash_hex"])
    m = build_message(v["app_id"], v["cell_id"], art, genesis)
    good = bytes.fromhex(v["sig_hex"])

    assert signer.verify(good, pubkey, m)                                   # positive accept
    assert good[0] == 0xBA and good[1] == 0x00

    wrong_header = bytes([0x3A]) + good[1:]                                 # 0x3A = randomized-Falcon header
    truncated = good[:-64]
    over_long = good + b"\x00" * (1424 - len(good))                         # > SIG_COMPRESSED_MAXSIZE (1423)
    bad_salt = bytes([good[0], good[1] ^ 0xFF]) + good[2:]                  # tampered salt-version byte
    assert len(over_long) > 1423
    for bad in (wrong_header, truncated, over_long, bad_salt):
        assert not signer.verify(bad, pubkey, m)

    m_wrong = build_message(v["app_id"], v["cell_id"], sha512_256(b"a different artifact"), genesis)
    assert not signer.verify(good, pubkey, m_wrong)                         # valid sigma, wrong M
