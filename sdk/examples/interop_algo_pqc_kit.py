"""
interop_algo_pqc_kit.py — end-to-end post-quantum on Algorand:
a QuantaChain *algo-pqc-kit* PQ account + a TRELYAN *trelyan-pq* write-once inscription.

THE STORY
  algo-pqc-kit answers "who may act" (a Falcon-1024 PQ account / FalconLsig).
  trelyan-pq  answers "what is recorded, immutably" (a write-once inscription gated by falcon_verify).
  Joined: the SAME Falcon-1024 key that controls the PQ account is the committed authority for a
  TRELYAN cell — so both the actor and the record are post-quantum, with no Ed25519 in the
  authorization path.

STATUS (honest)
  Draft reference, written against both projects' PUBLIC APIs. NOT yet executed end-to-end. To run
  it you need: `pip install algo-pqc-kit "trelyan-pq[algorand]"`, the Falcon C library for
  trelyan-pq's signer (see trelyan_pq.falcon), a funded TestNet DEPLOYER_MNEMONIC, and the generated
  `TrelyanInscriptionFactory` (algokit generate client ...).

  The one open item is the exact Falcon *compressed-signature encoding* shared by both signers
  (algo-pqc-kit's opcode sig is documented as [1232]B; trelyan-pq emits 0xBA-headed, <=1423B). It is
  tracked in quantachain/algo-pqc-kit issue #1. Until it's confirmed, set INTEROP_RECONCILED = False
  to run the inscription half today with trelyan-pq's own signer; flip it to True for the full
  cross-library flow once we've aligned the bytes.
"""

from __future__ import annotations

import os

from trelyan_pq import sha512_256, build_message
from trelyan_pq.falcon import FalconDet1024
from trelyan_pq.inscription import TrelyanInscriptionClient

# Flip to True once algo-pqc-kit <-> trelyan-pq Falcon key/signature encodings are reconciled
# (quantachain/algo-pqc-kit issue #1). False = run the inscription half today (verifiable now).
INTEROP_RECONCILED = False


def main() -> None:
    mnemonic = os.environ.get("DEPLOYER_MNEMONIC")
    if not mnemonic:
        raise SystemExit("Set DEPLOYER_MNEMONIC to a funded TestNet account "
                         "(faucet: https://bank.testnet.algorand.network/).")

    # --- algo-pqc-kit: the post-quantum ACCOUNT layer ------------------------------------------
    from algo_pqc_kit import FalconAccount  # QuantaChain PQ accounts (Falcon-1024)
    pq = FalconAccount.generate()
    print(f"PQ account (algo-pqc-kit): {pq.address}")
    print(f"  Falcon pubkey: {pq.public_key.hex()[:32]}... ({len(pq.public_key)} bytes)")

    # --- trelyan-pq: the post-quantum INSCRIPTION layer ---------------------------------------
    from trelyan_client import TrelyanInscriptionFactory  # generated from the contract ARC-56
    c = TrelyanInscriptionClient.deploy_testnet(mnemonic, TrelyanInscriptionFactory)
    print(f"TRELYAN app: {c.app_id}")
    c.fund_app()
    cell = c.mint_cell(asset_name="TRELYAN x algo-pqc-kit")
    print(f"cell ASA: {cell}")

    artifact = b"end-to-end post-quantum: a PQ account authorizes a PQ inscription"
    artifact_hash = sha512_256(artifact)

    # === THE JOIN (issue #1 reconcile point) ==================================================
    if INTEROP_RECONCILED:
        # Full interop: the PQ account's own Falcon key is the cell authority, and the PQ account
        # signs the inscription message directly.
        c.register_cell(cell, c.deployer.address, pq.public_key)
        M = build_message(c.app_id, cell, artifact_hash, c.network_genesis_hash())
        sig = pq.sign(M)
        assert sig[:1] == b"\xba", (
            "algo-pqc-kit signature header != 0xBA — encoding not yet reconciled (issue #1)"
        )
    else:
        # Until reconciled: demonstrate the inscription half end-to-end with trelyan-pq's signer.
        # (The PQ account above shows the account layer; the join swaps this block for the one above.)
        signer = FalconDet1024()
        pub, priv = signer.keygen()
        c.register_cell(cell, c.deployer.address, pub)
        M = build_message(c.app_id, cell, artifact_hash, c.network_genesis_hash())
        sig = signer.sign(priv, M)

    # --- inscribe + verify --------------------------------------------------------------------
    c.inscribe(cell, artifact_hash, sig, b"ipfs://demo")
    assert c.read_back_matches(cell, artifact), "on-chain record did not match!"
    print("VERIFIED on TestNet: the write-once post-quantum inscription is written and re-verifies.")
    print("  (Set INTEROP_RECONCILED=True for the full PQ-account-authorizes-PQ-inscription flow.)")


if __name__ == "__main__":
    main()
