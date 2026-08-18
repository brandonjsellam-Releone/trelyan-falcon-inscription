# Constant-time evidence — **v3.1 power addendum**

**Written 2026-08-18, after the v3b session and before the high-power session it governs.**

This is an **addendum to `METHODOLOGY-v3.md`, not a replacement.** Every decision rule in v3 is
unchanged and is restated in §4 so no reader has to take that on trust. What is new is (a) a
pre-registered **sample size with the power it buys**, (b) a **correction** to a resolution claim
this repository has already published, and (c) a harness change that makes every future session
state its own resolution.

**Why the rules are not touched.** v3b ended in PASS. A methodology edited *after* a favourable
result, in the direction of keeping it, is worthless. So the statistic, the threshold, the
combination rule and the null construction stay exactly as they were; the only quantity moved is
the sample count, and it moves **up** — which can only make a FAIL more likely, never less.

---

## 1. The correction (read this before the numbers)

`CT_REPORT.md` §4b says the v3b CIs are ±25–60 µs and that "±15 µs effects are neither confirmed
nor excluded", and estimates "≈ 40–80 k measurements per experiment" to resolve them. **Two of
those three statements are wrong, and both errors flatter the result.**

1. **A 95 % CI half-width is not the detection floor.** The pre-registered rule is `|t| ≥ 4.5`,
   not `|t| ≥ 1.96`. A test at a 4.5 σ line detects a true difference `d` with probability
   ≈ `P(Z ≥ 4.5 − d/SE)`, so the difference detected with probability `power` is
   **`(4.5 + z_power)·SE`** — about **2.95×** the 95 % CI half-width at 90 % power, not equal to
   it. Quoting the CI as if it were the resolution overstates the run by that factor.

   Four qualifications, all raised by the council review of this addendum and all kept:
   - **`MDE₉₀` is not a floor below which detection is impossible.** It is the size detected with
     probability 0.90. Smaller effects retain a smaller, non-zero detection probability — e.g. a
     true effect equal to the CI half-width has `E[t] = 1.96` and is flagged about 0.5 % of the
     time, which is why "not resolved" and "not present" are different sentences.
   - **Normal approximation, stated.** Power is computed as `Φ(d/SE − 4.5)`, i.e. `T ~ N(d/SE, 1)`
     with the SE treated as known. The exact quantity is a noncentral-*t* with Welch–Satterthwaite
     df; here df is in the thousands, so the difference is a few per cent, and it goes the
     *conservative* way (the exact threshold is slightly **larger**, so the true resolution is
     slightly worse than stated, never better).
   - **One look per experiment.** Unlike dudect's accumulate-and-recheck loop, this harness takes
     a single fixed-size measurement of each experiment and applies the rule once, so the
     single-look calculation is the right one for the primary statistic. The nine crops are a
     separate family and are handled by the empirical null, not by this figure.
   - **The conversion assumes SE-based intervals**, which is a fact about this harness rather than
     an assumption: `mean_diff_ci95` is `d ± 1.96·SE` with the same Welch SE the statistic uses.
2. **What v3b actually resolved**, recomputed from its own committed `report.json`:

   | experiment | n / class | sd | SE | 95 % CI ± | **MDE₈₀** | **MDE₉₀** |
   |---|---|---|---|---|---|---|
   | `sign-kk-0` | 2 352 | 733 µs | 21.4 µs | 41.9 µs | 114 µs | **124 µs** |
   | `sign-kk-1` | 2 352 | 425 µs | 12.4 µs | 24.3 µs | 66 µs | **72 µs** |
   | `sign-kk-2` | 2 352 | 1 039 µs | 30.3 µs | 59.4 µs | 162 µs | **175 µs** |
   | `sign-rr` | 2 352 | 826 µs | 24.1 µs | 47.2 µs | 129 µs | **139 µs** |

   So the honest reading of v3b is: **no per-key mean difference of ~72–175 µs or larger was
   detected** (the figure depends on the pair, because the pairs' sds differ by 2.4×) — 72 µs is
   `sign-kk-1`'s own MDE₉₀ and 175 µs is `sign-kk-2`'s, each computed from that experiment's own
   SE. They are **not** the CI range ±25–60 µs scaled by 2.95, which would give 74–177 µs; three
   reviewers read them that way, so the derivation is spelled out here. The report's "±15 µs"
   sentence claimed roughly an order of magnitude more resolution than the session had.
3. **The sample-size estimate was low by ~4×.** Reaching MDE₉₀ = 15 µs at the median sd needs
   ≈ 320 000 measurements per experiment (≈ 22 h on this machine), not 40–80 k.

`CT_REPORT.md` is corrected in the same commit as this file. The v3b **verdict** does not change —
PASS at the pre-registered lines is still what the data says; what changes is the size of the
claim that PASS supports.

## 2. The pre-registered size for the next session

**`--samples 82000`, `--null-sessions 20`**, one machine, quiet, no builds running alongside.

n per class after the 2 % warm-up: **40 180** (binomial sd of the split ≈ 143, far above the
2 000 floor). Resolution is **per experiment**, because the pairs' sds differ by 2.4×:

| gated line | sd | SE | 95 % CI ± | MDE₈₀ | **MDE₉₀** |
|---|---|---|---|---|---|
| `sign-kk-0` | 733 µs | 5.17 µs | ±10.1 µs | 27.6 µs | **29.9 µs** |
| `sign-kk-1` | 425 µs | 3.00 µs | ±5.9 µs | 16.0 µs | **17.4 µs** |
| `sign-kk-2` | 1 039 µs | 7.33 µs | ±14.4 µs | 39.2 µs | **42.4 µs** |
| `sign-rr` | 826 µs | 5.83 µs | ±11.4 µs | 31.1 µs | **33.7 µs** |
| `sign-aa` (control, planning sd) | 733 µs | 5.17 µs | ±10.1 µs | 27.6 µs | **29.9 µs** |

**The session's resolution is therefore MDE₉₀ 17–42 µs, CI ±5.9 to ±14.4 µs.** An earlier draft of
this file, and of `CT_REPORT.md` §4b, quoted "30–42 µs / ±10–14 µs": that is the *median-to-worst*
range and silently drops `sign-kk-1`, the narrowest pair. The error under-claims the session's
resolution rather than overstating it, but a range that is not the range is still wrong, and each
experiment's own `mde90_ns` is authoritative over any table written in advance.

Estimated wall-clock **≈ 5.5 h, band 5.5–5.9 h** (the earlier "≈ 5.7 h" scaled from a six-signing-
experiment session; `sign-aa` makes it seven and adds ≈ 0.19 h).

Derivation, so it can be checked rather than believed: `SE = √(sd₀²/n₀ + sd₁²/n₁)`;
`MDE_power = (4.5 + z_power)·SE` with `z₈₀ = 0.8416`, `z₉₀ = 1.2816`. Wall-clock is measured, not
guessed: v3b spent 38.8 s per null session and 379.5 s on experiments + controls at 4 800
samples (plus ≈ 85 s of fixture and null-pool key generation), and every experiment and null
session runs at the same `--samples` value, so the session scales linearly at ≈ 0.24 s per
sample-unit: 85 s + 82 000 × 0.2405 s ≈ 19 800 s ≈ 5.5 h, rising to ≈ 5.9 h if the null's
per-signature cost matches `sign-rr`'s 8.27 ms rather than the 7.66 ms its measured 38.8 s
implies. Roughly two thirds of the session is the 20-session null.

**Why 82 000 and not more.** It is the largest size that finishes in one unattended evening on
the machine that is available, and it is the point where the marginal return falls off: 82 k
takes ≈ 5.5 h to reach 17–42 µs, while 15 µs everywhere needs 320 k and ≈ 22 h — a 4× cost for
roughly a 2× improvement. The choice is a budget, and it is stated as one. **This is not the size at which a PASS would
become a constant-time claim; no size is.**

## 2a. One new control: `sign-aa` (added *because* of the high power, not despite it)

A pre-run audit of the committed data found a pattern that only becomes dangerous at this
sample size. Across the v2, v3 and v3b sessions — **nine independent key pairs** — the `sign-kk`
mean difference is positive in **8 of 9** cases, mean **+13.9 µs**: class 1 slower.

| session | kk-0 | kk-1 | kk-2 | (rr) |
|---|---|---|---|---|
| v2 | +16.6 | +11.8 | +15.0 | −10.0 |
| v3 | +14.3 | +16.6 | +6.9 | −36.6 |
| v3b | +13.8 | −1.0 | +31.4 | −0.9 |

If that offset were a property of particular keys, its sign would be a coin flip across nine
independent pairs; 8/9 has binomial *p* ≈ 0.04. It follows the **arm**, not the key. There is a
concrete candidate mechanism in the harness, not in Falcon: a `sign-kk` pair is one tuple, so
class 0's secret key sits at tuple offset 0 and class 1's at offset `size_of::<Keypair>()`
(4 098 B) — a different address and a different cache-line alignment on every single
measurement. `sign-rr`, whose two arms live in **separate allocations**, shows the opposite sign,
which is what that explanation predicts and what a key-property explanation does not.

At 4 800 samples this sat at |t| ≈ 0.2–3.2 and was correctly withdrawn as descriptive. At 82 000
samples the CI on it is ±10 µs: the session **would have measured a harness artefact precisely
and had no control capable of saying so.**

So `sign-aa` is added: **both arms sign with copies of the same keypair**, in a tuple laid out
exactly like a `sign-kk` pair, with the same four-message rotation. Its true mean difference is
**exactly zero by construction**, so anything it produces is harness, layout or environment.

- It is **informational** — never gated, never part of the session verdict.
- It is a **control**: the session's key verdicts are readable **only if `sign-aa` PASSes**.
  FAIL (arms differ in location), SHAPE (arms differ in the crop diagnostic the secondary arm
  rests on) and INCONCLUSIVE all force every key verdict to INCONCLUSIVE.
- It is **downgrade-only**. This is enforced as a pure function (`flat_verdict_under_aa`) with a
  property test asserting that for every pair of inputs the output is either the flat control's
  verdict or INCONCLUSIVE — the rule cannot invent a verdict the session did not otherwise have.

Adding a control after seeing data is legitimate in exactly one direction: this one can only
make the session harder to believe, never easier. Nothing that produces a PASS was touched.

**And if `sign-aa` FAILs, that is the session's most valuable result** — it would mean the
+13.9 µs pattern the last three sessions recorded as a key observation is the measurement
apparatus, and the `sign-kk` design needs the arms randomised (a v4 item) before it measures
keys at all.

## 3. What the session will and will not license

**If it PASSes**, the sentence it licenses is:

> Across three fixed-key pairs and a pool-vs-pool control, no difference in mean signing time
> was detected at the pre-registered lines. At this sample size the session would have detected a
> true difference of **17 µs (narrowest pair) to 42 µs (widest pair)** with 90 % probability —
> each experiment's own MDE₉₀ applies to that experiment; smaller differences remain neither
> confirmed nor excluded. Machine-, build- and
> input-distribution-specific. Not a proof, and not evidence of absence below those figures.

**Sentences it does not license, at any sample size:** that the signer *is* constant-time; that
the secret key does not leak through timing; that Falcon-1024 as a design is constant-time; that
any FIPS-206 / NIST property has been shown. A timing session can demonstrate leakage; it cannot
demonstrate its absence — and this one measures wall-clock only, so power, EM, cache and
microarchitectural channels are entirely outside it.

**If it FAILs**, the sentence it licenses is narrower than it will look: a resolvable difference
in mean signing time *between two particular keys on this machine*. Any FAIL is published with
the caveats below attached, goes to the council, and the reading is downgraded before it is
raised — the same direction the previous three rounds went.

**The gated experiments do not test a true null hypothesis, and at high power that matters.**
This is the sharpest thing the pre-run audit surfaced and it is stated here rather than
discovered afterwards:

- `sign-kk` compares two *fixed* keys. Falcon's per-signature work depends on the sampled basis,
  so two particular keys almost certainly do differ in mean work by *something*. The true
  difference is not zero, so with enough measurements a FAIL is **guaranteed** — a large enough
  *n* eventually resolves any non-zero difference. A FAIL therefore reports partly on the size
  of the effect and partly on the size of *n*, and the honest quantity is the **estimate with
  its CI**, not the verdict word.
- `sign-rr` compares two fixed pools of 32 keys. The same argument applies to the difference of
  the two pool means, weakened by 32× averaging: the pool-mean difference implied by the observed
  per-key spread is ≈ 4 µs, which needs on the order of a million measurements per class to
  reach |t| = 4.5. At 40 000 per class it is not expected to trip — but it is not a true null
  either, and this is why the null sessions (fresh pools each time) are the calibration rather
  than a theoretical zero.
- The one experiment with a **true zero by construction** is the new `sign-aa` (§2a).

The consequence for reading this session: **PASS remains meaningful** (it bounds the effect from
above at a stated power), while a **FAIL must be read as "an effect of size Δ ± CI is now
resolvable", never as "a key-dependent leak was discovered"** — and never as an exploitable
channel without a separate argument about what an attacker could do with an effect that size.
A per-key mean difference is also not the threat model that matters most: an attacker with a
signing oracle holds *one* key and varies the *message*, which is `sign-msg` (screening), not
`sign-kk`. That gap is a v4 design item.

## 4. Rules carried over from v3 — unchanged, restated

- Primary: raw Welch *t*, **|t| ≥ 4.5 → FAIL**; minimum 2 000 per class.
- **Admission rule, documented here for the first time:** the binary refuses `--samples < 4600`.
  It was added to the code after v3 run 1 went INCONCLUSIVE on a random class split of
  1934/2182, and until now lived only in a code comment citing a §1 that does not contain it.
  The rule itself is right — the class bit is drawn per measurement, so the split has binomial
  sd ≈ √(n)/2 and a floor set at the exact half-split guarantees chance INCONCLUSIVEs — but an
  admission rule that exists only in the implementation is not pre-registered. It is now.
- Secondary: crop statistic against the empirical null of **20 pool-vs-pool sessions of the real
  operation**, each at the same measurement count; every null session must itself PASS on the raw
  statistic or all Falcon verdicts are INCONCLUSIVE. **SHAPE** iff raw |t| < 4.5 and the crop
  statistic exceeds every null session. SHAPE is never PASS and never FAIL.
- `sign-kk` combination: **FAIL** if any of the three pairs FAILs; **SHAPE** only if ≥ 2 of 3 are
  SHAPE; otherwise PASS. Individual pairs reported regardless.
- Gated: `sign-kk` (combined) and `sign-rr`. `sign-key` / `sign-msg` are screening;
  `verify-ctrl` / `keygen` informational (keygen is rejection-sampled and *expected* to be
  variable-time).
- Descriptive statistics — Δmean, CI, *p*, **and the new MDE figures** — are reported and are
  **not** decision criteria.
- Observation, never a gate. The vendored primitive is never patched. The session is published
  whatever it says.

## 5. Harness change (`falcon-ct`)

`welch_se`, `inverse_normal_cdf` (Acklam; unit-tested against published quantiles) and
`min_detectable_effect` are added to the library, and **every experiment now reports `se_ns`,
`mde80_ns` and `mde90_ns`** in `report.json` and on the console, under a printed reminder that a
PASS reads "nothing at or above MDE₉₀ was detected". The point is structural: after this change a
session cannot report a non-detection without also publishing the size of what it could have
seen, so §1's error cannot recur silently.

No decision rule reads these fields. `min_detectable_effect` is computed from the **observed** sd,
so it describes the run that happened rather than a plan made before it.

Three further changes, none of which touches a decision rule or the timed region:

- **The null becomes auditable.** It costs two thirds of the session and previously survived as
  20 bare floats. `report.json` now carries `controls.null_detail`: the full judged result of
  every null session — *n* per class, means, sds, raw *t*, df, CI and all ten *t* values. An
  auditor can now recheck the calibration that every SHAPE verdict rests on. (The null's raw
  samples are still discarded; writing 20 × 82 000 rows is ~23 MB and is a v4 decision.)
- `sign-aa` (§2a) and its downgrade-only gate.
- `schema_version` 4. The new fields are additive and `#[serde(default)]`, so a schema-3 reader
  still parses these reports; the bump is how a reader tells a session that published its
  resolution from one that could not.

## 6. Known limits of this session, stated in advance

- **Prediction recorded before the run: the null gate should survive, narrowly enough to be
  worth stating.** The pool-vs-pool null is a random-effects null, not a theoretical zero: two
  fresh 32-key pools have a genuinely different mean, so the null *t* is not standard normal but
  has `sd(t)² ≈ 1 + (σ_between-key / σ_total)²·(n/32)`. That grows with *n*, so a gate written as
  "every null session must have raw |t| < 4.5" gets harder to pass at high power. With
  σ_total ≈ 733 µs, n ≈ 40 180 per class and a between-key sd of 10–20 µs, `sd(t)` ≈ 1.1–1.4 and
  the chance that **any** of the 20 sessions trips 4.5 is ≈ 0.1–2 %. So the gate is expected to
  hold here — but it is a real ceiling on this design, and at ~10× these samples it would start
  failing for arithmetic rather than environmental reasons. If the null does trip, the session is
  INCONCLUSIVE **and that is the correct outcome under the rules as pre-registered**; it is not
  re-run under a looser gate. Fixing the gate (a null-referenced threshold rather than a fixed
  4.5) is a v4 item, to be decided before the next size increase, not after this result.
- **One machine, unpinned.** `affinity_pinned: false` (std has no affinity API and no dependency
  is added for it). Over ~5.7 h, thermal and DVFS drift are larger than over 20 min.
- **Time order.** The 20 null sessions run *before* the experiments, so null and experiments
  occupy different parts of the thermal envelope. Class assignment is randomised *within* each
  experiment and within each null session, which protects every *within-experiment* comparison —
  the primary statistic — against slow drift. It does not equally protect the *null-vs-experiment*
  comparison that the secondary diagnostic rests on. The secondary is therefore read with less
  weight than the primary in this session, and interleaving the null with the experiments is
  listed for v4.
- **Nothing is written until the end.** `report.json` and the CSVs are written after the last
  experiment, so a crash at hour 5 loses the session. Accepted for this run rather than changing
  the measurement path on the eve of it (writing between measurements is new I/O in the timed
  environment, and the session is repeatable). The console log is captured by **the launch
  command's redirect** (`falcon-ct … > <session-dir>/console.log 2>&1`) — the harness itself
  writes no log file, and an earlier draft of this bullet wrongly implied it did. **How little
  that buys, stated exactly:** the null loop logs only its start line and, ≈ 3.7 h later, its
  summary; individual null sessions are logged only if one *fails* to run. So for the first two
  thirds of the session the console shows a single line, and a crash inside the null phase is
  diagnosable only as "it died somewhere in the null". Each experiment after that does log as it
  starts. A second draft of this bullet claimed "the per-null-session progress survives", which
  is false, and it is corrected here rather than left to be discovered from an empty log.
  Per-session progress output and incremental structured results are v4 items.
- **det1024 is deterministic**: one (key, message) pair always does the same work, which is why
  `sign-kk` rotates four messages identically across both classes.
- **Known reporting defect, not fixed before this run (deliberately).** When the null is unfit or
  absent, `judge_v2` computes the empirical *p* as `(0+1)/(0+1) = 1.0` from an empty null and its
  SHAPE arm is guarded by `n > 0`, so it cannot fire — the experiment then falls through to PASS
  with a PASS-shaped `crop_empirical_p: 1.0` in the JSON. It is visible in the committed
  `session-…-v3/report.json` (four `PASS` rows beside `null_ok: false`). **It cannot change this
  session's verdicts:** an unfit null already forces the flat control to INCONCLUSIVE, which
  forces every key verdict to INCONCLUSIVE through the same lever. But it does mean a reader must
  check `null_ok` before believing any `crop_empirical_p`, and it would silently disable
  `sign-aa`'s SHAPE arm in that state. Fixed after the run (`None` and INCONCLUSIVE when `n == 0`),
  not during it — the harness must not be rebuilt while a session is measuring.
- Still open from v3: fixed-vs-random screening compares a point mass with a mixture (`sign-key`
  SHAPE is a hypothesis, not a reading). The variance-matched design that would settle it —
  multiple fixed keys against variance-matched mixtures — is a **v4** item and is not attempted
  here.

---

## 7. Predictions, recorded 2026-08-18 while the session was still in its null phase

The session launched at 16:39; the 20 null sessions take ≈ 3.7 h and **no experiment had run**
when this section was written. Everything below is arithmetic on the *v3b* numbers, projected to
n = 40 180 per class. It is written now so that none of it can be offered afterwards as insight.

**A. Three non-gated lines are expected to cross |t| = 4.5, and none of them is a finding.**
At this sample size the screening and informational designs become trivially "significant"
because their v3b effects are large relative to the new SE:

| line | v3b Δ | SE at 40 180/class | expected \|t\| | status |
|---|---|---|---|---|
| `sign-key` | −46.4 µs | 3.72 µs | **≈ 12.5** | screening, **not gated** |
| `verify-ctrl` | +1.3 µs | 0.04 µs | **≈ 33** | informational — public data only |
| `keygen` | +11.1 ms | 73.4 µs | **≈ 151** | informational — rejection-sampled, *expected* variable-time |

`sign-key` compares a fixed (key, message) point mass against a 32-key mixture; that design was
demoted to screening in v2 precisely because such a comparison is confounded, and a bigger *n*
does not decorrelate it. **A raw FAIL on any of these three is a prediction being met, not a
discovery**, and none of them touches the session verdict.

**B. A session FAIL is close to a coin flip, and will not be re-run smaller if it happens.**
Taking v3b's own per-pair deltas *as if they were true* (their v3b CIs all span zero, so this is
"not a low-probability event", not a forecast): `sign-kk-2` (Δ +31.4 µs, λ = 4.29) → **P(FAIL) ≈
42 %**; `sign-kk-0` (+13.8 µs, λ = 2.67) → 3.4 %; `sign-kk-1` (−1.0 µs) → ≈ 0 %; `sign-rr` → ≈ 0 %.
**P(at least one `sign-kk` pair FAILs) ≈ 44 %**, which by the pre-registered combination rule
(FAIL if *any* pair FAILs) is a session FAIL. The sentence §3 licenses for a FAIL — *an effect of
size Δ ± CI is now resolvable between two particular keys on this machine* — is the sentence that
has to survive a 44 % event without becoming "Falcon leaks the key".

**C. `sign-aa` will most likely PASS, and its verdict word is the least interesting thing about
it.** Its gate fires at |t| ≥ 4.5, i.e. |Δ| ≥ 23.3 µs, while the arm offset it exists to test is
≈ +13.9 µs — comfortably under the gate. So **read `sign-aa`'s Δmean and its CI, not its verdict**:

- Δ ≈ +14 µs with a CI excluding zero → the arm artefact is **confirmed**, the +12–17 µs "key
  deltas" of v2/v3/v3b are the apparatus, and `sign-kk` must randomise its arms before it measures
  keys again (v4). This is the outcome that would make the session worth its 5.5 hours regardless
  of every other line.
- Δ ≈ 0 with a CI of ±10 µs → the layout hypothesis is disfavoured at that resolution, and the
  8-of-9 sign pattern needs another explanation (it is not thereby a key effect).
- |t| ≥ 4.5 → every key verdict in the session is INCONCLUSIVE by §2a, and that is the correct
  outcome, not a reason to re-read anything.

**D. Two procedural notes for the person reading the output.** The binary was **not** smoke-run
end-to-end before this session — `sign-aa`, `controls.null_detail`, the three power fields and
`schema_version: 4` are all new since v3b, and the cheapest end-to-end check (`--samples 4600`)
costs ≈ 19 min of load, which cannot be spent while a timing session is running. The fixture path
is known good (the session got past `Fixtures::prepare`, which builds the new `aa` pair), and the
remaining new code is one experiment runner, one pure gate function (property-tested) and three
`f64` fields. If serialisation nevertheless fails at the end, the loss is the session, not the
method: re-run it. **This ordering was a mistake — smoke-test first, then launch — and it is
recorded here rather than quietly fixed.**
