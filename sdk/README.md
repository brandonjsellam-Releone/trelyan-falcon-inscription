# trelyan-pq

**Post-quantum (Falcon-1024) inscription tooling for Algorand.** An open, MIT-licensed Python
SDK that turns the [TRELYAN reference implementation](https://github.com/brandonjsellam-Releone/trelyan-falcon-inscription)
into importable infrastructure: build post-quantum-authenticated, write-once records on Algorand
using the network's **native `falcon_verify` opcode**.

This package exists so you don't lose a week to the two non-obvious integration traps the
reference solved:

1. **The opcode needs *deterministic*, COMPRESSED Falcon-1024 with header `0xBA`** — generic
   liboqs/pqcrypto Falcon is randomized and gets rejected on-chain. `trelyan_pq.falcon` produces
   exactly the accepted bytes.
2. **A single app call's ApplicationArgs are capped at 2048 bytes**, but a Falcon-1024 public key
   (1793 B) + compressed signature (≤1423 B) is ~3 KB. `trelyan_pq.message` gives you the
   pubkey-box-commit + box-name helpers that mirror the contract's layout, so you commit the key
   once and pass only the signature at inscribe.

> **Status: alpha.** Validated on localnet (20/20) and Algorand TestNet. **Not externally
> audited; not for MainNet value.** Treat as a reference/building block.

## Install

```bash
pip install trelyan-pq                # core: message + encoding + signer (stdlib-only)
pip install "trelyan-pq[algorand]"    # + the high-level on-chain client (algokit-utils)
```

The signer needs the `algorand/falcon` C library built once (it is not a pip package):

```bash
git clone https://github.com/algorand/falcon && cd falcon
cc -O3 -fPIC -shared -o libfalcondet1024.so \
   codec.c common.c falcon.c fft.c fpr.c keygen.c rng.c shake.c sign.c vrfy.c deterministic.c
export FALCON_DET1024_LIB="$PWD/libfalcondet1024.so"   # .dylib on macOS, .dll on Windows
```

## Core API (no network needed)

```python
from trelyan_pq import FalconDet1024, build_message, sha512_256, box_refs

falcon = FalconDet1024()                       # uses $FALCON_DET1024_LIB
pubkey, privkey = falcon.keygen()              # 1793-byte pubkey, 2305-byte privkey

# Reconstruct the EXACT message the contract verifies on-chain (do not pre-hash it):
M = build_message(app_id=1001, cell_id=1,
                  artifact_hash=sha512_256(b"my artifact"),
                  genesis_hash=GENESIS_32_BYTES)
sig = falcon.sign(privkey, M)                  # first byte is 0xBA
assert falcon.verify(sig, pubkey, M)
assert box_refs(1) == [b"k_...", b"o_...", b"i_..."]   # the 3 boxes an inscribe touches
```

## On-chain client

```python
from trelyan_client import TrelyanInscriptionFactory          # generated from the contract ARC-56
from trelyan_pq.inscription import TrelyanInscriptionClient

c = TrelyanInscriptionClient.deploy_testnet(MNEMONIC, TrelyanInscriptionFactory)
c.fund_app()
pk, sk = c.signer.keygen()
cell = c.mint_cell()                            # clean pure-NFT cell ASA
c.register_cell(cell, c.deployer.address, pk)   # commit the Falcon key (once)
c.inscribe_bytes(cell, b"my artifact", sk, b"ipfs://...")
assert c.read_back_matches(cell, b"my artifact")
```

The generated `TrelyanInscriptionFactory` is build-specific — produce it from the contract's
ARC-56 with `algokit generate client ...` (see the reference repo) and pass the class in.

## What's in the box

| Module | Needs | Purpose |
|---|---|---|
| `trelyan_pq.message` | stdlib only | byte-exact message `M`, sha512_256, box names/refs, constants |
| `trelyan_pq.falcon` | the Falcon C lib | deterministic Falcon-1024 keygen / sign / verify (0xBA encoding) |
| `trelyan_pq.inscription` | `[algorand]` extra | high-level deploy / register / inscribe / read-back client |

## Develop / test

```bash
pip install "trelyan-pq[dev]"
PYTHONPATH=src pytest tests -v        # pure-Python wire-format tests (no lib/network needed)
```

## Security & scope

- **Scope:** this is **app-level post-quantum inscription signing** — a contract verifies a
  Falcon-1024 signature and writes a write-once record. It is **not** a replacement for
  Algorand account/transaction authentication or consensus security.
- **Unaudited, alpha.** Validated on localnet (20/20) and TestNet; **not externally audited**
  and **not for MainNet value**. An independent audit is planned before any MainNet use.
- **Native C dependency.** The signer is a `ctypes` binding to the `algorand/falcon` C library
  you build yourself — provenance and a reproducible build are your responsibility. No
  constant-time / side-channel guarantees are claimed for the binding.
- **Sign through `sign_inscription()`**, not raw `sign()`: the domain-separated message binds
  `app_id`, `cell_id`, artifact, and network genesis, which is what makes a signature
  non-replayable across apps/cells/networks.
- **Disclosure:** report security issues privately per the reference repo's `SECURITY.md`.
- Independent of, and not endorsed by, the Algorand Foundation.

## License

MIT. See the [reference repository](https://github.com/brandonjsellam-Releone/trelyan-falcon-inscription)
for the protocol spec, threat model, and validation record.
