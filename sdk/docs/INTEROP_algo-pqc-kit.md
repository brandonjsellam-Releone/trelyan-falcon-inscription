# Interop: TRELYAN inscriptions × algo-pqc-kit accounts (end-to-end post-quantum)

A concrete proposal for a joint reference between **QuantaChain `algo-pqc-kit`** (post-quantum
accounts / vaults / governance) and **TRELYAN `trelyan-pq`** (post-quantum write-once inscriptions).
Tracking discussion: `quantachain/algo-pqc-kit` issue #1.

## The idea

- **algo-pqc-kit** answers *"who may act"* — a `FalconLsig` derives an Algorand address from a
  Falcon-1024 public key and gates spending via `falcon_verify`.
- **trelyan-pq** answers *"what is recorded, immutably"* — a contract verifies a Falcon-1024
  signature via `falcon_verify` and writes a write-once inscription.

**Compose them:** make a Falcon-1024 PQ account (algo-pqc-kit `FalconLsig`) the **authority that
signs a TRELYAN inscription**. Then both the actor *and* the record are post-quantum — **no Ed25519
anywhere in the authorization path**. That's a complete PQ stack on Algorand, and a story both teams
can point to.

## Why it's clean

Both libraries verify **Falcon-1024 via the same native `falcon_verify` opcode**. The *same* Falcon
keypair can (a) control an algo-pqc-kit PQC account and (b) be the committed authority for a TRELYAN
cell. No new trust assumptions — just two layers sharing one primitive.

## The one open item (issue #1, question 2)

Reconcile the exact **deterministic compressed signature encoding** between the two signers:
algo-pqc-kit's opcode signature is documented as `[1232]B`; trelyan-pq emits the `0xBA`
deterministic-compressed form (≤1423 B). Note `1232 B` is the *typical* length and `1423 B` is the
format **max** (`SIG_COMPRESSED_MAXSIZE(10) − 40 + 1`) — the on-chain bound must stay `≤1423`, since a
hard `≤1232` cap would reject valid large signatures. Once we align on the exact bytes `falcon_verify`
accepts (a known-answer test in both directions), **one keypair signs for both layers**. Bonus:
algo-pqc-kit's signer is **pure-Python**, so aligning could let trelyan-pq drop its `ctypes`/C-library
dependency.

**The reconcile test is now scaffolded:** [`tests/test_interop_algo_pqc_kit_kat.py`](../tests/test_interop_algo_pqc_kit_kat.py)
is a bidirectional KAT that (1) asserts algo-pqc-kit reproduces the committed goldens **byte-for-byte**
(no C lib needed — the goldens are the exact bytes the live opcode accepts), (2) checks the same
private key derives the same public key in both signers ("one keypair, both layers"), and (3) with the
C lib present, cross-verifies the two signers. The full alignment contract (header `0xBA`, salt-version
`0x00`, `≤1423 B`, M signed raw, FPEMU backend) is pinned at the top of that file. Wiring is a single
`_ApkAdapter` class; until it's wired the tests skip with an actionable message.

## Demo sketch (post-reconcile)

```python
from algo_pqc_kit import FalconAccount                 # PQ account layer
from trelyan_pq.inscription import TrelyanInscriptionClient
from trelyan_client import TrelyanInscriptionFactory   # generated from the contract ARC-56

# 1) A post-quantum account (Falcon-1024; Algorand address via lsig)
pq = FalconAccount.generate()

# 2) Stand up the TRELYAN inscription app + a cell
c = TrelyanInscriptionClient.deploy_testnet(MNEMONIC, TrelyanInscriptionFactory)
c.fund_app()
cell = c.mint_cell(asset_name="TRELYAN x algo-pqc-kit")

# 3) Commit the PQ account's Falcon public key as the cell's authority
c.register_cell(cell, c.deployer.address, pq.public_key)

# 4) The SAME PQ account authorizes the inscription:
#    message M = build_message(app_id, cell, sha512_256(artifact), genesis)
#    sig = pq.sign(M)            # <-- the reconcile point (issue #1): emit 0xBA-compatible bytes
#    c.inscribe(cell, sha512_256(artifact), sig, b"ipfs://...")
#
# Result: a write-once record whose authorization chains to a post-quantum account.
```

(Until the encoding is reconciled, `trelyan-pq`'s own signer demonstrates the inscription path
end-to-end — see `examples/quickstart.py`. The interop step swaps in the algo-pqc-kit account's
signature.)

## What it proves

A real, reusable **end-to-end post-quantum pattern on Algorand** — PQ account authorizes PQ
inscription — published jointly, MIT, with on-chain TestNet evidence. For both projects it's a
genuine external integration (the signal that strengthens any xGov / grant case).

## Run (once the encoding step is aligned)

```bash
pip install algo-pqc-kit "trelyan-pq[algorand]"
export FALCON_DET1024_LIB=/path/to/libfalcondet1024.so      # only if using trelyan-pq's C signer
export DEPLOYER_MNEMONIC="<funded TestNet account>"
python examples/interop_algo_pqc_kit.py
```

MIT, commons-first. Repo: https://github.com/brandonjsellam-Releone/trelyan-falcon-inscription
