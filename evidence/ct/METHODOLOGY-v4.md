# Constant-time evidence — methodology **v4** (matched nulls)

**Written 2026-08-19, before any v4 measurement. Supersedes nothing yet.** `METHODOLOGY-v3.md` +
`METHODOLOGY-v3.1-POWER.md` remain the rules in force for any session that does not say
`--null-design ss`. This file governs the sessions that do, and only after the commit that adds
it is on the branch. The reasoning lives in `METHODOLOGY-v4-DRAFT.md` (two reviews, two
revisions, four of the author's own claims withdrawn in place); **this file is the rules only.**

## 0. Why a v4 exists — in one paragraph

The v3 null draws class 0 from a fresh 32-key pool A and class 1 from a *different* fresh pool B.
Two finite pools do not share a mean, so the null *t* is not standard normal:
`sd(t)² ≈ 1 + (σ_key/σ_total)²·(n/32)`, a spread that grows with *n* **and as the environment
gets quieter**. Measured twice on committed v3.1 data by disjoint routes (sd of the 20 null *t* =
1.742; offset-from-Δmean route predicts 1.756); the same `σ_key` ≈ 10 µs explains 5 of 20 null
sessions tripping the fixed 4.5 gate on a quiet CI runner. A gate that penalises precision is not a
gate. The fix is structural: **match each reference to the class structure of what it judges.**

## 1. What changes, exactly

| role | v3 (`--null-design rr`, default, still in force) | v4 (`--null-design ss`) |
|---|---|---|
| **environment gate** | 20× `null-rr` (pool A vs pool B), every raw \|t\| < 4.5 | 20× **`null-ss`** (ONE pool, both classes, independent index draws), every raw \|t\| < 4.5 |
| crop reference for `sign-kk-*` | the gate null's crops | **repeated `sign-aa`** (`--aa-repeats N`, N ≥ 20 for a verdict session) |
| crop reference for `sign-rr` | the gate null's crops | **`null-rr` sessions**, run purely as reference (`--rr-sessions`), used *empirically only* |
| crop reference for screening / informational lines | the gate null's crops | the gate null's crops (unchanged) |
| `sign-aa` as downgrade-only control | yes | yes (the first repeat) |

**Nothing else moves.** Primary statistic, threshold, 2 000-per-class floor, 2 % warm-up, nine
crops, SHAPE rule (crop exceeds *every* reference session), `sign-kk` ≥ 2-of-3 combination,
session = worst of `kk_combined` and `sign-rr`, A/A downgrade-only gate, INCONCLUSIVE never PASS.

**`sign-rr` is no longer held to a fixed threshold on the crop arm** — under v3 it was judged
against a null with its own construction, which made that coherent; under v4 it is judged against
`null-rr` empirically, which is the same thing stated honestly. Its *raw* statistic is still held
to 4.5 like every gated line, with this caveat on record: a pool-vs-pool raw *t* carries the same
inflation as the old null, so at roughly 10× v3.1's samples `sign-rr` would cross 4.5 **with no
leak present**. A `sign-rr` raw FAIL is therefore read as *"Δ ± CI is now resolvable between two
pools"* and never as a leak — and v4.1 will decide whether to move it to a null-referenced raw
threshold. That decision is deferred, written down, and will be made before any such session.

## 2. Session 1 is a **validation** run, not a verdict run

**Pre-registered purpose:** determine whether `null-ss` behaves as a true null on this machine.
**Nothing in session 1 is read as evidence about the signer.**

- `--null-design ss --samples 4800 --null-sessions 20 --aa-repeats 20 --rr-sessions 20`, laptop,
  quiet. Cost ≈ 1 h (60 real-operation sessions + experiments at v3b scale).
- **The number that decides:** `controls.null_raw_t_sd`, the sample sd of the 20 `null-ss` raw *t*
  values. Pre-registered reading:

  | `null_raw_t_sd` | reading |
  |---|---|
  | ≤ 1.25 | `null-ss` behaves as a true null at this scale → proceed to a verdict session design |
  | 1.25 – 1.60 | partial: the dominant term is removed but residual dependence is material → v4.1 must add a null-referenced raw threshold before any verdict session |
  | > 1.60 | the same-pool construction does **not** remove the inflation → the mechanism in §0 is wrong or incomplete; **stop and re-derive** before spending another hour |

  (1.742 is v3.1's value under `rr`; the χ² 95 % band for an sd estimated from 20 values is
  roughly ×0.76–×1.46, so these lines are deliberately coarse.)
- **Secondary reading, also pre-registered:** the crop-statistic maximum of the 20 `null-ss`
  sessions versus the 20 `null-rr` sessions run alongside. Draft §3.2 expects `ss` < `rr` but
  could not predict by how much (four routes gave 4.0–7.7 against 10.24). Whatever the ratio is,
  it is recorded, and it is *not* used to re-judge anything in session 1.
- If any `null-ss` session trips 4.5, that is **a result, not a failure** — it is the environment
  or the mechanism speaking, and the session is published INCONCLUSIVE under the rules as written.

## 3. After session 1 — sequenced, each step gated on the previous

1. **Re-judge v3.1's committed experiment CSVs** against the 20 `sign-aa` repeats from session 1,
   with the three branches already pre-registered in the draft (`sign-kk` crops 3.4754 / 5.3584 /
   5.8405): reference crop max ≥ 5.8405 → nothing moves; 5.3584–5.8405 → `sign-kk-1` alone
   SHAPE, **session PASS unchanged**, `CT_REPORT.md` §4c row corrected; < 5.3584 → `kk_combined`
   SHAPE, session re-read. The reference is a *later* null on *different* key material in a
   *different* thermal state, and that is stated with the result. The best available prior (v3b's
   near-true null, crop max 5.749) points at the middle branch.
2. **Size a verdict session** only if §2 reads "proceed": state reference counts, *n*, wall-clock,
   and the power it buys, in a v4.1 addendum, **before** running it. Three references at 82 000 is
   ≈ 10.5 h of null alone and is not a laptop session.
3. **Decide the machine** (founder gate) as a separate change from the gate fix, so a failed
   session can be attributed.

## 4. Unchanged standing rules

Observation, not a gate. INCONCLUSIVE never PASS. SHAPE never PASS, never FAIL. A PASS is
*"nothing at or above this experiment's MDE₉₀ was detected on this machine and build"*. The
vendored primitive is never patched. Every session is published whatever it says. A methodology
is never edited after a favourable result in the direction of keeping it.
