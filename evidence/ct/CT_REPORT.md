# Falcon-1024 det1024 constant-time evidence — session reports

**Target throughout:** pinned `algorand/falcon@ce15e75b`, vendored at
`third_party/falcon-det1024/src`, compiled by `trelyan-pq-ffi` with
`-O3 -DFALCON_UNALIGNED=0 -fno-strict-aliasing`, `config.h` `FALCON_FPEMU=1`. **Harness:**
`rust/crates/falcon-ct` (release). The vendored primitive is never patched.

---

## Where this stands — read this first

**Five sessions, four pre-registered methodologies. The current reading is §4c.**

| session | method | verdict | what it is worth today |
|---|---|---|---|
| v1 `…-local` | `METHODOLOGY.md` | FAIL by the v1 rule | **Withdrawn.** Crop-driven; the v1 statistic (max \|t\| over ten crops against a single-test cutoff) was unfit. §3a |
| v2 `…-v2` | `METHODOLOGY-v2.md` | SHAPE by the v2 rule | **Not interpretable.** Its null was a synthetic loop unfit for an 8 ms operation. §4a |
| v3 `…-v3` | `METHODOLOGY-v3.md` | INCONCLUSIVE | Correct refusal: the random class split fell under the per-class floor. §4b |
| v3b `…-v3b` | `METHODOLOGY-v3.md` | PASS | Real but **power-limited**: MDE₉₀ 72–175 µs. §4b |
| **v3.1 `…-v31-hp82k`** | **+ `METHODOLOGY-v3.1-POWER.md`** | **PASS** | **The current result: 82 000 measurements/experiment, all five gates passed, MDE₉₀ ≈ 14.5 µs. §4c** |

**Nothing in this document is a constant-time claim.** The strongest statement any session
supports is *no per-key location difference at or above that session's stated MDE₉₀ was detected
on this machine and build* — which is non-detection at a stated power, not absence. A timing
session can demonstrate leakage; it cannot demonstrate its absence.

Earlier sections are kept **unedited except where a correction is marked**, because the record of
what was claimed and then withdrawn is itself the evidence that the process works. Three separate
readings were weakened by council review before v3.1, and v3.1 then failed to reproduce the
numbers behind two of them (§4c).

---

## 1st session (v1) — SESSION VERDICT: **FAIL** (by the pre-registered rule) — **withdrawn; read §3a**

**Session:** `session-2026-08-18-local` · **Method:** `METHODOLOGY.md` (2026-08-18, pre-registered before this run; commit `65d2c42`).

Both gated experiments distinguish their two classes at `max |t| ≥ 4.5` with both controls behaving, so by the rule fixed in METHODOLOGY v1 the word is FAIL. **This is an observation, not a gate** (METHODOLOGY §0): it blocks Phase E (the self-KAT signer as a default) and any constant-time claim for the pinned signer, and it does **not** result in any change to the vendored primitive.

**What the FAIL supports, after the team's review (§3a): only that the two timing distributions differ in *shape/scale* — the raw Welch *t* is null (−0.73 / +0.83) and the separation appears only under percentile cropping. That is not sufficient evidence of secret-dependent timing, and for exploitability this session is INCONCLUSIVE.** The v1 rule (max |t| over ten crops against a single-test 4.5 cutoff, without multiplicity control) is the part of the methodology this session exposed as too weak; v2 will fix the statistic before any Falcon result is called a leak.

## 1. Environment (recorded)

| | |
|---|---|
| Machine | desktop, Intel Core i9-9900K, 16 hardware threads, Windows 11 (`windows` / `x86_64`), no other load |
| Toolchain | rustc 1.97.1 (release profile), MinGW-w64 GCC 16.1.0 for the C |
| Timer | `std::time::Instant` (monotonic; on Windows this is `QueryPerformanceCounter`, **≈ 100 ns ticks** — sub-microsecond, not nanosecond; adequate against ~8 ms operations but stated exactly) |
| Not controlled | CPU affinity/pinning, turbo/frequency scaling, thermal state — none pinned in this session (a v2 item) |
| Samples | 8,000 per experiment (≈ 3,900 per class after the 2 % warm-up discard); key pool 32; messages 64 B |
| Raw data | `session-2026-08-18-local/report.json` + `raw-*.csv` (class, nanoseconds; every measurement incl. warm-up) |

## 2. Results

| experiment | class 0 | class 1 | n0 / n1 | mean0 (ms) | mean1 (ms) | max \|t\| (crop) | verdict |
|---|---|---|---|---|---|---|---|
| control-flat | identical work | identical work | 3 906 / 3 934 | — | — | **1.32** | PASS ✔ (environment quiet enough) |
| control-leaky | 40 k iterations | 60 k iterations | 3 903 / 3 937 | — | — | **1197.36** | FAIL ✔ (harness has power) |
| **sign-key** | fixed key K0, fixed msg M0 | pool key, fixed msg M0 | 3 892 / 3 948 | 8.1246 | 8.1348 | **11.04** (@ 0.5) | **FAIL** |
| **sign-msg** | fixed key K0, fixed msg M0 | fixed key K0, random 64-B msg | 3 873 / 3 967 | 7.9066 | 7.9016 | **9.35** (@ 0.5) | **FAIL** |
| verify-ctrl *(informational)* | fixed (S0, pk0) | pool (Sj, pkj) | 3 893 / 3 947 | 0.0515 | 0.0525 | 90.06 (@ 0.8) | FAIL — public data; expected (variable-length signature decoding) |
| keygen *(informational)* | fixed seed | fresh seed | 3 907 / 3 933 | 25.29 | 37.11 | 56.23 (@ 0.97) | FAIL — expected: rejection-sampled key generation; the fixed seed always takes the same number of restarts |

The ten *t* values per experiment are in `report.json`. Crops are one-sided: samples above the *pooled* p-th percentile are discarded (METHODOLOGY §1). For `sign-key` the raw (uncropped) *t* is **−0.73** — the overall means are indistinguishable (class 0's overall mean is in fact slightly *lower*, because class 1 carries a heavier upper tail: max 33 ms vs 15 ms, sd 0.69 vs 0.54 ms) — and the separation appears only in the fastest-half crop (**+11.04** at the 50th percentile, +6.73 at 60 %, ≈ 0 above 70 %): within the retained core, the fixed (K0, M0) input is a few microseconds *slower* than the pool keys. For `sign-msg` the separation is across the body (*t* ≈ 9 from the 50th to the 80th percentile, decaying to 2 at 99 %); the fixed message is ≈ 4 µs slower than random messages at every quantile up to p95, while the raw *t* is 0.83. The flat control's ten *t* values are all below 1.4 — but that is one draw of the null, not a calibration of the max-over-ten statistic (see §3a).

Magnitudes of the cropped effect: **≈ 4–15 µs on ≈ 8 ms signatures (0.05–0.2 %)**. Bimodality: no *visible* second mode (p95 within ≈ 4 % of the median in both classes); a low-mass second mode is not excluded by that check.

## 3a. Team review (2026-08-18, five seats, unmerged) and the revised reading

The report was put to the R&D team's five API seats. All five converged on the same statistical objection, so it is adopted here rather than argued with:

- **Multiplicity:** `max |t|` over ten *correlated* tests (raw + nine crops) judged against dudect's *single-test* 4.5 cutoff inflates the false-positive rate; one passing flat control is a single draw of the null, not a calibration of the max statistic (GPT-5.6, Grok, DeepSeek, Kimi).
- **Crop bias:** a raw *t* near zero that becomes 9–11 only under cropping, with class 1 having the larger variance, is the signature of *variance × percentile-crop* asymmetry — one-sided cropping at a pooled percentile removes more of the higher-variance class's samples and can shift the retained means apart even when the true means are equal — plus a fixed **point mass** (deterministic K0‖M0 fingerprint) being compared against a **mixture** (32 keys / random messages). Neither is evidence of a location leak (Grok, DeepSeek, Kimi, GPT-5.6).
- **Confounds not controlled:** no core pinning, turbo/DVFS, Windows QPC ~100 ns ticks (Kimi corrected the timer claim), a 32-key pool's cache residency vs. one hot key (Grok, DeepSeek).
- **Interpretation is a hypothesis:** the BerExp / sampler / retry-loop attribution is source-plausible but not causally isolated (Hermes, GPT-5.6) — retained below as *hypothesis*.
- **Overclaim vote:** three seats said yes (escalating a crop-only difference to a "blocks any CT claim" statement), two said no (the labels were honest). The revision above resolves it in the critics' favour: the FAIL word stays because the v1 rule says so; the *reading* is downgraded to shape/scale difference; exploitability INCONCLUSIVE.

**Revised reading, adopted:** this session shows that the pinned signer's timing distributions for a fixed input and for varied inputs **differ in shape/scale**, not that their means differ, and not that the difference is secret-dependent. That is consistent with det1024's deterministic per-input rejection pattern *and* with benign confounds. **Nothing here should be cited as "Falcon leaks the key through timing."**

## 3. What this shows — and what it does not

**Established by this run (by the pre-registered rule):** the pre-registered statistic crossed its threshold for both gated experiments with the controls behaving. **Established in substance (after §3a):** the two classes' timing distributions differ in shape/scale on this build and machine; the means do not measurably differ; the v1 statistic is not fit to call that a leak.

**Mechanism — HYPOTHESIS (source reading of the vendored `sign.c`; not causally isolated by this run):**
- `BerExp` (≈ line 1340): a lazy comparison `do { … } while (!w && i > 0)` whose iteration count depends on PRNG output against a threshold derived from the sampling target.
- `sampler` (≈ line 1385): the per-coefficient rejection loop `for (;;) { z0 = gaussian0_sampler(); … accept/reject }` — data-dependent iteration count.
- `do_sign_*` (≈ lines 1450 / 1495): the whole-signature retry `for (;;)` when the candidate is not short — rare (no bimodality is visible in the raw data: p95 within ≈ 4 % of the median in both classes), so not the driver here.

The reference design treats these loops as acceptable ("isochronous" in *distribution* over the PRNG). **det1024 makes the PRNG a deterministic function of `sk ‖ msg`**, so a fixed (key, message) always follows the same rejection pattern — its timing is a fixed fingerprint of that input — while random inputs vary. A fixed-vs-random test is sensitive to exactly that, and that is what these numbers look like: the same test on `sign-msg` (public message varied, key fixed) separates just as `sign-key` does. Whether the fingerprint leaks *usable* information about the secret key is a different question and **is not established either way by this run.**

**Not established:** exploitability; behaviour on Linux/macOS or on a native-FP build (out of scope); anything about the AVM's `falcon_verify` opcode (verification is public data); anything about NERION or polaris-shield.

## 4. Consequences (per the plan)

- Phase E (`keygen_sign_seal` as the documented default with an in-process self-KAT) stays **blocked** — not because a leak is shown, but because no PASS under a sound statistic exists yet. The flagship SDK's existing statement "no constant-time / side-channel guarantees are claimed" stands, unearned either way.
- No patch to the vendored primitive. The zero-patch ledger stays empty. If a constant-time signer is required, the answer is a different *approved artifact* or scoping Falcon signing out of the product claim — never a hand edit here.
- The audit pack (Phase P) carries this report as-is; INCONCLUSIVE/FAIL are never rewritten as PASS.

## 4a. Second session — METHODOLOGY **v2** (`session-2026-08-18-local-v2`, same machine)

Run after `METHODOLOGY-v2.md` was committed (`ff655d9`). Same machine, release build, 8 000 measurements per experiment, key pools of 32, **24 flat-control null sessions**. Raw CSVs and `report.json` (schema 2) committed beside it.

### SESSION VERDICT: **SHAPE** by the v2 rule as written — **read the revised reading below: the crop-derived SHAPE labels are not interpretable in this session, and the defensible statement is narrower**

After a second team review (5 seats, 3 "reading over-claims" / 2 "honest"), the reading was revised: **the v2 empirical null (a ~50 µs synthetic loop) is unfit for an 8 ms heavy-tailed operation — every crop *p* sits at the 1/25 floor, including the pool-vs-pool control — so by the methodology's own logic a misbehaving null makes the crop diagnostic INCONCLUSIVE, and no SHAPE label in this session may be read as "the distributions differ in shape."** What survives is the primary statistic only: **no gated experiment reaches the pre-registered FAIL line (raw |t| < 4.5 for all four); no location difference is demonstrated.** The three fixed-key mean differences below are reported as *descriptive, hypothesis-generating* numbers — their CIs were pre-registered as *reported*, not as decision criteria.

| | raw *t* | *p*(raw) | Δmean (µs) [95 % CI] | crop stat | crop *p*ₑₘₚ | verdict |
|---|---|---|---|---|---|---|
| null (24 flat sessions) | max \|t\| < 4.5 ✔ | | | **max 1.89**, min 0.47 | — | null OK |
| control-flat | 1.49 | | | 1.33 | | PASS ✔ |
| control-leaky | −75.2 | | | | | FAIL ✔ |
| **sign-kk-0** (K_a vs K_b) | **−3.22** | 1.3e-3 | **+16.6 [+6.5, +26.7]** | **26.2** | 0.040 | **SHAPE** |
| **sign-kk-1** (K_c vs K_d) | **−2.35** | 1.9e-2 | **+11.8 [+2.0, +21.7]** | **26.3** | 0.040 | **SHAPE** |
| **sign-kk-2** (K_e vs K_f) | **−3.00** | 2.7e-3 | **+15.0 [+5.2, +24.8]** | **10.3** | 0.040 | **SHAPE** |
| **sign-rr** (pool A vs pool B) | +1.51 | 0.13 | −10.0 [−23.1, +3.0] | **3.06** | 0.040 | SHAPE |
| sign-key *(screening)* | +1.14 | 0.25 | −7.2 [−19.5, +5.2] | 9.1 | 0.040 | SHAPE |
| sign-msg *(screening)* | +0.81 | 0.42 | −4.3 [−14.7, +6.1] | 15.1 | 0.040 | SHAPE |
| verify-ctrl *(informational)* | −23.4 | ≈0 | +1.5 [+1.3, +1.6] | 113 | 0.040 | FAIL (public data; expected) |
| keygen *(informational)* | −50.2 | ≈0 | +11 739 | 56.5 | 0.040 | FAIL (rejection-sampled; expected) |

(Δmean = class 1 − class 0; signing ≈ 7.85–7.90 ms; sd ≈ 0.21–0.31 ms; df ≈ 7 600–7 800.)

**Reading (revised after the second team review), stated exactly:**

1. **Primary statistic: no gated experiment reaches the pre-registered FAIL line** (raw |t| ≥ 4.5). No location difference in signing time is demonstrated between any two classes.
2. **Crop diagnostic: INCONCLUSIVE in this session.** The v2 null was built from a ~50 µs synthetic loop; every experiment's crop *p* — including the pool-vs-pool control's — sits at the 1/25 floor, which means the null does not model an 8 ms heavy-tailed operation. A null that misbehaves invalidates the diagnostic that depends on it. The SHAPE labels the harness printed are therefore **not** to be read as "the distributions differ in shape"; no ratios against that null are meaningful (an earlier draft of this section quoted "3–9×" and called `sign-rr` a "noise floor" — both withdrawn: one `sign-rr` draw is a draw, not a floor).
3. **Descriptive numbers, hypothesis-generating only:** the three fixed-key pairs showed mean differences of +16.6, +11.8 and +15.0 µs (0.15–0.2 % of ≈ 7.9 ms) with 95 % CIs excluding zero (raw-*t* *p* = 0.001–0.02, no multiplicity correction; the CIs were pre-registered as *reported*, not as a decision criterion). Sub-threshold *t* under heavy tails and uncontrolled drift is exactly where the 4.5 line exists to withhold claims. **Cause undetermined:** each pair used one fixed message, so a key effect is confounded with key×message; classes were randomised per measurement but not core-pinned; the same-sign pattern across three pairs is noted and not read. **Hypothesis** (not supported by timing alone): det1024's deterministic per-input rejection pattern gives each (key, message) a fixed timing; equally consistent with scheduler/frequency effects and FPEMU code paths.

   **Update 2026-08-18 — the same-sign pattern now has a better explanation than the keys.** Pooled over v2, v3 and v3b it stands at **8 of 9 independent key pairs putting class 1 slower, mean +13.9 µs** (binomial *p* ≈ 0.04 against a coin flip), while `sign-rr` shows the *opposite* sign in all three sessions. A sign pattern that follows the measurement **arm** across independent keys is not a key property. Candidate mechanism, in the harness rather than in Falcon: a `sign-kk` pair is a single tuple, so class 0's secret key sits at tuple offset 0 and class 1's at `size_of::<Keypair>()` = 4 098 B — a different address and cache-line alignment on every measurement — whereas `sign-rr`'s two arms are separate allocations. The `sign-aa` control pre-registered in `METHODOLOGY-v3.1-POWER.md` §2a (same keypair in both arms, identical layout) tests exactly this. **Until it reports, these deltas may not be attributed to the keys at all** — a stronger statement than the "cause undetermined" above, and the fourth time this document has had to weaken a reading.
4. Environment caveats unchanged: Windows QPC ≈ 100 ns, no core pinning, turbo not controlled, FPEMU-specific, one machine.

**v3 requirements (before any crop-based verdict is issued again):** build the empirical null from **repeated pool-vs-pool signing sessions** of the real operation (≥ 20), interleave classes and repeat each key across several messages to separate key from key×message, pin a core where the platform allows, and pre-register any cross-pair combination rule and multiplicity correction. Until then the crop diagnostic is reported but not used for verdicts.

**Consequences:** unchanged from §4 — Phase E stays blocked (no PASS exists); no patch to the vendored primitive; nothing here is a key-leak claim. The finding to carry forward, precisely: *at the pre-registered line, no location difference in det1024 signing time was found between fixed keys, between random key pools, or between fixed and random inputs on this machine; small sub-threshold differences were observed for three specific (key, message) pairs, cause undetermined; the crop diagnostic needs a real-operation null before it can say anything.*

## 4b. Third session — METHODOLOGY **v3** (`session-2026-08-18-local-v3` INCONCLUSIVE, then `…-v3b` on a quiet machine)

`METHODOLOGY-v3.md` was committed (`3061ae1`) before either run. **v3 changes:** the empirical null is **20 pool-vs-pool signing sessions of the real operation** (fresh 32-key pools each); `sign-kk` rotates **four fixed messages identically for both classes** (key-only, message-balanced); the kk **combination rule** is pre-registered (FAIL if any pair FAILs on the raw statistic; SHAPE only if ≥ 2 of 3 pairs SHAPE; else PASS); descriptive statistics are barred from the words "distinguishable / fingerprint / leak".

**First v3 run (`-v3`, 4 200 measurements): INCONCLUSIVE.** With a random per-measurement class bit, 4 200 sits ≈ 2 sd above the 2 000-per-class floor and several sessions split below it (e.g. `sign-kk-0` 1934/2182); the harness rejected the null and refused every verdict — correct behaviour, boring cause. It also overlapped cargo builds on the same machine. Kept as evidence of the refusal path; the sample default became 4 800 and the harness now refuses `< 4600` up front, naming the reason.

**Second v3 run (`-v3b`, 4 800 measurements, no other load): SESSION VERDICT — PASS (by the v3 rule).**

| | n0 / n1 | raw *t* | *p*(raw) | Δmean (µs) [95 % CI] | crop stat | crop *p*ₑₘₚ | verdict |
|---|---|---|---|---|---|---|---|
| null (20 pool-vs-pool sessions, real operation) | ≥ 2 000 each ✔ | all \|t\| < 4.5 ✔ | | | **min 0.67 · median 1.84 · max 5.75** | — | null OK |
| control-flat | | −0.21 | | | | | PASS ✔ |
| control-leaky | | −21.9 | | | | | FAIL ✔ |
| **sign-kk-0** (K_a vs K_b, 4 msgs) | 2314 / 2390 | −0.65 | 0.52 | +13.8 [−28, +56] | 4.93 | 0.095 | **PASS** |
| **sign-kk-1** (K_c vs K_d) | 2369 / 2335 | +0.08 | 0.93 | −1.0 [−25, +23] | 2.57 | 0.286 | **PASS** |
| **sign-kk-2** (K_e vs K_f) | 2343 / 2361 | −1.04 | 0.30 | +31.4 [−28, +91] | 2.78 | 0.286 | **PASS** |
| **sign-kk combined** (≥ 2 of 3 rule) | | | | | | | **PASS** |
| **sign-rr** (pool A vs pool B) | 2288 / 2416 | +0.04 | 0.97 | −0.9 [−48, +46] | 3.62 | 0.143 | **PASS** |
| sign-key *(screening: fixed vs random)* | 2308 / 2396 | +3.01 | 0.003 | −46.4 [−77, −16] | 11.67 | 0.048 | SHAPE (informational) |
| sign-msg *(screening)* | 2381 / 2323 | −0.28 | 0.78 | +5.4 [−33, +44] | 12.94 | 0.048 | SHAPE (informational) |
| verify-ctrl / keygen *(informational)* | | −8.1 / −36.9 | | +1.3 / +11 118 | 55 / 40 | | FAIL (expected: public-data decoding / rejection-sampled keygen) |

**Reading, stated exactly:**

1. **At the pre-registered lines, key-dependence of signing time is not detected — at this power:** all three message-balanced fixed-key pairs and the pool-vs-pool control PASS on the raw statistic (|t| ≤ 1.04, every CI spanning zero) **and** on the crop diagnostic against a null of the same kind (crop *p*ₑₘₚ 0.10–0.29; with N = 20 the empirical *p* has resolution 1/21). The v3 rule's word is **PASS**, and PASS means exactly: *the pre-registered detection conditions were not met at this power on this machine and build; not a proof of absence.* **Corrected 2026-08-18 (`METHODOLOGY-v3.1-POWER.md` §1): the resolution originally stated here — "insensitive to effects of order ±15 µs … bounds them within the reported CIs (±25–60 µs)" — was wrong, in the flattering direction.** A 95 % CI half-width is not the detection floor when the rule is `|t| ≥ 4.5`: the effect detected with probability 0.90 is `(4.5 + z₀.₉₀)·SE` ≈ **2.95×** that half-width. Recomputed from this session's own `report.json`, its **MDE₉₀ was 124 / 72 / 175 µs** across the three `sign-kk` pairs and **139 µs** for `sign-rr`. The honest sentence is therefore: *no per-key mean difference of about 72–175 µs (pair-dependent — the pairs' sds differ by 2.4×) was detected.* Smaller effects were never within reach, though they keep a smaller, non-zero detection probability. Sign convention: raw *t* is (mean₀ − mean₁)/se while Δmean is mean₁ − mean₀, so their signs are opposite by construction.
2. **The real-operation null is wide (crop-stat max 5.75, median 1.84)** — confirming that v2's flat-loop null (max 1.89) was unrepresentative; v2's crop-SHAPE labels are therefore **non-evidentiary / uninterpretable under the corrected null** (compatible with being artefacts; not proven to be), as §4a already concluded.
3. **Power caveat, stated plainly:** the four-message rotation widens each class into a mixture (sd 0.41–1.06 ms here vs 0.21–0.23 ms in v2), so 95 % CIs on Δmean are ≈ ±25–60 µs versus ±10 µs in v2. **The ~12–17 µs fixed-key deltas v2 recorded are therefore neither confirmed nor excluded by this session.** Resolving effects of that size needs far more data. **The estimate first given here — "≈ 40–80 k measurements per experiment" for ±15 µs — was low by about 4×, corrected in `METHODOLOGY-v3.1-POWER.md` §1:** it solved for a 15 µs *standard error*, but the decision line is 4.5 σ, so 90 % power at 15 µs needs `SE ≤ 15/5.78 ≈ 2.6 µs` — about 158 k per class, i.e. **≈ 320 k measurements per experiment** (≈ 22 h on this machine). The pre-registered next session runs at **82 000** (MDE₉₀ ≈ 30–42 µs, CI ≈ ±10–14 µs), same rules, target power stated in writing beforehand.
4. **`sign-key` (fixed vs random, one message) is a screening result, not a verdict** — the SHAPE word is pre-registered for gated designs only; the harness prints it, the report does not use it. Its numbers (crop 11.7; raw *t* +3.0, Δ −46 µs, CI [−77, −16]) are recorded. **Hypothesis, not established:** a fixed (key, message) is a point mass with a narrower timing distribution than a mixture of 32 keys, which would produce exactly this asymmetry — the reason the design was demoted. Testing it (multiple fixed keys vs variance-matched mixtures) is a v4 item; it is not read as key-dependence and not read away either.
5. Environment: same i9 desktop, Windows QPC ≈ 100 ns, no core pinning, turbo uncontrolled, FPEMU-specific; **no other load during `-v3b`** (unlike `-v3`).

**Consequences:** Phase E stays **blocked** — one PASS on one machine at limited power is not "a sound PASS exists"; METHODOLOGY says a PASS is not a proof, and the v2 deltas are unresolved. What this session adds: after three pre-registered iterations, the pinned det1024 signer's timing shows **no detectable location dependence on the key at the tested power** — where that power is MDE₉₀ ≈ 72–175 µs, not the ±15 µs this paragraph first claimed (corrected 2026-08-18); the earlier FAIL (v1) and SHAPE (v2) readings are non-evidentiary under the corrected statistic and null; the open question is sized (≈ 320 k measurements per experiment to resolve 15 µs; the pre-registered next session runs at 82 k for ≈ 30–42 µs). No patch to the vendored primitive; nothing here is a security claim in either direction.

## 4c. Fifth session — **v3.1 high power** (`session-2026-08-18-local-v31-hp82k`)

### SESSION VERDICT: **PASS**, all five pre-registered gates satisfied, at **MDE₉₀ ≈ 14.5 µs**

**Method:** `METHODOLOGY-v3.md` + `METHODOLOGY-v3.1-POWER.md`, both committed **before** the run;
**no decision rule was changed** — only the sample size moved, and upward. 82 000 measurements
per experiment (40 180 per class), 20 real-operation null sessions, 2026-08-18 16:39–22:10
(5 h 31 m, inside the 5.5–5.9 h predicted band), same laptop as v3b, no other load.

**Gates, in the order §8 of the addendum fixed in advance:**

| # | gate | result |
|---|---|---|
| 1 | `schema_version == 4` | ✔ the v3.1 binary ran |
| 2 | `null_ok`, 20/20 `null_detail`, none with \|raw *t*\| ≥ 4.5 | ✔ **max 3.94**; every split within ±170 of 40 180 |
| 3 | `controls_ok`: flat PASS, leaky FAIL | ✔ *t* = −0.15 / **−296.34** |
| 4 | `sign-aa` PASS | ✔ |
| 5 | `sign-aa` Δ and CI, read regardless of verdict | **+1.40 µs [−3.53, +6.33]** |

| experiment | n0 / n1 | sd | raw *t* | Δmean (µs) [95 % CI] | crop *p*ₑₘₚ | **MDE₉₀** | verdict |
|---|---|---|---|---|---|---|---|
| **`sign-aa`** *(A/A control)* | 40152 / 40208 | 357 µs | −0.56 | **+1.40 [−3.5, +6.3]** | 0.952 | 14.5 µs | **PASS** |
| **`sign-kk-0`** | 40114 / 40246 | 356 µs | −1.62 | +4.05 [−0.9, +9.0] | 0.571 | 14.5 µs | **PASS** |
| **`sign-kk-1`** | 40186 / 40174 | 356 µs | +2.88 | −7.22 [−12.1, −2.3] | 0.476 | 14.5 µs | **PASS** |
| **`sign-kk-2`** | 40196 / 40164 | 353 µs | +2.79 | −6.94 [−11.8, −2.1] | 0.476 | 14.4 µs | **PASS** |
| **`sign-kk` combined** (≥ 2 of 3) | | | | | | | **PASS** |
| **`sign-rr`** | 40201 / 40159 | 350 µs | +0.73 | −1.80 [−6.6, +3.0] | 0.952 | 14.3 µs | **PASS** |
| `sign-key` *(screening)* | 40254 / 40106 | 354 µs | +2.36 | −5.91 [−10.8, −1.0] | 0.476 | 14.5 µs | PASS |
| `sign-msg` *(screening)* | 40318 / 40042 | 356 µs | +1.83 | −4.60 [−9.5, +0.3] | 0.476 | 14.5 µs | PASS |
| `verify-ctrl` *(informational)* | | 8 µs | −25.54 | +1.45 [+1.3, +1.6] | 0.048 | 0.33 µs | FAIL — **pre-stated** |
| `keygen` *(informational)* | | 10 015 µs | −161.47 | +11 417 [+11 278, +11 556] | 0.048 | 409 µs | FAIL — **pre-stated** |

### 1. The arm-layout hypothesis is excluded on the machine where the pattern was seen

`sign-aa` — the *same keypair* in both arms, in a tuple laid out exactly like a `sign-kk` pair —
measures the arm offset at **+1.40 µs with a 95 % CI of [−3.53, +6.33] µs**. **That CI excludes
+13.9 µs.** The control added the day before, because 8 of 9 pairs across v2/v3/v3b had put class 1
slower, has answered its question in one session: **there is no systematic arm/layout offset of
that size on this machine.**

The pattern itself also failed to reproduce. This session's three pairs are **+4.05, −7.22,
−6.94 µs** — one positive, two negative — taking the pooled count to **9 of 12** (two-sided
binomial *p* ≈ 0.15, no longer significant). Two independent lines of evidence, one experimental
and one observational, point the same way.

### 2. What the PASS licenses, exactly

> Across three fixed-key pairs and a pool-vs-pool control, **no difference in mean signing time
> was detected** at the pre-registered lines (every gated raw \|t\| ≤ 2.9 against the 4.5 rule;
> every gated crop *p*ₑₘₚ ≥ 0.476 against a real-operation null whose own crop statistic reached
> 10.24). At this size the session would have detected a true difference of **≈ 14.5 µs** with
> 90 % probability. Smaller differences remain neither confirmed nor excluded, though they keep a
> smaller, non-zero detection probability. Machine-, build- and input-distribution-specific.

**It does not license**, at any sample size: that the signer *is* constant-time; that the secret
key does not leak through timing; that Falcon-1024 as a design is constant-time; or any FIPS-206
property. This session measures **wall-clock only** — power, EM, cache and microarchitectural
channels are entirely outside it.

The session **over-delivered on resolution**: MDE₉₀ came out at 14.3–14.5 µs against a planned
30–42 µs, because the observed sd was 350–357 µs against the 425–1 039 µs planning band. The
laptop was quieter than during v3b. The consequence is that this session **does** resolve the
12–17 µs range that every earlier session was blind to.

### 3. Predictions scorecard — including the one that was wrong

`METHODOLOGY-v3.1-POWER.md` §7 was written while the session was still in its null phase, before
any experiment ran:

| prediction | outcome |
|---|---|
| Null gate holds (≈ 0.1–2 % risk on this machine) | **Correct** — max \|t\| 3.94, and that it sits above a standard-normal max-of-20 is itself the predicted `sd(t) ≈ 1.1–1.4` |
| `verify-ctrl` crosses 4.5 (E\|t\| ≈ 33) | **Correct** — *t* = −25.5 |
| `keygen` crosses 4.5 (E\|t\| ≈ 151) | **Correct** — *t* = −161 |
| `sign-key` near-certain FAIL (E\|t\| ≈ 12.5) | **WRONG** — *t* = 2.36, PASS |
| P(≥ 1 `sign-kk` pair FAILs) ≈ 44 % | **No FAIL** |

The two failures share one cause: both assumed v3b's *point estimates* (`sign-key` Δ = −46.4 µs;
`sign-kk-2` Δ = +31.4 µs) were true. They were not — the observed values are −5.9 µs and −6.9 µs.
The caveat was stated at the time ("point estimates whose v3b CIs all span zero"), and it was the
operative fact.

**This is the session's methodological result, and it is worth more than the verdict.** The
"+12–17 µs fixed-key deltas" that three rounds of council review forced this repository to
withdraw as claims have now **failed to reproduce at 17× the samples, including their sign**.
Sub-threshold *t* with a CI excluding zero is hereby a documented non-replicating shape in this
system, not a weak signal. The reviewers who insisted on withdrawal were right, and the
pre-registered 4.5 line did the job it exists to do.

### 4. Recorded before anyone reads them as a finding

Two gated pairs again show sub-threshold *t* (2.88, 2.79) with CIs excluding zero — now
**negative** (−7.22, −6.94 µs), the opposite sign to the earlier pattern. `sign-key` shows the
same shape (−5.91 [−10.8, −1.0]). By the pre-registered rules these are **descriptive only and are
not read**. This is the fourth consecutive session to produce this shape and the first three did
not replicate; the standing expectation is therefore that these will not either. `sign-key`'s
SHAPE label from v3b did not recur (crop *p*ₑₘₚ 0.476), which is consistent with the v2/v3b SHAPE
readings having been null artefacts, as §4a and §4b already concluded.

### 5. Consequences

- **Phase E stays blocked** pending the council reading. One PASS, however well-powered, is one
  machine and one build; the standing rule is that a PASS is not a proof.
- **The next session moves machines, not sample counts.** The ubuntu CI runner's sd is ≈ 32 µs
  against this laptop's 350–733 µs, so a 20-minute run there resolves ≈ 5 µs
  (`OBSERVATION_ci-ubuntu-2026-08-18.md`). That is blocked behind the null-gate defect: the gate
  as written voids sessions on quiet machines for arithmetic reasons (`V4_BACKLOG.md` §C4).
- The `sign-kk` arm-randomisation item is **de-prioritised** — `sign-aa` says there is nothing of
  that size to fix — but the A/A control stays in every future session.

## 5. METHODOLOGY v2 — what changed before the second session (implemented; see `METHODOLOGY-v2.md`)

Adopted from the team's review; none of this is retro-applied to this session.

1. **One primary statistic, pre-registered:** the raw Welch *t* (or a permutation test on the raw samples). Crops become **secondary diagnostics**, and `max |t|` over crops is judged against an **empirical null** built from ≥ 20 repeated flat-control sessions on the same machine (or a Bonferroni-corrected cutoff), not against 4.5. A crop-only spike with a null raw *t* is reported as INCONCLUSIVE, never FAIL.
2. **Designs that isolate key-dependence:** **fixed-vs-fixed** (`sign-kk`: K_a vs K_b at M0 — the only design that measures a per-key fingerprint directly) and **random-vs-random** (`sign-rr`: two independent pools — a control for mixture-vs-point-mass asymmetry). Fixed-vs-random stays only as a screening test.
3. **Report Welch–Satterthwaite df, p-values, effect sizes with confidence intervals**, and per-crop retained counts (already in `report.json`) — Hermes.
4. **Environment controls:** core pinning where the OS allows, turbo/DVFS noted or disabled, timer resolution stated per OS (Windows QPC ≈ 100 ns; Linux `clock_gettime` ≈ ns), Linux replication (the CI job) and ideally a second quiet machine; native-FP builds remain out of scope and the verdict is FPEMU-specific.
5. **Modality:** a histogram or a formal test in the report rather than a p95-vs-median glance.
6. **Source-level constant-time reading** of `sign.c` / `fpr.c` as a human deliverable, each data-dependent loop listed with its inputs traced to secret vs. public data — supporting evidence, not dispositive.
7. Longer runs (≥ 20 k per class) once the statistic is fixed.

*This report is evidence about a pinned artifact on a named machine. It is not a security proof and it is not a vulnerability disclosure; it records what the pre-registered test found.*
