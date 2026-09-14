# Changelog

All notable changes to `trelyan-pq` are documented here. Versions follow SemVer;
pre-1.0 the public API may change.

## [Unreleased] — source version 0.2.2 (not yet on PyPI)
Changes since 0.1.0, the only PyPI release (written 2026-09-11 from the repository history; not
exhaustive).

### Changed
- Removed the `fn-dsa` and `fips-206` keywords published with 0.1.0 (2026-08-28). This package
  implements Algorand's deterministic Falcon-1024 (`falcon_det1024`), not FN-DSA; FIPS 206 is
  unpublished.
- The README's build recipe fetches the pinned `algorand/falcon` commit `ce15e75b` and compiles
  with `-DFALCON_UNALIGNED=0 -fno-strict-aliasing` (see `PINNED_BUILD.md`); the 0.1.0 README built
  the default branch without those flags.
- Documented that `sign()` hangs, rather than raising, on a header-valid but corrupt private key.
- Status wording: the reference contract's suite is now 28 tests, run on LocalNet in CI; the 0.1.0
  "localnet (20/20)" figure is the 2026-06-01 run against an earlier contract.

## [0.1.0] — 2026-06-03 (uploaded to PyPI 2026-06-12)
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
