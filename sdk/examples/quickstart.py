"""
Quickstart — end-to-end TRELYAN post-quantum inscription on Algorand TestNet, via trelyan_pq.

This is the 150-line reference deploy script reduced to a handful of SDK calls.

Prereqs
  pip install "trelyan-pq[algorand]"
  export FALCON_DET1024_LIB=/path/to/libfalcondet1024.so          # see trelyan_pq.falcon
  export DEPLOYER_MNEMONIC="<25-word funded TestNet account>"     # faucet: https://bank.testnet.algorand.network/
  # generate the typed client from the contract ARC-56:
  #   algokit generate client crypto/contracts/out/TrelyanInscription.arc56.json --output trelyan_client.py

  python quickstart.py
"""

import os

from trelyan_client import TrelyanInscriptionFactory  # generated typed app client
from trelyan_pq.inscription import TrelyanInscriptionClient


def main() -> None:
    mnemonic = os.environ.get("DEPLOYER_MNEMONIC")
    if not mnemonic:
        raise SystemExit(
            "Set DEPLOYER_MNEMONIC to a funded TestNet account "
            "(fund free at https://bank.testnet.algorand.network/)."
        )

    c = TrelyanInscriptionClient.deploy_testnet(mnemonic, TrelyanInscriptionFactory)
    print(f"app deployed: {c.app_id}")

    c.fund_app()                                   # box min-balance
    pubkey, privkey = c.signer.keygen()            # deterministic Falcon-1024 keypair
    cell = c.mint_cell(asset_name="TRELYAN cell #demo")
    print(f"cell ASA: {cell}")

    c.register_cell(cell, c.deployer.address, pubkey)   # commit the key (once)
    artifact = b"hello, after Q-Day"
    h = c.inscribe_bytes(cell, artifact, privkey, b"ipfs://demo-artifact")
    print(f"inscribed cell {cell}; artifact hash {h.hex()}")

    assert c.read_back_matches(cell, artifact), "on-chain record did not match!"
    print("verified on-chain: the post-quantum inscription is written and re-verifies.")


if __name__ == "__main__":
    main()
