# Roadmap

All roadmap work ships as **FOSS (MIT)** in this repository. Dates are intent,
not commitments.

## Done
- Reference contract (`contracts/inscription.py`), AVM v12 — compiles; its 28-test
  suite runs on LocalNet in CI (last run on `main` 28/28, 2026-09-04). The 20/20 hand
  run of 2026-06-01 predates the 2026-06-16 contract change.
- Deployed + verified on Algorand TestNet (app `770964251`).
- Spec v0.2, threat model + invariant->test->code traceability, localnet
  validation record, Falcon encoding/budget notes.
- Continuous integration (`.github/workflows/ci.yml`): the committed TEAL checked
  against a fresh compile, the signer byte-identity KAT on 3 OSes, and the full
  contract suite on LocalNet (the runner provides Docker), on pushes and PRs that
  touch the filtered paths.

## Next (near-term)
- **1,024-record cap test:** add a static/unit check for the `cells_registered <
  TOTAL_RECORDS` cap (currently reasoned, not unit-tested).
- **Signature-suite agility:** document and prototype an **ML-DSA (FIPS 204)**
  path alongside Falcon-1024, so the primitive is algorithm-agile.
- **FN-DSA / FIPS 206 tracking:** when FIPS 206 is published, document how it relates to this
  reference and track Algorand's opcode roadmap. The on-chain det1024 (`0xBA`) path cannot
  become FIPS 206 conformant unilaterally: NIST's provisional plan for FN-DSA permits randomized
  signing only, and the AVM opcode accepts deterministic signatures only.

## Before MainNet (gated)
- **Independent third-party security audit.** The NLnet NGI Zero → Radically Open
  Security route was **declined on 2026-06-29** (NLnet: the NGI Zero programmes have
  ended and no audit funding is available). The audit would therefore have to be a **paid
  engagement** or an alternative grant not yet identified; **none is engaged or funded yet**. **No
  MainNet deployment until the audit closes.**

## Known limitations (see `LOCALNET_VALIDATION_2026-06-01.md`)
- Not externally audited; not on MainNet.
- Records whose Falcon private key is lost are **permanently un-inscribable** by
  design (immutable key commitment, no rotation).
- Admin (mint) blast radius is bounded to mis-minting *unregistered* records; it
  cannot alter existing inscriptions.
- The 1,024 cap is a reference parameter of this implementation, not a sales
  construct (see README "Scope").
