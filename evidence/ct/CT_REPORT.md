# Falcon-1024 det1024 constant-time evidence — session report

**Session:** `session-2026-08-18-local` · **Method:** `METHODOLOGY.md` (2026-08-18, pre-registered before this run; commit `65d2c42`) · **Harness:** `rust/crates/falcon-ct` (release build) · **Target:** pinned `algorand/falcon@ce15e75b`, vendored at `third_party/falcon-det1024/src`, compiled by `trelyan-pq-ffi` with `-O3 -DFALCON_UNALIGNED=0 -fno-strict-aliasing`, `config.h` `FALCON_FPEMU=1`.

## SESSION VERDICT: **FAIL** (by the pre-registered rule) — **read §3a before drawing any conclusion**

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

## 5. METHODOLOGY v2 — what changes before the next Falcon verdict (to be written, dated, before running)

Adopted from the team's review; none of this is retro-applied to this session.

1. **One primary statistic, pre-registered:** the raw Welch *t* (or a permutation test on the raw samples). Crops become **secondary diagnostics**, and `max |t|` over crops is judged against an **empirical null** built from ≥ 20 repeated flat-control sessions on the same machine (or a Bonferroni-corrected cutoff), not against 4.5. A crop-only spike with a null raw *t* is reported as INCONCLUSIVE, never FAIL.
2. **Designs that isolate key-dependence:** **fixed-vs-fixed** (`sign-kk`: K_a vs K_b at M0 — the only design that measures a per-key fingerprint directly) and **random-vs-random** (`sign-rr`: two independent pools — a control for mixture-vs-point-mass asymmetry). Fixed-vs-random stays only as a screening test.
3. **Report Welch–Satterthwaite df, p-values, effect sizes with confidence intervals**, and per-crop retained counts (already in `report.json`) — Hermes.
4. **Environment controls:** core pinning where the OS allows, turbo/DVFS noted or disabled, timer resolution stated per OS (Windows QPC ≈ 100 ns; Linux `clock_gettime` ≈ ns), Linux replication (the CI job) and ideally a second quiet machine; native-FP builds remain out of scope and the verdict is FPEMU-specific.
5. **Modality:** a histogram or a formal test in the report rather than a p95-vs-median glance.
6. **Source-level constant-time reading** of `sign.c` / `fpr.c` as a human deliverable, each data-dependent loop listed with its inputs traced to secret vs. public data — supporting evidence, not dispositive.
7. Longer runs (≥ 20 k per class) once the statistic is fixed.

*This report is evidence about a pinned artifact on a named machine. It is not a security proof and it is not a vulnerability disclosure; it records what the pre-registered test found.*
