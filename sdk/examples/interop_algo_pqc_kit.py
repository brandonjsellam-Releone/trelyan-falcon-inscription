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

  TWO open items, and they are different in kind:

  1. The Falcon *compressed-signature encoding* shared by both signers (algo-pqc-kit's opcode sig is
     documented as [1232]B; trelyan-pq emits 0xBA-headed, <=1423B). Tracked in
     quantachain/algo-pqc-kit issue #1.

  2. **trelyan-pq has no entry point that submits an externally produced signature.**
     `TrelyanInscriptionClient.inscribe(cell_id, artifact_hash, privkey, ...)` takes a PRIVATE KEY
     and re-derives M and re-signs internally (inscription.py:135-136). So the full cross-library
     flow — where the algo-pqc-kit account signs and TRELYAN submits those bytes — cannot be
     expressed against today's SDK at all, regardless of how issue #1 lands. It needs a new
     `inscribe_presigned(cell_id, artifact_hash, signature, ...)`, which is a design decision, not
     a patch.

  INTEROP_RECONCILED = False runs the inscription half today with trelyan-pq's own signer, and is
  the only branch that can execute. Setting it True stops with an explicit error rather than
  pretending: see the branch below.
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
        # The full cross-library flow needs to submit a signature produced by the PQ account.
        # There is no SDK method that accepts one: inscribe() and inscribe_bytes() both take a
        # PRIVATE KEY and sign internally. Writing this branch against the current API would mean
        # passing pq.sign(M) into the `privkey` parameter, which is what this file used to do --
        # it failed at falcon.py:192 ("privkey must be 2305 bytes"), in both branches, so the
        # example had never run as shipped. Stopping here is the honest state of the interop.
        raise SystemExit(
            "INTEROP_RECONCILED=True cannot run yet: trelyan-pq has no inscribe_presigned() entry "
            "point, so an externally produced Falcon signature cannot be submitted. This is a "
            "missing API, not a configuration problem -- see this file's STATUS item 2. The PQ "
            "account layer above is real and does run; only the join is blocked."
        )

    # Until reconciled: demonstrate the inscription half end-to-end with trelyan-pq's signer.
    # (The PQ account above shows the account layer; the join swaps this block for the one above.)
    signer = FalconDet1024()
    pub, priv = signer.keygen()
    c.register_cell(cell, c.deployer.address, pub)

    # M is shown for reference only -- inscribe() re-derives it from the same canonical
    # build_message() and signs with `priv` itself, so passing a signature here would be wrong.
    M = build_message(c.app_id, cell, artifact_hash, c.network_genesis_hash())
    print(f"  message M to be signed: {len(M)} bytes")

    # --- inscribe + verify --------------------------------------------------------------------
    c.inscribe(cell, artifact_hash, priv, b"ipfs://demo")
    assert c.read_back_matches(cell, artifact), "on-chain record did not match!"
    print("VERIFIED on TestNet: the write-once post-quantum inscription is written and re-verifies.")
    print("  (The full PQ-account-authorizes-PQ-inscription flow needs inscribe_presigned(); see STATUS.)")


if __name__ == "__main__":
    main()
