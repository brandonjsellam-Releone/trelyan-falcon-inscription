# End-to-end — deploy, register, inscribe, verify (TestNet)

With the `[algorand]` extra and the generated typed client (built from the contract's ARC-56),
the full flow is a handful of calls:

```python
from trelyan_client import TrelyanInscriptionFactory          # generated: algokit generate client ...
from trelyan_pq.inscription import TrelyanInscriptionClient

c = TrelyanInscriptionClient.deploy_testnet(MNEMONIC, TrelyanInscriptionFactory)
c.fund_app()                                    # box min-balance (~0.9 ALGO)
pk, sk = c.signer.keygen()
cell = c.mint_cell()                            # clean pure-NFT cell ASA (total=1, decimals=0)
c.register_cell(cell, c.deployer.address, pk)   # commit the Falcon key (once)
c.inscribe_bytes(cell, b"my artifact", sk, b"ipfs://...")
assert c.read_back_matches(cell, b"my artifact")
```

`inscribe_bytes` does the right thing end-to-end: it hashes the artifact (`sha512_256`), builds
the domain-separated message, signs it deterministically (header `0xBA`), and submits — handling
the opcode budget, the box references, and a fee-fallback strategy proven on localnet (20/20) and
on TestNet.

Reads:

```python
rec = c.get_inscription(cell)                   # on-chain InscriptionRecord (readonly)
bytes(rec.artifact_hash) == sha512_256(b"my artifact")
```

Already deployed and verified on TestNet (app **763809096**) — see [DEMO](../DEMO.md) to reproduce.

> Status: alpha — TestNet, not externally audited, not for MainNet value.
