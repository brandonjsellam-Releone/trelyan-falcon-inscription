# Changelog

All notable changes to `trelyan-pq` are documented here. Versions follow SemVer;
pre-1.0 the public API may change.

## [0.1.1] — 2026-08-24
Corrective release. **Metadata only — no code, no API, no wire-format change.**

### Fixed
- **Removed `fn-dsa` and `fips-206` from the published PyPI keywords.** Those terms asserted, on
  the public index, exactly what `THREAT_MODEL_AND_TRACEABILITY.md` forbids: `det1024` can never
  be FIPS 206 conformant as specified, because NIST's FN-DSA status update states FN-DSA will
  allow **only randomized signing**, and this signer is deterministic by design — deterministic
  compressed Falcon-1024 is what the on-chain `falcon_verify` opcode verifies. Published PyPI
  metadata cannot be edited in place, so 0.1.0 carries the terms permanently; this release is the
  correction. Found by the 2026-08-24 repository audit.
- Reconciled the package version, which had drifted: `pyproject.toml` declared `0.2.2` while
  `__init__.py`, this changelog and both Dockerfiles said `0.1.0`, and only `0.1.0` was ever
  published. All five locations now agree.

### Added
- `sdk/tests/test_public_claims.py` — parses the built manifest and fails if any published field
  claims FIPS 206 / FN-DSA conformance, across spellings. Carries a self-test proving the detector
  still bites, because every other assertion in it is a negative that would pass silently if the
  matcher broke.

## [0.1.0] — 2026-06-03
Initial release.

### Added
- `trelyan_pq.message` — stdlib-only wire-format helpers: byte-exact `build_message()`,
  `sha512_256()`, box-name/`box_refs()` helpers, and protocol constants. Matches the
  reference contract (inscription.py) and spec v0.2.
- `trelyan_pq.falcon` — deterministic Falcon-1024 signer (keygen/sign/verify) in the exact
  0xBA-header compressed encoding Algorand's native `falcon_verify` opcode accepts, plus
  domain-bound `sign_inscription()` / `verify_inscription()` convenience.
- `trelyan_pq.inscription` — high-level on-chain client (deploy/fund/mint/register/inscribe/
  read), behind the `[algorand]` extra.
- Pinned golden test vectors and pure-Python wire-format tests.

### Status
Alpha. Validated on localnet (20/20) and Algorand TestNet. NOT externally audited;
NOT for MainNet value. App-level post-quantum inscription signing — NOT a replacement for
Algorand account/transaction authentication.
