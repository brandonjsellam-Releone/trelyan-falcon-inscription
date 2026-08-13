# Pinned signing-library build

All TRELYAN signing (`trelyan_pq.falcon`) builds the deterministic Falcon-1024 library from exactly this source:

**Repository:** https://github.com/algorand/falcon
**Pinned commit:** `ce15e75bceb372867daf6b8e81918ab6978686eb` (committed 2023-06-08)

> [!IMPORTANT]
> **This pin is deliberate: it is the release the Algorand network itself runs.**
> `go-algorand`'s `go.mod` requires `github.com/algorand/falcon v0.1.0`, and that tag dereferences
> to exactly `ce15e75b`. It is the repository's only tag. Pinning here is therefore *alignment with
> the code that defines on-chain `falcon_verify` behaviour*, not staleness — which is the whole
> point for a signer whose output must be accepted byte-for-byte by that verifier.
>
> **Upstream has moved, but has not released.** `algorand/falcon` was quiet from 2023-06 to
> 2026-06 and resumed in June–July 2026. `main` is currently `956d9bc0` (2026-07-01), **7 commits
> ahead, 0 behind** — an untagged, unreleased descendant. Its security-relevant change is PR #16:
> `convert_compressed_to_ct` gains a `< 2` length guard (preventing a `size_t` underflow, since
> `sig_compressed_len - 2` wraps to `SIZE_MAX` on a 1-byte input) and rejects trailing bytes after
> the decoded signature; `verify_compressed` reorders its max-size check to avoid the same class of
> overflow.
>
> **Scope, stated precisely:** that is *non-canonical input acceptance in a parser*, **not**
> signature malleability — no distinct valid signatures for one (key, message) pair are produced or
> accepted by either build. And `falcon_det1024_convert_compressed_to_ct` is **not bound by this
> SDK at all** (`trelyan_pq.falcon` binds only `shake256_init_prng_from_system`, `keygen`,
> `sign_compressed`, `verify_compressed`), so it is unreachable from TRELYAN. It *is* reachable in
> go-algorand via `GetFixedLengthHashableRepresentation` → `ConvertToCT`, which makes it an upstream
> matter to report rather than a reason to diverge from the network's release.
>
> Bumping was tested rather than assumed: both trees were built with `FALCON_FPEMU=1` and compared
> over **120 signatures (12 keypairs × 10 message shapes)** plus the committed KAT — byte-identical
> throughout, with each build accepting the other's output. So a bump would be *safe*; it would
> simply make this repo stricter than the deployed verifier for no reachable benefit. **Any future
> pin bump MUST still be gated on re-running the byte-identity KAT** — a silent sampler or encoding
> change would be catastrophic for a deterministic signer.
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
