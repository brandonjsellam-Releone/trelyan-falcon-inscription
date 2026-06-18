# Verifying a `trelyan-pq` release

Every tagged release (`v*`) of the `trelyan-pq` SDK is published by
[`.github/workflows/release.yml`](.github/workflows/release.yml) with two
independent supply-chain proofs that the artifact you downloaded was built from
**this repository at that exact tag**:

1. **SLSA provenance** (`*.intoto.jsonl`) — a Sigstore-signed, Build-L3
   attestation produced by the official
   [`slsa-github-generator`](https://github.com/slsa-framework/slsa-github-generator)
   generic generator, verifiable with `slsa-verifier`.
2. **cosign keyless signature** (`*.cosign.bundle`, plus `*.sig` / `*.pem`) —
   a Sigstore blob signature tied to this repo's GitHub Actions OIDC identity,
   verifiable with `cosign`.

Both are attached to the GitHub Release alongside the `.whl` and `.tar.gz`.

> **Status / honesty note.** TRELYAN is an UNAUDITED reference implementation.
> These steps prove *build provenance and artifact integrity* (the bytes came
> from this repo+tag and were not altered) — they do **not** constitute a
> security audit of the code itself. The commands below have not yet been run
> against a real published tag; the first actual `v*` release run is required to
> confirm the asset names and the recorded builder/identity strings. Adjust the
> filenames to match what the Release actually carries.

---

## 0. Download the release assets

Pick a tag (here `v0.1.0`) and fetch the artifact plus its proofs. With the
GitHub CLI:

```bash
TAG=v0.1.0
gh release download "$TAG" \
  --repo brandonjsellam-Releone/trelyan-falcon-inscription \
  --dir ./verify

cd verify
ls -l
# Expected (names confirmed by the first real release):
#   trelyan_pq-0.1.0-py3-none-any.whl
#   trelyan_pq-0.1.0.tar.gz
#   trelyan-pq.intoto.jsonl                 <- SLSA provenance
#   *.cosign.bundle  *.sig  *.pem           <- cosign keyless material
```

---

## (a) Verify the SLSA provenance with `slsa-verifier`

`slsa-verifier` checks the Sigstore signature on the provenance **and** that the
provenance binds the artifact's sha256 to this repository at the given tag.

### Install `slsa-verifier`

```bash
# Requires Go 1.22+. Pinned to a known-good release.
go install github.com/slsa-framework/slsa-verifier/v2/cli/slsa-verifier@v2.7.1
```

(Or download a prebuilt binary from
<https://github.com/slsa-framework/slsa-verifier/releases> and verify its own
checksum.)

### Verify (run once per artifact)

```bash
TAG=v0.1.0
REPO=github.com/brandonjsellam-Releone/trelyan-falcon-inscription

slsa-verifier verify-artifact \
  trelyan_pq-0.1.0-py3-none-any.whl \
  --provenance-path trelyan-pq.intoto.jsonl \
  --source-uri "$REPO" \
  --source-tag "$TAG"

slsa-verifier verify-artifact \
  trelyan_pq-0.1.0.tar.gz \
  --provenance-path trelyan-pq.intoto.jsonl \
  --source-uri "$REPO" \
  --source-tag "$TAG"
```

A successful run prints `Verifying artifact ... PASSED` and
`PASSED: SLSA verification passed`. Add `--print-provenance` to inspect the
builder id and the exact source commit the bytes were built from:

```bash
slsa-verifier verify-artifact trelyan_pq-0.1.0-py3-none-any.whl \
  --provenance-path trelyan-pq.intoto.jsonl \
  --source-uri "$REPO" --source-tag "$TAG" \
  --print-provenance | less
```

The verifier fails closed: a tampered artifact, a mismatched repo, or a
mismatched tag exits non-zero.

---

## (b) Verify the cosign keyless signature

The release also carries a Sigstore **bundle** per artifact (self-contained:
signing certificate + signature + Rekor transparency-log entry), so no separate
public key is needed.

### Install cosign

```bash
go install github.com/sigstore/cosign/v2/cmd/cosign@v2.6.0
# or: brew install cosign  (any cosign >= v2.6.0)
```

### Verify the bundle

```bash
cosign verify-blob trelyan_pq-0.1.0-py3-none-any.whl \
  --bundle trelyan_pq-0.1.0-py3-none-any.whl.cosign.bundle \
  --certificate-oidc-issuer "https://token.actions.githubusercontent.com" \
  --certificate-identity-regexp "^https://github.com/brandonjsellam-Releone/trelyan-falcon-inscription/\.github/workflows/release\.yml@refs/tags/v.*$"
```

What the two identity flags enforce:

- `--certificate-oidc-issuer` — the signing certificate was issued against
  GitHub Actions' OIDC issuer (not some other identity provider).
- `--certificate-identity-regexp` — the cert's SAN is *this* workflow in *this*
  repo, signing on a `v*` tag. To pin a single release exactly, replace the
  regexp with the literal identity for that tag, e.g.
  `--certificate-identity "https://github.com/brandonjsellam-Releone/trelyan-falcon-inscription/.github/workflows/release.yml@refs/tags/v0.1.0"`.

A successful run prints `Verified OK`. Repeat for the sdist
(`trelyan_pq-0.1.0.tar.gz` + its `.cosign.bundle`).

> If you prefer the detached pair instead of the bundle, the same release also
> ships `*.sig` and `*.pem`; pass `--signature <file>.sig --certificate <file>.pem`
> in place of `--bundle`.

---

## What this does and does not prove

- **Proves:** the downloaded bytes hash-match an artifact whose provenance is
  cryptographically signed by GitHub Actions OIDC and bound to
  `brandonjsellam-Releone/trelyan-falcon-inscription` at the verified tag —
  i.e. the artifact was built from this repo+tag and was not modified in transit
  or on the release page.
- **Does not prove:** that the source code is correct, audited, or safe for
  production. TRELYAN is a reference implementation on Algorand TestNet,
  UNAUDITED, and not for MainNet value.

## Caveats

- Filenames (`trelyan-pq.intoto.jsonl`, the `.whl`/`.tar.gz`, the cosign assets)
  and the recorded builder/identity strings must be confirmed against the first
  real `v*` release run; values above are the expected outputs of
  `release.yml`, not yet observed in CI.
- PyPI publishing is **separate and optional** (disabled by default in
  `release.yml`). If/when published via PyPI Trusted Publishing, PyPI records its
  own attestations; this document covers verification of the **GitHub Release**
  assets only.
