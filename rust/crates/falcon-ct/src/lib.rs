//! `falcon-ct` — the statistics and the runner behind TRELYAN's Falcon constant-time EVIDENCE.
//!
//! Everything numerical here implements `evidence/ct/METHODOLOGY.md` literally, and that file —
//! not this one — is the source of truth for the rules: Welch's *t* on the raw samples plus nine
//! percentile-cropped variants, reported statistic `max |t|`, threshold `|t| ≥ 4.5` in absolute
//! value, minimum 2 000 samples per class, randomised class order, 2 % warm-up discard, and the
//! three verdict words with INCONCLUSIVE never collapsing into PASS.
//!
//! The library knows nothing about Falcon. It times any `FnMut(class: bool)` closure and judges
//! the two timing distributions. The binary (`main.rs`) supplies the Falcon experiments and the two
//! synthetic controls. Keeping the statistics Falcon-agnostic is what lets the controls validate
//! the harness itself: a leaky loop must FAIL and a flat loop must PASS *in the same session*,
//! or the Falcon numbers of that session are INCONCLUSIVE.

#![forbid(unsafe_code)]
// Statistics on nanosecond timings and sample counts: every `u64`/`usize` → `f64` cast here is of
// a value far below 2^52 (a session is at most millions of samples of at most seconds each), so
// the precision-loss lint cannot fire on real data; the `f64` → `usize` casts are of percentile
// indices already clamped into range and warm-up counts derived from a length. Allowed crate-wide
// with this reason rather than sprinkled per line, so the numeric code reads as numeric code.
// `suboptimal_flops` (nursery) asks for `mul_add` in the erfc polynomial and the CI bounds; the
// textbook forms are kept because a reader should recognise Abramowitz–Stegun 7.1.26 and
// `d ± 1.96·se` at sight, and FMA-level precision is irrelevant to a reported p-value.
#![allow(
    clippy::cast_precision_loss,
    clippy::cast_possible_truncation,
    clippy::cast_sign_loss,
    clippy::suboptimal_flops
)]

use std::time::Instant;

use serde::{Deserialize, Serialize};

/// The pre-registered threshold on `max |t|` (METHODOLOGY §1).
pub const T_THRESHOLD: f64 = 4.5;
/// Minimum measurements per class before a verdict is issued (METHODOLOGY §1).
pub const MIN_PER_CLASS: usize = 2_000;
/// Fraction of leading measurements discarded as warm-up (METHODOLOGY §1).
pub const WARMUP_FRACTION: f64 = 0.02;
/// The percentile crops, as fractions of the pooled distribution (METHODOLOGY §1). Samples above
/// the pooled percentile are discarded before recomputing *t*.
pub const CROP_PERCENTILES: [f64; 9] = [0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 0.97, 0.98, 0.99];

/// The words a session or an experiment can end in.
///
/// v1 (`METHODOLOGY.md`) used PASS / FAIL / INCONCLUSIVE. v2 (`METHODOLOGY-v2.md`) adds
/// `SHAPE`: the raw Welch *t* is null but the crop diagnostic exceeds the session's empirical
/// null — the distributions differ in shape/scale, not in location. SHAPE is never PASS and never
/// FAIL; it is a call for the source-level reading, not a leak claim.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum Verdict {
    /// Controls behaved, enough samples, no location difference (and, in v2, no shape signal).
    Pass,
    /// (v2 only) Raw *t* null, crop diagnostic beyond the empirical null. Informational.
    Shape,
    /// Controls behaved, enough samples, the classes are distinguishable in location.
    Fail,
    /// A control misbehaved, too few samples, or the harness could not run. No statement.
    Inconclusive,
}

impl Verdict {
    /// The worse of two verdicts, for folding a session. INCONCLUSIVE dominates (a bad control
    /// invalidates every Falcon verdict), then FAIL, then SHAPE, then PASS.
    #[must_use]
    pub const fn worse(self, other: Self) -> Self {
        match (self, other) {
            (Self::Inconclusive, _) | (_, Self::Inconclusive) => Self::Inconclusive,
            (Self::Fail, _) | (_, Self::Fail) => Self::Fail,
            (Self::Shape, _) | (_, Self::Shape) => Self::Shape,
            (Self::Pass, Self::Pass) => Self::Pass,
        }
    }
}

/// Summary statistics of one class's samples.
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct ClassStats {
    pub n: usize,
    pub mean_ns: f64,
    pub stddev_ns: f64,
    pub min_ns: u64,
    pub max_ns: u64,
}

/// One *t* value with the crop it was computed under (`crop = 1.0` means uncropped).
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
pub struct TValue {
    pub crop: f64,
    pub t: f64,
    pub n0: usize,
    pub n1: usize,
}

/// The full result of one experiment.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ExperimentResult {
    pub id: String,
    pub description: String,
    /// Measurements per class after warm-up discard.
    pub class0: ClassStats,
    pub class1: ClassStats,
    /// Ten *t* values: raw + nine crops.
    pub t_values: Vec<TValue>,
    /// `max |t|` over ALL ten `t_values` — the v1 reported statistic (kept for comparability).
    pub max_abs_t: f64,
    /// Whether `max_abs_t >= T_THRESHOLD` — the v1 raw finding.
    pub distinguishable: bool,
    /// Whether both classes reached `MIN_PER_CLASS`.
    pub enough_samples: bool,
    /// The verdict for this experiment IN ISOLATION (controls not yet applied). The session
    /// applies the control rule and may downgrade to INCONCLUSIVE.
    pub isolated_verdict: Verdict,
    // ── v2 fields (METHODOLOGY-v2 §1). Absent (`None`/default) on v1-judged results. ──
    /// The raw (uncropped) Welch *t* — the v2 PRIMARY statistic.
    #[serde(default)]
    pub raw_t: f64,
    /// Welch–Satterthwaite degrees of freedom for the raw *t*.
    #[serde(default)]
    pub df: f64,
    /// Two-sided *p*-value for the raw *t* (normal approximation; df here is always ≫ 100).
    #[serde(default)]
    pub p_raw: f64,
    /// `mean1 − mean0` in nanoseconds, with its 95 % confidence interval.
    #[serde(default)]
    pub mean_diff_ns: f64,
    #[serde(default)]
    pub ci95_ns: (f64, f64),
    /// `max |t|` over the NINE crops only (excluding raw) — the v2 SECONDARY diagnostic.
    #[serde(default)]
    pub crop_max_abs_t: f64,
    /// Empirical *p* of `crop_max_abs_t` against the session's empirical null:
    /// (number of null sessions with a crop statistic ≥ observed + 1) / (N + 1). The null is N
    /// pool-vs-pool sessions of the REAL operation since v3 (v2's synthetic flat loop was found
    /// unfit for an 8 ms operation). **`None` means the diagnostic did not run** — v1 judging, or
    /// a rejected/empty null — in which case the verdict is INCONCLUSIVE and never PASS.
    #[serde(default)]
    pub crop_empirical_p: Option<f64>,
    // ── v3.1 power fields. Descriptive, never decision criteria. ──
    /// Welch standard error of `mean_diff_ns`, in nanoseconds.
    #[serde(default)]
    pub se_ns: f64,
    /// The smallest true mean difference this experiment would have flagged at the
    /// pre-registered `|t| >= 4.5` line with probability 0.80 / 0.90, in nanoseconds
    /// ([`min_detectable_effect`]). A PASS means "nothing at or above this size was detected",
    /// and these two numbers are what makes that sentence readable.
    #[serde(default)]
    pub mde80_ns: f64,
    #[serde(default)]
    pub mde90_ns: f64,
}

/// Raw samples of one experiment, kept for the CSV.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct RawSamples {
    /// `(class, nanoseconds)` in measurement order, warm-up included (the CSV keeps everything;
    /// the statistics discard the warm-up themselves so the CSV can reproduce the report).
    pub samples: Vec<(u8, u64)>,
}

// ── statistics ─────────────────────────────────────────────────────────────────────────────

/// Mean and (sample) standard deviation. Empty input → `(0, 0)`.
#[must_use]
pub fn mean_stddev(xs: &[u64]) -> (f64, f64) {
    if xs.is_empty() {
        return (0.0, 0.0);
    }
    let n = xs.len() as f64;
    // Two-pass for numerical sanity; sums of nanosecond values fit comfortably in f64.
    let mean = xs.iter().map(|&x| x as f64).sum::<f64>() / n;
    if xs.len() < 2 {
        return (mean, 0.0);
    }
    let var = xs
        .iter()
        .map(|&x| {
            let d = x as f64 - mean;
            d * d
        })
        .sum::<f64>()
        / (n - 1.0);
    (mean, var.sqrt())
}

/// Welch's two-sample *t* statistic.
///
/// Returns `0.0` if either sample has fewer than two points, or if both variances are zero with
/// equal means (nothing to distinguish). A zero pooled variance with unequal means is reported as
/// a very large finite `t` (sign preserved) rather than `±INFINITY`, so the JSON stays finite.
#[must_use]
pub fn welch_t(a: &[u64], b: &[u64]) -> f64 {
    if a.len() < 2 || b.len() < 2 {
        return 0.0;
    }
    let (ma, sa) = mean_stddev(a);
    let (mb, sb) = mean_stddev(b);
    let va = sa * sa / a.len() as f64;
    let vb = sb * sb / b.len() as f64;
    let denom = (va + vb).sqrt();
    if denom == 0.0 {
        // Both classes perfectly constant. Equal means: indistinguishable. Unequal: maximally
        // distinguishable — report a large finite value so JSON stays finite.
        return if (ma - mb).abs() < f64::EPSILON {
            0.0
        } else {
            1.0e9_f64.copysign(ma - mb)
        };
    }
    (ma - mb) / denom
}

/// Welch–Satterthwaite degrees of freedom for two samples. `0.0` if either has < 2 points.
#[must_use]
pub fn welch_df(a: &[u64], b: &[u64]) -> f64 {
    if a.len() < 2 || b.len() < 2 {
        return 0.0;
    }
    let (_, sa) = mean_stddev(a);
    let (_, sb) = mean_stddev(b);
    let (na, nb) = (a.len() as f64, b.len() as f64);
    let va = sa * sa / na;
    let vb = sb * sb / nb;
    let num = (va + vb) * (va + vb);
    let den = va * va / (na - 1.0) + vb * vb / (nb - 1.0);
    if den == 0.0 { 0.0 } else { num / den }
}

/// Complementary error function, Abramowitz & Stegun 7.1.26 (|error| < 1.5e-7). Enough for a
/// reported *p*-value; the constitution's numeric caution is about crypto, not statistics.
#[must_use]
pub fn erfc(x: f64) -> f64 {
    let z = x.abs();
    let t = 1.0 / (1.0 + 0.5 * z);
    let poly = t
        * (-z * z - 1.265_512_23
            + t * (1.000_023_68
                + t * (0.374_091_96
                    + t * (0.096_784_18
                        + t * (-0.186_288_06
                            + t * (0.278_868_07
                                + t * (-1.135_203_98
                                    + t * (1.488_515_87
                                        + t * (-0.822_152_23 + t * 0.170_872_77)))))))))
            .exp();
    if x >= 0.0 { poly } else { 2.0 - poly }
}

/// Two-sided *p*-value for a *t* statistic under the normal approximation (valid for large df,
/// which every experiment here has: thousands per class).
#[must_use]
pub fn two_sided_p_normal(t: f64) -> f64 {
    erfc(t.abs() / core::f64::consts::SQRT_2)
}

/// `mean(b) − mean(a)` and its 95 % confidence interval (normal approximation).
#[must_use]
pub fn mean_diff_ci95(a: &[u64], b: &[u64]) -> (f64, (f64, f64)) {
    if a.len() < 2 || b.len() < 2 {
        return (0.0, (0.0, 0.0));
    }
    let (ma, sa) = mean_stddev(a);
    let (mb, sb) = mean_stddev(b);
    let se = (sa * sa / a.len() as f64 + sb * sb / b.len() as f64).sqrt();
    let d = mb - ma;
    (d, (d - 1.96 * se, d + 1.96 * se))
}

/// The standard error of the difference in means (Welch), in the samples' unit.
#[must_use]
pub fn welch_se(a: &[u64], b: &[u64]) -> f64 {
    if a.len() < 2 || b.len() < 2 {
        return f64::INFINITY;
    }
    let (_, sa) = mean_stddev(a);
    let (_, sb) = mean_stddev(b);
    (sa * sa / a.len() as f64 + sb * sb / b.len() as f64).sqrt()
}

/// The standard normal quantile `z` such that `P(Z <= z) = p`, for `p` in (0, 1).
///
/// Acklam's rational approximation, relative error < 1.15e-9 over the whole domain. Needed
/// because the harness reports its own statistical power and a power statement needs `z_beta`;
/// no dependency is added for it (constitution §3).
///
/// **No Halley refinement**, deliberately. The textbook refinement step
/// (`x -= u / (1 + x·u/2)` with `u` from the CDF) is only an improvement if the CDF used is more
/// accurate than the approximation being refined. This crate's [`erfc`] is Abramowitz–Stegun
/// 7.1.26, whose absolute error is ≈ 1.5e-7 — two orders of magnitude WORSE than Acklam — so
/// refining with it moved the answer away from the published quantiles (measured: z(0.9) off by
/// ~1e-7 with the step, < 1e-9 without). Kept as a comment because the step looks like free
/// precision and someone will otherwise add it back.
#[must_use]
#[allow(clippy::many_single_char_names)]
pub fn inverse_normal_cdf(p: f64) -> f64 {
    const A: [f64; 6] = [
        -3.969_683_028_665_376e1,
        2.209_460_984_245_205e2,
        -2.759_285_104_469_687e2,
        1.383_577_518_672_69e2,
        -3.066_479_806_614_716e1,
        2.506_628_277_459_239e0,
    ];
    const B: [f64; 5] = [
        -5.447_609_879_822_406e1,
        1.615_858_368_580_409e2,
        -1.556_989_798_598_866e2,
        6.680_131_188_771_972e1,
        -1.328_068_155_288_572e1,
    ];
    const C: [f64; 6] = [
        -7.784_894_002_430_293e-3,
        -3.223_964_580_411_365e-1,
        -2.400_758_277_161_838e0,
        -2.549_732_539_343_734e0,
        4.374_664_141_464_968e0,
        2.938_163_982_698_783e0,
    ];
    const D: [f64; 4] = [
        7.784_695_709_041_462e-3,
        3.224_671_290_700_398e-1,
        2.445_134_137_142_996e0,
        3.754_408_661_907_416e0,
    ];
    const P_LOW: f64 = 0.024_25;
    if !(p > 0.0 && p < 1.0) {
        return f64::NAN;
    }
    if p < P_LOW {
        let q = (-2.0 * p.ln()).sqrt();
        (((((C[0] * q + C[1]) * q + C[2]) * q + C[3]) * q + C[4]) * q + C[5])
            / ((((D[0] * q + D[1]) * q + D[2]) * q + D[3]) * q + 1.0)
    } else if p <= 1.0 - P_LOW {
        let q = p - 0.5;
        let r = q * q;
        (((((A[0] * r + A[1]) * r + A[2]) * r + A[3]) * r + A[4]) * r + A[5]) * q
            / (((((B[0] * r + B[1]) * r + B[2]) * r + B[3]) * r + B[4]) * r + 1.0)
    } else {
        let q = (-2.0 * (1.0 - p).ln()).sqrt();
        -(((((C[0] * q + C[1]) * q + C[2]) * q + C[3]) * q + C[4]) * q + C[5])
            / ((((D[0] * q + D[1]) * q + D[2]) * q + D[3]) * q + 1.0)
    }
}

/// The smallest true mean difference this experiment would flag with probability `power`,
/// given its own standard error and the pre-registered decision threshold.
///
/// **This is the number that makes a PASS readable.** A non-detection is only as strong as the
/// effect it could have detected: with `|t| >= threshold` as the rule, a true difference `d`
/// is flagged with probability ≈ `P(Z >= threshold - d/se)`, so the detectable effect is
/// `(threshold + z_power) * se`. Reported per experiment so no session can state "no difference
/// detected" without publishing the size of what it could have seen.
///
/// Normal approximation: the degrees of freedom here are in the thousands. It is a *planning*
/// quantity — computed from the observed sd, so it describes the run that happened, and it is
/// never a decision criterion (METHODOLOGY-v3 §1: only the raw statistic and the crop/null
/// comparison decide).
#[must_use]
pub fn min_detectable_effect(se: f64, threshold: f64, power: f64) -> f64 {
    if !se.is_finite() || se <= 0.0 || !(power > 0.0 && power < 1.0) {
        return f64::NAN;
    }
    (threshold + inverse_normal_cdf(power)) * se
}

/// The value at the `p`-th percentile (0..=1) of the POOLED samples, by nearest-rank.
#[must_use]
pub fn pooled_percentile(a: &[u64], b: &[u64], p: f64) -> u64 {
    let mut pooled: Vec<u64> = a.iter().chain(b.iter()).copied().collect();
    if pooled.is_empty() {
        return 0;
    }
    pooled.sort_unstable();
    let idx = ((p * pooled.len() as f64).ceil() as usize).clamp(1, pooled.len()) - 1;
    pooled[idx]
}

/// Compute the ten *t* values (raw + nine crops) per METHODOLOGY §1.
#[must_use]
pub fn t_values(a: &[u64], b: &[u64]) -> Vec<TValue> {
    let mut out = Vec::with_capacity(1 + CROP_PERCENTILES.len());
    out.push(TValue {
        crop: 1.0,
        t: welch_t(a, b),
        n0: a.len(),
        n1: b.len(),
    });
    for &p in &CROP_PERCENTILES {
        let cut = pooled_percentile(a, b, p);
        let a2: Vec<u64> = a.iter().copied().filter(|&x| x <= cut).collect();
        let b2: Vec<u64> = b.iter().copied().filter(|&x| x <= cut).collect();
        out.push(TValue {
            crop: p,
            t: welch_t(&a2, &b2),
            n0: a2.len(),
            n1: b2.len(),
        });
    }
    out
}

fn class_stats(xs: &[u64]) -> ClassStats {
    let (mean_ns, stddev_ns) = mean_stddev(xs);
    ClassStats {
        n: xs.len(),
        mean_ns,
        stddev_ns,
        min_ns: xs.iter().copied().min().unwrap_or(0),
        max_ns: xs.iter().copied().max().unwrap_or(0),
    }
}

/// Split warm-up-trimmed samples by class.
fn split_classes(raw: &RawSamples) -> (Vec<u64>, Vec<u64>) {
    let total = raw.samples.len();
    let skip = ((total as f64) * WARMUP_FRACTION).floor() as usize;
    let (mut c0, mut c1) = (Vec::new(), Vec::new());
    for &(class, ns) in raw.samples.iter().skip(skip) {
        if class == 0 { c0.push(ns) } else { c1.push(ns) }
    }
    (c0, c1)
}

/// The nine-crop statistic alone (excluding the raw *t*) — the v2 secondary diagnostic.
#[must_use]
pub fn crop_statistic(a: &[u64], b: &[u64]) -> f64 {
    t_values(a, b)
        .iter()
        .skip(1)
        .map(|v| v.t.abs())
        .fold(0.0_f64, f64::max)
}

/// **v1 judging** (`METHODOLOGY.md`): `max |t|` over raw + nine crops against 4.5. Kept so the
/// first session's numbers stay reproducible; new sessions use [`judge_v2`].
#[must_use]
pub fn judge(id: &str, description: &str, raw: &RawSamples) -> ExperimentResult {
    let (c0, c1) = split_classes(raw);
    let tv = t_values(&c0, &c1);
    let max_abs_t = tv.iter().map(|v| v.t.abs()).fold(0.0_f64, f64::max);
    let enough = c0.len() >= MIN_PER_CLASS && c1.len() >= MIN_PER_CLASS;
    let distinguishable = max_abs_t >= T_THRESHOLD;
    let isolated_verdict = if !enough {
        Verdict::Inconclusive
    } else if distinguishable {
        Verdict::Fail
    } else {
        Verdict::Pass
    };
    let raw_t = tv.first().map_or(0.0, |v| v.t);
    let (mean_diff_ns, ci95_ns) = mean_diff_ci95(&c0, &c1);
    let se_ns = welch_se(&c0, &c1);
    ExperimentResult {
        se_ns,
        mde80_ns: min_detectable_effect(se_ns, T_THRESHOLD, 0.80),
        mde90_ns: min_detectable_effect(se_ns, T_THRESHOLD, 0.90),
        id: id.to_owned(),
        description: description.to_owned(),
        class0: class_stats(&c0),
        class1: class_stats(&c1),
        crop_max_abs_t: crop_statistic(&c0, &c1),
        t_values: tv,
        max_abs_t,
        distinguishable,
        enough_samples: enough,
        isolated_verdict,
        raw_t,
        df: welch_df(&c0, &c1),
        p_raw: two_sided_p_normal(raw_t),
        mean_diff_ns,
        ci95_ns,
        crop_empirical_p: None,
    }
}

/// **v2 judging** (`METHODOLOGY-v2.md` §1).
///
/// The raw Welch *t* is primary (|t| ≥ 4.5 → FAIL). The nine-crop statistic is judged against
/// `null_crop_stats` — the crop statistics of the session's N flat-control runs — and a
/// crop-only exceedance yields SHAPE, never FAIL. Empirical *p* = (#null ≥ observed + 1) /
/// (N + 1); SHAPE iff raw |t| < 4.5 and *p* < 1/N.
#[must_use]
pub fn judge_v2(
    id: &str,
    description: &str,
    raw: &RawSamples,
    null_crop_stats: &[f64],
) -> ExperimentResult {
    let mut r = judge(id, description, raw);
    let n = null_crop_stats.len();
    // v2's `distinguishable` means "in LOCATION": the raw statistic only.
    r.distinguishable = r.raw_t.abs() >= T_THRESHOLD;

    // NO NULL, NO SECONDARY VERDICT. With an empty null the arithmetic below would compute
    // p = (0+1)/(0+1) = 1.0 — a PASS-shaped number derived from nothing — and the SHAPE arm,
    // guarded by `n > 0`, could never fire, so every experiment fell through to PASS with a
    // confident-looking `crop_empirical_p: 1.0` beside it.
    //
    // Observed live, not hypothesised: the ubuntu CI session of 2026-08-18 (five of twenty null
    // sessions tripped the raw gate, so the null was rejected and this vector was empty) printed
    //     sign-kk-0 … crop max|t| = 38.17  p_emp = 1.000
    // and reported the `sign-aa` control as PASS with its shape arm never run. The gated
    // experiments were saved by the control rule, which forces INCONCLUSIVE when the null is
    // rejected — but `sign-aa` is read on its own isolated verdict, so the control that gates the
    // session was the one the defect could mislabel.
    //
    // A check that cannot fail is worse than no check. Fail closed instead: no `p`, and
    // INCONCLUSIVE, which is what "the diagnostic did not run" actually means.
    if n == 0 {
        r.crop_empirical_p = None;
        r.isolated_verdict = if r.distinguishable {
            // The PRIMARY statistic stands on its own and never depended on the null.
            Verdict::Fail
        } else {
            Verdict::Inconclusive
        };
        return r;
    }

    let ge = null_crop_stats
        .iter()
        .filter(|&&s| s >= r.crop_max_abs_t)
        .count();
    let p = (ge as f64 + 1.0) / (n as f64 + 1.0);
    r.crop_empirical_p = Some(p);
    r.isolated_verdict = if !r.enough_samples {
        Verdict::Inconclusive
    } else if r.distinguishable {
        Verdict::Fail
    } else if p < 1.0 / n as f64 {
        Verdict::Shape
    } else {
        Verdict::Pass
    };
    r
}

/// **Raw-only judging for SYNTHETIC controls** — the interim ruling of 2026-08-20, from the
/// six-seat review of the v4.1 validation session (transcript committed beside it).
///
/// The defect it corrects: the synthetic flat control was crop-judged against a bank of REAL
/// signing operations (under `--null-design ss`, the null-ss sessions) and came out "Shape" at
/// raw t = 2.99, flipping the whole session's controls to NOT OK. A synthetic loop and an 8 ms
/// signature do not share a crop nuisance distribution — judging one against the other is the
/// same mismatched-reference error METHODOLOGY-v4.1 exists to prevent, pointed at ourselves.
///
/// The rule: a synthetic control's verdict comes from the fixed raw line ONLY.
/// `|raw t| >= 4.5` ⇒ FAIL (the leaky control must do exactly this); below it ⇒ PASS; too few
/// samples ⇒ INCONCLUSIVE. The crop statistic remains in the artifact as a descriptive number,
/// and `crop_empirical_p` is `None` — the crop diagnostic DID NOT RUN, and nothing downstream
/// may cite it as if it had. Whether a crop-shape validation of the controls returns later —
/// with its own matched synthetic reference family AND a synthetic-shape positive control with
/// a numeric fire condition — is an open design choice that belongs to its own
/// pre-registration, not to this function.
#[must_use]
pub fn judge_raw_only(id: &str, description: &str, raw: &RawSamples) -> ExperimentResult {
    let mut r = judge(id, description, raw);
    r.distinguishable = r.raw_t.abs() >= T_THRESHOLD;
    r.crop_empirical_p = None;
    // REVIEW S8 (2026-08-20): NaN compares false with everything, so a degenerate series
    // (e.g. zero variance in both classes) would fall through `>= T_THRESHOLD` into Pass —
    // a fail-open. A statistic that is not a finite number supports no verdict.
    r.isolated_verdict = if !r.enough_samples || !r.raw_t.is_finite() {
        Verdict::Inconclusive
    } else if r.distinguishable {
        Verdict::Fail
    } else {
        Verdict::Pass
    };
    r
}

// ── runner ─────────────────────────────────────────────────────────────────────────────────

/// Time `op(class)` `total` times with a randomised class per measurement.
///
/// `next_class_bit` supplies the class for each measurement (the binary draws it from the
/// audited SHAKE PRNG; tests may pass a deterministic sequence). Only the call to `op` is inside
/// the timed region; the closure must do its own preparation outside (the binary pre-generates
/// key pools and messages, and picks by index inside `op` — a slice index is a few nanoseconds
/// against a millisecond signature).
pub fn measure<F, R>(total: usize, mut next_class_bit: R, mut op: F) -> RawSamples
where
    F: FnMut(bool),
    R: FnMut() -> bool,
{
    let mut samples = Vec::with_capacity(total);
    for _ in 0..total {
        let class = next_class_bit();
        let t0 = Instant::now();
        op(class);
        let dt = t0.elapsed();
        // Saturate rather than wrap; a >584-year measurement is not a real sample.
        let ns = u64::try_from(dt.as_nanos()).unwrap_or(u64::MAX);
        samples.push((u8::from(class), ns));
    }
    RawSamples { samples }
}

/// Apply the session rule (METHODOLOGY §3).
///
/// If the flat control did not PASS or the leaky control did not FAIL, every Falcon experiment's
/// verdict becomes INCONCLUSIVE; otherwise it keeps its isolated verdict.
#[must_use]
pub const fn apply_controls(
    isolated: Verdict,
    flat_control: Verdict,
    leaky_control: Verdict,
) -> Verdict {
    let controls_ok =
        matches!(flat_control, Verdict::Pass) && matches!(leaky_control, Verdict::Fail);
    if controls_ok {
        isolated
    } else {
        Verdict::Inconclusive
    }
}

/// Fold the null sessions (v2: flat loops; v3: pool-vs-pool signing).
///
/// Every one must have enough samples per class and PASS on the RAW statistic, else no Falcon
/// verdict may be issued. Returns the crop statistics for the null, or the reason it is unusable.
///
/// # Errors
/// A one-line reason naming which sessions failed which precondition.
pub fn null_from_sessions(sessions: &[ExperimentResult]) -> Result<Vec<f64>, String> {
    if sessions.is_empty() {
        return Err("no null sessions ran".to_owned());
    }
    let too_few: Vec<&str> = sessions
        .iter()
        .filter(|s| !s.enough_samples)
        .map(|s| s.id.as_str())
        .collect();
    let raw_fail: Vec<&str> = sessions
        .iter()
        .filter(|s| s.enough_samples && s.raw_t.abs() >= T_THRESHOLD)
        .map(|s| s.id.as_str())
        .collect();
    if !too_few.is_empty() || !raw_fail.is_empty() {
        return Err(format!(
            "below the per-class minimum: [{}]; raw |t| >= {T_THRESHOLD}: [{}]",
            too_few.join(", "),
            raw_fail.join(", ")
        ));
    }
    Ok(sessions.iter().map(|s| s.crop_max_abs_t).collect())
}

/// Render raw samples as CSV (`class,ns` per line, header first).
#[must_use]
pub fn to_csv(raw: &RawSamples) -> String {
    use std::fmt::Write as _;
    let mut s = String::with_capacity(raw.samples.len() * 12 + 16);
    s.push_str("class,ns\n");
    for &(c, ns) in &raw.samples {
        // Writing to a String cannot fail; the Result is discarded on purpose.
        let _ = writeln!(s, "{c},{ns}");
    }
    s
}

#[cfg(test)]
mod tests {
    #![allow(clippy::expect_used, clippy::unwrap_used, clippy::panic)]

    use super::*;

    /// Regression for the defect the ubuntu CI session of 2026-08-18 exhibited: with the null
    /// rejected, `judge_v2` used to emit `crop_empirical_p = 1.0` — computed from nothing — and
    /// fall through to PASS, printing `crop max|t| = 38.17` beside `p_emp = 1.000`. The control
    /// that gates the whole session (`sign-aa`) is read on its isolated verdict, so it was the
    /// one the defect could mislabel.
    #[test]
    fn an_empty_null_yields_no_p_and_no_pass() {
        let mut rng = Xs(0xdead_beef_0123_4567);
        // Two classes with identical distributions: the raw statistic is null, and under a
        // working null this would be a legitimate PASS.
        let flat: Vec<(u8, u64)> = (0..8_000)
            .map(|i| (u8::from(i % 2 == 1), 8_000_000 + rng.next() % 100_000))
            .collect();
        let raw = RawSamples { samples: flat };

        // A null WIDER than this sample's own crop statistic, so the crop arm is quiet and the
        // legitimate answer is PASS. (Null values below the observed statistic would correctly
        // give SHAPE — a different arm, and not the one this test is about.)
        let with_null = judge_v2("x", "", &raw, &[6.0, 7.5, 5.5, 8.0, 6.5]);
        assert_eq!(
            with_null.isolated_verdict,
            Verdict::Pass,
            "sanity: with a real, wide null this same data is a legitimate PASS (crop stat {:.2})",
            with_null.crop_max_abs_t
        );
        assert_eq!(with_null.crop_empirical_p, Some(1.0));

        let without = judge_v2("x", "", &raw, &[]);
        assert_eq!(
            without.crop_empirical_p, None,
            "an empty null must yield NO empirical p — 1.0 from zero samples is a number that              looks like evidence and is not"
        );
        assert_eq!(
            without.isolated_verdict,
            Verdict::Inconclusive,
            "no null means the secondary diagnostic did not run, which is INCONCLUSIVE, not PASS"
        );
        assert!(
            without.raw_t.abs() < T_THRESHOLD && without.crop_max_abs_t > 0.0,
            "the statistics themselves are still computed and reported"
        );
    }

    /// The PRIMARY statistic never depended on the null, so a real location difference must still
    /// FAIL even when the secondary diagnostic is unavailable. Fail-closed must not become
    /// fail-silent in the direction that hides a signal.
    #[test]
    fn an_empty_null_does_not_suppress_a_real_fail() {
        let mut rng = Xs(0x0f0f_0f0f_0f0f_0f0f);
        let leaky: Vec<(u8, u64)> = (0..8_000)
            .map(|i| {
                let class = i % 2 == 1;
                let base = if class { 9_000_000 } else { 8_000_000 };
                (u8::from(class), base + rng.next() % 100_000)
            })
            .collect();
        let raw = RawSamples { samples: leaky };
        let r = judge_v2("leaky", "", &raw, &[]);
        assert!(r.distinguishable, "a 1 ms shift is a location difference");
        assert_eq!(r.isolated_verdict, Verdict::Fail);
        assert_eq!(r.crop_empirical_p, None, "still no p from an empty null");
    }

    #[test]
    fn inverse_normal_cdf_matches_published_quantiles() {
        // Reference values (Abramowitz & Stegun / any standard table), to 1e-9.
        for &(p, want) in &[
            (0.5_f64, 0.0_f64),
            (0.8, 0.841_621_233_572_914_4),
            (0.9, 1.281_551_565_544_600_4_f64),
            (0.95, 1.644_853_626_951_472_7),
            (0.975, 1.959_963_984_540_054),
            (0.999, 3.090_232_306_167_813),
            (0.01, -2.326_347_874_040_841),
            (0.001, -3.090_232_306_167_813),
        ] {
            let got = inverse_normal_cdf(p);
            assert!(
                (got - want).abs() < 1e-8,
                "z({p}) = {got}, want {want} (diff {:e})",
                (got - want).abs()
            );
        }
        assert!(
            inverse_normal_cdf(0.0).is_nan(),
            "p outside (0,1) is NaN, not a number to use"
        );
        assert!(inverse_normal_cdf(1.0).is_nan());
        assert!(inverse_normal_cdf(-0.5).is_nan());
    }

    #[test]
    fn min_detectable_effect_is_the_threshold_plus_z_times_se() {
        // The rule is |t| >= 4.5, NOT 1.96: a 4.5-sigma line needs (4.5 + z_power) * SE, so
        // the detectable effect is ~2.7x the 95% CI half-width, never equal to it. Getting this
        // wrong is how a report claims four times the resolution it has.
        let se = 10_000.0; // 10 us
        let m90 = min_detectable_effect(se, T_THRESHOLD, 0.90);
        let m80 = min_detectable_effect(se, T_THRESHOLD, 0.80);
        assert!((m90 - (4.5 + 1.281_551_565_544_6) * se).abs() < 1e-4);
        assert!((m80 - (4.5 + 0.841_621_233_572_9) * se).abs() < 1e-4);
        assert!(m90 > m80, "more power costs a bigger detectable effect");
        assert!(
            m90 > 2.9 * 1.96 * se && m90 < 3.0 * 1.96 * se,
            "MDE90 ({m90}) must be ~2.95x the CI half-width ({}), not equal to it",
            1.96 * se
        );
        assert!(min_detectable_effect(f64::INFINITY, T_THRESHOLD, 0.9).is_nan());
        assert!(min_detectable_effect(0.0, T_THRESHOLD, 0.9).is_nan());
        assert!(min_detectable_effect(se, T_THRESHOLD, 1.0).is_nan());
    }

    #[test]
    fn power_fields_scale_as_one_over_sqrt_n() {
        // Quadrupling the sample count halves the standard error, and therefore halves the
        // detectable effect. This is the whole cost model of a high-power session.
        let mut rng = Xs(0x1234_5678_9abc_def0);
        let make = |rng: &mut Xs, n: usize| -> RawSamples {
            let samples = (0..n)
                .map(|i| {
                    let noise = rng.next() % 200_000;
                    (u8::from(i % 2 == 1), 8_000_000 + noise)
                })
                .collect();
            RawSamples { samples }
        };
        let small = judge("s", "", &make(&mut rng, 10_000));
        let big = judge("b", "", &make(&mut rng, 40_000));
        let ratio = small.mde90_ns / big.mde90_ns;
        assert!(
            (ratio - 2.0).abs() < 0.15,
            "4x the samples should halve MDE90; got ratio {ratio}"
        );
        assert!(small.se_ns.is_finite() && big.se_ns.is_finite());
    }

    /// A tiny deterministic PRNG for tests (xorshift64*). NOT for anything but tests.
    struct Xs(u64);
    impl Xs {
        fn next(&mut self) -> u64 {
            let mut x = self.0;
            x ^= x >> 12;
            x ^= x << 25;
            x ^= x >> 27;
            self.0 = x;
            x.wrapping_mul(0x2545_F491_4F6C_DD1D)
        }
        fn bit(&mut self) -> bool {
            self.next() & 1 == 1
        }
        /// Uniform-ish integer in [lo, hi].
        fn range(&mut self, lo: u64, hi: u64) -> u64 {
            lo + self.next() % (hi - lo + 1)
        }
    }

    #[test]
    fn welch_t_is_near_zero_for_identical_distributions_and_large_for_shifted() {
        let mut r = Xs(0x9E37_79B9_7F4A_7C15);
        let a: Vec<u64> = (0..5_000).map(|_| r.range(1_000, 1_100)).collect();
        let b: Vec<u64> = (0..5_000).map(|_| r.range(1_000, 1_100)).collect();
        let t_same = welch_t(&a, &b);
        assert!(
            t_same.abs() < 3.0,
            "same distribution should not separate: t={t_same}"
        );
        let c: Vec<u64> = (0..5_000).map(|_| r.range(1_010, 1_110)).collect();
        let t_shift = welch_t(&a, &c);
        assert!(
            t_shift.abs() > T_THRESHOLD,
            "a 10-unit shift on a 100-unit range must separate at n=5000: t={t_shift}"
        );
        assert!(
            t_shift < 0.0,
            "a is smaller than c, so t must be negative — the sign is real information"
        );
    }

    #[test]
    fn welch_t_handles_degenerate_inputs_without_nan_or_infinity() {
        // These are exact-zero returns by construction, so an exact comparison is the intent.
        assert!(welch_t(&[], &[1, 2, 3]).abs() < f64::EPSILON);
        assert!(welch_t(&[5], &[1, 2, 3]).abs() < f64::EPSILON);
        let t = welch_t(&[7, 7, 7], &[7, 7, 7]);
        assert!(t.abs() < f64::EPSILON);
        let t2 = welch_t(&[7, 7, 7], &[9, 9, 9]);
        assert!(t2.is_finite() && t2 < 0.0);
    }

    #[test]
    fn pooled_percentile_is_nearest_rank() {
        assert_eq!(
            pooled_percentile(&[1, 2, 3, 4, 5], &[6, 7, 8, 9, 10], 0.5),
            5
        );
        assert_eq!(
            pooled_percentile(&[1, 2, 3, 4, 5], &[6, 7, 8, 9, 10], 0.99),
            10
        );
        assert_eq!(pooled_percentile(&[], &[], 0.5), 0);
    }

    #[test]
    fn judge_reports_inconclusive_below_minimum_samples_regardless_of_t() {
        // 100 wildly different samples per class: hugely distinguishable, but too few.
        let mut samples = Vec::new();
        for i in 0..200u64 {
            samples.push((u8::from(i % 2 == 1), if i % 2 == 1 { 10_000 } else { 100 }));
        }
        let r = judge("tiny", "too few", &RawSamples { samples });
        assert!(r.distinguishable, "the classes ARE distinguishable");
        assert!(!r.enough_samples);
        assert_eq!(
            r.isolated_verdict,
            Verdict::Inconclusive,
            "INCONCLUSIVE, not FAIL, below the minimum"
        );
    }

    #[test]
    fn a_leaky_operation_fails_and_a_flat_one_passes_end_to_end() {
        // The harness's own validation: synthetic operations with known behaviour, timed for real
        // through `measure`. The leaky op does class-dependent work; the flat op identical work.
        // Uses `std::hint::black_box` so the loops are not optimised away.
        let mut r = Xs(0xDEAD_BEEF_CAFE_F00D);
        let total = 2 * MIN_PER_CLASS + 400;

        let leaky = measure(
            total,
            || r.bit(),
            |class| {
                let iters = if class { 60_000u64 } else { 40_000u64 };
                let mut acc = 0u64;
                for i in 0..iters {
                    acc = acc.wrapping_add(std::hint::black_box(i));
                }
                std::hint::black_box(acc);
            },
        );
        let leaky_res = judge("control-leaky", "class-dependent work", &leaky);
        assert!(leaky_res.enough_samples);
        assert_eq!(
            leaky_res.isolated_verdict,
            Verdict::Fail,
            "a 50% work difference must be detected: max|t|={}",
            leaky_res.max_abs_t
        );

        let mut r2 = Xs(0x1234_5678_9ABC_DEF0);
        let flat = measure(
            total,
            || r2.bit(),
            |class| {
                // Same work for both classes; the class only selects which of two equal-cost
                // accumulators is touched, so the compiler cannot fold the branch away.
                let mut acc = 0u64;
                for i in 0..50_000u64 {
                    acc = acc.wrapping_add(std::hint::black_box(i));
                }
                std::hint::black_box((acc, class));
            },
        );
        let flat_res = judge("control-flat", "identical work", &flat);
        assert!(flat_res.enough_samples);
        // On a loaded CI runner this can occasionally trip on noise; that is exactly the
        // INCONCLUSIVE case the session rule exists for. Assert the STRUCTURE (max_abs_t computed
        // over ten crops, verdict consistent with it), and separately assert PASS only when the
        // environment is quiet enough that the raw t is small — otherwise print and accept.
        assert_eq!(flat_res.t_values.len(), 10);
        let consistent = if flat_res.max_abs_t >= T_THRESHOLD {
            flat_res.isolated_verdict == Verdict::Fail
        } else {
            flat_res.isolated_verdict == Verdict::Pass
        };
        assert!(consistent, "verdict must follow max|t|: {flat_res:?}");
        if flat_res.isolated_verdict != Verdict::Pass {
            eprintln!(
                "note: flat control did not PASS on this machine (max|t|={:.2}); a real session \
                 would report INCONCLUSIVE, which is the honest outcome",
                flat_res.max_abs_t
            );
        }
    }

    /// INTERIM RULING 2026-08-20 (six-seat review of the v4.1 validation session): synthetic
    /// controls are judged on the raw line only. The regression this pins is the live failure:
    /// a flat operation whose CROP statistic would exceed every member of a real-operation
    /// bank must still PASS, because the crop diagnostic does not run for synthetic controls.
    #[test]
    fn synthetic_controls_are_judged_on_the_raw_line_only() {
        // A flat series: identical work both classes, raw t ~ 0 — but heavy alternation gives
        // it a crop profile unlike a real signature (the live session's flat control read
        // "Shape" against the null-ss bank at raw t = 2.99).
        let flat = RawSamples {
            samples: (0..9600u64)
                .map(|i| (u8::from(i % 2 == 1), 1_000 + (i % 13) * 3))
                .collect(),
        };
        let r = judge_raw_only("control-flat", "x", &flat);
        assert!(
            r.raw_t.abs() < T_THRESHOLD,
            "flat by construction: {}",
            r.raw_t
        );
        assert_eq!(r.isolated_verdict, Verdict::Pass);
        assert_eq!(
            r.crop_empirical_p, None,
            "the crop diagnostic must not have run"
        );
        // Contrast: judged v2-style against a tight real-op bank, the same series would have
        // been dragged into the crop arm — the exact category error the ruling removes.
        // REVIEW S6: the pin must be TWO-SIDED — the same series through the old judging
        // against a tight multi-element real-op-style bank must be DEMOTED by the crop arm
        // (the live failure's mechanism), while raw-only Passes it. If someone reverts the
        // production wiring to judge_v2, this contrast is what goes red.
        // The bank is built strictly BELOW the series' own crop statistic — a bank drawn
        // from a different (tighter) DGP, which is precisely how the real-op bank related to
        // the flat control in the live session.
        let c = judge("control-flat", "x", &flat).crop_max_abs_t;
        assert!(c > 0.0, "sanity: the crop statistic exists");
        let tight_bank = [c * 0.5, c * 0.6, c * 0.7];
        let v2 = judge_v2("control-flat", "x", &flat, &tight_bank);
        assert_eq!(
            v2.isolated_verdict,
            Verdict::Shape,
            "the same flat series must be dragged into the crop arm under v2 judging              (crop {} vs a bank strictly below it) — the exact category error the ruling removes",
            v2.crop_max_abs_t
        );

        // REVIEW S8 follow-up: `welch_t` is TOTAL (degenerate inputs yield a finite value —
        // pinned by `welch_t_handles_degenerate_inputs_without_nan_or_infinity`), so the
        // `is_finite` guard in `judge_raw_only` is unreachable through real samples today; it
        // exists so INCONCLUSIVE-never-PASS survives any future `welch_t` change. What IS
        // checkable here: a constant series is genuinely flat and must Pass with a finite t.
        let constant = RawSamples {
            samples: (0..9600u64)
                .map(|i| (u8::from(i % 2 == 1), 5_000))
                .collect(),
        };
        let r = judge_raw_only("control-flat", "x", &constant);
        assert!(r.raw_t.is_finite(), "welch_t is total: {}", r.raw_t);
        assert_eq!(r.isolated_verdict, Verdict::Pass);

        // The leaky control still fails loudly on the raw line alone.
        let leaky = RawSamples {
            samples: (0..9600u64)
                .map(|i| {
                    let class = u8::from(i % 2 == 1);
                    (class, 1_000 + u64::from(class) * 500 + i % 7)
                })
                .collect(),
        };
        let r = judge_raw_only("control-leaky", "x", &leaky);
        assert_eq!(r.isolated_verdict, Verdict::Fail);
        assert_eq!(r.crop_empirical_p, None);

        // Too few samples: INCONCLUSIVE, never PASS.
        let short = RawSamples {
            samples: (0..100u64).map(|i| (u8::from(i % 2 == 1), 1_000)).collect(),
        };
        let r = judge_raw_only("control-flat", "x", &short);
        assert_eq!(r.isolated_verdict, Verdict::Inconclusive);
    }

    #[test]
    fn null_from_sessions_names_the_reason_it_is_unusable() {
        let mut ok = judge(
            "n0",
            "x",
            &RawSamples {
                samples: (0..4600u64)
                    .map(|i| (u8::from(i % 2 == 1), 1_000 + i % 7))
                    .collect(),
            },
        );
        assert!(ok.enough_samples);
        assert!(null_from_sessions(std::slice::from_ref(&ok)).is_ok());
        // Too few samples → named.
        let few = judge(
            "n1",
            "x",
            &RawSamples {
                samples: (0..400u64).map(|i| (u8::from(i % 2 == 1), 1_000)).collect(),
            },
        );
        let e = null_from_sessions(&[ok.clone(), few]).unwrap_err();
        assert!(e.contains("n1") && e.contains("minimum"), "{e}");
        // Raw statistic failed → named.
        ok.raw_t = 9.0;
        let e = null_from_sessions(&[ok]).unwrap_err();
        assert!(e.contains("n0") && e.contains("raw"), "{e}");
        assert!(null_from_sessions(&[]).is_err());
    }

    #[test]
    fn controls_downgrade_to_inconclusive_and_session_folds_worst() {
        assert_eq!(
            apply_controls(Verdict::Pass, Verdict::Pass, Verdict::Fail),
            Verdict::Pass
        );
        assert_eq!(
            apply_controls(Verdict::Fail, Verdict::Pass, Verdict::Fail),
            Verdict::Fail
        );
        // Flat control failed → environment too noisy → INCONCLUSIVE regardless.
        assert_eq!(
            apply_controls(Verdict::Pass, Verdict::Fail, Verdict::Fail),
            Verdict::Inconclusive
        );
        // Leaky control did not fail → harness lacks power → INCONCLUSIVE regardless.
        assert_eq!(
            apply_controls(Verdict::Fail, Verdict::Pass, Verdict::Pass),
            Verdict::Inconclusive
        );
        assert_eq!(Verdict::Pass.worse(Verdict::Fail), Verdict::Fail);
        assert_eq!(
            Verdict::Fail.worse(Verdict::Inconclusive),
            Verdict::Inconclusive
        );
        assert_eq!(Verdict::Pass.worse(Verdict::Pass), Verdict::Pass);
    }

    #[test]
    fn csv_round_trips_the_samples() {
        let raw = RawSamples {
            samples: vec![(0, 10), (1, 20), (0, 30)],
        };
        let csv = to_csv(&raw);
        assert_eq!(csv, "class,ns\n0,10\n1,20\n0,30\n");
    }

    #[test]
    fn verdict_serialises_as_the_three_words() {
        assert_eq!(serde_json::to_string(&Verdict::Pass).unwrap(), "\"PASS\"");
        assert_eq!(serde_json::to_string(&Verdict::Fail).unwrap(), "\"FAIL\"");
        assert_eq!(
            serde_json::to_string(&Verdict::Inconclusive).unwrap(),
            "\"INCONCLUSIVE\""
        );
    }
}
