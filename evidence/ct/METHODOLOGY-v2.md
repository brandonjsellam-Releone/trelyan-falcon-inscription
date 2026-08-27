# Constant-time evidence for the pinned Falcon-1024 det1024 signer — methodology **v2**

**Written 2026-08-18, after the first v1 session and its review, before any v2 measurement.**
Supersedes `METHODOLOGY.md` (v1) for every session dated after this file. v1 is left unchanged
as the record of what the first session was judged by. What v2 changes, and why, is stated per
rule; everything not restated here (experiments' fixture construction, the meaning of the
verdict words, "observation not gate", the never-patch rule, what is recorded) carries over
from v1 unchanged.

## 0. Why a v2 exists

The v1 session (`session-2026-08-18-local`) produced FAIL on both gated experiments with a
**null raw Welch *t*** (−0.73 / +0.83) and separation only under percentile cropping. Five
independent reviewers converged on the same objection: `max |t|` over ten *correlated* tests
against a *single-test* cutoff has no multiplicity control, and one-sided cropping at a pooled
percentile removes more samples from the higher-variance class, which can shift the retained
means apart with no location difference in the underlying distributions. v1's statistic could
therefore call "shape differs" a "leak". v2 fixes the statistic before any Falcon result is
called one.

## 1. Statistic and rule (changed)

- **Primary statistic: the raw (uncropped) Welch two-sample *t*** on the warm-up-trimmed
  samples. Threshold **|t| ≥ 4.5** in absolute value, minimum **2 000 per class** — as v1, but
  applied to the raw *t* only.
- **Secondary diagnostic: the crop statistic `max |t|` over the nine v1 crops**, judged **not**
  against 4.5 but against an **empirical null** built in the same session: the harness runs the
  flat control **N ≥ 20** times (default 24), computes `max |t|` over the nine crops for each,
  and reports the observed Falcon crop statistic's rank against that null as an empirical
  *p*-value. **A crop finding is called "distinguishable in shape/scale" only if its `max |t|`
  exceeds every null session's (empirical *p* < 1/N); it is never called FAIL on its own.**
- **Reported per experiment:** raw *t*, Welch–Satterthwaite degrees of freedom, a two-sided
  *p*-value for the raw *t* (Student's *t* approximated by the normal for df ≥ 100, which every
  experiment here exceeds), the difference of means with a 95 % confidence interval, the crop
  statistic and its empirical *p*, per-crop retained counts.
- **Verdict words (unchanged meaning, changed inputs):** PASS = controls behaved, n ≥ minimum,
  raw |t| < 4.5 **and** crop empirical *p* ≥ 1/N; **SHAPE** (new, informational) = raw |t| < 4.5
  but crop empirical *p* < 1/N — *distributions differ in shape/scale, means do not*; FAIL = raw
  |t| ≥ 4.5 with controls behaved (a **location** difference); INCONCLUSIVE = a control
  misbehaved or n below minimum. SHAPE is never reported as PASS and never as FAIL.
- Controls: as v1 (flat must PASS on the raw statistic; leaky must FAIL on the raw statistic),
  plus the N flat sessions must themselves all PASS on the raw statistic or the environment is
  declared too noisy → every Falcon verdict INCONCLUSIVE.

## 2. Experiments (changed: two designs added, one demoted)

| id | timed call | class 0 | class 1 | role in v2 |
|---|---|---|---|---|
| `control-flat` ×N | fixed-work loop | — | — | environment + empirical null for the crop statistic |
| `control-leaky` | class-dependent loop | short | long | harness power |
| **`sign-kk`** (new) | `sign_compressed(sk, M0)` | fixed key **K_a** | fixed key **K_b** | **the primary key-dependence design**: two point masses; a raw-*t* separation is a per-key timing fingerprint of size (mean₁ − mean₀). Repeated for three key pairs (a,b), (c,d), (e,f) drawn fresh; the session's key verdict is the worst of the three. |
| **`sign-rr`** (new) | `sign_compressed(sk, M0)` | key from pool A (32) | key from pool B (32) | **mixture-vs-mixture control**: symmetric variance; a separation here would indicate a systematic difference between two random key populations, which should not exist — expected PASS. |
| `sign-key` | as v1 | fixed K0 | pool key | **demoted to screening**; reported, not gated |
| `sign-msg` | as v1 | fixed M0 | random msg | screening; reported, not gated |
| `verify-ctrl`, `keygen` | as v1 | | | informational |

**Gated in v2:** `sign-kk` (all three pairs) and `sign-rr`. Session verdict = worst gated verdict
with SHAPE ranking between PASS and FAIL for reporting but **not** blocking anything by itself
(it is a call for the source-level reading, not a leak claim).

## 3. Environment (changed: stated and, where possible, controlled)

- Timer resolution stated per OS in the report: Windows `Instant` = QPC (~100 ns); Linux/macOS
  `clock_gettime`/`mach_absolute_time` (~ns).
- The harness attempts to pin itself to one CPU where the platform allows (recorded as
  `affinity_pinned: true/false` in the report; not attempted on platforms without a std path).
- Turbo/DVFS state is not controlled by the harness; the report says so and the local session
  notes the machine state by hand.
- Same measurement discipline as v1: fixtures outside the timed region, randomised class order,
  2 % warm-up discard.

## 4. What v2 does not change

Observation, not a gate. INCONCLUSIVE never reads as PASS. SHAPE never reads as PASS or FAIL.
The vendored primitive is never patched. Raw CSVs are retained for every named session. A PASS
is machine- and build-specific and is not a proof of constant-time behaviour. The source-level
reading of `sign.c` / `fpr.c` remains a separate human deliverable.
