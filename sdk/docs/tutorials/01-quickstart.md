# Quickstart (5 minutes)

Install the core (stdlib-only) and, for on-chain calls, the Algorand extra:

```bash
pip install trelyan-pq                 # core: signer + message/box helpers
pip install "trelyan-pq[algorand]"     # + the high-level on-chain client
```

Build the deterministic Falcon-1024 C library once (the signer binds to it — it is not a pip
package):

```bash
# PINNED tarball, not `git clone` of the default branch. The tarball is LF on every OS;
# a clone applies the local core.autocrlf and on Windows rewrites the C sources, changing
# deterministic.c's digest. See PINNED_BUILD.md.
curl -sfL https://github.com/algorand/falcon/archive/ce15e75bceb372867daf6b8e81918ab6978686eb.tar.gz -o falcon-src.tar.gz
tar xzf falcon-src.tar.gz && cd falcon-ce15e75bceb372867daf6b8e81918ab6978686eb
# -DFALCON_UNALIGNED=0 -fno-strict-aliasing are MANDATORY, not tuning. Without the first,
# CI's own sanitizer gate proves the default autodetected build traps on a misaligned
# uint64 load; the second removes a TBAA-UB class. Omitting them builds a signer whose
# output is only accidentally byte-identical.
cc -O3 -fPIC -DFALCON_UNALIGNED=0 -fno-strict-aliasing -shared \
   -o libfalcondet1024.so codec.c common.c falcon.c fft.c fpr.c keygen.c rng.c shake.c sign.c vrfy.c deterministic.c
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
