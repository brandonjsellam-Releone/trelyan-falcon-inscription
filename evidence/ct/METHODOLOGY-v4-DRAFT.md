# METHODOLOGY v4 — **DRAFT DESIGN, NOT A PRE-REGISTRATION**

**Status: draft, 2026-08-19.** This file proposes a fix for the defect that is currently blocking
progress. It is **not** in force and governs **no** session. Nothing here may be cited as a rule
until it has been (a) reviewed by the council, (b) revised, and (c) committed as
`METHODOLOGY-v4.md` **before** the first measurement it governs.

That sequence matters more than usual here, because this draft is written **immediately after
seeing results** (v3.1 PASS locally, INCONCLUSIVE on CI). The defect it fixes was identified from
the *algebra* of the gate and then confirmed by observation — not chosen to make any result come
out a particular way — and the change proposed **makes sessions harder to pass, not easier**. Both
claims are checkable against what follows.

---

## 1. The defect

The v3 null gate says: the empirical null is N ≥ 20 **pool-vs-pool** sessions (fresh 32-key pool A
against fresh 32-key pool B), and **every one must have raw |t| < 4.5** or the session is
INCONCLUSIVE.

**Two different pools do not have the same mean.** Each pool is a finite sample of 32 keys, and
per-key work genuinely varies, so pool A's mean work and pool B's differ by a fixed, non-zero
amount for that session. The null session's *t* therefore is not standard normal but

```
sd(t_null)² ≈ 1 + (σ_key / σ_total)² · (n / 32)
```

where `σ_key` is the between-key sd of mean work, `σ_total` the per-measurement sd, and `n` the
per-class count. The gate is a fixed cutoff applied to a statistic whose spread **grows with n and
grows as the environment gets quieter**.

**Consequence, observed:** on the ubuntu CI runner (`σ_total` ≈ 32 µs against the laptop's
350–733 µs), `(σ_key/σ_total)²` is ~500× larger, and **5 of 20 null sessions tripped 4.5 at
n = 2 350** while both synthetic controls behaved perfectly (flat PASS, leaky FAIL at *t* = −296).
The session was voided. That is why **every CI session to date reads INCONCLUSIVE**
(`OBSERVATION_ci-ubuntu-2026-08-18.md`).

**The gate as written punishes precision.** The better the measurement environment, the likelier a
session is voided — for arithmetic reasons, not environmental ones. It also fails from the other
direction at scale: at ~10× the v3.1 sample count the same term trips on the laptop too.

## 2. The fix — revised after council review (5 CONFIRMED / 1 OVERSTATED)

The pool-vs-pool design was chosen to be "the real operation", which was right — v2's synthetic
50 µs loop was unfit for an 8 ms operation. The error was using **two different pools**, which
makes it a *random-effects* null rather than a *true* null.

**A first version of this section proposed one replacement null and claimed it "makes the fixed
4.5 gate valid again". The review upheld the mechanism but broke the single-null proposal.** Two
seats independently landed on the same gap (GPT-5.6 F5, Kimi F7): the inflation applies to **any**
pool-A-vs-pool-B comparison, null or not — **including `sign-rr`, which is a gated experiment.**
A same-pool null is matched to `sign-kk` and *mismatched* to `sign-rr`, so one null cannot serve
both. The revised proposal is §2a. The single-pool construction below is still correct; it is one
of three, not the whole design.

**The construction: draw both classes from the SAME pool.**

| | v3 (current) | v4 (proposed) |
|---|---|---|
| id | `null-rr-k` | `null-ss-k` (same-split) |
| pool A | fresh 32 keys | one fresh 32-key pool |
| pool B | a *different* fresh 32 keys | **the same pool** |
| class 0 draws | pool A by index stream | that pool by index stream |
| class 1 draws | pool B by the same index | **that pool, by an independent index draw** |
| true Δmean | **not zero** (two finite pools differ) | **exactly zero by construction** |
| `sd(t)` | `√(1 + (σ_key/σ_total)²·(n/32))` — grows with n | **1**, as the fixed 4.5 gate assumes |

Both classes are then the *same* 32-key mixture, so:

- the true difference is **zero by construction** (`E[x̄₀ − x̄₁] = 0` exactly, conditional on the
  pool), which restores the gate's meaning — **approximately**, not exactly: Welch normality is
  asymptotic, temporal dependence or class-correlated drift can still inflate it, and twenty tests
  retain a non-zero familywise trip rate (GPT F5). "Removes the dominant, growing term" is the
  claim; "makes the gate valid" is not;
- the **mixture shape is preserved**, which matters because the crop statistic is sensitive to
  distribution shape and the gated `sign-rr` experiment compares mixtures. An A/A null on a single
  key (which `sign-aa` already provides) is a true null but a *unimodal* one, so it is not a
  substitute for calibrating a mixture comparison;
- nothing about the operation changes — same signer, same message, same measurement path.

## 2a. One null cannot do two jobs — the matched-null design

The v3 harness used a single construction for two incompatible purposes: **gating the
environment** (which needs a true zero, so any excursion is the machine) and **calibrating the
crop statistic of each experiment** (which needs a reference with the *same class structure* as
the experiment it judges). Pool-vs-pool is wrong for the first and right for the second — but only
for the one experiment built the same way.

| purpose | construction | true zero? | threshold |
|---|---|---|---|
| **environment gate** | `null-ss` — one pool, both classes, independent index draws | **yes** | fixed \|t\| < 4.5 is meaningful here |
| crop reference for **`sign-kk`** (fixed key vs fixed key) | `sign-aa` — same keypair both arms, repeated | **yes** | empirical, from the repetitions |
| crop reference for **`sign-rr`** (pool A vs pool B) | `null-rr` — the *current* null | **no**, by construction | empirical only; a fixed cutoff is meaningless |

With `null-ss` as the gate, Kimi's independent derivation puts the per-session false-trip rate at
**≈ 6.8 × 10⁻⁶**, i.e. ≈ 1.4 × 10⁻⁴ across twenty sessions — a gate that fires on the environment
rather than on arithmetic.

### `sign-rr` cannot be gated against a fixed threshold at all

This follows from §1 and is the review's sharpest consequence. `sign-rr` compares two *fixed*
pools, so under **no leak whatsoever** its statistic carries the same inflation:
`sd(t) ≈ √(1 + (σ_key/σ_total)²·(n/32))`. At v3.1's numbers that is 1.742, and its observed
\|t\| = 0.73 sits comfortably inside it — but at ~10× the samples `sign-rr` would cross 4.5 **with
no leak present**, exactly as the null sessions did on the CI runner. Gating it at 4.5 is the same
error one level up.

So v4 must choose, and pre-register the choice: either **judge `sign-rr` empirically against
`null-rr`** (its matched reference, which is what the current null already is), or **de-gate it**
and report it as informational. The draft's recommendation is the former — it keeps a real
measurement and costs nothing new, since those null sessions are already being run.

`sign-rr` therefore **stays as an experiment**; what changes is that it stops being judged against
a threshold that assumes something untrue about it.

## 3. Measured, not asserted: what the committed data says about this fix

A first version of this section asserted that the fix "does not change v3.1's PASS", because its
crop *p*ₑₘₚ values sat far from the 1/N line. **That was checked against the committed
`report.json` and is wrong.** The numbers below change the proposal's stakes in both directions.

### 3.1 The inflation is real on the laptop too — and larger than predicted

v3.1's 20 null sessions give a **directly observable** test of §1's formula: under a true null the
20 raw *t* values would have sd = 1.

| quantity | value |
|---|---|
| observed sd of the 20 null *t* values | **1.742** |
| mean | −0.593 |
| max \|t\| | 3.94 (the gate is 4.5) |
| implied `σ_key` (per-key sd of mean work) | **≈ 10.4 µs**, from `σ_total` = 257 µs, n ≈ 40 236/class |

The null *t* is **74 % wider than the gate assumes** — on the machine where the gate held. A
`σ_key` of ≈ 10.4 µs predicts `sd(t) ≈ 2.95` on the CI runner (`σ_total` ≈ 32 µs, n = 2 350),
where 5 of 20 sessions tripped 4.5. **A consistent `σ_key` explains both environments** — which is
good evidence that §1's mechanism is real and not a story fitted to an outcome.

**Three caveats the council attached to those numbers, all kept** (`σ_key` was quoted far more
precisely than 20 observations support):

- **`σ_key` is not 10.4 µs; it is somewhere around 10 µs.** An sd estimated from 20 values is
  imprecise: the χ² interval for the underlying *t* spread is ≈ 1.33–2.54, which maps to
  **`σ_key` ≈ 6.3–17.0 µs** (GPT-5.6 F3). Kimi's standard-error view gives ±1.7 µs — a narrower
  statement of a different quantity; the interval is the honest one to quote.
- **5 of 20 is consistent with, not confirmation of, `sd(t) = 2.95`.** At that spread the expected
  number of trips is 2.5 and P(X ≥ 5) ≈ 0.10 — plausible, ≈ 1.6 binomial sd above expectation, and
  far too small a sample to identify the spread (GPT F4, Kimi F3).
- **Carrying `σ_key` between machines is an assumption, not a derivation.** It is a between-key sd
  in absolute microseconds, and different hardware could rescale it independently of the noise
  floor (Kimi F4). The wording above is therefore "a consistent `σ_key` explains both", not "the
  same `σ_key` predicts".

**And the formula is an approximation, not an identity** (GPT F2, Kimi F5). It assumes a
hierarchical model `Y = μ + U_key + ε`, treats the Welch denominator as deterministic, and uses a
32-key CLT; the within-pool key variance is really `(31/32)·σ_key²`, so the denominator is not
literally `σ_total²`. Autocorrelation, non-uniform key selection and key-dependent residual
variance all perturb it. At n in the thousands this is negligible for the *variance*; only
tail-probability statements — which is what a gate is — carry the approximation.

**A pre-registered probability of mine was also too optimistic, by roughly 10×.**
`METHODOLOGY-v3.1-POWER.md` §6 put the chance of any null session tripping 4.5 at 0.1–2 % for
v3.1. At the measured sd(t) = 1.742 it was ≈ **18 %**. The estimate used v3b's `σ_total` = 733 µs,
but the session ran *quieter*, at 257–357 µs — and quieter makes it worse, which is exactly the
counter-intuitive direction this section is about. The prediction's direction held; its confidence
did not.

### 3.2 The fix could flip v3.1's secondary arm — the opposite of what I claimed

SHAPE requires an experiment's crop statistic to exceed **all 20** null sessions.

| gated experiment | crop stat | null sessions ≥ it | *p*ₑₘₚ |
|---|---|---|---|
| `sign-kk-0` | 3.48 | 11 / 20 | 0.571 |
| `sign-kk-1` | **5.84** | 9 / 20 | 0.476 |
| `sign-kk-2` | 5.36 | 9 / 20 | 0.476 |
| `sign-rr` | 1.51 | 19 / 20 | 0.952 |

The null's crop statistics run 0.98 … **10.24**. For `sign-kk-1` to become SHAPE, every null
session must fall below 5.84 — a **43 %** shrink of the null's maximum. Is that plausible under
the fix? The raw-*t* inflation factor is 1.742, and **10.24 / 1.742 = 5.88** — within 1 % of
`sign-kk-1`'s 5.84. If the crop statistic deflates by roughly the same factor as the raw
statistic, the v4 null lands **exactly at the boundary** where v3.1's `sign-kk-1` flips PASS →
SHAPE.

**Therefore:**

- **"This does not change v3.1's PASS" is withdrawn.** It may well change it, and whether the crop
  statistic deflates like the raw *t* is an open empirical question (§4.1), not something to
  settle by reasoning here.
- **The v3 secondary arm has been systematically insensitive.** The same inflation that voids
  sessions on quiet machines also makes SHAPE *too hard to reach*, because the reference it is
  compared against is wider than a true null. Every "no SHAPE" reading in v2, v3, v3b and v3.1 was
  made against an inflated null. That is a **second defect from the same root**, pointing the
  other way: the primary statistic was never affected, but the diagnostic meant to catch
  shape/scale differences has been running with its threshold set too high.
- **The direction of the change is still conservative:** a narrower null makes SHAPE *more*
  likely, never less. v4 makes sessions harder to pass, as §2 claimed — the correction is that
  "harder" may reach back to a result already published, and that must be said now rather than
  discovered later.

### 3.3 Required before v4 is adopted

**Re-judge v3.1's committed raw CSVs against a v4-style null, and publish the outcome whatever it
is.** All ten experiments' raw samples are committed with `SHA256SUMS`, so the experiment side is
byte-reproducible; only fresh same-pool null sessions need measuring. If `sign-kk-1` flips to
SHAPE, `CT_REPORT.md` §4c gets a correction and v3.1 is re-read — not quietly, and not after the
next session has moved on.

## 4. Open questions this draft does not settle

1. **Is `sd(t) = 1` actually restored, or only improved?** Same-pool splitting removes the
   between-pool term. Serial dependence (frequency scaling, interrupts, thermal drift) remains and
   inflates the variance of *any* difference-of-means statistic. The honest claim is "removes the
   dominant, growing term", and the residual **must be measured**: run the v4 null and compare the
   observed sd of its *t* values against 1 — the same check §3.1 applies to v3.1, where it gave
   **1.742**. And separately: **does the CROP statistic deflate by the same factor as the raw
   *t*?** §3.2 shows v3.1's secondary verdict may hinge on that ratio, and it is not derivable
   from first principles — it depends on how cropping interacts with the mixture's tails.
2. **Should the gate be a per-session cutoff at all?** An alternative is to gate on the *set*: e.g.
   reject if the observed sd of the N null *t* values exceeds a pre-registered bound, which tests
   the assumption directly instead of via a max-of-N. That is more robust but needs its own
   pre-registered threshold and would change the INCONCLUSIVE rate in ways not yet modelled.
3. **Class-bit independence.** With both classes drawing from one pool, the two arms must draw
   **independent** indices — reusing the same index for both classes would make every measurement
   pair the same key and collapse the mixture. This is an implementation trap worth a test.
4. **What N should be**, once the gate is valid. N = 20 gives the empirical *p* a 1/21 floor; that
   was chosen when the null was the expensive part. If the null gets cheaper to satisfy, more
   sessions buy resolution in the SHAPE arm.
5. **Whether the machine changes at the same time.** Doing both at once confounds them. The
   proposal is to run v4 **on the laptop first** to verify the gate behaves, then move machines as
   a separate, second change.

## 5. Not in this draft

Everything else in `V4_BACKLOG.md` §C — interleaving the null with the experiments, `sign-kk` arm
randomisation, the different-key swapped-arm control, cluster-robust standard errors, TOST with a
pre-registered margin, the gated message-varying design. Each needs its own pre-registration, and
bundling them would make a failed session impossible to attribute.

---

**Next step: council review of this draft, then revision, then commit as `METHODOLOGY-v4.md`
before any v4 measurement.** The machine change is a separate decision and is Brandon's.
