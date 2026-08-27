# Constant-time evidence — methodology **v4.1** (matched reference banks)

**Written 2026-08-19, before any measurement it governs.** Extends `METHODOLOGY-v4.md` §2a from a
sketch into rules. In force only for sessions that pass `--null-design ss` **and** supply the
reference banks below; every other session is still governed by v3 + v3.1.

**Provenance — and it is not mine.** This design came from the six-seat R&D team as a `council
zuss` (layered mixture-of-agents) on the *design question*, put out **before any code was
written**, under Brandon's standing directive of 2026-08-19. **DEGRADED: 6 of 9 seat-slots
succeeded** — `xai` and `deepseek` failed in Layer 0, `moonshot` in Layer 1 — though every one of
the six providers contributed in at least one layer, and the synthesis was written by a seat that
had failed earlier. Read the conclusions accordingly. The two load-bearing decisions (§1, §2)
were reached independently in Layer 0 and again in synthesis.

## 0. The principle the whole design rests on

> **A reference distribution must not contain the effect being tested.**

Call it the *null-inclusion principle*. It decides §1 immediately: using **two different fixed
keys** as the "null" for `sign-kk` would embed key-dependent work into the reference and
**calibrate away the very effect the experiment exists to find.** Every rule below is an
application of it.

## 1. `sign-kk` crop reference — repeated `sign-aa`, matched in everything but key identity

For each accepted reference session: generate **one fresh keypair**; place **two separately
allocated clones** in the exact tuple positions the two `sign-kk` arms use; give the arms
**independent RNG and class schedules**, as `sign-kk` has; collect the **same measurement count**
as one `sign-kk` pair; record its crop statistic `C_aa[i]`.

Pair *j* is **crop-positive** iff `C_kk[j] > max(C_aa)` — **strict `>`; ties do not fire.**
Combination is unchanged: **SHAPE iff ≥ 2 of the 3 pairs are crop-positive.**

- **One AA bank governs all three pairs** (identical protocol and sample count). It must **not**
  be presented as three independent empirical tests — they share one random threshold. Acceptable
  only because SHAPE is an annotation that can neither PASS nor FAIL.
- **Why same-key arms are right:** under the constant-time null, two different fixed keys and two
  clones of one key have the same class-conditional timing law — both are point-mass designs, not
  mixtures — and the A/A design supplies the environmental, scheduling, allocator, RNG and
  crop-selection variability under a **true zero**. §0 forbids the alternative.
- **The real risk is not "one key vs two"** but whether cloning the same bytes changes cache,
  aliasing, RNG or layout behaviour relative to two separately generated keys. That is why the
  clones must be separately allocated and identically placed — and it is listed unresolved in §6.

**Correction (2026-08-20, from the implementation review, before any governed run):** the
session's own **gating A/A control is not a bank member**. The gate is a *conditioned* draw —
the session proceeds only if it passed — so including its crop in `C_aa` would bias the bank's
maximum downward exactly when the environment ran hot. The AA bank is built from **dedicated
`sign-aa` repeats only** (fresh keypair each, ungated, run regardless of their own outcome), and
the harness refuses `--null-design ss` with fewer than **2** repeats, since a one-member bank is
a rank test against a single value. No governed or validation session had been run under the
uncorrected reading; nothing is re-judged.

**A correction to our own vocabulary, adopted:** `SHAPE` is too strong a name. A maximum over
cropped Welch statistics remains responsive to a **location** difference, so crop-positive means
*"a crop-sensitive class difference"*, not *"a pure shape difference"*. The label is kept for
compatibility with v1–v4 artifacts; the limitation is documented here and must be repeated
wherever a SHAPE result is reported.

## 2. `sign-rr` raw rule — three states, and the PASS set is not enlarged

A fixed 4.5 threshold is invalid for `sign-rr`: random finite-pool offsets are part of *its* null
and grow with sample count (`METHODOLOGY-v4.md` §0). It is calibrated against matched `null-rr`
references, which supply **both** its raw and crop references — one bank, not two.

Let `R = |t_raw|` and `R_ref[i] = |t_raw|` of reference *i*:

| condition | result |
|---|---|
| `R < 4.5` | raw `sign-rr` clears |
| `R ≥ 4.5` **and** `R ≤ max(R_ref)` | **`INCONCLUSIVE_POOL_OFFSET`** — cannot PASS |
| `R ≥ 4.5` **and** `R > max(R_ref)` | **FAIL** |

Crop: `C_rr > max(C_ref)` ⇒ SHAPE.

**The intermediate state is the point.** The naive fix (`FAIL iff R > max(4.5, max_ref)`, else
PASS) would let a result that fails the *old* rule become a PASS — the exact invariant I violated
with `ss` and was caught on. Nothing here enlarges the PASS set. With N = 20 an exceed-all result
has a rank floor of 1/21, which is far weaker than a parametric 4.5σ event; retaining **both**
conditions is what keeps a weak empirical rank from being promoted into a FAIL-capable rule.

**Interpretation caveat, mandatory wherever `sign-rr` is reported:** once calibrated against other
random 32-vs-32 splits, `sign-rr` tests whether *this* split is unusual **relative to random pool
imbalance**. It no longer tests "Falcon timing is independent of the key" — ordinary key-to-key
variation is now partly inside its reference law. **`sign-kk` remains the principal evidence for
that broader proposition.**

## 3. Banks: how many, and what may be reused

Pre-registered: **N = 20 accepted sessions per bank** — one `aa` bank, one `rr` bank, plus the
existing `ss` environment bank. **The accepted IDs are frozen before the governed experiment
runs; extras are held out.** There is no extension after seeing the governed statistic.

Permitted reuse — and only this: one AA bank for all three `sign-kk` pairs; one RR bank for
`sign-rr` raw *and* crop; the SS bank for environment gating and the screening/informational
lines **only**. A bank is valid only for the same pinned signer, harness/statistic version,
runner class, sample count, schedule, pool size and crop specification.

So §2a costs **two new banks, not six**: not one AA bank per pair, and not separate RR banks for
raw and crop.

**Explicitly forbidden shortcuts:**

- **No analytical crop null.** A standard-normal derivation covers none of: the maximum over nine
  *dependent* statistics, data-dependent percentile cuts, heavy-tailed timing noise, serial
  correlation and thermal drift, per-key clustering, or finite-pool offsets.
- **No permutation null** in this increment. It is exact only under a documented randomization
  mechanism with a schedule invariant to relabeling; permuting `sign-rr` observations would
  destroy per-key clustering and recreate the independence error this whole line of work exists to
  fix.
- **No within-session fake N.** Resampling or repeatedly permuting one AA session does **not**
  create independent session-level thermal environments and must never be advertised as raising N.
- **No superpool yet.** A balanced class-blind 64-key superpool with many pre-generated 32/32
  partitions could yield hundreds of conditional references from one signing series — a genuinely
  cheaper future design, and a protocol *and memory-layout* change that needs its own
  pre-registration and prospective validation. Not a shortcut to take here.

N = 99 would be needed for a formal 1 % empirical rank. Not justified for a secondary diagnostic
at the current cost per session.

## 4. Comparing the old and new nulls in one session — three-arm common control

Smallest acquisition change that puts both constructions in one thermal trajectory:

- **X** = pool A, index stream `a0`; **Y** = the *same* pool A, independent stream `a1`;
  **Z** = a fresh pool B, independent stream `b1`.
- `null-ss` = X vs Y; `null-rr` = X vs Z.

Three arms is minimal — SS needs two independently scheduled samples from one pool, RR needs a
second pool — and sharing X gives a paired comparison. Scheduling: balanced three-call
superblocks, the same message from the four-message rotation within a superblock, arm order drawn
from balanced permutations by the existing deterministic session RNG, equal observations per arm,
independent key-index streams. **Record the covariance induced by the shared X arm; the two
resulting statistics are not independent and may not be analysed as if they were.**

**`--null-design both` is DIAGNOSTIC-ONLY and issues no verdict**, because a third interleaved
signer call changes cadence and potentially cache and thermal behaviour relative to the canonical
two-arm protocols. Promotion requires prospective evidence that the three-arm cadence does not
materially change the SS distribution (§6.2).

## 5. Twelve rules, restated for the implementer

1. AA is the `sign-kk` crop null; two-distinct-key references are never used for `kk`.
2. N = 20 accepted IDs per bank; IDs frozen before the experiment; extras held out.
3. Exceed-all is strict `>`; ties do not fire.
4. `sign-kk` raw 4.5 and the ≥ 2-of-3 combination are unchanged.
5. `sign-rr` raw uses the three-state table; **the PASS set is not enlarged**.
6. SHAPE never issues PASS or FAIL; a **missing or mismatched bank ⇒ `NO_VERDICT`**.
7. **Large reference values are kept** — no outlier trimming of a null, ever.
8. `null-ss` gates the environment; it is **never** a fallback reference for AA or RR.
9. `--null-design both` does not verdict until the three-arm crossover passes.
10. No analytical crop null, no within-session fake N, no superpool in this increment.
11. An informational-line SHAPE does not void the session.
12. **Any later change to N, to the reuse rules, to the `sign-rr` PASS conjunction, or to
    three-arm promotion is a new methodology version, written before the data it governs.**

## 6. Unresolved — with the observation that would settle each

1. **A/A clone fidelity.** Does a deep-cloned A/A layout reproduce *all* the two-object `sign-kk`
   nuisances — allocation, cache, aliasing, independent mutable state? **Settled by** a known-zero
   two-object crossover: two separately generated keys whose *timing law is known equal* measured
   against A/A clones. Until then §1 rests on an argued, not demonstrated, equivalence.
2. **Three-arm promotion.** **Settled by** a prospective tail/dispersion crossover of three-arm
   SS against canonical two-arm SS on the same machine.
3. **Cheaper RR calibration.** The superpool construction is plausible and unvalidated; it needs
   its own protocol, partition list and prospective validation before any production use.

**Falsification of the whole design:** if the known-zero two-object crossover shows A/A clones do
**not** reproduce the `sign-kk` nuisance structure, §1 is wrong and the `sign-kk` crop arm has no
valid reference — in which case the honest position is that `sign-kk` has a raw statistic and no
secondary diagnostic at all, not that a convenient reference should be substituted.
