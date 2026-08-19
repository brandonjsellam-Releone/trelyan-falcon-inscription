# Constant-time evidence — backlog after the v3.1 high-power session

**Written 2026-08-18, while the v3.1 session was measuring.** One place for everything that is
known-needed and deliberately not done during a run. Sources: the four-lens pre-run audit
(4 auditors + 16 adversarial verifiers, 2 findings surviving refutation), the council `refute`
pass on the power correction, and `METHODOLOGY-v3.1-POWER.md` §§2a, 6, 7, 8.

Nothing here changes a decision rule. Anything that would — the arm randomisation and the null
gate — is marked **needs a new pre-registration**, to be written *before* the measurement it
governs, never after seeing one.

---

## A. Post-run code fixes (small, need a build; the harness is not rebuilt while it measures)

| # | Fix | Why | Where |
|---|---|---|---|
| A1 | With an empty null (`n == 0`), set `crop_empirical_p = None` and `isolated_verdict = INCONCLUSIVE` | Today `p = (0+1)/(0+1) = 1.0` and the SHAPE arm is guarded by `n > 0`, so an experiment falls through to **PASS with a PASS-shaped field** when the null is unfit. Visible in the committed `session-…-v3/report.json` (four PASS rows beside `null_ok: false`). It cannot change a session verdict — an unfit null already forces INCONCLUSIVE through the flat-control lever — but it **silently disables `sign-aa`'s SHAPE arm** in that state, and a check that cannot fail is this repository's standing complaint | `lib.rs` `judge_v2` |
| A2 | Surface the A/A verdict in the `Controls` block | The `sign-aa` downgrade is applied through a *local* `flat_for_rule`, so a failed A/A control leaves `controls_ok: true` and `controls.flat: PASS` in the JSON while every key verdict reads INCONCLUSIVE. The only trace is the `sign-aa` row | `main.rs` `Controls`, `run_aa_control` |
| A3 | `READING_GUIDE`: add `sign-aa` and its gate | The artifact's own glossary omits the control that gates it (written before it existed) | `main.rs` |
| A4 | `sign-kk` description: drop "fixed message M0" and "the per-key timing fingerprint measured directly" | Both false since v3's four-message rotation, and "fingerprint" presupposes the finding — barred by `METHODOLOGY-v3.md` §1 | `main.rs` |
| A5 | Three comments still call the v3 real-operation null a "flat-control null" | v2 leftover; the flat loop is now a separate informational control | `lib.rs`, `main.rs` ×2 |
| A6 | Serialise `null_reason` into `Controls` | Redundant now that `null_detail` lands, but the reason a null was rejected should be in the artifact, not only on stderr | `main.rs` |
| A7 | Log each null session as it completes | The null logs its start and, ≈ 3.7 h later, its summary; individual sessions are logged only on failure, so two thirds of a session shows one line | `main.rs` |
| A8 | Empty-null summary prints `crop-stat range inf..0.00` | A min/max fold over an empty vector. Cosmetic, same root cause as A1 | `main.rs` |

**A1 and A8 are no longer hypothetical.** Both are visible in the ubuntu CI session of
2026-08-18 (`OBSERVATION_ci-ubuntu-2026-08-18.md`), which printed `crop max|t| = 38.17` beside
`p_emp = 1.000` and reported `sign-aa` as **Pass** with its SHAPE arm never run. Use that session
as A1's regression fixture — it is a real artifact, not a synthetic one.

## B. Cheap wins that do not need a new pre-registration

- **Smoke-run the binary end-to-end (`--samples 4600`, ≈ 19 min) before any long session.** The
  v3.1 session was launched on a binary that had never produced one; recorded as an ordering
  mistake in `METHODOLOGY-v3.1-POWER.md` §7D. Make it a written pre-flight step.
- **Environment control is not a cheap win — it is the largest lever there is, and this is now
  measured.** The ubuntu CI runner's per-signature sd is ≈ **32 µs** against the laptop's
  **733 µs**, so a 20-minute CI session reaches MDE₉₀ ≈ **5.3 µs** while the 5.5-hour local 82 k
  session reaches ≈ 30–42 µs (`OBSERVATION_ci-ubuntu-2026-08-18.md` §4). Quadrupling samples buys
  2×; changing machine bought 23×. The sd also spans 2.4× *within* one local session
  (425–1 039 µs). **The next session's design question is "on what machine", not "how many
  samples"** — and it cannot be answered until C4 below is fixed, because today a quieter machine
  is *more* likely to have its session voided.
- **Stamp the artifact.** No wall-clock, elapsed time or run ordering is recorded in
  `report.json`. For a 5.5 h session you cannot tell from the artifact when each experiment ran,
  which is exactly what a thermal-drift question needs.
- **Decide the raw-null-CSV question** (≈ 23 MB at 20 × 82 k). `null_detail` covers the audit
  need; committing the raw samples is a separate call about repository weight.

## C. v4 methodology — **each needs a new pre-registration before the measurement it governs**

1. **Interleave the null sessions with the experiments.** They currently run entirely before,
   so null and experiments occupy different parts of the thermal envelope over ~5.5 h. This is
   the weakest joint in the secondary (crop/SHAPE) diagnostic. Class assignment is randomised
   *within* each experiment, which protects the primary statistic; it does not protect the
   null-vs-experiment comparison.
2. **Randomise the `sign-kk` arm assignment.** The actual fix if `sign-aa` returns a non-zero Δ.
   Note it **breaks the pre-registered three-pair combination rule as written**, so it needs a
   new rule, not a patch.
3. **Equalise `aa` and `kk` storage.** `sign-aa` reproduces the *intra-pair* offset exactly; put
   both in one `Vec` so the control also matches absolute allocation and page placement.
4. **Replace the fixed 4.5 gate on null sessions with a null-referenced threshold. — PROMOTED:
   this is now an evidenced defect blocking current runs, not a future concern.** The pool-vs-pool
   null is a random-effects null: `sd(t_null)² ≈ 1 + (σ_key/σ_tot)²·(n/32)`. It was filed as a
   large-*n* problem; the ubuntu CI session of 2026-08-18 shows it firing at **n = 2 350 on a
   quiet machine**, because the ratio blows up when `σ_tot` is *small* — **5 of 20 null sessions
   tripped 4.5** while both synthetic controls behaved perfectly, voiding the session
   (`OBSERVATION_ci-ubuntu-2026-08-18.md` §1). **The gate as written penalises precision:** the
   better the environment, the likelier the session is voided, for arithmetic rather than
   environmental reasons. This is why every CI session has been INCONCLUSIVE. Fix before any
   machine change *or* size increase — and pre-register the new gate before the measurement it
   governs, never after seeing a result.
5. **A gated message-varying design.** The threat model that matters most — an attacker with a
   signing oracle holding *one* key, varying the message — is today only `sign-msg`, which is
   *screening*. The gated experiments compare *keys*, which is a different question.
6. **Variance-matched fixed-vs-mixture design** to settle `sign-key`, whose SHAPE reading has
   been a hypothesis since v2 (a point mass compared against a 32-key mixture).
7. **Incremental / streaming structured output**, so a crash at hour 5 is survivable. Note the
   trade: writing between measurements is new I/O inside the timed environment and must be
   justified, not just added.

## D. Standing reading rules (not backlog — these do not expire)

- A PASS is *"nothing at or above this experiment's `mde90_ns` was detected"*. Never
  "constant-time", never "no leak".
- SHAPE and INCONCLUSIVE are never read as PASS. A null declared unfit mints no verdicts.
- The gated designs have **no true null**: a large enough *n* FAILs by construction, so a FAIL
  reads *"an effect of size Δ ± CI is now resolvable"*, never *"a leak was found"* — and never an
  exploitable channel without a separate argument about what an attacker does with an effect
  that size.
- `sign-aa` is read by its **Δ and CI**, not only its verdict word: its gate fires at |Δ| ≥ 23 µs
  while the artefact it tests is ≈ 14 µs.
- KATs in this repository are pin-relative TRELYAN vectors, **not** NIST FIPS-206 conformance.
- The vendored primitive is never patched. Sessions are published whatever they say.
