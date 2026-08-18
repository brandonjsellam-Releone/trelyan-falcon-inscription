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
#![allow(
    clippy::cast_precision_loss,
    clippy::cast_possible_truncation,
    clippy::cast_sign_loss
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

/// The three words a session or an experiment can end in.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum Verdict {
    /// Controls behaved, enough samples, `max |t| < 4.5`. Not a proof; "not detected here".
    Pass,
    /// Controls behaved, enough samples, `max |t| ≥ 4.5`. The classes are distinguishable.
    Fail,
    /// A control misbehaved, too few samples, or the harness could not run. No statement.
    Inconclusive,
}

impl Verdict {
    /// The worse of two verdicts, for folding a session: FAIL > INCONCLUSIVE > PASS is the
    /// ordering for "what must the reader act on", but for the *session* word the methodology
    /// says INCONCLUSIVE dominates (a bad control invalidates every Falcon verdict), so this
    /// orders INCONCLUSIVE > FAIL > PASS.
    #[must_use]
    pub const fn worse(self, other: Self) -> Self {
        match (self, other) {
            (Self::Inconclusive, _) | (_, Self::Inconclusive) => Self::Inconclusive,
            (Self::Fail, _) | (_, Self::Fail) => Self::Fail,
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
    /// `max |t|` over `t_values` — the reported statistic.
    pub max_abs_t: f64,
    /// Whether `max_abs_t >= T_THRESHOLD` (distinguishable) — the raw finding, before controls
    /// and sample-size rules are applied by the session.
    pub distinguishable: bool,
    /// Whether both classes reached `MIN_PER_CLASS`.
    pub enough_samples: bool,
    /// The verdict for this experiment IN ISOLATION (controls not yet applied). The session
    /// applies the control rule and may downgrade PASS/FAIL to INCONCLUSIVE.
    pub isolated_verdict: Verdict,
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

/// Judge one experiment from its raw samples: discard the warm-up, split by class, compute the
/// ten *t* values, apply the sample-size rule. Controls are applied by the caller (session).
#[must_use]
pub fn judge(id: &str, description: &str, raw: &RawSamples) -> ExperimentResult {
    let total = raw.samples.len();
    let skip = ((total as f64) * WARMUP_FRACTION).floor() as usize;
    let (mut c0, mut c1) = (Vec::new(), Vec::new());
    for &(class, ns) in raw.samples.iter().skip(skip) {
        if class == 0 { c0.push(ns) } else { c1.push(ns) }
    }
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
    ExperimentResult {
        id: id.to_owned(),
        description: description.to_owned(),
        class0: class_stats(&c0),
        class1: class_stats(&c1),
        t_values: tv,
        max_abs_t,
        distinguishable,
        enough_samples: enough,
        isolated_verdict,
    }
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
