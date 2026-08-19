# Observation — the ubuntu CI session of 2026-08-18 (run 32184522617, commit `eb2ea04`)

**Session verdict: INCONCLUSIVE. By the rules in `METHODOLOGY-v3.md` §1 no Falcon verdict may be
read from it, and none is read here.** What *is* readable is what the session says about the
**harness and the environment**, and that turns out to be more useful than a verdict would have
been. This file records it because the CI job publishes to a job summary that expires.

The job ran the v3.1 binary at `--samples 4800 --null-sessions 20` on `ubuntu-latest`, i.e. the
first end-to-end run of `sign-aa`, `null_detail`, the power fields and `schema_version: 4`
anywhere. It completed and wrote its artifacts — which is the end-to-end smoke test the pre-run
audit asked for and that could not be run locally while the 82 k session was measuring
(`METHODOLOGY-v3.1-POWER.md` §7D).

## 1. The null gate failed — on a *quiet* machine, at *low* n

```
null: 20 pool-vs-pool sessions, raw|t| max 6.79 → NOT OK
      raw |t| >= 4.5: [null-rr-9, null-rr-11, null-rr-13, null-rr-17, null-rr-18]
controls: flat=Pass (raw t=-0.32) leaky=Fail (raw t=-226.52) → NOT OK — every Falcon verdict INCONCLUSIVE
```

**5 of 20 null sessions tripped the gate.** Both synthetic controls behaved perfectly (flat
passes, leaky fails at *t* = −226), so this is not a noisy machine. It is the mechanism
pre-registered in `METHODOLOGY-v3.1-POWER.md` §6, firing from the direction that was not
expected:

> the pool-vs-pool null is a random-effects null … `sd(t_null)² ≈ 1 + (σ_between-key/σ_total)²·(n/32)`

That ratio blows up when `σ_total` is **small**. This runner's per-signature sd is ≈ 32 µs
against the laptop's 733 µs — 23× tighter — so `(σ_key/σ_total)²` is ~500× larger, and the null
*t* stops being standard normal even at n = 2 350 per class. Predicted `sd(t) ≈ 2.9` gives ≈ 12 %
per session and ≈ 92 % across twenty; **5 of 20 observed.**

**The consequence is uncomfortable and worth stating plainly: this null gate penalises precision.**
The better the measurement environment, the more likely the session is voided — for arithmetic
reasons, not environmental ones. v4 item **C4** (a null-referenced threshold instead of a fixed
4.5) was filed as a future concern about *large n*; it is now an evidenced defect affecting
*current* runs on good hardware, and it is why every CI session has been INCONCLUSIVE.

The local 82 k session is not affected: at σ_total = 733 µs the same formula gives ≈ 0.1–2 %
across twenty sessions, which is the prediction already recorded before that run started.

## 2. Defect A1 is visible in this output, including on the new control

With the null rejected, `null_crop_stats` is empty, so `judge_v2` computes
`p_emp = (0+1)/(0+1) = 1.0` and its SHAPE arm — guarded by `n > 0` — cannot fire. Every line in
the session prints `p_emp=1.000`, including:

```
sign-aa   … crop max|t|= 1.20 p_emp=1.000  Pass  (informational)
sign-kk-0 … crop max|t|=38.17 p_emp=1.000  Inconclusive
```

A crop statistic of **38.17** printed beside an empirical *p* of **1.000** is the defect in one
line. The key experiments are saved by the control rule (INCONCLUSIVE regardless), but **`sign-aa`
is not routed through that rule** — it reports its own isolated verdict — so the control reads
`Pass` while its shape arm never ran. That is exactly the failure mode V4_BACKLOG §A1 describes,
observed rather than argued. It moves A1 from "should fix" to "fix first, with this session as
its regression fixture".

Cosmetic, same cause: the summary prints `crop-stat range inf..0.00` when the null is empty (a
min/max fold over an empty vector). Added as A8.

## 3. `sign-aa` on this machine: Δ = −648 ns, 95 % CI [−2 452, +1 156] ns

Read as a **control**, per `METHODOLOGY-v3.1-POWER.md` §7C, and read narrowly because the session
is INCONCLUSIVE — but the location arm is interpretable and the resolution is real: SE = 920 ns,
so this session would have detected an arm offset of **≈ 5.3 µs** with 90 % probability.

**On this machine there is no arm/layout offset at the ≈ 5 µs level.** The +13.9 µs class-1
pattern seen across the laptop's nine `sign-kk` pairs is therefore **not reproduced here**, which
disfavours a pure struct-layout explanation as something universal — while leaving open that it
is real on the laptop (different allocator, alignment, OS scheduler and a 23× wider distribution).
The local `sign-aa`, at ±10 µs, is the measurement that speaks to the laptop; this one speaks to
this runner.

**What may not be concluded from this file:** nothing about key-dependence. The three `sign-kk`
pairs here show mixed signs and one large Δ, but the session is INCONCLUSIVE, its crop arm is
void per §2, and its pairs are freshly generated keys unrelated to any other session's. Those
numbers are in the artifact; they are not a reading, and no verdict word applies to them.

## 4. The strategic point: environment control beats sample count, by a lot

| | laptop (v3b) | this ubuntu runner |
|---|---|---|
| per-signature sd | 733 µs | ≈ 32 µs |
| n per class | 2 352 | 2 350 |
| SE of Δmean | 21.4 µs | 0.92 µs |
| **MDE₉₀** | **124 µs** | **≈ 5.3 µs** |
| wall-clock | ≈ 20 min | ≈ 20 min |

The 82 k local session buys MDE₉₀ ≈ 30–42 µs for **5.5 hours**. A 20-minute run on this class of
machine already resolves **≈ 5 µs** — six to eight times better, for 1/16 of the time — because
resolution is driven by `sd/√n` and this environment's `sd` is 23× smaller. Quadrupling samples
buys 2×; changing machine bought 23×.

**This reframes V4_BACKLOG §B.** "Environment control is cheaper than samples" was filed as a
cheap win; it is the single largest lever available, and the next session's design question is
not "how many samples" but "on what machine, and with the null gate fixed so a quiet machine is
not punished for being quiet". Both must be pre-registered before that session runs — and the
gate must be decided **before** a size or machine change, not after seeing a result (§C4).

---

*Provenance: GitHub Actions run 32184522617, job `falcon-ct evidence session (observation, never
a gate)`, commit `eb2ea04`, 2026-08-18. All seven other CI jobs on that commit passed (3-OS KAT,
fmt+clippy, MSRV, audit+deny). The `trelyan-pq CI` failure on the branch is the pre-existing
deployed-app-vs-committed-contract drift job, which is gated on a founder TestNet redeploy and is
unrelated to any of this.*
