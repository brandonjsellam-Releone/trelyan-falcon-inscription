# Controls pre-registration — TEAM DRAFT (2026-08-20) — NOT IN FORCE

**Status: DRAFT.** Produced by the six-seat team (zuss, 8/9 seats) under the blindness clause
of PREREG_v41-release-replicate.md §3a(3): written from methodology only, no numeric values
from any session. It takes force only when committed as a dated pre-registration AFTER the
release-replicate decision, in the ruled order. The majority locks **Option (a)** (crop-shape
is NOT part of the synthetic-control hypothesis: a synthetic crop null cannot calibrate the
Falcon crop path — the non-transfer argument); a full minority Option (b) draft is included
with the founder decision criterion, because the split is real. Transcript:
trelyan-apex-council/tasks/OUT_controls-prereg-design_2026-08-20.md.

---

## deepseek (deepseek-v4-pro)

# TRELYAN R&D — Controls pre-registration for `falcon-ct`: Is crop-shape part of the CONTROL hypothesis?

**Document:** `PREREG_falcon-ct_controls_crop-in-hypothesis`  
**Blindness:** methodology-only under `PREREG_v41-release-replicate.md §3a(3)`. No result from any existing session is used. The only numbers below are already committed (`|t| ≥ 4.5`; `40k` vs `60k`), algebraic consequences of those commitments (midpoint `50k`), or prospective design constants derived from stated error targets.

**Seat outcome:** split.  
**Majority lock:** **Option (a)** — crop-shape is **not** part of the synthetic control hypothesis.  
**Minority draft:** **Option (b)** — included in full because the split is real. It is a permissible choice only under the founder criterion below.

---

## 1. Core reasoning

The in-force interim ruling is:

> Synthetic controls are judged on the raw Welch `|t| ≥ 4.5` line only. Their crop statistics are descriptive and decide nothing, because a synthetic loop and the real signing operation do not share a crop null.

That mismatch is decisive. A synthetic crop null cannot calibrate, and cannot gate, the Falcon crop/SHAPE path. Option (b) would demonstrate that the crop code can see a planted synthetic shape difference and remain quiet on synthetic flats. That is a useful software-aliveness fact, but it does **not** transfer to Falcon crop behavior.

Therefore, for **session synthetics**, the correct control hypothesis remains:

> The apparatus does not invent a raw location difference on identical work, and it detects the committed planted raw location difference.

Shape-type claims, if ever made, require a separate **Falcon-matched** crop null and power study — not a synthetic crop-null family.

---

# DRAFT A — MAJORITY LOCK: Option (a)

## A.1 Choice

**Crop-shape detection is not part of the CONTROL hypothesis.**  
Option (a). The interim ruling becomes permanent for this harness profile.

## A.2 Normative rule set

### C0 — Scope of control judgment

For `control-flat` and `control-leaky`, the **only** gating statistic is raw Welch `|t|` on the per-trial scalar:

- Fire: `|t| ≥ 4.5`
- Quiet: `|t| < 4.5`

Crop/SHAPE outputs on those same trials SHALL be computed and retained as descriptive attachments only. They SHALL NOT gate, modify `|t|`, set a threshold, or be pooled into a running crop-null.

### C1 — `control-flat`

- Identical work in both classes.
- Same declared constant iteration count in both classes.
- Same `black_box` wrapper, trial count, harness, and profile as the Falcon arm it gates.

Required outcome:

- `|t| < 4.5` → `CTRL_FLAT = PASS`
- `|t| ≥ 4.5` → `CTRL_FLAT ≠ PASS`

### C2 — `control-leaky`

- Class-dependent location plant: `40k` vs `60k` black-boxed iterations by class.
- Otherwise identical wrapping, count, scheduler, and profile.

Required outcome:

- `|t| ≥ 4.5` → `CTRL_LEAKY = FAIL` — this is the **good** outcome: the planted leak was detected.
- `|t| < 4.5` → `CTRL_LEAKY = MISS`

### C3 — No third synthetic control

No synthetic-shape positive control. No synthetic crop-null family. No held-out crop-null sessions. No session-gating use of Annex S.

### C4 — Independence

Flat and leaky are separate trial streams. One stream’s scalars SHALL NOT enter the other stream’s Welch calculation.

### C5 — Descriptive crop watch

Each session SHALL log the crop/SHAPE tuple for both synthetics under a fixed schema. These logs exist for later falsification review. No numeric threshold is set here.

### C6 — Manifest freeze

Before Falcon sessions on a profile, freeze:

- harness hashes,
- compiler/runtime identifiers,
- machine/profile/affinity policy,
- scheduler,
- observation counts,
- wrapper behavior,
- ordered list of crop/SHAPE outputs.

A change that can affect timing, wrapping, counting, or crop procedure is a new profile.

## A.3 Failure semantics: INCONCLUSIVE-never-PASS binds

Let `V` be the session Falcon verdict.

Security evaluation is asymmetric:

- An apparatus that invents a difference on identical work taints both PASS and FAIL.
- An apparatus that misses a planted leak forbids a cleanliness PASS, but a real Falcon difference that survived a blind apparatus is not an artifact of that blindness.

| Controls | Allowed session verdict `V` |
|---|---|
| `CTRL_FLAT = PASS` and `CTRL_LEAKY = FAIL` | Falcon rules decide: `PASS`, `FAIL`, or `INCONCLUSIVE` |
| `CTRL_FLAT ≠ PASS` | **INCONCLUSIVE only** |
| `CTRL_LEAKY = MISS` and `CTRL_FLAT = PASS` | **PASS forbidden**; `V ∈ {FAIL, INCONCLUSIVE}` |
| Both misbehave | **INCONCLUSIVE only** |
| Mechanically invalid session | **INCONCLUSIVE only** |

**Never-PASS is absolute.** No crop plot, large Falcon statistic, post-hoc exclusion, or operator override may promote a session to PASS when the table forbids it.

Campaign PASS corpus membership requires both:

- `CTRL_FLAT = PASS`
- `CTRL_LEAKY = FAIL`

INCONCLUSIVE sessions count against cleanliness and do not count toward any pre-registered session N for PASS.

## A.4 Cost in sessions

- Incremental baseline sessions: **0**.
- Per Falcon session: **2 synthetic arms**, already required.
- Crop-null family: **0**.
- Held-out crop sessions: **0**.

**Mandatory disclosure on every report using this pre-registration:**

> Session controls demonstrated raw-location Type I and raw-location Type II. They did **not** demonstrate crop/SHAPE sensitivity or crop/SHAPE Type I. Crop figures attached to synthetics are descriptive. Absence of shape-type leakage is **not a control-backed claim**.

## A.5 Annex S — non-gating software-aliveness check

Once per harness/profile version, before any Falcon session, run the registered crop/SHAPE pipeline on an offline planted-shape synthetic:

- Class 0: equal-weight mixture of `40k` / `60k`; if `n` is odd, one trial at `50k`.
- Class 1: constant `50k`.
- Same wrapper, same count, same profile.
- A committed coin chooses which class receives the mixture.
- All comparisons two-sided.

Annex S passes only if the crop/SHAPE path reports the mixture class as more shape-extreme than a parallel flat run in the direction the registered Falcon procedure reads as shape.

If Annex S fails, the crop path is dead code. **Fix it before any Falcon session.** Annex S is not a session gate, does not set a numeric crop threshold, and does not license shape-absence claims.

## A.6 Falsification: when Option (a) must be revisited

Re-open this pre-registration if any of:

1. **Claim-set drift** — anyone issues a shape-absence or “crop-clean” claim under these controls without a separate Falcon-matched qualification study.
2. **Ghosting** — descriptive crop logs on `control-flat` are repeatedly loud in a concerning direction while raw `|t|` stays quiet.
3. **Verdict-path change** — a later Falcon pre-reg lets crop/SHAPE decide PASS/FAIL. Option (a) stays correct for synthetics, but Falcon must then supply a Falcon-matched null and power study.
4. **Relevant miss** — an independent mean-matched variance/tail plant in the real signing path, or a Falcon-faithful simulator, is missed by the crop pipeline.
5. **Misuse** — synthetic crop statistics are interpreted as sharing a null with Falcon.

Non-triggers: a single ugly descriptive crop plot; Annex S firing; wanting shape-absence claims; budget remaining for extra synthetic sessions.

---

# DRAFT B — MINORITY: Option (b)

This draft is for a founder who wants in-session proof that the crop path can see a synthetic shape plant and remain quiet on synthetic flats — **and who will still print that this does not transfer to Falcon.**

## B.1 Choice

**Crop-shape detection is part of the CONTROL hypothesis.**  
Option (b). The interim ruling is amended: raw Welch remains the gate for location controls, **and** crop/SHAPE is additionally gated by a matched synthetic-null family plus a synthetic shape-positive control.

`C` denotes the registered Falcon crop/SHAPE output reduced by a pre-declared, Falcon-identical functional. No new crop formula is introduced here. If `C` is undefined on a session, that arm is invalid.

## B.2 Generators

Let `K = 50k`.

- **G-flat:** both classes constant `K`.
- **G-leaky:** class 0 = `40k`, class 1 = `60k`. Unchanged.
- **G-shape:**
  - Fixed class: every observation at `K`.
  - Mixture class: half of observations at `40k`, half at `60k`; if `n` is odd, one observation at `K`.
  - Assignment permuted under a committed seed.
  - A committed coin chooses which class receives the mixture.
  - Scheduled means are equal; the plant is variance/tail, not location.

G-shape location pre-condition: raw Welch `|t|` on G-shape must be `< 4.5`. If it fires, the shape plant is location-confounded and the arm is invalid.

## B.3 Matched synthetic-null family

- Population: **G-flat** sessions, same harness, profile, count, and crop procedure.
- Family members are split by pre-registered session IDs **before** any `C` is inspected:
  - **CAL** sets the threshold.
  - **CONF** checks Type I and never sets the threshold.
- A Falcon session is gated by the CAL threshold only if it is not a family member.
- No pooling, interpolation, or reuse across profile/count cells.

## B.4 Tail-error target and session-count rule

Target type-I rate for crop on a new G-flat session:

> `α_crop = 0.01`

This is deliberately weaker than the Welch `4.5` line. A Welch-equivalent nonparametric tail is infeasible.

Calibration:

- `N_cal = 99`
- Threshold `τ` = maximum of the pre-declared extremity of `C` over the 99 CAL sessions.
- Crop-fire iff `extremity(C) > τ`. Ties are quiet.

This follows from exchangeability: for continuous i.i.d. `C`, the probability that a new flat is more extreme than all 99 calibration flats is `1/(99+1) = 0.01`.

Held-out confirmation:

- `N_conf = 300` fresh G-flat sessions, never in CAL.
- Let `X` = number of CONF sessions with `extremity(C) > τ`.
- **Family INVALID if `X ≥ 8`** under the design `p ≈ 0.01`.
- An INVALID family means no session may PASS until a new family is built under a revised pre-registration.

**Family build cost: 399 G-flat sessions before any Falcon session can be crop-gated.**

If the founder will not pay 399 sessions up front, Option (b) is infeasible. Do not shrink `N` to 20, and do not take `τ` from any existing or Falcon session.

## B.5 Numeric per-session fire conditions

After the family is valid, each Falcon session runs:

1. **G-flat raw:** `|t| < 4.5`
2. **G-leaky raw:** `|t| ≥ 4.5`
3. **G-flat crop:** `extremity(C) ≤ τ`
4. **G-shape crop:** `extremity(C) > τ` **and** G-shape raw `|t| < 4.5`

## B.6 Failure semantics

Never-PASS is absolute.

| Condition | Allowed session verdict `V` |
|---|---|
| All four gates good | Falcon rules apply |
| `CTRL_FLAT ≠ PASS` or flat crop ghost | **INCONCLUSIVE only** |
| `CTRL_LEAKY = MISS` or shape crop miss, with no ghosting | **PASS forbidden**; `V ∈ {FAIL, INCONCLUSIVE}` |
| G-shape invalid due to location confusion | **INCONCLUSIVE only** for any crop-using verdict; location-only Falcon FAIL remains admissible if leaky fired and flat quiet |
| Family INVALID or no family for the cell | **No session PASS** until revised pre-registration and new family |
| Mechanically invalid session | **INCONCLUSIVE only** |

Campaign PASS corpus requires the full four-gate conjunction.

**Mandatory residual disclosure even under Option (b):**

> Controls demonstrated that the crop path, on synthetic loops, is 1%-quiet relative to a synthetic-flat family and fires on a mean-matched `40k`/`60k` mixture. A synthetic crop-null does **not** transfer to Falcon. `extremity(C) ≤ τ` on synthetics is **not** evidence that Falcon is shape-clean.

## B.7 Cost

- Family build: **399 G-flat sessions** per profile/count cell.
- Per Falcon session: **3 synthetic arms** instead of 2.
- Rebuild required on any crop-procedure, count, wrapper, or profile change.
- Paying 399 sessions does **not** buy a Falcon shape claim.

## B.8 Falsification: when Option (b) must be revisited

1. Family cost not paid, `N` shrunk after seeing CONF, or `τ` taken from an existing/Falcon session → discard and revert to (a) or a new pre-registration.
2. G-shape systematically fails the location-quiet pre-condition.
3. A second independent family also fails CONF → drop crop-gating and revert to (a).
4. A Falcon-faithful simulator shows crop-on-synthetics and crop-on-Falcon disagree on fire/quiet → revert to (a).
5. Reports cite synthetic `C ≤ τ` as evidence Falcon is shape-clean → void.
6. Crop/SHAPE is removed from every Falcon decision path → revert to (a).

---

## 2. Founder decision criterion

Apply in order.

### Step 1 — Claim-set

Will this campaign, or any report from it, assert absence of shape-type leakage, or print crop/SHAPE as a reassuring Falcon result?

- **No:** Lock **Option (a)**. Annex S is mandatory.
- **Yes:** Option (b) still does **not** support that assertion. Go to Step 2.

### Step 2 — If a shape-absence claim is required

Commission a separate **Falcon-matched** crop null and power study.

For session synthetics, still lock **Option (a)**.

Lock Option (b) only if the founder additionally wants non-transferring synthetic crop theater, will pay **399** family sessions up front, and will still print the non-transfer disclaimer. Otherwise Option (b) is infeasible.

### Step 3 — Budget veto

If paying 399 G-flat sessions would reduce the Falcon corpus, lock **Option (a)**.

### Step 4 — Forbidden compromises

- Do not lock (a) and then let crop decide Falcon PASS.
- Do not lock (b) with `N = 20`, `α = 0.05`, or a threshold taken from any existing session.
- Do not treat Annex S as a Falcon-matched null.
- Do not treat Option (b)’s `τ` as evidence about Falcon.
- Do not amend the committed `40k`/`60k` leaky plant.
- Do not invent a new crop formula and call it a control for the registered pipeline.
- Do not convert INCONCLUSIVE to PASS after seeing Falcon `V`.

**Default if the founder does not take Step 1 explicitly:** lock **Option (a)**.

---

## CONFIDENCE

**High.** The decisive technical fact — that synthetic loops and real signing do not share a crop null — is already committed and is the correct reason to keep session synthetics on the raw Welch line. Option (b) is included only as a conditional minority because the founder’s claim-set and willingness to pay for non-transferring synthetic crop validation are not settled by the technical record.

## UNRESOLVED

- **Founder choice:** whether the campaign requires a shape-absence claim and/or will pay 399 synthetic family sessions. Settled by the founder applying Steps 1–3.
- **Exact crop score `C`:** Option (a) does not need it; Option (b) requires the registered Falcon crop/SHAPE scalarization to be frozen. Settled by the Falcon crop-pipeline specification.
- **Wrapper determinism/jitter:** whether `black_box` adds jitter affects whether G-shape’s fixed class is degenerate, but the variance plant remains specified. Settled by the harness manifest.
- **Whether Falcon verdicts may rest on crop/SHAPE:** this changes the cost of Option (a), not the non-transfer argument. Settled by the Falcon pre-registration.

8/9 seats succeeded
