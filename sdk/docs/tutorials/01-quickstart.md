# Quickstart (5 minutes)

Install the core (stdlib-only) and, for on-chain calls, the Algorand extra:

```bash
pip install trelyan-pq                 # core: signer + message/box helpers
pip install "trelyan-pq[algorand]"     # + the high-level on-chain client
```

Build the deterministic Falcon-1024 C library once (the signer binds to it — it is not a pip
package):

```bash
git clone https://github.com/algorand/falcon && cd falcon
cc -O3 -fPIC -shared -o libfalcondet1024.so \
   codec.c common.c falcon.c fft.c fpr.c keygen.c rng.c shake.c sign.c vrfy.c deterministic.c
export FALCON_DET1024_LIB="$PWD/libfalcondet1024.so"   # .dylib on macOS, .dll on Windows
```

Sign and verify an inscription message — no chain needed:

```python
from trelyan_pq import FalconDet1024, sha512_256

falcon = FalconDet1024()
pubkey, privkey = falcon.keygen()                 # 1793-byte pubkey, 2305-byte privkey

app_id, cell_id = 763809096, 1
artifact_hash = sha512_256(b"my artifact")
genesis_hash  = bytes(32)                          # use the real network genesis on-chain

sig = falcon.sign_inscription(privkey, app_id, cell_id, artifact_hash, genesis_hash)
assert sig[0] == 0xBA                              # exactly the encoding falcon_verify accepts
assert falcon.verify_inscription(sig, pubkey, app_id, cell_id, artifact_hash, genesis_hash)
```

Prefer `sign_inscription` / `verify_inscription` over raw `sign` / `verify`: they build the
domain-separated message that binds app, cell, artifact, and network, so a signature can't be
replayed elsewhere.

Next: [Trap 1 — the 0xBA header](02-deterministic-falcon-0xBA.md) ·
[Trap 2 — the 2048-byte arg cap](03-arg-cap-box-commit.md) ·
[End-to-end on TestNet](04-end-to-end-inscribe-verify.md).
