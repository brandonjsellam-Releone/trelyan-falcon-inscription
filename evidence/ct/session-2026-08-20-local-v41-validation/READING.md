# v4.1 validation session — the one pre-registered reading, and the v3.1 re-judgment

**Session:** `session-2026-08-20-local-v41-validation` · 2026-08-20 · local (same laptop as all
prior local sessions) · `--null-design ss --samples 4800 --null-sessions 20 --aa-repeats 20`
(rr-sessions defaulted to 20) · harness at commit `b7ea95a` · VALIDATION-ONLY by construction
(`validation_only: true`; every experiment ungated and INCONCLUSIVE; METHODOLOGY-v4 §2).

## 1. The reading (the only line this session is evidence for)

**`null_raw_t_sd = 1.045`** over 20 null-ss sessions.

Pre-registered bands (METHODOLOGY-v4 §2, committed before this run): **≤ 1.25 → proceed to a
verdict-session design**; 1.25–1.60 partial; > 1.60 stop. → **PROCEED.**

Context the bands were written against: 1.000 is the true-null value; **v3.1 measured 1.742 on
this same machine under the rr (pool-vs-pool) design.** The matched null-ss design lands at
1.045. The v4 diagnosis — the inflation was *design-induced* (σ_key contamination scaling with
n), not environmental — is now confirmed by construction on the same hardware: change only the
null design, and sd(t) falls from 1.742 to ≈ 1.

Supporting observations inside the same reading: raw |t| max over 20 null sessions = 2.68; no
null session approached the 4.5 line.

## 2. Deviations (recorded before any interpretation below)

1. **Debug-harness build (not known at pre-registration).** Windows App Control began blocking
   freshly built release executables on this machine on 2026-08-20 (hash-based; the debug build
   runs). The session therefore ran the **dev-profile harness**. The vendored Falcon C core is
   pinned at `opt_level(3)` in `trelyan-pq-ffi/build.rs` — the *measured signing code is
   byte-identical machine code in both profiles*; only the Rust measurement loop (timestamping,
   collection) is unoptimized, and that overhead is class-independent. We judge this immaterial
   to a null-design sd(t) reading and state it rather than argue it away.
2. **Bank count mismatch (known at pre-registration).** The aa bank is 20 × 4800-sample
   sessions; the v3.1 session it re-judges is 82k-sample. v4.1 §1's matched-count requirement
   is therefore not met for the §3 re-judgment — this was priced in when the three branches
   were pre-registered (the best bank available today), and is a named reason the re-judgment
   is an *annotation on v3.1*, not a new governed verdict.

## 3. The pre-registered v3.1 re-judgment (three branches, written before the bank existed)

Branches (pre-registered): max(C_aa) ≥ 5.8405 → nothing fires; 5.3584 ≤ max(C_aa) < 5.8405 →
kk-1 alone fires, session PASS unchanged; **max(C_aa) < 5.3584 → ≥ 2 pairs fire → session
SHAPE annotation.**

Measured: **max(C_aa) = 3.0133** (N = 20; crops 1.06 … 3.01). → **Third branch.**

| v3.1 line | crop max\|t\| | > 3.0133 ? |
|---|---|---|
| sign-kk-0 | 3.475 | fires (not anticipated by the branch thresholds, which were keyed to kk-1/kk-2) |
| sign-kk-1 | 5.840 | fires |
| sign-kk-2 | 5.358 | fires |

**Result: 3 of 3 crop-positive → the v3.1 session carries the SHAPE annotation.** What this
does and does not mean, exactly per METHODOLOGY-v4.1:

- SHAPE **cannot** issue PASS or FAIL. The v3.1 session verdict — **PASS at every
  pre-registered raw line, MDE₉₀ ≈ 14.5 µs** — stands untouched.
- The annotation states: the v3.1 `sign-kk` crop excursions exceed everything 20 matched
  A/A-design null sessions produced. Under v4.1 §1's argued (not yet demonstrated) A/A ≡ kk
  null equivalence, that is evidence of a **crop-sensitive class difference** linked to key
  identity — "crop-sensitive", not "shape", per the v4.1 vocabulary correction.
- The annotation is **conditional on §6.1**, the unresolved A/A-clone-fidelity question: if
  deep-cloned A/A layouts do *not* reproduce the two-distinct-key layout variance, the bank is
  too tight and fires spuriously. §6.1 is now the critical path (see §5).

## 4. Observations that are NOT evidence (pre-registration: "read nothing else here as evidence about the signer")

Recorded solely to shape the next pre-registration:

- Within this session (fully matched conditions: same build, same n=4800), sign-kk-0 crop 7.23
  and sign-kk-2 crop 8.75 vs the same-session aa bank max 3.01 — the same pattern as §3, under
  matched counts. To become evidence this exact comparison must be pre-registered and run gated.
- `null-rr-ref-18` produced a **null** crop of 5.19 > 4.5 — empirical confirmation of v4 §0:
  the fixed 4.5 line is invalid as a crop rule for rr-style designs.
- **Implementation gap found: the synthetic flat control was judged against the real-operation
  gate bank and came out "Shape" (raw t = 2.99), flipping controls to NOT OK.** A synthetic
  op judged against a real-op crop bank is a mismatched reference — the v4.1 thesis applied to
  our own controls. Harmless here (validation-only forces INCONCLUSIVE anyway) but it would
  block any future gated ss session. Needs a ruled fix before the verdict-session design:
  controls keep their own fixed-rule judgment, or get their own reference family.
- The leaky control still fails loudly (raw t = −107): the harness detects the planted leak.
- sign-aa gate itself: raw t = −0.73, Pass.

## 5. Next steps (in order, each gated as stated)

1. **Team review of this reading + re-judgment** (standing directive: full six-seat team).
2. **§6.1 A/A clone fidelity falsification test** — pre-register, then run: known-zero
   two-object crossover; if A/A clones fail to reproduce two-object variance, v4.1 §1's bank
   construction is rejected per its own falsification clause.
3. **Controls-reference fix** (the §4 gap) — small, ruled change + tests.
4. **Verdict-session pre-registration** (lifts validation-only; defines gated ss sessions).
5. **Machine decision** — founder gate (Brandon): whether CI runners move to the ss design
   once 2–4 land.
