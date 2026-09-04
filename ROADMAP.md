# Roadmap

All roadmap work ships as **FOSS (MIT)** in this repository. Dates are intent,
not commitments.

## Done
- Reference contract (`contracts/inscription.py`), AVM v12 — compiles; 20/20 on
  localnet as of 2026-06-01 (suite now 22 tests, not re-run on localnet since the
  2026-06-16 contract change).
- Deployed + verified on Algorand TestNet (app `770964251`).
- Spec v0.2, threat model + invariant->test->code traceability, localnet
  validation record, Falcon encoding/budget notes.

## Next (near-term)
- **Continuous integration:** compile + off-chain signer self-test + the unit
  portion of the suite on every push (full localnet remains a documented manual
  step — it needs Docker).
- **1,024-record cap test:** add a static/unit check for the `cells_registered <
  TOTAL_RECORDS` cap (currently reasoned, not unit-tested).
- **Signature-suite agility:** document and prototype an **ML-DSA (FIPS 204)**
  path alongside Falcon-1024, so the primitive is algorithm-agile.
- **FN-DSA / FIPS 206 tracking:** version the reference when FIPS 206 finalizes.

## Before MainNet (gated)
- **Independent third-party security audit.** The NLnet NGI Zero → Radically Open
  Security route was **declined on 2026-06-29** (NLnet: the NGI Zero programmes have
  ended and no audit funding is available). The audit is therefore a **paid
  engagement, not yet funded**, or an alternative grant not yet identified. **No
  MainNet deployment until the audit closes.**

## Known limitations (see `LOCALNET_VALIDATION_2026-06-01.md`)
- Not externally audited; not on MainNet.
- Records whose Falcon private key is lost are **permanently un-inscribable** by
  design (immutable key commitment, no rotation).
- Admin (mint) blast radius is bounded to mis-minting *unregistered* records; it
  cannot alter existing inscriptions.
- The 1,024 cap is a reference parameter of this implementation, not a sales
  construct (see README "Scope").
