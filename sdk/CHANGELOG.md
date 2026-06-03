# Changelog

All notable changes to `trelyan-pq` are documented here. Versions follow SemVer;
pre-1.0 the public API may change.

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
