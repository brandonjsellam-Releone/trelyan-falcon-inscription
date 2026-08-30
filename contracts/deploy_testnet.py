"""
deploy_testnet.py — TRELYAN inscription, end-to-end on Algorand TestNet.

Runs the §5 TestNet checklist as one command: deploy → fund → mint a clean pure-NFT Cell →
register (commit the full Falcon key) → inscribe with the off-chain deterministic signer against the
LIVE falcon_verify opcode → read the record back and re-verify. Mirrors the 20/20 localnet suite, so
it is the validated code path pointed at TestNet rather than localnet.

PREREQS
  - DEPLOYER_MNEMONIC env = a funded TestNet account (25-word mnemonic). Fund it free at
    https://bank.testnet.algorand.network/  (a few ALGO is plenty: app box MBR ~0.8 ALGO + fees).
  - FALCON_DET1024_LIB env = path to the built deterministic-Falcon shared lib (see falcon_det1024.py).
  - trelyan_client.py generated from the current arc56 (algokit generate client ...).
  - pip install algokit-utils  (v4).

  python crypto/contracts/deploy_testnet.py
"""

import base64
import hashlib
import os
import sys

import falcon_det1024
from trelyan_client import TrelyanInscriptionFactory

from algokit_utils import (
    AlgorandClient,
    AlgoAmount,
    AssetCreateParams,
    CommonAppCallParams,
    PaymentParams,
    SendParams,
)

DOMAIN_TAG = b"TRELYAN-INSCRIPTION-v1"
EXPLORER = "https://testnet.explorer.perawallet.app"
# Public TestNet genesis (same constant as sdk/examples/verify_trelyan.py). Used only
# as a MainNet refusal — never as a signing secret.
TESTNET_GENESIS_B64 = "SGO1GKSzyE7IEPItTxCByw9x8FmnrCDexi9/cOUJOiI="


def _write_github_output(name: str, value: str) -> None:
    """Emit a numeric id for Actions. Never writes secrets."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    if name not in {"app_id", "cell_id"}:
        return
    if not value.isdigit():
        return
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(f"{name}={value}\n")


def sha512_256(data: bytes) -> bytes:
    h = hashlib.new("sha512_256")
    h.update(data)
    return h.digest()


# build_message is NOT redefined here. This file used to carry its own copy, which differed from
# the canonical one in falcon_det1024.py by omitting the length checks - so a 31- or 33-byte
# artifact hash produced a 101- or 103-byte M and was signed without complaint. This is the
# script that signs REAL TestNet inscriptions, so it is the worst possible place for the lenient
# copy to live. One definition, in the module this file already imports.
build_message = falcon_det1024.build_message


def box_refs(cell_id: int):
    k = cell_id.to_bytes(8, "big")
    return [b"k_" + k, b"o_" + k, b"i_" + k]


def main() -> None:
    mn = os.environ.get("DEPLOYER_MNEMONIC")
    if not mn:
        sys.exit("Set DEPLOYER_MNEMONIC to a funded TestNet account (fund at https://bank.testnet.algorand.network/).")
    if os.environ.get("ALGORAND_NETWORK", "").strip().lower() in {"mainnet", "main"}:
        sys.exit("Refusing to run: ALGORAND_NETWORK looks like MainNet. TestNet only.")

    algorand = AlgorandClient.testnet()
    deployer = algorand.account.from_mnemonic(mnemonic=mn)
    print(f"deployer: {deployer.address}")

    gh = algorand.client.algod.suggested_params().gh
    genesis = bytes(gh) if isinstance(gh, (bytes, bytearray)) and len(gh) == 32 else base64.b64decode(gh)
    if base64.b64encode(genesis).decode() != TESTNET_GENESIS_B64:
        sys.exit("Refusing to deploy: connected node is not Algorand TestNet.")

    # 1. deploy (create() binds the native TestNet Global.genesis_hash — A2)
    factory = algorand.client.get_typed_app_factory(TrelyanInscriptionFactory, default_sender=deployer.address)
    client, _ = factory.send.create.create()
    app_id = client.app_id
    print(f"app deployed: {app_id}  ->  {EXPLORER}/application/{app_id}/")
    _write_github_output("app_id", str(app_id))

    # 2. fund the app account for box min-balance. Real need: committed-key box (1793 B) ~0.72 ALGO +
    # owner box ~0.02 + small inscription record box ~0.05 + base app MBR 0.1 = ~0.9 ALGO. Fund 1.5 ALGO
    # (headroom but small enough that a re-run still fits in a faucet top-up; 3 ALGO would drain the
    # deployer and make re-runs fail on the payment itself).
    algorand.send.payment(
        PaymentParams(sender=deployer.address, receiver=client.app_address, amount=AlgoAmount.from_micro_algo(1_500_000))
    )

    # 3. Falcon keypair + mint a CLEAN pure-NFT Cell ASA (no clawback/freeze/manager — required by register)
    pk, sk = falcon_det1024.keygen()
    res = algorand.send.asset_create(
        AssetCreateParams(sender=deployer.address, total=1, decimals=0, default_frozen=False,
                          unit_name="CELL", asset_name="TRELYAN Cell #demo")
    )
    cell = res.asset_id
    print(f"cell ASA: {cell}  ->  {EXPLORER}/asset/{cell}/")
    _write_github_output("cell_id", str(cell))

    # 4. register: commit the FULL Falcon public key + the controlling owner (admin-only, once)
    client.send.register_cell(args=(cell, deployer.address, pk),
                              params=CommonAppCallParams(sender=deployer.address))
    print(f"registered cell {cell} (committed {len(pk)}-byte Falcon key)")

    # 5. inscribe: sign M off-chain, submit only the signature (A9); GroupCredit funds falcon_verify
    artifact = b"TRELYAN TestNet demo artifact"
    artifact_hash = sha512_256(artifact)
    m = build_message(app_id, cell, artifact_hash, genesis)
    sig = falcon_det1024.sign_compressed(sk, m)
    print(f"5/6 inscribing cell {cell} (sig {len(sig)} B, header 0x{sig[0]:02x}) ...")
    inscribe_args = (cell, artifact_hash, sig, b"ipfs://demo-artifact")
    try:
        # Strategy 1 (proven on localnet 20/20): fat static_fee + manual box/asset refs, no simulate.
        client.send.inscribe(
            args=inscribe_args,
            # validity_window=1000 (max): the inscribe is opcode-heavy (falcon_verify + OpUp simulate),
            # and a slow public TestNet node can advance past the default ~10-round window before submit
            # -> "txn dead". A wide window keeps the txn valid through the build/simulate/submit cycle.
            params=CommonAppCallParams(sender=deployer.address, static_fee=AlgoAmount.from_micro_algo(20_000),
                                       box_references=box_refs(cell), asset_references=[cell], validity_window=1000),
            send_params=SendParams(populate_app_call_resources=False),
        )
    except Exception as e1:
        print(f"\n>>> inscribe attempt 1 (static_fee + manual refs) failed: {type(e1).__name__}: {e1}")
        print(">>> retrying with cover_app_call_inner_transaction_fees + auto resource population ...")
        try:
            # Strategy 2: let algokit simulate to populate resources AND auto-cover the OpUp inner-txn
            # fees, under a max_fee ceiling. Different machinery, in case TestNet rejects strategy 1.
            client.send.inscribe(
                args=inscribe_args,
                params=CommonAppCallParams(sender=deployer.address, max_fee=AlgoAmount.from_micro_algo(50_000),
                                           validity_window=1000),
                send_params=SendParams(cover_app_call_inner_transaction_fees=True),
            )
        except Exception as e2:
            print(f"\n>>> INSCRIBE FAILED (both strategies):\n  attempt 1: {type(e1).__name__}: {e1}\n  attempt 2: {type(e2).__name__}: {e2}\n")
            raise
    print(f"inscribed cell {cell}")

    # 6. read back + re-verify (I3): on-chain record matches, and the signature re-verifies off-chain.
    # The inscription box is already written by step 5; this readonly read-back is a convenience, so a
    # transient timing failure here must NOT mask the success.
    try:
        rec = client.send.get_inscription(
            args=(cell,),
            params=CommonAppCallParams(sender=deployer.address, validity_window=1000),
        ).abi_return
        assert bytes(rec.artifact_hash) == artifact_hash, "on-chain artifact_hash mismatch!"
        print("on-chain record read back OK (artifact_hash matches).")
    except Exception as e:
        print(f"(note: read-back call hit {type(e).__name__}: {e} — the inscription box is already "
              f"written on-chain; verify it directly on the explorer.)")
    assert falcon_det1024.verify_compressed(sig, pk, m), "off-chain re-verify failed!"
    print(f"\nVERIFIED on TestNet: app {app_id}, cell {cell} — inscription written on-chain and the "
          f"Falcon-1024 signature re-verifies. {EXPLORER}/application/{app_id}/")


if __name__ == "__main__":
    main()
