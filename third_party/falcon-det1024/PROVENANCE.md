# PROVENANCE — `third_party/falcon-det1024/`

Vendored copy of the **deterministic Falcon-1024 reference C implementation** that TRELYAN's
signing path is built from, at the commit tag `v0.1.0` resolves to: the version `go-algorand`'s
`go.mod` requires for the module its `falcon_verify` opcode calls (what was checked, and when, is
under "Why this commit" below). This directory is a byte-for-byte subset of one pinned upstream
commit. It is **consumed, never edited**
(constitution §0 Tier 2, §2.6): if upstream must change, re-vendor from a new pinned tarball and
update this file, `SHA256SUMS`, and the KAT goldens together in one reviewed diff.

## Upstream

| Field | Value |
|---|---|
| Repository | `https://github.com/algorand/falcon` |
| Commit | `ce15e75bceb372867daf6b8e81918ab6978686eb` |
| Fetched as | `https://github.com/algorand/falcon/archive/ce15e75bceb372867daf6b8e81918ab6978686eb.tar.gz` (the GitHub source **tarball**, not a clone — a clone applies the runner's `core.autocrlf` and can change bytes) |
| Tarball size | 1,391,487 bytes |
| Tarball SHA-256 | `dfac3e6f211b1d30589e75eeeaa8b64e13694076b2d0221106857ae1afb5ff30` |
| Vendored on | 2026-08-18 |
| Cross-check | `cd third_party/falcon-det1024 && sha256sum -c SHA256SUMS` &mdash; **27 of 27 OK**, re-verified 2026-08-30. This replaces a citation of a locally-kept evidence tree that is no longer on disk; see the note below. A command an auditor can run beats a document only one machine ever had |
| Upstream version string | `README.txt`: "DETERMINISTIC FALCON IMPLEMENTATION — Version: 2021-12-03" |

**Why this commit and not HEAD:** `go-algorand`'s `go.mod` requires `github.com/algorand/falcon`
at `v0.1.0`, that tag resolves to `ce15e75b`, and `go-algorand`'s `go.sum` pins exactly the bytes
of this tree for it. It is also the commit the SDK's KAT goldens
(`sdk/tests/vectors/det1024_kat.json`, `pinned_commit`) were produced from. `go-algorand` does
**not** vendor it. What was checked on 2026-09-14, from primary sources:

- `go-algorand`'s `go.mod` requires `github.com/algorand/falcon v0.1.0`, with no `replace`
  directive, on `master` (`3f804559`) and at tag `v4.3.0-stable` (`3e5d694b`).
- `v0.1.0` is an annotated tag (object `ebbdb56e`) that peels to commit
  `ce15e75bceb372867daf6b8e81918ab6978686eb` (`git ls-remote https://github.com/algorand/falcon`).
  `https://proxy.golang.org/github.com/algorand/falcon/@v/v0.1.0.info` records the same commit
  as its `Origin.Hash`.
- At both refs, `go.sum` pins `github.com/algorand/falcon v0.1.0` to
  `h1:xl832kfZ7hHG6B4p90DQynjfKFGbIUgUOnsRiMZXfAo=`. Recomputing that hash over the 27 files of
  `src/` gives the same value (Go's `dirhash` Hash1: one line per file, ordered by path in byte
  order, each line `<hex sha256 of file>  github.com/algorand/falcon@v0.1.0/<path>` ending in a
  newline; the value is `h1:` + base64 of the SHA-256 of the concatenated lines).
- `go-algorand` has **no `vendor/` directory** at either ref. The Go toolchain downloads the
  module at build time and checks it against that `go.sum` line.
- In that source, `opFalconVerify` (`data/transactions/logic/crypto.go`) calls
  `crypto.FalconVerifier.VerifyBytes` (`crypto/falconWrapper.go`), which calls this module's
  `PublicKey.Verify` (`src/falcon.go`), a cgo call into `falcon_det1024_verify_compressed`.
- **Not checked:** which `go-algorand` version or build any TestNet or MainNet node runs. Every
  statement above is about source code and published module metadata, not about a running node.

Upstream resumed activity in 2026 and its default branch has moved. **Do not bump the pin.** The
reason needs no separate document: this commit is the one `go-algorand`'s source resolves for
`falcon_verify` (checked as above), and it is what the KAT goldens were produced from. Bumping it
would make TRELYAN's signer source differ from that verifier source, and would leave
`sdk/tests/vectors/det1024_kat.json` recording a `pinned_commit` this tree no longer holds, in the
same move.

> **A citation removed on 2026-08-30.** This paragraph pointed at
> `FALCON_PIN_BUMP_EVIDENCE_2026-08-11.md` for that reasoning. **That file does not exist** &mdash;
> not in this repository and not anywhere on the machine that was supposed to hold it. It was
> found by resolving every document citation in the repository against the filesystem. The
> reasoning it was said to contain is stated inline above instead, because a reason an auditor can
> read is worth more than a reference to a document nobody can produce.

## Layout, and what is vendored

```
third_party/falcon-det1024/
├── PROVENANCE.md      this file
├── SHA256SUMS         one line per vendored file (paths relative to this directory)
└── src/               the upstream tree, EXACTLY — 27 files, byte-identical to the tarball
```

`src/` is the complete pinned tree, not a subset, so the SDK's existing verifier runs on it
unchanged: `python sdk/ci/verify_pinned_digest.py third_party/falcon-det1024/src` reports the
pinned tree digest `c6adf4871389dfdbf3ffbd853bd9e5ce15646b821d6dc84e327ab1b3d2adc980`, file count
27, `deterministic.c` sha512/256 `601390dc53521fc1b00eb962ea63d64c2d65bfe774450cf4ec59a3478e0a54a4`
— the same numbers CI checked against the downloaded tarball before this tree existed. Keeping the
tree exact is what makes "vendored" and "pinned" the same claim rather than two.

Contents of `src/`:

- Library sources (the 11 files every TRELYAN build compiles): `codec.c common.c deterministic.c falcon.c fft.c fpr.c keygen.c rng.c shake.c sign.c vrfy.c`
- Headers: `falcon.h deterministic.h config.h fpr.h inner.h`
- Upstream build file and docs: `Makefile`, `README.txt`, `falcon-det.pdf` (the deterministic-mode design note)
- Upstream tests: `tests/test_deterministic.c`, `tests/test_deterministic_kat.h`, `tests/test_falcon.c`, `tests/speed.c`
- **Go binding, present for digest-identity only, never built:** `falcon.go`, `falcon_test.go`,
  `go.mod`, `go.sum`. TRELYAN authors no Go (constitution §0) and no TRELYAN build step reads
  these four files; they are here so the tree digest above stays exactly the pinned one. A
  language inventory of this repository should count them as vendored upstream, not authored.

## Configuration that the KAT goldens depend on

`config.h` in `src/` has exactly five active `#define`s: **`FALCON_FPEMU 1`, `FALCON_FPNATIVE 0`,
`FALCON_ASM_CORTEXM4 0`, `FALCON_AVX2 0`, `FALCON_FMA 0`** — the emulated fixed-point
floating-point backend. (`FALCON_LE` and `FALCON_UNALIGNED` appear only inside comment blocks
and are therefore autodetected unless passed with `-D`.) The SDK's KAT goldens were produced with
exactly this backend (`det1024_kat.json` → `_fp_backend`). Building with a native FP backend can
change signature bytes on some platforms and would fail the byte-identity KAT by design.

Every TRELYAN consumer of this tree (the ctypes SDK build in `ci.yml`, the Rust `trelyan-pq-ffi`
crate) compiles the 11 library sources **as-is, with this `config.h`, plus exactly the flags CI
already proves byte-identical to the goldens: `-DFALCON_UNALIGNED=0 -fno-strict-aliasing`**
(portable byte-wise PRNG reads instead of the misaligned-`uint64` fast path; TBAA-safe
type-punning — see `FALCON_BUILD_HARDENING` §2 and the sanitizer gate in `ci.yml`). Those are
compiler flags, not source edits: the tree digest is unaffected. Never add `-ffast-math`,
`-DFALCON_FPNATIVE=1`, `-DFALCON_AVX2=1` or `-DFALCON_FMA=1`.

Sizes fixed by these headers (logn = 10): `FALCON_DET1024_PUBKEY_SIZE = 1793`,
`FALCON_DET1024_PRIVKEY_SIZE = 2305`, `FALCON_DET1024_SIG_COMPRESSED_MAXSIZE = 1423`
(= `FALCON_SIG_COMPRESSED_MAXSIZE(10)` 1462 − 40-byte salt + 1 salt-version byte), compressed
header byte `0xBA` (= `0x3A | 0x80`), `FALCON_DET1024_CURRENT_SALT_VERSION = 0`.

## Licence status — stated exactly

- 18 of the 22 C/H/Makefile/README files carry the upstream **MIT** header (Thomas Pornin's
  Falcon reference implementation, "Permission is hereby granted, free of charge…").
- **Four files carry NO licence or copyright header at all:** `deterministic.c`,
  `deterministic.h`, `tests/test_deterministic.c`, `tests/test_deterministic_kat.h` — the
  Algorand-authored deterministic layer. (The four Go files were not assessed; TRELYAN does not
  compile or distribute them separately.)
- **The upstream repository has no `LICENSE` file.** This is a known, open item
  (upstream issues #4 and #11 unanswered since 2022;
  a comment on #4 is drafted and not yet sent). Until upstream states terms, TRELYAN's position
  is *risk accepted, documented, ask outstanding* — recorded here so an auditor finds it in the
  vendored tree, not only in a workspace note.
  (A citation to `FINDING_falcon-licensing_2026-08-11.md` was removed here on 2026-08-30 for the
  same reason as above: the file does not exist. Nothing was lost by removing it &mdash; the
  finding's whole substance is the sentence it was attached to.)

## How to verify this tree

```bash
cd third_party/falcon-det1024 && sha256sum -c SHA256SUMS
```
```bash
python sdk/ci/verify_pinned_digest.py third_party/falcon-det1024/src
```

`SHA256SUMS` covers every file under `src/` (27 lines). CI runs both checks on every push and PR
(`vendored-falcon-integrity` job); a re-vendor that forgets to regenerate the sums, or that drifts
from the pinned digest, fails there — which is the point. The `signature-kat`, `contract-tests`
and TestNet jobs build the library **from this tree**, with no network fetch.

To re-derive from upstream rather than trust this tree:

```bash
curl -sfL https://github.com/algorand/falcon/archive/ce15e75bceb372867daf6b8e81918ab6978686eb.tar.gz -o falcon.tar.gz
sha256sum falcon.tar.gz   # expect dfac3e6f211b1d30589e75eeeaa8b64e13694076b2d0221106857ae1afb5ff30
```

then extract and compare each vendored path with `sha256sum`.

## Zero-patch ledger

| Date | File | Change | Reason |
|---|---|---|---|
| — | — | **none** | The tree is unmodified upstream bytes. Any row added here means the "consumed, never edited" rule was broken and must carry a Security Impact note. |
