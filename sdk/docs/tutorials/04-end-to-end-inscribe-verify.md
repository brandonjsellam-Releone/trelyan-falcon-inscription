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
the opcode budget, the box references, and a two-strategy submit. The primary path (fat static fee +
manual box/asset references) uses the same fee and resource parameters as the contract's LocalNet
suite (20/20 on 2026-06-01, against the pre-2026-06-16 contract; 28/28 in CI on 2026-09-04), which
exercises them through the contract test harness, not this client. The auto-populate + inner-fee
fallback is unit-tested against fakes (`sdk/tests/test_inscribe_retry_is_not_blind.py`) and has no
recorded live run.

Reads:

```python
rec = c.get_inscription(cell)                   # on-chain InscriptionRecord (readonly)
bytes(rec.artifact_hash) == sha512_256(b"my artifact")
```

Already deployed on TestNet (app **770964251**; its approval and clear-state programs match what the committed TEAL assembles to, and its state schemas and extra-program-pages match the committed artifacts; its global-state contents, boxes and creator are not compared) — see [DEMO](../DEMO.md) to reproduce.

> Status: alpha — TestNet, not externally audited, not for MainNet value.
