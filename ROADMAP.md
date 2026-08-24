# Roadmap

All roadmap work ships as **FOSS (MIT)** in this repository. Dates are intent,
not commitments.

## Done
- Reference contract (`contracts/inscription.py`), AVM v12 — compiles; the 25-test suite runs
  in CI on every push against a real AVM (job `contract-tests`, fails under 20 executed).
- Deployed + verified on Algorand TestNet (app `763809096`).
- **Continuous integration** — `.github/workflows/ci.yml` (9 jobs): gitleaks secret scan,
  offline vendored-Falcon integrity, 4x wire-format matrix, 3-OS signature byte-identity KAT,
  the 25-test contract suite on a real LocalNet AVM, deployed-vs-committed drift, and
  deployed-vs-declared. Plus `rust-ci.yml` and `release.yml`.
- Spec v0.2, threat model + invariant->test->code traceability, localnet
  validation record, Falcon encoding/budget notes.

## Next (near-term)

- **1,024-cell cap test:** add a static/unit check for the `cells_registered <
  TOTAL_CELLS` cap (currently reasoned, not unit-tested). The constant is
  `TOTAL_CELLS` (`contracts/inscription.py:114`); this item previously named a
  `TOTAL_RECORDS` that exists nowhere in the repository.
- **Signature-suite agility:** document and prototype an **ML-DSA (FIPS 204)**
  path alongside Falcon-1024, so the primitive is algorithm-agile.
- **FN-DSA / FIPS 206 tracking:** version the reference when FIPS 206 finalizes.

## Before MainNet (gated)
- **Independent third-party security audit** (intend to pursue NLnet's Radically
  Open Security path if supported). **No MainNet deployment until the audit
  closes.**

## Known limitations (see `LOCALNET_VALIDATION_2026-06-01.md`)
- Not externally audited; not on MainNet.
- Records whose Falcon private key is lost are **permanently un-inscribable** by
  design (immutable key commitment, no rotation).
- Admin (mint) blast radius is bounded to mis-minting *unregistered* records; it
  cannot alter existing inscriptions.
- The 1,024 cap is a reference parameter of this implementation, not a sales
  construct (see README "Scope").
