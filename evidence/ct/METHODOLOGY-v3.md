# Constant-time evidence for the pinned Falcon-1024 det1024 signer — methodology **v3**

**Written 2026-08-18, after the v2 session and its review, before any v3 measurement.**
Supersedes `METHODOLOGY-v2.md` for sessions dated after this file. v1 and v2 stay unchanged as
the records their sessions were judged by. Everything not restated here carries over from v2.

## 0. Why a v3 exists

The v2 session's crop diagnostic was uninterpretable: its empirical null came from a ~50 µs
synthetic loop, and every crop *p* — including the pool-vs-pool control's — sat at the 1/25
floor. A null that does not model the operation cannot judge it. Two further objections from
the review: `sign-kk` used one fixed message per key pair, so a key effect was confounded with
key × message; and no combination rule across the three pairs (or multiplicity correction) had
been pre-registered.

## 1. Statistic and rule (changed where stated)

- **Primary statistic — unchanged:** raw Welch *t*, |t| ≥ 4.5 → FAIL, minimum 2 000 per class.
- **Secondary diagnostic — the null is now the real operation.** The harness runs **N ≥ 20
  pool-vs-pool signing sessions** (each: two *fresh*, independent 32-key pools, the same
  measurement count as the experiments, class randomised per measurement) and takes their
  nine-crop statistics as the empirical null. Every null session must itself PASS on the raw
  statistic, else the environment is too noisy → all Falcon verdicts INCONCLUSIVE.
- **Per-experiment SHAPE** iff raw |t| < 4.5 **and** crop statistic > every null session
  (empirical *p* = 1/(N+1)).
- **Combination rule for `sign-kk` (pre-registered):** the three key pairs are three tests; the
  session's key-dependence verdict is **FAIL** if any pair FAILs on the raw statistic; **SHAPE**
  only if **at least two of the three pairs** are SHAPE (with N = 20 this bounds the family-wise
  false-SHAPE rate at ≈ 0.7 % under independence); otherwise PASS. Individual pair results are
  reported regardless.
- **Descriptive statistics** (Δmean, 95 % CI, *p* on the raw *t*) are reported and are **not**
  decision criteria. The report may not use the words "distinguishable", "fingerprint" or
  "leak" about them.

## 2. Experiments (changed: key × message separation)

| id | timed call | class 0 | class 1 | change vs v2 |
|---|---|---|---|---|
| `null-rr-k` ×N | `sign_compressed(sk, M0)` | key from fresh pool A_k | key from fresh pool B_k | **new**: the real-operation null |
| `control-leaky` | class-dependent loop | short | long | unchanged (harness power) |
| `control-flat` | fixed-work loop | — | — | unchanged, informational (no longer the null) |
| **`sign-kk-p`** ×3 | `sign_compressed(sk, m_i)` | fixed key K_a | fixed key K_b | **messages rotate**: `m_i` cycles through **four fixed messages in the same order for both classes** (message index = measurement index mod 4), so the comparison is key-only, message-balanced |
| `sign-rr` | `sign_compressed(sk, M0)` | pool A | pool B | unchanged; now one more draw against the same-kind null |
| `sign-key`, `sign-msg` | as v1 | | | screening, reported |
| `verify-ctrl`, `keygen` | as v1 | | | informational |

Gated: `sign-kk` (combined per §1) and `sign-rr`. Session verdict = worst of those two.

## 3. Environment (unchanged, stated)

Timer per OS stated; **no core pinning** (std has no affinity API and no dependency is added
for it — recorded as `affinity_pinned: false`); turbo/DVFS not controlled; FPEMU-specific;
one machine per session. Windows QPC ≈ 100 ns.

## 4. Cost

With 4 200 measurements per experiment (≈ 2 058 per class after warm-up) and N = 20 null
sessions, a session is ≈ 20 × 34 s (null) + ≈ 6 min (experiments) ≈ **17 min** on the i9
desktop; longer on shared CI runners.

## 5. Unchanged

Observation, not a gate. INCONCLUSIVE never PASS. SHAPE never PASS, never FAIL. The vendored
primitive is never patched. Raw CSVs retained for named sessions. A PASS is machine- and
build-specific and is not a proof.
