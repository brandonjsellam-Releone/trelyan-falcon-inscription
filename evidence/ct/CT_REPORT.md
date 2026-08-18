# Falcon-1024 det1024 constant-time evidence — session report

**Session:** `session-2026-08-18-local` · **Method:** `METHODOLOGY.md` (2026-08-18, pre-registered before this run; commit `65d2c42`) · **Harness:** `rust/crates/falcon-ct` (release build) · **Target:** pinned `algorand/falcon@ce15e75b`, vendored at `third_party/falcon-det1024/src`, compiled by `trelyan-pq-ffi` with `-O3 -DFALCON_UNALIGNED=0 -fno-strict-aliasing`, `config.h` `FALCON_FPEMU=1`.

## SESSION VERDICT: **FAIL** (by the pre-registered rule)

Both gated experiments distinguish their two classes at `max |t| ≥ 4.5` with both controls behaving. **This is an observation, not a gate** (METHODOLOGY §0): it blocks Phase E (the self-KAT signer as a default) and any constant-time claim for the pinned signer, and it does **not** result in any change to the vendored primitive.

## 1. Environment (recorded)

| | |
|---|---|
| Machine | desktop, Intel Core i9-9900K, 16 hardware threads, Windows 11 (`windows` / `x86_64`), no other load |
| Toolchain | rustc 1.97.1 (release profile), MinGW-w64 GCC 16.1.0 for the C |
| Timer | `std::time::Instant` (monotonic) |
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

The ten *t* values per experiment are in `report.json`. For `sign-key` the raw (uncropped) *t* is **−0.73** — the overall means are indistinguishable — and the separation appears in the fastest-half crop (**+11.04** at the 50th percentile, +6.73 at 60 %, ≈ 0 above 70 %): in the low-noise core of the distribution, the fixed (K0, M0) input is a few microseconds *slower* than the pool keys. For `sign-msg` the separation is across the body (*t* ≈ 9 from the 50th to the 80th percentile, decaying to 2 at 99 %); the fixed message is ≈ 4 µs slower than random messages at every quantile. The flat control's ten *t* values are all below 1.4, so the cropping does not manufacture separation on identical distributions in this environment.

Magnitudes: **≈ 4–15 µs on ≈ 8 ms signatures (0.05–0.2 %)**, detectable at ≈ 3.9 k measurements per class on a quiet desktop.

## 3. What this shows — and what it does not

**Established by this run (by the pre-registered rule):** the pinned det1024 signer's running time depends on the (key, message) input at a level a fixed-vs-random Welch test detects. Signing is not constant-time in the strict sense on this build and machine.

**Mechanism (source reading of the vendored `sign.c`, labelled interpretation, not measured attribution):**
- `BerExp` (≈ line 1340): a lazy comparison `do { … } while (!w && i > 0)` whose iteration count depends on PRNG output against a threshold derived from the sampling target.
- `sampler` (≈ line 1385): the per-coefficient rejection loop `for (;;) { z0 = gaussian0_sampler(); … accept/reject }` — data-dependent iteration count.
- `do_sign_*` (≈ lines 1450 / 1495): the whole-signature retry `for (;;)` when the candidate is not short — rare (no bimodality is visible in the raw data: p95 within ≈ 4 % of the median in both classes), so not the driver here.

The reference design treats these loops as acceptable ("isochronous" in *distribution* over the PRNG). **det1024 makes the PRNG a deterministic function of `sk ‖ msg`**, so a fixed (key, message) always follows the same rejection pattern — its timing is a fixed fingerprint of that input — while random inputs vary. A fixed-vs-random test is sensitive to exactly that, and that is what these numbers look like: the same test on `sign-msg` (public message varied, key fixed) separates just as `sign-key` does. Whether the fingerprint leaks *usable* information about the secret key is a different question and **is not established either way by this run.**

**Not established:** exploitability; behaviour on Linux/macOS or on a native-FP build (out of scope); anything about the AVM's `falcon_verify` opcode (verification is public data); anything about NERION or polaris-shield.

## 4. Consequences (per the plan)

- Phase E (`keygen_sign_seal` as the documented default with an in-process self-KAT) stays **blocked**; the flagship SDK's existing statement "no constant-time / side-channel guarantees are claimed" stands and is now backed by evidence rather than caution.
- No patch to the vendored primitive. The zero-patch ledger stays empty. If a constant-time signer is required, the answer is a different *approved artifact* or scoping Falcon signing out of the product claim — never a hand edit here.
- The audit pack (Phase P) carries this report as-is; INCONCLUSIVE/FAIL are never rewritten as PASS.

## 5. Proposed follow-ups (would need a v2 of METHODOLOGY.md, dated, before running)

1. **random-vs-random** (`sign-rr`): both classes draw keys from independent pools. If this PASSES while `sign-key` FAILS, the effect is the fixed-input fingerprint of determinism rather than a systematic bias between key populations.
2. **fixed-vs-fixed** (`sign-kk`): two specific keys K_a vs K_b, same message, many runs. Measures the *size* of the per-key fingerprint directly.
3. **Cross-platform replication:** the CI job runs the same session on `ubuntu-latest` (expected noisier; INCONCLUSIVE is an acceptable outcome there); a second quiet machine would strengthen the finding.
4. **Source-level constant-time reading** of `sign.c` / `fpr.c` (FPEMU) as a human deliverable, with each data-dependent loop listed and its inputs traced to secret vs. public data.
5. Longer runs (≥ 20 k per class) to tighten the estimate of the effect size.

*This report is evidence about a pinned artifact on a named machine. It is not a security proof and it is not a vulnerability disclosure; it records what the pre-registered test found.*
