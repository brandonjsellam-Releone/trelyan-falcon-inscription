# Pinned signing-library build

All TRELYAN signing (`trelyan_pq.falcon`) builds the deterministic Falcon-1024 library from exactly this source:

**Repository:** https://github.com/algorand/falcon
**Pinned commit:** `ce15e75bceb372867daf6b8e81918ab6978686eb` (committed 2023-06-08 — the upstream library has been frozen for three years; stability is a property, not an accident)
**Source-tree digest (sha512_256, 27 files):** `c6adf4871389dfdbf3ffbd853bd9e5ce15646b821d6dc84e327ab1b3d2adc980`
**deterministic.c (sha512_256):** `601390dc53521fc1b00eb962ea63d64c2d65bfe774450cf4ec59a3478e0a54a4`

Reproduce the tree digest on any machine:

```bash
curl -sL https://github.com/algorand/falcon/archive/ce15e75bceb372867daf6b8e81918ab6978686eb.tar.gz | tar xz
cd falcon-ce15e75b* && python3 - <<'EOF'
import hashlib, os
def h(p):
    d = hashlib.new('sha512_256'); d.update(open(p,'rb').read()); return d.hexdigest()
files = sorted(os.path.join(r,f) for r,_,fs in os.walk('.') for f in fs)
t = hashlib.new('sha512_256')
for f in files: t.update((f.lstrip('./') + ':' + h(f) + '\n').encode())
print(t.hexdigest())
EOF
```

Why this matters for a deterministic signer: det1024 signatures are a pure function of the key and the message, so any build divergence in the floating-point sampler is a correctness *and* security concern. Pinning the source is the first layer; cross-platform signature-level known-answer tests in CI are the second (roadmap item, pre-MainNet); the SDK's sign-once key lifecycle is the third.
