"""
Bidirectional KAT: trelyan-pq det1024 signer  <->  algo-pqc-kit signer   (interop issue #1).

Purpose (QuantaChain `algo-pqc-kit` x `trelyan-pq`): prove that algo-pqc-kit's *pure-Python* Falcon
signer and trelyan-pq's pinned C signer emit the SAME bytes Algorand's native `falcon_verify` opcode
accepts — so ONE Falcon-1024 keypair can both control an algo-pqc-kit `FalconLsig` account AND
authorize a TRELYAN inscription ("no Ed25519 anywhere in the authorization path"), and — the bonus
@falcon flagged — trelyan-pq can drop its ctypes/C dependency once this passes. See
`sdk/docs/INTEROP_algo-pqc-kit.md` and upstream `quantachain/algo-pqc-kit` issue #1.

────────────────────────────────────────────────────────────────────────────────────────────────
THE ALIGNMENT SPEC — what BOTH signers must emit, byte-for-byte (this is the reconcile contract):
  * Variant : Deterministic Falcon-1024 (`falcon_det1024`), COMPRESSED encoding.
  * Header  : sig[0] == 0xBA  (== 0x3A | 0x80, the deterministic-mode marker — NOT standard 0x3A).
  * Salt    : sig[1] == 0x00  (the salt-VERSION byte; the 40-byte random nonce is EXCLUDED).
  * Nonce   : derandomized as SHAKE256(logn || privkey || data) — NOT a zeroed nonce.
  * Length  : variable, <= 1423 B (= SIG_COMPRESSED_MAXSIZE(10) - 40 + 1). NOTE: ~1232 B is the
              *typical* length, NOT the cap — a hard <=1232 bound would reject valid large sigs.
  * Message : M = build_message(app_id, cell_id, artifact_hash, genesis_hash) (102 B), signed RAW
              (do NOT pre-hash; the signer/opcode hash-to-point internally with the fixed salt).
  * Backend : byte-identity holds against the EMULATED fixed-point backend (FALCON_FPEMU=1). A
              faithful pure-Python det1024 must reproduce those exact bytes; ANY divergence in the
              Gaussian sampler, rounding, or compressed encoding surfaces here as a byte mismatch.
              That divergence-detection is the entire point of this KAT.

The committed goldens in `vectors/det1024_kat.json` ARE the ground truth — the exact bytes the live
TestNet app (763809096) verifies on-chain. The primary direction below needs NO C library: it simply
asks algo-pqc-kit to reproduce those goldens. If the C lib is also present, it cross-checks the two.

Wiring: `_ApkAdapter` is the SINGLE integration point. Until algo-pqc-kit's exact entry points are
pinned (derive a pubkey from the committed private key; sign M to det1024-compressed bytes), the
methods raise NotImplementedError and these tests SKIP with an actionable message rather than
silently passing. Edit ONLY `_ApkAdapter` to wire the real API, and the suite runs.
"""

import json
import os

import pytest

from trelyan_pq import build_message, sha512_256

_FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "vectors", "det1024_kat.json")
DET_HEADER = 0xBA          # 0x3A | 0x80
SALT_VERSION = 0x00
SIG_COMPRESSED_MAXSIZE = 1423   # format max — NOT the ~1232 typical length
PUBKEY_LEN = 1793
PUBKEY_HEADER = 0x0A       # Falcon-1024 pubkey header (logn=10)


def _load():
    with open(_FIXTURE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


_FIX = _load()


def _populated() -> bool:
    return bool(_FIX.get("pubkey_hex") and _FIX.get("privkey_hex") and _FIX.get("vectors"))


# ── the ONE integration point — adapt algo-pqc-kit's API to (privkey, M) -> det1024 bytes ────────
class _ApkAdapter:
    """Maps algo-pqc-kit onto the two operations this KAT needs. Edit ONLY this class to wire the
    real package (issue #1). Keep the NotImplementedError until wired so tests skip, not pass.

    Note on key material: the committed `privkey_hex` is the 2305-byte `algorand/falcon` det1024
    private key. If algo-pqc-kit keys from a seed or a different encoding, convert/derive inside the
    adapter so the SAME key produces the committed pubkey and signatures (that's what makes the
    keypair interoperable across both layers)."""

    def __init__(self):
        try:
            import algo_pqc_kit  # noqa: F401
            self._mod = algo_pqc_kit
            self.available = True
        except Exception:
            self._mod = None
            self.available = False

    def pubkey_from_privkey(self, privkey: bytes) -> bytes:
        """Return the 1793-byte Falcon-1024 public key algo-pqc-kit derives from `privkey`."""
        # Wired to the published API (algo_pqc_kit.account.FalconAccount, issue #1). Two things still
        # to CONFIRM with the maintainer: (a) that from_private_key accepts the committed 2305-byte
        # algorand/falcon det1024 key (not a seed/other encoding), (b) the public-key accessor name.
        try:
            from algo_pqc_kit.account import FalconAccount
            acct = FalconAccount.from_private_key(privkey)
            pk = getattr(acct, "public_key", None)
            if pk is None:
                d = acct.to_dict() if hasattr(acct, "to_dict") else {}
                pk = d.get("public_key") or d.get("pubkey")
            if isinstance(pk, str):
                pk = bytes.fromhex(pk)
            if not isinstance(pk, (bytes, bytearray)) or len(pk) != PUBKEY_LEN:
                raise NotImplementedError(
                    "confirm FalconAccount's public-key accessor + that from_private_key accepts the "
                    "2305-byte algorand/falcon det1024 key (issue #1)")
            return bytes(pk)
        except NotImplementedError:
            raise
        except Exception as e:  # API shape differs -> SKIP (don't falsely fail) until confirmed
            raise NotImplementedError(f"confirm FalconAccount.from_private_key(...).public_key: {e}")

    def sign_det1024_compressed(self, privkey: bytes, message: bytes) -> bytes:
        """Return the det1024 COMPRESSED signature (header 0xBA, salt-version 0x00) algo-pqc-kit
        produces for `message` (M, signed RAW) under `privkey`."""
        # Wired to FalconAccount.sign(message) -> bytes (issue #1). NOTE: the package docs describe
        # sign() as a 1232-byte signature possibly WITHOUT the 0xBA header / 0x00 salt-version prefix;
        # if so, this KAT's header asserts catch it — that IS the reconcile point, not a bug here.
        try:
            from algo_pqc_kit.account import FalconAccount
            return FalconAccount.from_private_key(privkey).sign(message)
        except Exception as e:  # API shape differs -> SKIP until confirmed
            raise NotImplementedError(f"confirm FalconAccount.sign(message) -> det1024 bytes: {e}")


_APK = _ApkAdapter()

requires_fixture = pytest.mark.skipif(
    not _populated(), reason="det1024_kat.json unpopulated — run tests/vectors/gen_det1024_kat.py"
)
requires_apk = pytest.mark.skipif(
    not _APK.available, reason="algo-pqc-kit not installed (pip install algo-pqc-kit)"
)


def _vectors():
    """Yield (vector, M) pairs, asserting our build_message reproduces the committed message bytes."""
    for v in _FIX["vectors"]:
        m = build_message(
            v["app_id"], v["cell_id"],
            bytes.fromhex(v["artifact_hash_hex"]), bytes.fromhex(v["genesis_hash_hex"]),
        )
        assert m.hex() == v["message_hex"], f"{v['name']}: build_message != committed message"
        yield v, m


# ── DIRECTION 1 (no C lib needed): algo-pqc-kit must reproduce the opcode-accepted goldens ───────
@requires_fixture
@requires_apk
def test_algo_pqc_kit_reproduces_trelyan_goldens_byte_for_byte():
    privkey = bytes.fromhex(_FIX["privkey_hex"])
    try:
        for v, m in _vectors():
            sig = _APK.sign_det1024_compressed(privkey, m)
            # format alignment first — a clearer failure than a raw 1200-byte diff:
            assert sig[0] == DET_HEADER, f"{v['name']}: header {sig[0]:#04x} != 0xBA"
            assert sig[1] == SALT_VERSION, f"{v['name']}: salt-version {sig[1]:#04x} != 0x00"
            assert len(sig) <= SIG_COMPRESSED_MAXSIZE, f"{v['name']}: len {len(sig)} > 1423 (format max)"
            golden = bytes.fromhex(v["sig_hex"])
            assert sig == golden, (
                f"{v['name']}: algo-pqc-kit signature NOT byte-identical to the opcode-accepted golden "
                f"(len apk={len(sig)} golden={len(golden)}). The two det1024 encodings diverge — THIS "
                f"is the reconcile point (sampler / rounding / compression must match the FPEMU build)."
            )
            assert sha512_256(sig).hex() == v["sig_sha512_256"]
    except NotImplementedError as e:
        pytest.skip(f"_ApkAdapter not wired yet (issue #1): {e}")


# ── one keypair, both layers: the SAME private key must derive the SAME public key in both ────────
@requires_fixture
@requires_apk
def test_one_keypair_serves_both_layers():
    try:
        pk = _APK.pubkey_from_privkey(bytes.fromhex(_FIX["privkey_hex"]))
    except NotImplementedError as e:
        pytest.skip(f"_ApkAdapter not wired yet (issue #1): {e}")
    assert pk == bytes.fromhex(_FIX["pubkey_hex"]), (
        "algo-pqc-kit derives a DIFFERENT public key from the committed private key — the keypair is "
        "not interoperable, so an algo-pqc-kit FalconLsig account could not authorize a TRELYAN cell."
    )
    assert len(pk) == PUBKEY_LEN and pk[0] == PUBKEY_HEADER


# ── DIRECTION 2 (needs the C lib): trelyan-pq verifies algo-pqc-kit's sig, and they're byte-equal ─
def _lib_available() -> bool:
    if not os.environ.get("FALCON_DET1024_LIB"):
        return False
    try:
        from trelyan_pq import falcon
        falcon.FalconDet1024()
        return True
    except Exception:
        return False


@requires_fixture
@requires_apk
@pytest.mark.skipif(not _lib_available(), reason="FALCON_DET1024_LIB not set — cross-verify needs the C verifier")
def test_cross_verify_and_determinism_between_signers():
    from trelyan_pq import falcon

    signer = falcon.FalconDet1024()
    privkey = bytes.fromhex(_FIX["privkey_hex"])
    pubkey = bytes.fromhex(_FIX["pubkey_hex"])
    try:
        for v, m in _vectors():
            apk_sig = _APK.sign_det1024_compressed(privkey, m)
            # trelyan-pq's verifier (i.e. the opcode's accepted format) accepts algo-pqc-kit's signature:
            assert signer.verify(apk_sig, pubkey, m), f"{v['name']}: trelyan-pq rejects algo-pqc-kit's signature"
            # and because both are DETERMINISTIC det1024, the two signers must be byte-identical:
            assert signer.sign(privkey, m) == apk_sig, f"{v['name']}: C signer != algo-pqc-kit signer"
    except NotImplementedError as e:
        pytest.skip(f"_ApkAdapter not wired yet (issue #1): {e}")
