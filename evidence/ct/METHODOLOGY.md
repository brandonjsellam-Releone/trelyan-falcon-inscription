# Constant-time evidence for the pinned Falcon-1024 det1024 signer — pre-registered methodology

**Written 2026-08-18, before the first measurement of the Falcon path.** This document fixes what
will be measured, how, and what the words PASS / FAIL / INCONCLUSIVE mean, so that the result
cannot be tuned after the fact. Changing any rule here after a Falcon run requires a new dated
version of this file and a re-run.

## 0. What this is and is not

- It is **timing evidence** about the pinned reference implementation
  (`third_party/falcon-det1024/src`, `algorand/falcon@ce15e75b`, emulated fixed-point FP backend
  `FALCON_FPEMU=1`, built with the flags in `rust/crates/trelyan-pq-ffi/build.rs`), measured
  through the Rust FFI on a named machine. It answers: *do the signing (and key-generation) times
  depend, detectably, on the secret key or on the message?*
- It is **an observation, not a product gate** (`PLAN_RD-AtoZ_2026-08-18.md` Phase D). A FAIL or
  INCONCLUSIVE result blocks Phase E (the self-KAT signer as a default) and any constant-time
  claim; it never results in a patch to the vendored primitive (constitution §2.6, zero-patch
  ledger). PASS on one machine is *not* a proof of constant-time behaviour — statistical testing
  cannot establish source-level constant-time; it can only fail to find a leak at a given power.
- Constitution §2.2 requires constant-time **discipline**; this is the first piece of **evidence**
  about whether the pinned artifact meets it. The flagship SDK's own README already disclaims CT
  guarantees for the binding; nothing here changes that disclaimer until it is earned.

## 1. Test statistic and rule (fixed)

- **Welch's two-sample *t*** between the timing samples of two classes, computed on the raw
  samples and on nine percentile-cropped variants (samples above the pooled 50th, 60th, 70th, 80th,
  90th, 95th, 97th, 98th, 99th percentile discarded — dudect's cropping to reduce tail noise from
  interrupts and scheduling). **The reported statistic is `max |t|` over the ten variants.**
- **Threshold: `|t| ≥ 4.5` ⇒ the two classes are distinguishable at this sample size.** Absolute
  value — a large *negative* *t* is a leak in the other direction, not a pass (the ZUSS draft's
  one-sided `t ≥ 4.5` was rejected in adversarial review for exactly this reason).
- **Minimum sample size:** at least 2,000 measurements per class per experiment before any verdict
  is issued; fewer ⇒ INCONCLUSIVE.
- **Class order is randomised per measurement** (a random bit from the SHAKE PRNG), so slow drift
  (thermal, frequency scaling, background load) affects both classes equally.
- **Warm-up:** the first 2 % of measurements of each experiment are discarded.
- **Multiple tests:** four Falcon experiments and two controls are run per session; the threshold
  is applied per experiment, and the session verdict is the *worst* Falcon experiment's verdict.
  No p-value correction is applied — the threshold 4.5 already corresponds to a very small
  false-positive rate for a single test, and under-reporting a leak is the more expensive error here.

## 2. Experiments (fixed)

Each experiment times exactly one call through `trelyan-pq-ffi` (no allocation inside the timed
region; stack buffers pre-allocated), with `std::time::Instant` (monotonic; sub-microsecond
resolution on all three CI OSes; the timed operation is on the order of a millisecond, so counter
resolution is not the limiting factor). Cycle counters are deliberately not used: reading them
needs `unsafe`, which the constitution confines to the ffi crate, and they add nothing at this
time scale.

| id | timed call | class 0 | class 1 | what a FAIL means |
|---|---|---|---|---|
| `control-flat` | a fixed-work synthetic loop, identical for both classes | — | — | the **environment** is too noisy for a verdict → every Falcon experiment in this session is INCONCLUSIVE |
| `control-leaky` | a synthetic loop whose work depends on the class bit | short | long | if this does **not** FAIL, the harness lacks power → every Falcon experiment in this session is INCONCLUSIVE |
| `sign-key` | `sign_compressed(sk, M0)` | one fixed key `K0` | a key drawn uniformly per measurement from a pool of 32 fresh keys (`K0` excluded) | signing time depends on the **secret key** — the leak that matters most |
| `sign-msg` | `sign_compressed(K0, m)` | fixed 64-byte message `M0` | fresh random 64-byte message per measurement | signing time depends on the (public) message; informative for the hash-to-point / sampler path, less severe |
| `verify-ctrl` | `verify_compressed(sig, pk, M0)` | fixed valid signature `S0` | a valid signature drawn from a pool of 32 (each under its own key/pk) | verification is public-data only; reported as a reference point, not gated |
| `keygen` | `keygen(rng)` | PRNG seeded from a fixed seed | PRNG seeded from a fresh random seed per measurement | Falcon key generation is rejection-sampled and therefore **expected** to be variable-time; reported, never gated, so the report does not read as "keygen leaks" without that context |

Message length 64 bytes throughout (the SDK's inscription messages are ~102 bytes; the length is
public and fixed within an experiment).

## 3. Verdict words (fixed)

- **PASS** — both controls behaved (flat < 4.5, leaky ≥ 4.5), n ≥ minimum, and the experiment's
  `max |t| < 4.5`. Meaning: *no timing dependence detected at this power on this machine.* Not a
  proof.
- **FAIL** — controls behaved, n ≥ minimum, and `max |t| ≥ 4.5`. Meaning: *the two classes are
  distinguishable; the operation's timing depends on the class input.*
- **INCONCLUSIVE** — a control misbehaved, or n below minimum, or the harness errored. Meaning:
  *no statement can be made from this run.* **INCONCLUSIVE is never reported as PASS**, in the
  JSON, in CI, or in prose.

## 4. What is recorded (fixed)

Per session: `report.json` (parameters, environment: OS/arch/toolchain/CPU count/hostname-free,
per-experiment n, means, standard deviations, the ten *t* values, `max |t|`, verdict; session
verdict) and one raw CSV per experiment (`class,nanoseconds`) so anyone can recompute the
statistic. Raw data from the first local session and from CI runs are retained (repo for the
first; CI step summary + job log for CI runs).

## 5. Known limitations (stated up front)

- One machine, one compiler, one OS per run: a PASS is machine-specific. CI runs on shared
  runners are noisy and are expected to come back INCONCLUSIVE more often than not — that is the
  honest outcome, not a defect of the harness.
- The FPEMU backend does its floating point in integer arithmetic; a native-FP build (never used
  by TRELYAN) would have a different timing profile and is out of scope.
- No source-level constant-time review accompanies this first version; that is a separate,
  human-read deliverable (Phase D's second half in the plan) and this document does not claim it.
