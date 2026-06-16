"""
gen_det1024_kat.py — generate the Deterministic Falcon-1024 signature KAT fixture (T2).

Run ONCE on a machine with the pinned Falcon shared library built (see PINNED_BUILD_NOTE), then
commit the resulting tests/vectors/det1024_kat.json. Thereafter test_signature_kat.py asserts the
produced compressed signature is byte-identical to the committed golden on every platform — the
cross-platform build-divergence control (reviewer Q11/Q7).

    # build the pinned lib first (see falcon.py docstring / PINNED_BUILD_NOTE), then:
    FALCON_DET1024_LIB=/path/to/libfalcondet1024.so python tests/vectors/gen_det1024_kat.py

Why a committed keypair: det1024 keygen draws from the OS RNG, so a keypair is NOT reproducible.
We pin one throwaway pair here; only the SIGNING step (privkey, M) -> sigma is deterministic, and
that determinism across OSes is exactly what the KAT checks.

SECURITY: the keypair written here is a TEST-ONLY throwaway — bound to no cell, never used on-chain,
never produced via keygen_sign_seal. It is a test vector, not a secret (NIST Falcon KATs likewise
ship private keys).
"""

from __future__ import annotations

import json
import os
import sys

# allow running from the sdk/ root or the vectors/ dir
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))

from trelyan_pq import build_message, sha512_256  # noqa: E402
from trelyan_pq import falcon  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "det1024_kat.json")

PINNED_COMMIT = "ce15e75bceb372867daf6b8e81918ab6978686eb"
DETERMINISTIC_C_SHA512_256 = "601390dc53521fc1b00eb962ea63d64c2d65bfe774450cf4ec59a3478e0a54a4"
APP_ID = 763809096  # TestNet app id (not load-bearing — just a fixed, realistic value)

# Fixed, network-agnostic messages: distinct (cell_id, artifact, genesis) so each sigma differs.
# genesis_hash is fixed bytes here (not a live network value) — these are off-chain wire KATs.
_CASES = [
    {"name": "cell-1-artifactA-genesisZ", "cell_id": 1,
     "artifact": sha512_256(b"trelyan KAT artifact A"), "genesis": bytes(32)},
    {"name": "cell-2-artifactB-genesis1s", "cell_id": 2,
     "artifact": sha512_256(b"trelyan KAT artifact B"), "genesis": bytes([0x11]) * 32},
    {"name": "cell-1024-artifactC-genesisSeq", "cell_id": 1024,
     "artifact": sha512_256(b"trelyan KAT artifact C"), "genesis": bytes(range(32))},
]


def main() -> int:
    signer = falcon.FalconDet1024()
    pubkey, privkey = signer.keygen()
    if len(pubkey) != falcon.PUBKEY_SIZE or len(privkey) != falcon.PRIVKEY_SIZE:
        raise SystemExit(f"unexpected key sizes pk={len(pubkey)} sk={len(privkey)}")
    if pubkey[0] != 0x0A:
        raise SystemExit(f"unexpected pubkey header {pubkey[0]:#04x} (expected 0x0A)")

    vectors = []
    for c in _CASES:
        m = build_message(APP_ID, c["cell_id"], c["artifact"], c["genesis"])
        sig = signer.sign(privkey, m)
        if sig[0] != 0xBA or sig[1] != 0x00:
            raise SystemExit(f"unexpected sig header/salt {sig[0]:#04x}/{sig[1]:#04x}")
        if not signer.verify(sig, pubkey, m):
            raise SystemExit("self-verify failed during generation — bad build?")
        vectors.append({
            "name": c["name"],
            "app_id": APP_ID,
            "cell_id": c["cell_id"],
            "artifact_hash_hex": c["artifact"].hex(),
            "genesis_hash_hex": c["genesis"].hex(),
            "message_hex": m.hex(),
            "sig_len": len(sig),
            "sig_hex": sig.hex(),
            "sig_sha512_256": sha512_256(sig).hex(),
        })

    out = {
        "_status": "POPULATED",
        "_security": ("PUBLIC TEST VECTOR — NOT SECRET. Throwaway keypair for byte-identity KATs: "
                      "bound to no cell, never used on-chain, never produced via keygen_sign_seal. "
                      "Do not use operationally."),
        "_fp_backend": ("Goldens produced by the EMULATED fixed-point FP backend (config.h "
                        "FALCON_FPEMU=1). Build the lib from the pinned source (which pins this) — do "
                        "NOT enable FALCON_FPNATIVE or -ffast-math, or byte-identity will break."),
        "_not_a_nist_kat": ("TRELYAN-pinned regression vectors for the Algorand deterministic Falcon "
                            "variant, NOT NIST FIPS-206 vectors. Header 0xBA = 0x3A | 0x80."),
        "scheme": "Deterministic Falcon-1024 (algorand/falcon, COMPRESSED, header 0xBA, salt 0x00)",
        "pinned_commit": PINNED_COMMIT,
        "deterministic_c_sha512_256": DETERMINISTIC_C_SHA512_256,
        "pubkey_hex": pubkey.hex(),
        "privkey_hex": privkey.hex(),
        "vectors": vectors,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)
        f.write("\n")
    print(f"wrote {OUT} with {len(vectors)} vectors; pubkey[0]={pubkey[0]:#04x}, "
          f"sig headers all 0xBA. COMMIT THIS FILE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
