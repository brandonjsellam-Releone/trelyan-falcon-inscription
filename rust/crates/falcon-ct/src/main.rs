//! `falcon-ct` — run the pre-registered constant-time evidence session against the pinned
//! Falcon-1024 det1024 signer and write `report.json` + one raw CSV per experiment.
//!
//! Usage:
//!   falcon-ct [--samples N] [--null-sessions N] [--out DIR] [--json-only]
//!            [--null-design rr|ss]  (--aa-repeats / --rr-sessions parse but are REFUSED: METHODOLOGY-v4 2a is the next increment)
//!
//! `--null-design` selects the environment-gate null: **`rr` (default) is the v3 rule in force** —
//! fresh pool A vs fresh pool B — and `ss` is v4's true-zero construction (ONE pool, both classes,
//! independent index draws; `METHODOLOGY-v4.md` §1). `--aa-repeats` and `--rr-sessions` configure
//! v4's matched crop references and are REFUSED under `rr`, where they would be ignored.
//!
//! `--samples N` is measurements PER EXPERIMENT (both classes together; default 4800, i.e. ~2350
//! per class, above the 2 000 minimum; below 4600 is refused). `--out DIR` (default
//! `evidence/ct/out`) receives
//! `report.json` and `raw-<experiment>.csv`. The exit code is 0 whenever the session ran to
//! completion — including on FAIL or INCONCLUSIVE — because this is an observation, not a gate
//! (METHODOLOGY §0). Non-zero only if the harness itself could not run (I/O, keygen error).
//!
//! Everything below is glue around `falcon_ct::{measure, judge, apply_controls}` and the ffi.
//! No `unsafe` here (the ffi crate holds it); no crypto here (the vendored C holds it).

#![forbid(unsafe_code)]

use std::{fs, path::PathBuf};

use anyhow::{Context, Result, anyhow};
use falcon_ct::{
    ExperimentResult, RawSamples, Verdict, apply_controls, judge, judge_raw_only, judge_v2,
    measure, null_from_sessions, to_csv,
};
use serde::Serialize;
use trelyan_pq_ffi::{
    PRIVKEY_SIZE, PUBKEY_SIZE, SIG_COMPRESSED_MAXSIZE, Shake256Context, keygen, prng_extract,
    prng_from_seed, prng_from_system, sign_compressed, verify_compressed,
};

/// 4 800 → ≈ 2 352 per class after the 2 % warm-up: comfortably above the 2 000 minimum even
/// with the random class split's ± ~35 swing (4 200 was too tight — see `parse_opts`), and short
/// enough that a v3 session (20 real-operation null sessions + experiments) is ≈ 20 min locally.
const DEFAULT_SAMPLES: usize = 4_800;
const KEY_POOL: usize = 32;
const MSG_LEN: usize = 64;
/// Number of fixed-key pairs for `sign-kk` (three pairs; METHODOLOGY-v3 §1 combination rule).
const KK_PAIRS: usize = 3;
/// Messages rotated through in `sign-kk`, identically for both classes (v3 §2).
const KK_MESSAGES: usize = 4;
/// Real-operation null sessions (v3 §1: N ≥ 20).
const DEFAULT_NULL_SESSIONS: usize = 20;
const METHODOLOGY: &str = "evidence/ct/METHODOLOGY-v3.md (2026-08-18) + METHODOLOGY-v3.1-POWER.md \
    (sample size and reported power; NO decision rule changed); v2 = METHODOLOGY-v2.md; \
    v1 = METHODOLOGY.md";
const READING_GUIDE: &str = "v3. Primary: raw Welch |t| >= 4.5 => FAIL (a LOCATION difference). \
    Secondary: crop statistic vs an empirical null of N pool-vs-pool signing sessions of the \
    REAL operation; SHAPE = raw |t| < 4.5 but crop stat beyond every null session (shape/scale, \
    never PASS, never FAIL). sign-kk combination (pre-registered): FAIL if any pair FAILs; SHAPE \
    only if >= 2 of 3 pairs SHAPE; else PASS. INCONCLUSIVE = a control or the null misbehaved, \
    or too few samples; never PASS. Descriptive stats (dmean, CI, p) are NOT decision criteria. \
    Gated: sign-kk (combined) and sign-rr. Screening/informational: sign-key, sign-msg, \
    verify-ctrl, keygen, and sign-aa. CONTROL (v3.1): sign-aa signs with the SAME keypair in both \
    arms, laid out exactly as a sign-kk pair, so its true difference is zero by construction and \
    any signal is harness/layout/environment, never a key effect. Only a PASS on sign-aa lets the \
    key verdicts be read — FAIL, SHAPE or INCONCLUSIVE there forces every key verdict to \
    INCONCLUSIVE (see controls.aa_verdict / controls.aa_ok). It can only downgrade, never lift. \
    Read its dmean and CI whatever its verdict: its gate fires only at |t| >= 4.5. POWER (v3.1): each experiment reports se_ns and mde80_ns/mde90_ns = \
    (4.5 + z_power) * SE — the smallest true mean difference it would have flagged at that \
    probability. A PASS therefore reads 'nothing at or above mde90_ns was detected', NOT 'the \
    means are equal' and NOT 'no leak exists'; smaller effects keep a smaller, non-zero \
    detection probability. mde is descriptive and decides nothing. Not a proof; machine- and \
    build-specific. CONTROLS (interim ruling 2026-08-20, from the six-seat review of the v4.1 \
    validation session): the SYNTHETIC controls (control-flat, control-leaky) are judged on the \
    raw |t| >= 4.5 line ONLY — their crop diagnostic does not run (crop_empirical_p is null), \
    because a synthetic loop and the real signing operation do not share a crop null and \
    judging one against the other is a mismatched reference. Their crop_max_abs_t remains as a \
    descriptive number that decides nothing.";

#[derive(Serialize)]
struct Environment {
    os: &'static str,
    arch: &'static str,
    family: &'static str,
    available_parallelism: usize,
    rustc_version: &'static str,
    profile: &'static str,
    pinned_falcon_commit: &'static str,
    ffi_flags: &'static str,
    timer: &'static str,
}

impl Environment {
    fn current() -> Self {
        Self {
            os: std::env::consts::OS,
            arch: std::env::consts::ARCH,
            family: std::env::consts::FAMILY,
            available_parallelism: std::thread::available_parallelism()
                .map_or(0, std::num::NonZero::get),
            rustc_version: option_env!("FALCON_CT_RUSTC")
                .unwrap_or("unrecorded (set FALCON_CT_RUSTC at build)"),
            profile: if cfg!(debug_assertions) {
                "debug"
            } else {
                "release"
            },
            pinned_falcon_commit: "ce15e75bceb372867daf6b8e81918ab6978686eb",
            ffi_flags: "-O3 -DFALCON_UNALIGNED=0 (-fno-strict-aliasing on non-MSVC); \
                        config.h FALCON_FPEMU=1",
            timer: "std::time::Instant (monotonic)",
        }
    }
}

#[derive(Serialize)]
struct Report {
    methodology: &'static str,
    schema_version: u32,
    samples_per_experiment: usize,
    key_pool: usize,
    message_len: usize,
    environment: Environment,
    controls: Controls,
    experiments: Vec<Judged>,
    /// The worst gated Falcon-experiment verdict after controls (v2 §1–§2) — or, when
    /// [`Self::validation_only`] is set, INCONCLUSIVE regardless of what was measured.
    session_verdict: Verdict,
    /// `true` under `--null-design ss`: this session may **not** issue a Falcon verdict.
    ///
    /// `ss` narrows the null without §2a's compensating matched crop references, so it makes the
    /// fixed `|t| < 4.5` gate easier to clear. Such a session is measurement only: every
    /// experiment is ungated, `session_verdict` is INCONCLUSIVE, and the reading is
    /// `controls.null_raw_t_sd` (`METHODOLOGY-v4.md` §2).
    validation_only: bool,
    reading_guide: &'static str,
}

#[derive(Serialize)]
struct Controls {
    flat: ExperimentResult,
    leaky: ExperimentResult,
    /// flat PASSED and leaky FAILED — the precondition for any Falcon verdict.
    #[serde(rename = "controls_ok")]
    ok: bool,
    /// The crop statistics of the N null sessions — the empirical null — or empty if a null
    /// session failed the raw statistic (environment too noisy). v3 replaced v2's synthetic flat
    /// loop with N pool-vs-pool sessions of the REAL signing operation; the flat loop survives
    /// only as an informational control.
    null_sessions: usize,
    null_crop_stats: Vec<f64>,
    null_ok: bool,
    /// v4: which construction played the environment gate — `"rr"` (v3, default) or `"ss"`.
    /// In the artifact because the rules a session ran under must be readable from the artifact.
    null_design: NullDesign,
    /// v4 (METHODOLOGY-v4 §2): the sample sd of the null sessions' raw *t* values. **1.000 under
    /// a true null.** v3.1 measured 1.742 under `rr`, which is the defect §0 of that file
    /// describes; it is the single number the v4 validation run exists to read.
    ///
    /// **`null` when fewer than two sessions were usable** — not `0.0`. A false zero would land
    /// §2's only decision in its "≤ 1.25 → proceed" band on no data.
    null_raw_t_sd: Option<f64>,
    /// Who applies §2's `1.25 / 1.60` lines — always `"human"`.
    ///
    /// The harness computes `null_raw_t_sd` and prints it with its pre-registered band, and **no
    /// verdict anywhere reads it**. Recorded in the artifact so `null_ok: true` can never be
    /// mistaken for "§2 was satisfied". The protection that *is* mechanical is
    /// [`Report::validation_only`].
    null_raw_t_sd_gate: &'static str,
    /// A6: **why** the null was accepted or rejected — `"OK"`, or the reason naming which
    /// sessions failed which precondition. It previously existed only as a console line, so a
    /// reader holding `report.json` alone could see `null_ok: false` and had no way to tell a
    /// too-noisy environment from sessions that never ran.
    null_reason: String,
    /// v2: whether the harness pinned itself to one CPU. std has no affinity API and the
    /// constitution allows no new dependency for it here, so this is `false` and stated.
    affinity_pinned: bool,
    /// v3.1: the full judged result of **every** null session, not just its crop statistic.
    ///
    /// The null costs about two thirds of a session's wall-clock and previously survived as 20
    /// bare floats: an auditor could not check the *n* per class, the means, the raw *t*, or the
    /// ten *t* values that produced each one, and the raw samples were dropped. The summaries are
    /// small (no raw samples ride in [`ExperimentResult`]) and make the most expensive part of
    /// the session auditable. Serialising them costs nothing in the timed region — it happens
    /// after the last measurement.
    null_detail: Vec<ExperimentResult>,
    /// v3.1 A/A layout control (§2a): its verdict, and whether it let the session speak.
    ///
    /// `None` until the control has run — the `Controls` block is built before the experiments.
    /// Written here because the downgrade was otherwise **invisible in the artifact**: the gate is
    /// applied through a local `flat_for_rule` inside `falcon_experiments`, so a failed A/A
    /// control left `controls_ok: true` and `flat: PASS` in `report.json` while every key verdict
    /// read INCONCLUSIVE, with the `sign-aa` row as the only trace of why. A reader checking the
    /// controls block alone would have found the downgrade unexplained.
    #[serde(skip_serializing_if = "Option::is_none")]
    aa_verdict: Option<Verdict>,
    /// `false` when the A/A control forced every key verdict to INCONCLUSIVE.
    #[serde(skip_serializing_if = "Option::is_none")]
    aa_ok: Option<bool>,
    /// v4.1 §2: the `null-rr` reference bank for `sign-rr` (full judged summaries), present
    /// only under `--null-design ss`. Raw samples ARE written (`raw-null-rr-ref-<k>.csv`).
    #[serde(skip_serializing_if = "Vec::is_empty")]
    rr_detail: Vec<ExperimentResult>,
    /// S4 (review): the REQUESTED bank sizes, so the artifact shows the operator's choice next
    /// to what completed. Banks are all-or-nothing, so a mismatch cannot occur silently — but
    /// the exchangeable rank floor is 1/(N+1), which makes N itself part of the decision rule,
    /// and it must be readable from the artifact.
    #[serde(skip_serializing_if = "Option::is_none")]
    aa_repeats_requested: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    rr_sessions_requested: Option<usize>,
}

#[derive(Serialize)]
struct Judged {
    #[serde(flatten)]
    result: ExperimentResult,
    /// Verdict after the control rule.
    verdict: Verdict,
    /// Whether this experiment participates in the session verdict (keygen and verify do not).
    gated: bool,
    /// `sign-rr` only, `--null-design ss` only: the v4.1 §2 three-state raw reading
    /// (`clears` / `inconclusive_pool_offset` / `fail_beyond_reference`) against the matched
    /// `null-rr` bank. **Reported, not enforced** in this increment — `ss` sessions are
    /// validation-only and issue no verdicts, and under `rr` the v3 rule stands untouched.
    #[serde(skip_serializing_if = "Option::is_none")]
    rr_raw_state: Option<&'static str>,
}

/// Which construction plays the **environment gate** null (METHODOLOGY-v4 §1).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
enum NullDesign {
    /// v3: fresh pool A vs fresh pool B. The rules in force by default. Its *t* is inflated by
    /// `1 + (σ_key/σ_total)²·(n/32)` because two finite pools do not share a mean — the defect
    /// `METHODOLOGY-v4.md` §0 describes. Kept as the default so no session changes its rules
    /// without saying so on the command line.
    Rr,
    /// v4: ONE pool, both classes, independent index draws. True zero by construction
    /// (conditional on the pool), mixture shape preserved.
    Ss,
}

struct Opts {
    samples: usize,
    out: PathBuf,
    json_only: bool,
    null_sessions: usize,
    /// `--null-design rr|ss`. Default `rr` = v3 rules; `ss` selects the v4 matched-null design.
    null_design: NullDesign,
    /// `--aa-repeats N` (v4 only): how many A/A sessions run; the first is the downgrade-only
    /// control exactly as today, and under `ss` all N crop statistics are the reference for
    /// `sign-kk-*`. **`None` = not supplied** — the distinction matters, because
    /// `--null-design rr --aa-repeats 1` must be refused as a category error even though the
    /// value happens to equal the default (checking the value instead of the presence let that
    /// through).
    aa_repeats: Option<usize>,
    /// `--rr-sessions N` (v4 only): how many pool-vs-pool sessions run as `sign-rr`'s crop
    /// reference when they no longer gate anything. Default = `--null-sessions`.
    rr_sessions: Option<usize>,
}

fn parse_opts() -> Result<Opts> {
    let mut o = Opts {
        samples: DEFAULT_SAMPLES,
        out: PathBuf::from("evidence/ct/out"),
        json_only: false,
        null_sessions: DEFAULT_NULL_SESSIONS,
        null_design: NullDesign::Rr,
        aa_repeats: None,
        rr_sessions: None,
    };
    let args: Vec<String> = std::env::args().skip(1).collect();
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--samples" => {
                i += 1;
                o.samples = args
                    .get(i)
                    .context("--samples needs a number")?
                    .parse()
                    .context("--samples must be a positive integer")?;
            }
            "--out" => {
                i += 1;
                o.out = PathBuf::from(args.get(i).context("--out needs a path")?);
            }
            "--json-only" => o.json_only = true,
            "--null-sessions" => {
                i += 1;
                o.null_sessions = args
                    .get(i)
                    .context("--null-sessions needs a number")?
                    .parse()
                    .context("--null-sessions must be a positive integer")?;
            }
            "--null-design" => {
                i += 1;
                o.null_design = match args.get(i).map(String::as_str) {
                    Some("rr") => NullDesign::Rr,
                    Some("ss") => NullDesign::Ss,
                    other => {
                        return Err(anyhow!(
                            "--null-design must be rr (v3, default) or ss (v4); got {other:?}"
                        ));
                    }
                };
            }
            "--aa-repeats" => {
                i += 1;
                o.aa_repeats = Some(
                    args.get(i)
                        .context("--aa-repeats needs a number")?
                        .parse()
                        .context("--aa-repeats must be a positive integer")?,
                );
            }
            "--rr-sessions" => {
                i += 1;
                o.rr_sessions = Some(
                    args.get(i)
                        .context("--rr-sessions needs a number")?
                        .parse()
                        .context("--rr-sessions must be a positive integer")?,
                );
            }
            "-h" | "--help" => {
                println!(
                    "falcon-ct [--samples N] [--null-sessions N] [--out DIR] [--json-only] \
                     [--null-design rr|ss]  (--aa-repeats / --rr-sessions parse but are REFUSED: METHODOLOGY-v4 2a is the next increment)"
                );
                std::process::exit(0);
            }
            other => return Err(anyhow!("unknown option {other}")),
        }
        i += 1;
    }
    check_v4_options(&o)?;
    // 2 000 per class after the 2 % warm-up needs ≈ 4 082 measurements at an EXACT half split;
    // the class bit is random per measurement (binomial sd ≈ 32 at this size), so anything
    // close to that floor produces INCONCLUSIVE sessions by chance alone (seen 2026-08-18 at
    // 4 200: one experiment split 1934/2182). Refuse under-powered sessions up front.
    if o.samples < 4_600 {
        return Err(anyhow!(
            "--samples must be at least 4600 so both classes clear the 2 000 minimum after warm-up with a comfortable margin (METHODOLOGY-v3 §1); got {}",
            o.samples
        ));
    }
    if o.null_sessions < 20 {
        return Err(anyhow!(
            "--null-sessions must be at least 20 (METHODOLOGY-v2 §1)"
        ));
    }
    Ok(o)
}

/// Refuse v4 options that are parsed but not honoured, rather than letting an operator believe a
/// knob is turned.
///
/// Two separate refusals, because they mean different things:
/// * under `--null-design rr` these options do not apply at all — the v3 rules have one null and
///   one A/A control, so setting them would be a category error;
/// * under `ss` they *will* apply, but the matched crop references of `METHODOLOGY-v4.md` §2a
///   (repeated `sign-aa` for `sign-kk-*`, `null-rr` for `sign-rr`) are **not wired yet** — this
///   increment adds the `null-ss` construction and `null_raw_t_sd` only. Accepting `--aa-repeats
///   20` and then running a single A/A session is exactly the inert knob this project's register
///   is full of, so it is an error until the wiring lands.
///
/// # Errors
/// Naming which option is unhonoured and why.
fn check_v4_options(o: &Opts) -> Result<()> {
    // Zero of either is a request for a reference built from nothing.
    if o.aa_repeats == Some(0) || o.rr_sessions == Some(0) {
        return Err(anyhow!(
            "--aa-repeats and --rr-sessions must be at least 1 when supplied; zero would ask for \
             a crop reference built from no sessions"
        ));
    }
    // PRESENCE, not value: `--null-design rr --aa-repeats 1` is still a category error, and
    // testing the value let it through because 1 is the default.
    if o.null_design == NullDesign::Rr && (o.aa_repeats.is_some() || o.rr_sessions.is_some()) {
        return Err(anyhow!(
            "--aa-repeats and --rr-sessions only apply to --null-design ss; under rr (the v3 \
             rules) they would be silently ignored, which is worse than an error"
        ));
    }
    // S2 (review): the gating A/A control is a CONDITIONED draw and is excluded from the
    // sign-kk bank, so the bank is exactly the repeats — and a one-member reference bank is a
    // rank test against a single value. ss therefore requires an explicit bank size of >= 2.
    if o.null_design == NullDesign::Ss && o.aa_repeats.is_none_or(|n| n < 2) {
        return Err(anyhow!(
            "--null-design ss requires --aa-repeats N with N >= 2: the sign-kk crop reference \
             bank is built from the repeats ONLY (the gating control is a conditioned draw and \
             is excluded), and a bank needs at least two unconditioned members. The v4 \
             validation session uses --aa-repeats 20 (METHODOLOGY-v4 §2)."
        ));
    }
    Ok(())
}

/// The crop-reference banks each experiment family is judged against (METHODOLOGY-v4.1 §2a:
/// **match each reference to the class structure of what it judges**).
///
/// Under `rr` (v3, the default) every family points at the gate null — byte-identical judging to
/// v3, which a test asserts. Under `ss`: `sign-kk-*` is judged against the repeated-`sign-aa`
/// bank (point-mass A/A, true zero), `sign-rr` against the `null-rr` bank (its own
/// construction), and screening/informational lines against the gate null, as before.
struct CropRefs {
    /// The environment-gate null's crop statistics (v3: `null-rr`; v4: `null-ss`).
    gate: Vec<f64>,
    /// `sign-kk-*` crop reference. == `gate` under `rr`.
    kk: Vec<f64>,
    /// `sign-rr` crop reference. == `gate` under `rr`.
    rr_crop: Vec<f64>,
    /// `sign-rr` RAW reference bank (|t| of each `null-rr` reference session), for the v4.1 §2
    /// three-state raw rule. `None` under `rr`, where the fixed 4.5 rule stands alone.
    rr_raw: Option<Vec<f64>>,
}

/// v4.1 §2: the three-state raw reading for `sign-rr` under the matched-reference design.
///
/// A fixed 4.5 threshold is invalid for `sign-rr` — random finite-pool offsets are part of its
/// null and grow with the sample count — so the raw statistic is read against the matched
/// `null-rr` bank. **The middle state is the point**: a value beyond 4.5 but inside the
/// reference bank's range may not PASS (nothing that failed the old rule may pass the new one)
/// and may not FAIL (the reference says pool offsets alone reach there). Strict `>` against
/// every reference; ties do not fire, same as the crop rule.
///
/// In this increment the state is **reported, not enforced**: `ss` sessions are validation-only
/// and issue no verdicts, and under `rr` the v3 rule stands untouched. Pure so it can be tested
/// against its truth table without timing anything.
fn rr_raw_state(raw_abs_t: f64, reference_raw: &[f64]) -> &'static str {
    // A statistic that is not a number, or a bank with no members, supports NO statement about
    // references. The review caught the earlier version labelling |t| ≥ 4.5 against an EMPTY
    // bank as `fail_beyond_reference` — asserting "beyond every reference" with zero references
    // — and NaN would have fallen into the same arm because every IEEE comparison on it is
    // false. Banks are all-or-nothing upstream, so these states indicate a harness fault, and
    // they must read as one.
    if raw_abs_t.is_nan() {
        return "invalid_statistic";
    }
    if reference_raw.is_empty() {
        return "no_reference_bank";
    }
    if raw_abs_t < falcon_ct::T_THRESHOLD {
        "clears"
    } else if reference_raw.iter().any(|&r| raw_abs_t <= r) {
        // Beyond the fixed line, but not beyond every matched reference: a pool offset of this
        // size occurs under the no-leak null. Cannot PASS; cannot FAIL.
        "inconclusive_pool_offset"
    } else {
        "fail_beyond_reference"
    }
}

/// A class-bit source over the audited SHAKE PRNG: one byte per bit, no buffering games.
struct ClassBits(Shake256Context);
impl ClassBits {
    fn next(&mut self) -> bool {
        let mut b = [0u8; 1];
        prng_extract(&mut self.0, &mut b);
        b[0] & 1 == 1
    }
}

fn random_bytes(rng: &mut Shake256Context, n: usize) -> Vec<u8> {
    let mut v = vec![0u8; n];
    prng_extract(rng, &mut v);
    v
}

#[derive(Clone)]
struct Keypair {
    sk: [u8; PRIVKEY_SIZE],
    pk: [u8; PUBKEY_SIZE],
}

fn gen_keypair(rng: &mut Shake256Context) -> Result<Keypair> {
    let mut sk = [0u8; PRIVKEY_SIZE];
    let mut pk = [0u8; PUBKEY_SIZE];
    keygen(rng, &mut sk, &mut pk).map_err(|c| anyhow!("keygen failed (reference code {c})"))?;
    Ok(Keypair { sk, pk })
}

/// Everything the timed closures index into — prepared OUTSIDE any timed region.
struct Fixtures {
    k0: Keypair,
    pool: Vec<Keypair>,
    /// v2: a second, independent pool for `sign-rr`.
    pool_b: Vec<Keypair>,
    /// v2: fixed key pairs for `sign-kk`.
    kk: Vec<(Keypair, Keypair)>,
    /// v3.1 A/A control: **the same keypair twice**, in a tuple laid out exactly like a `kk`
    /// pair. Class 0 reads the copy at tuple offset 0, class 1 the copy at offset
    /// `size_of::<Keypair>()` — the identical difference in address and cache alignment that
    /// class 0 and class 1 see in `sign-kk`, but with byte-identical key material. Its true mean
    /// difference is therefore **exactly zero by construction**, so any *t* it produces is
    /// harness, layout or environment, and never a key effect.
    ///
    /// It exists because the committed data says it must: over the v2, v3 and v3b sessions,
    /// **8 of 9 independent `sign-kk` pairs put class 1 slower, mean +13.9 µs** — a sign pattern
    /// that follows the *arm* rather than any particular key (binomial *p* ≈ 0.04), while
    /// `sign-rr`, whose two arms live in separate allocations, shows the opposite sign. At
    /// 82 000 measurements the CI on that offset is ±10 µs, so the session would have measured
    /// it precisely and had no control that could say whether it came from the keys.
    aa: (Keypair, Keypair),
    m0: Vec<u8>,
    msgs: Vec<Vec<u8>>,
    s0: Vec<u8>,
    pool_sigs: Vec<Vec<u8>>,
    /// Two `samples`-long streams of pool indices (one per random-class experiment).
    idx_stream: Vec<usize>,
    seeds: Vec<[u8; 32]>,
    fixed_seed: [u8; 32],
}

impl Fixtures {
    fn prepare(rng: &mut Shake256Context, samples: usize) -> Result<Self> {
        let k0 = gen_keypair(rng)?;
        let mut pool = Vec::with_capacity(KEY_POOL);
        for _ in 0..KEY_POOL {
            pool.push(gen_keypair(rng)?);
        }
        let mut pool_b = Vec::with_capacity(KEY_POOL);
        for _ in 0..KEY_POOL {
            pool_b.push(gen_keypair(rng)?);
        }
        let mut kk = Vec::with_capacity(KK_PAIRS);
        for _ in 0..KK_PAIRS {
            kk.push((gen_keypair(rng)?, gen_keypair(rng)?));
        }
        // Same keypair in both slots — see the field's doc comment. Cloned rather than
        // referenced twice so the two arms read DIFFERENT addresses holding IDENTICAL bytes,
        // which is exactly the asymmetry `sign-kk` has and the property being controlled for.
        let aa_key = gen_keypair(rng)?;
        let aa = (aa_key.clone(), aa_key);
        let m0 = random_bytes(rng, MSG_LEN);
        let msgs = (0..KEY_POOL).map(|_| random_bytes(rng, MSG_LEN)).collect();
        let mut sig_buf = [0u8; SIG_COMPRESSED_MAXSIZE];
        let n0 =
            sign_compressed(&k0.sk, &m0, &mut sig_buf).map_err(|c| anyhow!("sign failed ({c})"))?;
        let s0 = sig_buf[..n0].to_vec();
        let mut pool_sigs = Vec::with_capacity(KEY_POOL);
        for kp in &pool {
            let n = sign_compressed(&kp.sk, &m0, &mut sig_buf)
                .map_err(|c| anyhow!("sign failed ({c})"))?;
            pool_sigs.push(sig_buf[..n].to_vec());
        }
        let idx_stream = random_bytes(rng, samples * 2)
            .into_iter()
            .map(|b| usize::from(b) % KEY_POOL)
            .collect();
        let seeds = (0..samples)
            .map(|_| {
                let mut s = [0u8; 32];
                prng_extract(rng, &mut s);
                s
            })
            .collect();
        Ok(Self {
            k0,
            pool,
            pool_b,
            kk,
            aa,
            m0,
            msgs,
            s0,
            pool_sigs,
            idx_stream,
            seeds,
            fixed_seed: [0x5Au8; 32],
        })
    }
}

fn run_control_flat(samples: usize, bits: &mut ClassBits) -> RawSamples {
    measure(
        samples,
        || bits.next(),
        |class| {
            let mut acc = 0u64;
            for i in 0..50_000u64 {
                acc = acc.wrapping_add(std::hint::black_box(i));
            }
            std::hint::black_box((acc, class));
        },
    )
}

fn run_control_leaky(samples: usize, bits: &mut ClassBits) -> RawSamples {
    measure(
        samples,
        || bits.next(),
        |class| {
            let iters = if class { 60_000u64 } else { 40_000u64 };
            let mut acc = 0u64;
            for i in 0..iters {
                acc = acc.wrapping_add(std::hint::black_box(i));
            }
            std::hint::black_box(acc);
        },
    )
}

/// sign-key: fixed message; class 0 = K0, class 1 = a pool key by index stream.
fn run_sign_key(f: &Fixtures, samples: usize, bits: &mut ClassBits) -> RawSamples {
    let mut i = 0usize;
    let mut out = [0u8; SIG_COMPRESSED_MAXSIZE];
    measure(
        samples,
        || bits.next(),
        |class| {
            let sk = if class {
                &f.pool[f.idx_stream[i]].sk
            } else {
                &f.k0.sk
            };
            i += 1;
            let _ = std::hint::black_box(sign_compressed(sk, &f.m0, &mut out));
        },
    )
}

/// v3 sign-kk: class 0 = key `K_a`, class 1 = key `K_b` (pair `pair`); the message rotates
/// through four fixed messages in the SAME order for both classes (index = measurement mod 4),
/// so the comparison is key-only and message-balanced (METHODOLOGY-v3 §2).
fn run_sign_kk(f: &Fixtures, pair: usize, samples: usize, bits: &mut ClassBits) -> RawSamples {
    let (ka, kb) = &f.kk[pair];
    let mut out = [0u8; SIG_COMPRESSED_MAXSIZE];
    let mut i = 0usize;
    measure(
        samples,
        || bits.next(),
        |class| {
            let sk = if class { &kb.sk } else { &ka.sk };
            let m: &[u8] = &f.msgs[i % KK_MESSAGES];
            i += 1;
            let _ = std::hint::black_box(sign_compressed(sk, m, &mut out));
        },
    )
}

/// v3.1 `sign-aa`: the A/A layout control. Byte-for-byte identical to [`run_sign_kk`] except
/// that both arms sign with copies of the **same** keypair, so the true difference is zero.
/// A FAIL here means the harness distinguishes its own arms and no key verdict in the session
/// may be believed (it can only downgrade a verdict, never lift one).
fn run_sign_aa(f: &Fixtures, samples: usize, bits: &mut ClassBits) -> RawSamples {
    run_sign_aa_pair(&f.aa, &f.msgs, samples, bits)
}

/// One A/A session over an explicit pair — the shared body of the gating control (pair =
/// `Fixtures::aa`) and the v4.1 §1 repeated-`sign-aa` reference bank (fresh pair per repeat,
/// each "matched in every respect other than key identity": same tuple layout, same message
/// rotation, same measurement count).
fn run_sign_aa_pair(
    pair: &(Keypair, Keypair),
    msgs: &[Vec<u8>],
    samples: usize,
    bits: &mut ClassBits,
) -> RawSamples {
    let (ka, kb) = pair;
    let mut out = [0u8; SIG_COMPRESSED_MAXSIZE];
    let mut i = 0usize;
    measure(
        samples,
        || bits.next(),
        |class| {
            let sk = if class { &kb.sk } else { &ka.sk };
            let m: &[u8] = &msgs[i % KK_MESSAGES];
            i += 1;
            let _ = std::hint::black_box(sign_compressed(sk, m, &mut out));
        },
    )
}

/// v2 sign-rr: fixed message M0; class 0 = key from pool A, class 1 = key from pool B.
fn run_sign_rr(f: &Fixtures, samples: usize, bits: &mut ClassBits) -> RawSamples {
    let mut i = 0usize;
    let mut out = [0u8; SIG_COMPRESSED_MAXSIZE];
    measure(
        samples,
        || bits.next(),
        |class| {
            let j = f.idx_stream[i % f.idx_stream.len()];
            let sk = if class {
                &f.pool_b[j].sk
            } else {
                &f.pool[j].sk
            };
            i += 1;
            let _ = std::hint::black_box(sign_compressed(sk, &f.m0, &mut out));
        },
    )
}

/// sign-msg: fixed key K0; class 0 = M0, class 1 = a random message by index stream.
fn run_sign_msg(f: &Fixtures, samples: usize, bits: &mut ClassBits) -> RawSamples {
    let mut i = 0usize;
    let mut out = [0u8; SIG_COMPRESSED_MAXSIZE];
    measure(
        samples,
        || bits.next(),
        |class| {
            let m: &[u8] = if class {
                &f.msgs[f.idx_stream[samples + i]]
            } else {
                &f.m0
            };
            i += 1;
            let _ = std::hint::black_box(sign_compressed(&f.k0.sk, m, &mut out));
        },
    )
}

/// verify-ctrl: class 0 = S0 under pk0; class 1 = a pool signature under its own pk.
fn run_verify_ctrl(f: &Fixtures, samples: usize, bits: &mut ClassBits) -> RawSamples {
    let mut i = 0usize;
    measure(
        samples,
        || bits.next(),
        |class| {
            let (sig, pk): (&[u8], &[u8; PUBKEY_SIZE]) = if class {
                let j = f.idx_stream[i];
                (&f.pool_sigs[j], &f.pool[j].pk)
            } else {
                (&f.s0, &f.k0.pk)
            };
            i += 1;
            let _ = std::hint::black_box(verify_compressed(sig, pk, &f.m0));
        },
    )
}

/// keygen: class 0 = fixed seed, class 1 = fresh seed per measurement. Expected variable-time.
fn run_keygen(f: &Fixtures, samples: usize, bits: &mut ClassBits) -> RawSamples {
    let mut i = 0usize;
    let mut sk = [0u8; PRIVKEY_SIZE];
    let mut pk = [0u8; PUBKEY_SIZE];
    measure(
        samples,
        || bits.next(),
        |class| {
            let mut r = if class {
                prng_from_seed(&f.seeds[i])
            } else {
                prng_from_seed(&f.fixed_seed)
            };
            i += 1;
            let _ = std::hint::black_box(keygen(&mut r, &mut sk, &mut pk));
        },
    )
}

/// The flat-control verdict the session must be judged under, given what the A/A control did.
///
/// **Only a PASS on A/A lets the session speak.** A FAIL means the harness separates its own
/// arms in location; a SHAPE means it separates them in the crop diagnostic, which is the very
/// statistic the key experiments' secondary arm rests on; an INCONCLUSIVE means the control
/// itself could not be judged. In all three the session cannot tell an arm effect from a key
/// effect, so no key verdict may be issued.
///
/// Pure, so the rule can be tested without running a ten-minute experiment — the rule and the
/// thing that enforces it are the same line of code (this repository's standing complaint is
/// checks that cannot fail).
const fn flat_verdict_under_aa(aa: Verdict, flat: Verdict) -> Verdict {
    match aa {
        Verdict::Pass => flat,
        _ => Verdict::Inconclusive,
    }
}

/// Run and judge the v3.1 A/A layout control, and return it with the flat-control verdict the
/// rest of the session must be judged under.
///
/// Both arms sign with copies of the SAME keypair (see [`Fixtures::aa`]), so the true mean
/// difference is zero by construction and any signal is harness, layout or environment. A FAIL
/// here means the harness distinguishes its own arms, which would make every key comparison in
/// the session unreadable — so it forces them all INCONCLUSIVE. It can only **downgrade**: no
/// rule that produces a PASS is touched by it.
///
/// The downgrade is routed through the flat control's verdict, the lever [`apply_controls`]
/// already reads, so a future reader cannot find two different ways for a session to be gated.
fn run_aa_control(
    f: &Fixtures,
    samples: usize,
    bits: &mut ClassBits,
    controls: &Controls,
    log: &dyn Fn(&str),
) -> (Judged, RawSamples, Verdict) {
    log("running sign-aa (A/A layout control; true difference is zero by construction) …");
    let raw = run_sign_aa(f, samples, bits);
    let aa = judge_v2(
        "sign-aa",
        "sign_compressed: the SAME keypair in both arms, laid out exactly as a sign-kk pair \
         (class 0 at tuple offset 0, class 1 at offset size_of::<Keypair>()); identical message \
         rotation. True Δmean = 0 by construction, so any signal is harness/layout/environment, \
         never a key effect. CONTROL: a FAIL forces every key verdict INCONCLUSIVE.",
        &raw,
        &controls.null_crop_stats,
    );
    let ok = aa.isolated_verdict == Verdict::Pass;
    log(&format!(
        "sign-aa: raw t={:.2} Δmean={:+.0}ns [{:+.0},{:+.0}] → {:?}{}",
        aa.raw_t,
        aa.mean_diff_ns,
        aa.ci95_ns.0,
        aa.ci95_ns.1,
        aa.isolated_verdict,
        if ok {
            ""
        } else {
            "  — ARM BIAS: every key verdict in this session is INCONCLUSIVE"
        }
    ));
    let flat_for_rule = flat_verdict_under_aa(aa.isolated_verdict, controls.flat.isolated_verdict);
    let verdict = aa.isolated_verdict;
    (
        Judged {
            verdict,
            gated: false,
            rr_raw_state: None,
            result: aa,
        },
        raw,
        flat_for_rule,
    )
}

/// Run exactly `n` sessions through `run` — **all or nothing**.
///
/// A failed session PROPAGATES as the error, naming the tag and index; it never yields a short
/// bank. The review of this increment found the truncating version relabelled "could not
/// collect references" as statistical evidence: an empty raw bank made `rr_raw_state` say
/// `fail_beyond_reference` — *beyond every reference* — when there were no references at all.
/// A reference bank either exists at its pre-registered size or the run stops.
///
/// The counting seam is also deliberate: a reviewer of the previous increment required a test
/// proving that `--aa-repeats N` / `--rr-sessions N` change EXECUTION, not just parsing — this
/// function is where that is provable without timing anything.
fn collect_sessions<F>(
    n: usize,
    tag: &str,
    log: &dyn Fn(&str),
    mut run: F,
) -> Result<Vec<RawSamples>>
where
    F: FnMut(usize) -> Result<RawSamples>,
{
    let mut out = Vec::with_capacity(n);
    for k in 0..n {
        match run(k) {
            Ok(raw) => out.push(raw),
            Err(e) => {
                log(&format!("{tag} session {k} could not run: {e}"));
                return Err(e.context(format!(
                    "{tag} reference session {k} of {n} failed; a reference bank is \
                     all-or-nothing (a short bank silently changes the empirical rule)"
                )));
            }
        }
    }
    Ok(out)
}

/// [`CropRefs`] for the default `rr` design: every family points at the gate null, so v3
/// judging is unchanged. Pure and public-to-tests so the selection identity is asserted on the
/// PRODUCTION path, not on a hand-built copy (the review caught the earlier test doing that).
fn refs_for_rr(gate_crops: &[f64]) -> CropRefs {
    CropRefs {
        gate: gate_crops.to_vec(),
        kk: gate_crops.to_vec(),
        rr_crop: gate_crops.to_vec(),
        rr_raw: None,
    }
}

/// Build the v4.1 §2a reference banks and the [`CropRefs`] the experiments are judged against.
///
/// Under `rr` this runs NOTHING new — [`refs_for_rr`]. Under `ss` it runs the `sign-aa`
/// reference repeats and the `null-rr` reference sessions, **all-or-nothing** each
/// ([`collect_sessions`]): a failed reference session stops the run rather than shrinking a
/// bank.
///
/// **The gating A/A control is NOT a bank member.** The review's statistical finding: sessions
/// that get to use the bank are exactly those whose control passed the gate, so the control's
/// crop statistic is a *conditioned* draw — including it makes the reference anti-conservative.
/// The `sign-kk` bank is therefore built only from the unconditioned repeats, and `ss` requires
/// `--aa-repeats ≥ 2` (enforced in `check_v4_options`) so the bank never has fewer than two
/// members.
///
/// Raw retention is symmetric on the diff's own terms now: BOTH banks' raw samples are written
/// as CSVs (`raw-sign-aa-<k>.csv`, `raw-null-rr-ref-<k>.csv`) — they are the references the new
/// fields are judged against, and they are small at validation scale.
fn build_reference_banks(
    f: &Fixtures,
    opts: &Opts,
    rng: &mut Shake256Context,
    bits: &mut ClassBits,
    gate_crops: &[f64],
    log: &dyn Fn(&str),
) -> Result<ReferenceBanks> {
    if opts.null_design == NullDesign::Rr {
        return Ok(ReferenceBanks {
            refs: refs_for_rr(gate_crops),
            aa_extra: Vec::new(),
            bank_raws: Vec::new(),
            rr_detail: Vec::new(),
        });
    }
    // A/A reference bank: `check_v4_options` guarantees Some(n >= 2) under ss. Fresh keypair
    // per repeat; the ids start at 1 because sign-aa (unnumbered) is the gate control.
    let repeats = opts
        .aa_repeats
        .ok_or_else(|| anyhow!("--null-design ss requires --aa-repeats (checked at parse)"))?;
    log(&format!(
        "running {repeats} sign-aa reference repeats (v4.1 §1 crop reference bank for sign-kk) …"
    ));
    let aa_session_raws = collect_sessions(repeats, "sign-aa-ref", log, |_| {
        let pair_key = gen_keypair(rng)?;
        let pair = (pair_key.clone(), pair_key);
        Ok(run_sign_aa_pair(&pair, &f.msgs, opts.samples, bits))
    })?;
    let mut bank_raws = Vec::new();
    let mut aa_judged = Vec::new();
    for (i, raw) in aa_session_raws.into_iter().enumerate() {
        let k = i + 1;
        let r = judge_v2(
            &format!("sign-aa-{k}"),
            "v4.1 §1 A/A reference repeat: a FRESH keypair cloned into both arms, matched to \
             sign-kk in everything but key identity. Unconditioned reference bank member — \
             informational, never gated, and NOT the gating control (whose statistic is a \
             conditioned draw and is excluded from the bank).",
            &raw,
            gate_crops,
        );
        log(&format!(
            "  sign-aa-{k}: raw t={:+.2} crop={:.2}",
            r.raw_t, r.crop_max_abs_t
        ));
        bank_raws.push((format!("sign-aa-{k}"), raw));
        aa_judged.push(r);
    }
    let aa_bank: Vec<f64> = aa_judged.iter().map(|r| r.crop_max_abs_t).collect();
    // null-rr reference bank for sign-rr (raw + crop, one bank for both — v4.1 §2).
    let rr_n = opts.rr_sessions.unwrap_or(opts.null_sessions);
    log(&format!(
        "running {rr_n} null-rr reference sessions (v4.1 §2 raw+crop reference for sign-rr) …"
    ));
    let rr_session_raws = collect_sessions(rr_n, "null-rr-ref", log, |_| {
        run_null_rr(rng, opts.samples, bits)
    })?;
    let mut rr_detail = Vec::new();
    for (k, raw) in rr_session_raws.into_iter().enumerate() {
        let r = judge(
            &format!("null-rr-ref-{k}"),
            "sign_compressed: fresh pool A vs fresh pool B — sign-rr's matched reference \
             (v4.1 §2); used empirically, never against a fixed threshold",
            &raw,
        );
        log(&format!(
            "  null-rr-ref-{k}: raw t={:+.2} crop={:.2}",
            r.raw_t, r.crop_max_abs_t
        ));
        bank_raws.push((format!("null-rr-ref-{k}"), raw));
        rr_detail.push(r);
    }
    let refs = CropRefs {
        gate: gate_crops.to_vec(),
        kk: aa_bank,
        rr_crop: rr_detail.iter().map(|r| r.crop_max_abs_t).collect(),
        rr_raw: Some(rr_detail.iter().map(|r| r.raw_t.abs()).collect()),
    };
    Ok(ReferenceBanks {
        refs,
        aa_extra: aa_judged,
        bank_raws,
        rr_detail,
    })
}

/// Everything [`build_reference_banks`] produces, named so the signatures stay legible.
struct ReferenceBanks {
    refs: CropRefs,
    /// The judged A/A reference repeats (informational rows; the gating control is separate and
    /// NOT among them).
    aa_extra: Vec<ExperimentResult>,
    /// BOTH banks' raw samples, written as `raw-sign-aa-<k>.csv` / `raw-null-rr-ref-<k>.csv` —
    /// they are the references the new fields are judged against.
    bank_raws: Vec<(String, RawSamples)>,
    /// The `null-rr` reference summaries, destined for `controls.rr_detail`.
    rr_detail: Vec<ExperimentResult>,
}

/// What [`falcon_experiments`] hands back to `main`.
struct ExperimentsOutput {
    judged: Vec<Judged>,
    raws: Vec<(String, RawSamples)>,
    rr_detail: Vec<ExperimentResult>,
}

/// A screening/informational experiment runner.
type Runner = fn(&Fixtures, usize, &mut ClassBits) -> RawSamples;

/// The screening / informational lines (v1 designs, demoted in v2) — data, not control flow.
/// They keep the GATE null as their crop reference under both designs (v4.1 §3 reuse rule 3).
const fn screening_plan() -> [(&'static str, &'static str, bool, Runner); 4] {
    [
        (
            "sign-key",
            "sign_compressed: fixed message; fixed key K0 vs key drawn from a pool of 32 — v1 \
             fixed-vs-random, SCREENING only in v2 (point mass vs mixture)",
            false,
            run_sign_key,
        ),
        (
            "sign-msg",
            "sign_compressed: fixed key K0; fixed 64-byte message vs random 64-byte message — v1 \
             design, SCREENING only in v2",
            false,
            run_sign_msg,
        ),
        (
            "verify-ctrl",
            "verify_compressed: public data only; fixed (S0,pk0) vs pool (Sj,pkj) — reference \
             point, not gated",
            false,
            run_verify_ctrl,
        ),
        (
            "keygen",
            "keygen: fixed seed vs fresh seed — rejection-sampled, EXPECTED variable-time; \
             reported, not gated",
            false,
            run_keygen,
        ),
    ]
}

/// The Falcon experiments in METHODOLOGY-v2 §2 order, each judged (v2) against its matched
/// reference bank (METHODOLOGY-v4.1 §2a; under the default `rr` every bank IS the gate null,
/// so v3 judging is unchanged).
fn falcon_experiments(
    f: &Fixtures,
    opts: &Opts,
    rng: &mut Shake256Context,
    bits: &mut ClassBits,
    controls: &Controls,
    log: &dyn Fn(&str),
) -> Result<ExperimentsOutput> {
    let samples = opts.samples;
    let mut judged = Vec::new();
    let mut raws = Vec::new();

    // v3.1 A/A layout control, before anything else is judged (see `run_aa_control`).
    let (aa_judged, aa_raw, flat_for_rule) = run_aa_control(f, samples, bits, controls, log);
    judged.push(aa_judged);
    raws.push(("sign-aa".to_owned(), aa_raw));

    // v4.1 §2a reference banks (no-ops under rr).
    let mut banks = build_reference_banks(f, opts, rng, bits, &controls.null_crop_stats, log)?;
    let refs = banks.refs;
    for r in banks.aa_extra {
        judged.push(Judged {
            verdict: r.isolated_verdict,
            gated: false,
            rr_raw_state: None,
            result: r,
        });
    }
    raws.append(&mut banks.bank_raws);

    let mut push = |id: String, description: &str, gated: bool, raw: RawSamples, bank: &[f64]| {
        let r = judge_v2(&id, description, &raw, bank);
        let rr_state = if id == "sign-rr" {
            refs.rr_raw
                .as_deref()
                .map(|bank| rr_raw_state(r.raw_t.abs(), bank))
        } else {
            None
        };
        judged.push(Judged {
            verdict: apply_controls(
                r.isolated_verdict,
                flat_for_rule,
                controls.leaky.isolated_verdict,
            ),
            gated,
            rr_raw_state: rr_state,
            result: r,
        });
        raws.push((id, raw));
    };

    // ── gated (v2 §2): sign-kk × KK_PAIRS, then sign-rr ────────────────────────────────────
    for pair in 0..KK_PAIRS {
        let id = format!("sign-kk-{pair}");
        log(&format!("running {id} (gated) …"));
        let raw = run_sign_kk(f, pair, samples, bits);
        push(
            id,
            "sign_compressed: fixed key K_a vs fixed key K_b, with four fixed messages rotated \
             in the SAME order for both classes (v3 §2), so the comparison is key-only and \
             message-balanced. Gated. This describes the design, not a finding: a per-key timing \
             difference is what the experiment tests for, never what it presupposes.",
            true,
            raw,
            &refs.kk,
        );
    }
    log("running sign-rr (gated) …");
    let raw = run_sign_rr(f, samples, bits);
    push(
        "sign-rr".to_owned(),
        "sign_compressed: fixed message M0; key from pool A vs key from pool B — symmetric \
         mixture control (v2). Under --null-design ss its crop AND raw statistics are read \
         against the matched null-rr reference bank (v4.1 §2); see rr_raw_state.",
        true,
        raw,
        &refs.rr_crop,
    );

    // ── screening / informational (v1 designs, demoted in v2) ──────────────────────────────
    for (id, description, gated, run) in screening_plan() {
        log(&format!(
            "running {id}{} …",
            if gated { "" } else { " (informational)" }
        ));
        let raw = run(f, samples, bits);
        // Screening and informational lines keep the GATE null as their crop reference under
        // both designs (v4.1 §3 reuse rule 3).
        push(id.to_owned(), description, gated, raw, &refs.gate);
    }
    Ok(ExperimentsOutput {
        judged,
        raws,
        rr_detail: banks.rr_detail,
    })
}

fn write_outputs(opts: &Opts, report: &Report, raws: &[(String, RawSamples)]) -> Result<()> {
    let json = serde_json::to_string_pretty(report).context("serialising report")?;
    fs::write(opts.out.join("report.json"), &json).context("writing report.json")?;
    for (id, raw) in raws {
        fs::write(opts.out.join(format!("raw-{id}.csv")), to_csv(raw))
            .with_context(|| format!("writing raw-{id}.csv"))?;
    }
    if opts.json_only {
        println!("{json}");
        return Ok(());
    }
    println!();
    println!("falcon-ct session — {}", report.methodology);
    println!(
        "  null: {} pool-vs-pool sessions (crop-stat max {:.2}) {} | controls: flat {:?} (raw t {:.2}), leaky {:?} (raw t {:.2}) → {}",
        report.controls.null_sessions,
        report
            .controls
            .null_crop_stats
            .iter()
            .copied()
            .fold(0.0_f64, f64::max),
        if report.controls.null_ok {
            "ok"
        } else {
            "NOT OK"
        },
        report.controls.flat.isolated_verdict,
        report.controls.flat.raw_t,
        report.controls.leaky.isolated_verdict,
        report.controls.leaky.raw_t,
        if report.controls.ok { "ok" } else { "NOT OK" }
    );
    println!(
        "  power: each line's MDE90 is the smallest true Δmean that experiment would have \
         flagged at |t|>=4.5 with probability 0.90. A PASS reads 'nothing at or above MDE90 was \
         detected', never 'no difference exists'."
    );
    for j in &report.experiments {
        println!(
            "  {:<11} n={:<4}/{:<4} Δmean={:>+9.0}ns [{:>+8.0},{:>+8.0}]  raw t={:>6.2} p={:<8.2e} crop max|t|={:>6.2} p_emp={:<5.3}  {:?}{}",
            j.result.id,
            j.result.class0.n,
            j.result.class1.n,
            j.result.mean_diff_ns,
            j.result.ci95_ns.0,
            j.result.ci95_ns.1,
            j.result.raw_t,
            j.result.p_raw,
            j.result.crop_max_abs_t,
            j.result.crop_empirical_p.unwrap_or(f64::NAN),
            j.verdict,
            if j.gated { "" } else { "  (informational)" }
        );
        println!(
            "  {:<11} SE={:>8.0}ns  MDE80={:>9.0}ns  MDE90={:>9.0}ns",
            "", j.result.se_ns, j.result.mde80_ns, j.result.mde90_ns
        );
    }
    println!("  SESSION VERDICT: {:?}", report.session_verdict);
    println!("  written: {}/report.json + raw-*.csv", opts.out.display());
    Ok(())
}

/// v2 empirical null (N flat-control sessions, each must PASS on the RAW statistic) followed by
/// the two controls. Returns the `Controls` block and the two controls' raw samples.
/// One v3 null session: fresh pool A vs fresh pool B on a fixed message.
fn run_null_rr(
    rng: &mut Shake256Context,
    samples: usize,
    bits: &mut ClassBits,
) -> Result<RawSamples> {
    let mut pool_a = Vec::with_capacity(KEY_POOL);
    let mut pool_b = Vec::with_capacity(KEY_POOL);
    for _ in 0..KEY_POOL {
        pool_a.push(gen_keypair(rng)?);
        pool_b.push(gen_keypair(rng)?);
    }
    let m0 = random_bytes(rng, MSG_LEN);
    let idx: Vec<usize> = random_bytes(rng, samples)
        .into_iter()
        .map(|b| usize::from(b) % KEY_POOL)
        .collect();
    let mut i = 0usize;
    let mut out = [0u8; SIG_COMPRESSED_MAXSIZE];
    Ok(measure(
        samples,
        || bits.next(),
        |class| {
            let j = idx[i % idx.len()];
            let sk = if class { &pool_b[j].sk } else { &pool_a[j].sk };
            i += 1;
            let _ = std::hint::black_box(sign_compressed(sk, &m0, &mut out));
        },
    ))
}

/// Two independent index streams into a `pool_len`-key pool, one per class, for a `null-ss`
/// session (METHODOLOGY-v4 §1). Pure and separated from the timed region so the property that
/// matters can be tested without timing anything.
///
/// **The trap this exists to close:** if both classes used the *same* index every measurement
/// pair would sign with the same key, the mixture would collapse to a single key, and the "null"
/// would be a fixed-key A/A comparison wearing a pool's name. The two streams are drawn from
/// disjoint halves of one random byte buffer, so they are independent, and
/// [`index_pairs_differ_fraction`] lets a test assert they differ at ≈ `1 − 1/pool_len`.
fn null_ss_index_pairs(
    rng: &mut Shake256Context,
    samples: usize,
    pool_len: usize,
) -> Vec<(usize, usize)> {
    let bytes = random_bytes(rng, samples * 2);
    (0..samples)
        .map(|k| {
            let a = usize::from(bytes[k]) % pool_len;
            let b = usize::from(bytes[samples + k]) % pool_len;
            (a, b)
        })
        .collect()
}

/// Fraction of index pairs whose two arms differ. Expectation for independent uniform draws over
/// `p` keys is `1 − 1/p`; a value near 0 would mean the two arms are correlated (the collapsed
/// mixture the design must avoid).
// Counts and lengths of a measurement session are far below 2^52, so the `f64` conversion cannot
// lose precision on any input this harness produces.
#[cfg(test)]
#[allow(clippy::cast_precision_loss)]
fn index_pairs_differ_fraction(pairs: &[(usize, usize)]) -> f64 {
    if pairs.is_empty() {
        return 0.0;
    }
    let diff = pairs.iter().filter(|(a, b)| a != b).count();
    diff as f64 / pairs.len() as f64
}

/// One v4 `null-ss` session: ONE fresh 32-key pool, both classes drawing from it by INDEPENDENT
/// index streams on a fixed message. True mean difference zero by construction (conditional on
/// the pool); the mixture shape is preserved, unlike a single-key A/A null.
fn run_null_ss(
    rng: &mut Shake256Context,
    samples: usize,
    bits: &mut ClassBits,
) -> Result<RawSamples> {
    let mut pool = Vec::with_capacity(KEY_POOL);
    for _ in 0..KEY_POOL {
        pool.push(gen_keypair(rng)?);
    }
    let m0 = random_bytes(rng, MSG_LEN);
    let pairs = null_ss_index_pairs(rng, samples, KEY_POOL);
    let mut i = 0usize;
    let mut out = [0u8; SIG_COMPRESSED_MAXSIZE];
    Ok(measure(
        samples,
        || bits.next(),
        |class| {
            let (a, b) = pairs[i % pairs.len()];
            let sk = if class { &pool[b].sk } else { &pool[a].sk };
            i += 1;
            let _ = std::hint::black_box(sign_compressed(sk, &m0, &mut out));
        },
    ))
}

/// Fold the null sessions into `(ok, crop statistics, reason)` and log the summary.
///
/// Split out of [`null_and_controls`] so that function stays readable, and so the empty-null
/// display (A8) lives next to the decision that produces it: with no usable null the min/max
/// folds print `inf..0.00`, a range that reads like a measurement and is the empty set.
fn fold_null(
    results: &[ExperimentResult],
    expected: usize,
    log: &dyn Fn(&str),
) -> (bool, Vec<f64>, String) {
    let folded = if results.len() == expected {
        null_from_sessions(results)
    } else {
        Err(format!(
            "only {} of {expected} null sessions ran",
            results.len()
        ))
    };
    let (ok, stats, reason) = match folded {
        Ok(v) => (true, v, String::from("OK")),
        Err(reason) => (false, Vec::new(), format!("NOT OK — {reason}")),
    };
    let range = if stats.is_empty() {
        "none (null rejected)".to_owned()
    } else {
        format!(
            "{:.2}..{:.2}",
            stats.iter().copied().fold(f64::INFINITY, f64::min),
            stats.iter().copied().fold(0.0_f64, f64::max)
        )
    };
    log(&format!(
        "null: {} pool-vs-pool sessions, raw|t| max {:.2}, crop-stat range {range} → {reason}",
        results.len(),
        results
            .iter()
            .map(|r| r.raw_t.abs())
            .fold(0.0_f64, f64::max),
    ));
    (ok, stats, reason)
}

/// Sample standard deviation (**n − 1**, not the population sd), or `None` for fewer than two
/// observations.
///
/// **`None`, not `0.0`.** A sample sd of one observation is undefined, and returning zero would
/// put the v4 validation reading (`METHODOLOGY-v4.md` §2: `≤ 1.25` → proceed) in its *proceed*
/// band on no data at all — a check that cannot fail, which is this project's dominant defect
/// class. The incomplete-run path can produce it for real: the null loop breaks on the first
/// session that cannot run, so a session that dies after one null would report a confident
/// `0.000` spread.
// A session has at most a few dozen null sessions, so `len() as f64` cannot lose precision.
#[allow(clippy::cast_precision_loss)]
fn sample_sd(xs: &[f64]) -> Option<f64> {
    if xs.len() < 2 {
        return None;
    }
    let n = xs.len() as f64;
    let mean = xs.iter().sum::<f64>() / n;
    Some((xs.iter().map(|x| (x - mean) * (x - mean)).sum::<f64>() / (n - 1.0)).sqrt())
}

/// Run `opts.null_sessions` null sessions of the given construction, logging each as it lands.
///
/// Split out of [`null_and_controls`] so that function stays under the line limit and so the two
/// constructions sit side by side: `rr` is the v3 rule in force by default, `ss` is v4's.
fn run_null_sessions(
    design: NullDesign,
    opts: &Opts,
    rng: &mut Shake256Context,
    bits: &mut ClassBits,
    log: &dyn Fn(&str),
) -> Vec<ExperimentResult> {
    let (tag, what) = match design {
        NullDesign::Rr => (
            "null-rr",
            "sign_compressed: fixed message; fresh pool A vs fresh pool B (null session)",
        ),
        NullDesign::Ss => (
            "null-ss",
            "sign_compressed: fixed message; ONE fresh pool, both classes drawing from it by \
             independent index streams (v4 true-zero null session)",
        ),
    };
    log(&format!(
        "running {} {tag} null sessions (real operation; fresh pool(s) each) …",
        opts.null_sessions
    ));
    let mut out = Vec::with_capacity(opts.null_sessions);
    for k in 0..opts.null_sessions {
        let run = match design {
            NullDesign::Rr => run_null_rr(rng, opts.samples, bits),
            NullDesign::Ss => run_null_ss(rng, opts.samples, bits),
        };
        let raw = match run {
            Ok(r) => r,
            // Keep the error text: key generation, allocation and FFI failures are otherwise
            // indistinguishable, and this line is the only diagnostic a long run leaves behind.
            Err(e) => {
                log(&format!("null session {k} could not run: {e}"));
                break;
            }
        };
        let r = judge(&format!("{tag}-{k}"), what, &raw);
        // A7: one line per null session as it lands. The null is two thirds of a long session's
        // wall-clock, and it used to print its start and then nothing for hours — a crash inside
        // it was diagnosable only as "it died somewhere in the null", and a session drifting
        // towards the gate was invisible until the end.
        log(&format!(
            "  {tag}-{k}: n={}/{} raw t={:+.2} crop={:.2}{}",
            r.class0.n,
            r.class1.n,
            r.raw_t,
            r.crop_max_abs_t,
            if r.raw_t.abs() >= falcon_ct::T_THRESHOLD {
                "  ← TRIPS THE GATE (this session will be INCONCLUSIVE)"
            } else {
                ""
            }
        ));
        out.push(r);
    }
    out
}

fn null_and_controls(
    opts: &Opts,
    rng: &mut Shake256Context,
    bits: &mut ClassBits,
    log: &dyn Fn(&str),
) -> (Controls, RawSamples, RawSamples) {
    // v3 (METHODOLOGY-v3 §1): the null is the REAL operation — N pool-vs-pool signing sessions,
    // each with two fresh independent 32-key pools, the same measurement count as the
    // experiments, class randomised per measurement. Every null session must PASS on the raw
    // statistic or the environment is too noisy for any Falcon verdict.
    let null_results = run_null_sessions(opts.null_design, opts, rng, bits, log);
    let (null_ok, null_crop_stats, null_reason) = fold_null(&null_results, opts.null_sessions, log);
    let null_raw_t_sd = sample_sd(&null_results.iter().map(|r| r.raw_t).collect::<Vec<_>>());
    // METHODOLOGY-v4 §2: this is the number the v4 validation run exists to read. Under a TRUE
    // null it is 1; v3.1 measured 1.742 under `rr`. Printed for both designs so the two can be
    // compared on the same machine in one session. The pre-registered bands are printed WITH it,
    // so the reading cannot drift from the file that fixed it.
    log(&null_raw_t_sd.map_or_else(
        || {
            format!(
                "null: sd of the raw t values = UNDEFINED (only {} session(s) usable; a sample sd \
                 needs 2). This is NOT the '<= 1.25 proceed' band — it is no reading at all.",
                null_results.len()
            )
        },
        |sd| {
            let band = if sd <= 1.25 {
                "<= 1.25 → v4 §2 'proceed to a verdict-session design'"
            } else if sd <= 1.60 {
                "1.25-1.60 → v4 §2 'partial; v4.1 must add a null-referenced raw threshold first'"
            } else {
                "> 1.60 → v4 §2 'STOP and re-derive — the construction does not remove the \
                 inflation'"
            };
            format!(
                "null: sd of the {} raw t values = {sd:.3}  ({band}; 1.000 under a true null, \
                 v3.1 measured 1.742 under rr)",
                null_results.len()
            )
        },
    ));

    // INTERIM RULING (2026-08-20, six-seat review of the v4.1 validation session): synthetic
    // controls are judged on the raw line ONLY (`judge_raw_only`). Crop-judging a synthetic
    // loop against a bank of REAL signing operations is a mismatched reference — observed
    // live: the flat control read "Shape" at raw t = 2.99 against the null-ss bank and flipped
    // controls to NOT OK. Whether a crop-shape control validation returns (with its own
    // synthetic reference family + a positive shape control) is a future pre-registration.
    log("running control-flat …");
    let flat_raw = run_control_flat(opts.samples, bits);
    let flat = judge_raw_only(
        "control-flat",
        "identical synthetic work for both classes; raw-line verdict only (interim ruling \
         2026-08-20 — the crop diagnostic does not run for synthetic controls)",
        &flat_raw,
    );
    log("running control-leaky …");
    let leaky_raw = run_control_leaky(opts.samples, bits);
    let leaky = judge_raw_only(
        "control-leaky",
        "class-dependent synthetic work (40k vs 60k iterations); raw-line verdict only \
         (interim ruling 2026-08-20)",
        &leaky_raw,
    );
    // The flat control must PASS and the leaky control must FAIL — both on the raw statistic
    // alone — and the null itself must be ok.
    let ok = null_ok
        && flat.isolated_verdict == Verdict::Pass
        && leaky.isolated_verdict == Verdict::Fail;
    log(&format!(
        "controls: flat={:?} (raw t={:.2}) leaky={:?} (raw t={:.2}) → {}",
        flat.isolated_verdict,
        flat.raw_t,
        leaky.isolated_verdict,
        leaky.raw_t,
        if ok {
            "OK"
        } else {
            "NOT OK — every Falcon verdict below is INCONCLUSIVE"
        }
    ));
    // If the null is not ok, force every Falcon verdict to INCONCLUSIVE by making the flat
    // control read as not-PASS for `apply_controls`.
    let flat_for_rule = if ok {
        flat
    } else {
        let mut f = flat;
        f.isolated_verdict = Verdict::Inconclusive;
        f
    };
    (
        Controls {
            flat: flat_for_rule,
            leaky,
            ok,
            null_sessions: null_results.len(),
            null_crop_stats,
            null_ok,
            null_design: opts.null_design,
            null_raw_t_sd,
            null_raw_t_sd_gate: "human (METHODOLOGY-v4 §2); no verdict reads this number",
            null_reason,
            affinity_pinned: false,
            null_detail: null_results,
            // Filled in after `run_aa_control`; the block is built before the experiments run.
            aa_verdict: None,
            aa_ok: None,
            rr_detail: Vec::new(),
            aa_repeats_requested: opts.aa_repeats,
            rr_sessions_requested: opts
                .rr_sessions
                .or_else(|| (opts.null_design == NullDesign::Ss).then_some(opts.null_sessions)),
        },
        flat_raw,
        leaky_raw,
    )
}

fn main() -> Result<()> {
    let opts = parse_opts()?;
    fs::create_dir_all(&opts.out)
        .with_context(|| format!("creating output directory {}", opts.out.display()))?;
    let quiet = opts.json_only;
    let log = move |line: &str| {
        if !quiet {
            eprintln!("{line}");
        }
    };

    // One system-seeded PRNG for everything random in the session: class bits, key pool, messages.
    let mut rng = prng_from_system().map_err(|c| anyhow!("OS RNG unavailable (code {c})"))?;
    let mut bits = ClassBits(prng_from_seed(&random_bytes(&mut rng, 32)));
    let fixtures = Fixtures::prepare(&mut rng, opts.samples)?;
    log(&format!(
        "falcon-ct: {} measurements per experiment, key pool {KEY_POOL}, message {MSG_LEN} B, out {}",
        opts.samples,
        opts.out.display()
    ));

    let (mut controls, flat_raw, leaky_raw) = null_and_controls(&opts, &mut rng, &mut bits, &log);

    // ── Falcon ─────────────────────────────────────────────────────────────────────────────
    let out = falcon_experiments(&fixtures, &opts, &mut rng, &mut bits, &controls, &log)?;
    let (mut experiments, mut raws) = (out.judged, out.raws);
    controls.rr_detail = out.rr_detail;
    // Record what the A/A control did IN THE ARTIFACT, not only on the console. Without this the
    // controls block reads `controls_ok: true` while every key verdict is INCONCLUSIVE.
    if let Some(aa) = experiments.iter().find(|j| j.result.id == "sign-aa") {
        controls.aa_verdict = Some(aa.verdict);
        controls.aa_ok = Some(aa.verdict == Verdict::Pass);
    }
    let mut all_raws = vec![
        ("control-flat".to_owned(), flat_raw),
        ("control-leaky".to_owned(), leaky_raw),
    ];
    all_raws.append(&mut raws);

    // v3 §1 combination rule for sign-kk: FAIL if any pair FAILs; SHAPE only if >= 2 of the 3
    // pairs are SHAPE; INCONCLUSIVE if any pair is INCONCLUSIVE; else PASS. sign-rr stands alone.
    let kk: Vec<Verdict> = experiments
        .iter()
        .filter(|j| j.gated && j.result.id.starts_with("sign-kk-"))
        .map(|j| j.verdict)
        .collect();
    let kk_combined = if kk.contains(&Verdict::Inconclusive) {
        Verdict::Inconclusive
    } else if kk.contains(&Verdict::Fail) {
        Verdict::Fail
    } else if kk.iter().filter(|v| **v == Verdict::Shape).count() >= 2 {
        Verdict::Shape
    } else {
        Verdict::Pass
    };
    let rr = experiments
        .iter()
        .filter(|j| j.gated && j.result.id == "sign-rr")
        .map(|j| j.verdict)
        .fold(Verdict::Pass, Verdict::worse);
    let measured_verdict = kk_combined.worse(rr);
    log(&format!(
        "sign-kk combined (>=2 of 3 rule): {kk_combined:?} from {kk:?}; sign-rr: {rr:?}"
    ));

    // VALIDATION-ONLY MODE. `METHODOLOGY-v4.md` §2 says a session under `ss` is a validation run
    // and that "nothing in session 1 is read as evidence about the signer". Until now that was
    // prose: a reader holding only `report.json` would have seen `session_verdict: PASS` and
    // quoted it. It is enforced here, because `ss` is NOT yet the whole v4 design — it narrows
    // the null (correctly; that is the fix) while §2a's compensating matched crop references are
    // not wired, so the same fixed |t| < 4.5 gate trips LESS often and the session is easier to
    // clear. A change that makes a session easier to pass may not also be allowed to issue the
    // verdict. Under `ss` every experiment is therefore ungated and the session verdict is
    // INCONCLUSIVE: measurement and `null_raw_t_sd` publication only.
    let (session_verdict, validation_only) = match opts.null_design {
        NullDesign::Rr => (measured_verdict, false),
        NullDesign::Ss => {
            for j in &mut experiments {
                j.gated = false;
            }
            log(&format!(
                "VALIDATION-ONLY (--null-design ss): the measured gated verdict would have been \
                 {measured_verdict:?}; the session verdict is INCONCLUSIVE and every experiment is \
                 ungated, because the v4 matched crop references (METHODOLOGY-v4 §2a) are not \
                 implemented and `ss` alone only makes the gate easier to clear. Read \
                 null_raw_t_sd; read nothing else here as evidence about the signer."
            ));
            (Verdict::Inconclusive, true)
        }
    };

    let report = Report {
        methodology: METHODOLOGY,
        // 5: `controls.null_design` and `controls.null_raw_t_sd` (METHODOLOGY-v4 §1–§2).
        // 4: every experiment carries `se_ns` / `mde80_ns` / `mde90_ns` (v3.1 power addendum).
        // Additive and `#[serde(default)]`, so a schema-3 reader still parses these reports; the
        // bump is how a reader tells "this session published its resolution" from one that could
        // not. Decision rules are unchanged from v3.
        // 6: v4.1 §2a matched reference banks — sign-aa-<k> repeat rows, controls.rr_detail and
        //    rr_raw_state on sign-rr (all additive; absent under the default rr design).
        schema_version: 6,
        samples_per_experiment: opts.samples,
        key_pool: KEY_POOL,
        message_len: MSG_LEN,
        environment: Environment::current(),
        controls,
        experiments,
        session_verdict,
        validation_only,
        reading_guide: READING_GUIDE,
    };
    write_outputs(&opts, &report, &all_raws)
}

#[cfg(test)]
mod tests {
    #![allow(clippy::expect_used, clippy::unwrap_used, clippy::panic)]

    use falcon_ct::Verdict;

    use super::flat_verdict_under_aa;

    /// The A/A control's whole purpose: it can shut the session up, and it can never open it.
    #[test]
    fn only_a_passing_aa_control_lets_the_session_speak() {
        // PASS on A/A: the flat control's own verdict is carried through untouched, whatever it
        // is — the A/A control adds no new way to reach a verdict.
        for flat in [
            Verdict::Pass,
            Verdict::Shape,
            Verdict::Fail,
            Verdict::Inconclusive,
        ] {
            assert_eq!(
                flat_verdict_under_aa(Verdict::Pass, flat),
                flat,
                "a passing A/A control must not change how the session is judged"
            );
        }
        // Anything else on A/A: INCONCLUSIVE, even when the flat control passed. A FAIL means the
        // harness tells its own arms apart in location; SHAPE means it does so in the crop
        // diagnostic the key experiments' secondary arm rests on; INCONCLUSIVE means the control
        // could not be judged. None of the three can be distinguished from a key effect.
        for aa in [Verdict::Shape, Verdict::Fail, Verdict::Inconclusive] {
            for flat in [
                Verdict::Pass,
                Verdict::Shape,
                Verdict::Fail,
                Verdict::Inconclusive,
            ] {
                assert_eq!(
                    flat_verdict_under_aa(aa, flat),
                    Verdict::Inconclusive,
                    "A/A = {aa:?} must force INCONCLUSIVE even with flat = {flat:?}"
                );
            }
        }
    }

    /// Downgrade-only, stated as a property rather than as four cases: for every pair of
    /// verdicts, the rule's output is either the flat control's verdict or INCONCLUSIVE. It can
    /// never invent a PASS, a SHAPE or a FAIL that the session did not otherwise have.
    #[test]
    fn the_aa_rule_can_only_downgrade() {
        let all = [
            Verdict::Pass,
            Verdict::Shape,
            Verdict::Fail,
            Verdict::Inconclusive,
        ];
        for aa in all {
            for flat in all {
                let out = flat_verdict_under_aa(aa, flat);
                assert!(
                    out == flat || out == Verdict::Inconclusive,
                    "A/A = {aa:?}, flat = {flat:?} produced {out:?} — the rule invented a verdict"
                );
            }
        }
    }
}

#[cfg(test)]
mod v4_tests {
    // Pool sizes and session counts are tiny; no `usize` here is anywhere near 2^52.
    #![allow(
        clippy::expect_used,
        clippy::unwrap_used,
        clippy::panic,
        clippy::cast_precision_loss
    )]

    use trelyan_pq_ffi::prng_from_seed;

    use super::{
        KEY_POOL, NullDesign, Opts, index_pairs_differ_fraction, null_ss_index_pairs, rr_raw_state,
        sample_sd,
    };
    use falcon_ct::RawSamples;

    /// THE TRAP THE v4 NULL MUST AVOID. If both arms of a `null-ss` session drew the same index,
    /// every measurement pair would sign with the same key, the 32-key mixture would collapse to
    /// a fixed-key A/A comparison, and the "null" would silently be a different construction than
    /// the one `METHODOLOGY-v4.md` §1 pre-registers. Independent uniform draws over 32 keys differ
    /// with probability 1 − 1/32 = 0.969.
    #[test]
    fn null_ss_arms_draw_independent_indices() {
        let mut rng = prng_from_seed(&[0x5A; 32]);
        let pairs = null_ss_index_pairs(&mut rng, 20_000, KEY_POOL);
        assert_eq!(pairs.len(), 20_000);
        let differ = index_pairs_differ_fraction(&pairs);
        let expect = 1.0 - 1.0 / KEY_POOL as f64;
        assert!(
            (differ - expect).abs() < 0.02,
            "arms differ {differ:.4} of the time, expected ≈ {expect:.4}; a value near 0 means \
             the two arms are correlated and the mixture has collapsed"
        );
        // And both arms must actually span the pool — a stream stuck on one key would also pass
        // a naive difference check if the other arm moved.
        for arm in [0usize, 1] {
            let mut seen = [false; KEY_POOL];
            for p in &pairs {
                seen[if arm == 0 { p.0 } else { p.1 }] = true;
            }
            assert!(
                seen.iter().all(|s| *s),
                "arm {arm} did not reach every key in the pool"
            );
        }

        // NEITHER CHECK ABOVE IS AN INDEPENDENCE TEST, and a reviewer supplied the counterexample:
        // b := (a + 1) mod 32, forced equal to a on 1/32 of positions, has full marginal coverage
        // AND exactly the expected differing fraction while being a deterministic function of a.
        // Independence is a property of the JOINT distribution, so test the joint distribution.
        let mut joint = [[0usize; KEY_POOL]; KEY_POOL];
        for &(a, b) in &pairs {
            joint[a][b] += 1;
        }
        let cells = (KEY_POOL * KEY_POOL) as f64;
        let expected_cell = pairs.len() as f64 / cells;
        // Pearson chi-square against uniform over the 1024 cells. Under independence with uniform
        // marginals this is ≈ χ² on 1023 df — mean 1023, sd √(2·1023) ≈ 45 — while the shifted
        // counterexample puts all mass on 32 cells and scores in the hundreds of thousands.
        let chi2: f64 = joint
            .iter()
            .flatten()
            .map(|&c| {
                let d = c as f64 - expected_cell;
                d * d / expected_cell
            })
            .sum();
        assert!(
            chi2 < 10.0f64.mul_add(45.0, 1023.0),
            "joint index distribution is far from uniform (chi2 = {chi2:.0} on 1023 df): the two \
             arms are not independent"
        );
        // A coupled construction also leaves most (a,b) combinations at exactly zero. The
        // chi-square already catches that; assert it directly because it is the property a reader
        // can check by eye.
        let empty = joint.iter().flatten().filter(|&&c| c == 0).count();
        assert_eq!(
            empty, 0,
            "{empty} of {cells} (a,b) combinations never occurred — the arms are coupled"
        );
    }

    /// v4.1 §2 truth table for the sign-rr three-state raw reading. The middle state is the
    /// design's point: beyond the fixed line but inside the matched reference's range may
    /// neither PASS nor FAIL.
    #[test]
    fn rr_raw_state_truth_table() {
        let bank = [1.2, 3.7, 5.1, 2.0];
        // Below the fixed 4.5 line: clears, whatever the bank says.
        assert_eq!(rr_raw_state(0.4, &bank), "clears");
        assert_eq!(rr_raw_state(4.4999, &bank), "clears");
        // Beyond 4.5 but not beyond every reference (5.1 >= 4.8): pool offsets reach here
        // under the no-leak null — cannot PASS, cannot FAIL.
        assert_eq!(rr_raw_state(4.8, &bank), "inconclusive_pool_offset");
        // A TIE with the bank maximum does not fire — strict >, same as the crop rule.
        assert_eq!(rr_raw_state(5.1, &bank), "inconclusive_pool_offset");
        // Beyond the fixed line AND beyond every reference.
        assert_eq!(rr_raw_state(5.100_000_1, &bank), "fail_beyond_reference");
        assert_eq!(rr_raw_state(20.0, &bank), "fail_beyond_reference");
        // REVIEW S1: an empty bank supports NO statement about references — the earlier
        // version returned fail_beyond_reference here ("beyond every reference", with zero
        // references), and the review correctly called that a relabelled collection failure.
        // Banks are all-or-nothing upstream, so these are harness-fault states.
        assert_eq!(rr_raw_state(4.6, &[]), "no_reference_bank");
        assert_eq!(rr_raw_state(0.5, &[]), "no_reference_bank");
        // NaN compares false with everything under IEEE, which previously dropped it into the
        // fail arm. A statistic that is not a number is not a failure beyond references.
        assert_eq!(rr_raw_state(f64::NAN, &bank), "invalid_statistic");
        assert_eq!(rr_raw_state(f64::NAN, &[]), "invalid_statistic");
    }

    /// The reviewer requirement from increment 1: bank COUNTS must provably change execution,
    /// not just parse. `collect_sessions` is the seam every bank runs through; this proves the
    /// requested count is the executed count — and (REVIEW S1) that a failing session
    /// PROPAGATES as an error rather than yielding a short bank, because a short bank silently
    /// changes the empirical rule.
    #[test]
    fn bank_counts_drive_execution_and_failures_propagate() {
        let log = |_: &str| {};
        let mut calls = 0usize;
        let out = super::collect_sessions(7, "t", &log, |_k| {
            calls += 1;
            Ok(RawSamples {
                samples: vec![(0u8, 1u64), (1u8, 2u64)],
            })
        })
        .expect("all sessions succeed");
        assert_eq!(
            calls, 7,
            "7 requested sessions must mean 7 executed sessions"
        );
        assert_eq!(out.len(), 7);

        let mut calls2 = 0usize;
        let err = super::collect_sessions(10, "t", &log, |k| {
            calls2 += 1;
            if k == 3 {
                Err(anyhow::anyhow!("boom"))
            } else {
                Ok(RawSamples {
                    samples: vec![(0u8, 1u64)],
                })
            }
        })
        .expect_err("a failed reference session must be an error, never a short bank");
        assert_eq!(calls2, 4, "collection stops AT the failure");
        assert!(
            err.to_string().contains("all-or-nothing"),
            "the error names the rule: {err}"
        );
    }

    /// Under the default `rr` design the reference banks are all the gate null and no raw bank
    /// exists — v3 judging unchanged. REVIEW S3: this now pins the PRODUCTION selection
    /// function (`refs_for_rr`, the exact value `build_reference_banks` returns under rr),
    /// not a hand-built copy of it.
    #[test]
    fn rr_design_banks_are_all_the_gate_null() {
        let gate = vec![1.0, 2.5, 3.75];
        let refs = super::refs_for_rr(&gate);
        assert_eq!(refs.gate, gate);
        assert_eq!(
            refs.kk, gate,
            "sign-kk judged against the gate null under rr"
        );
        assert_eq!(
            refs.rr_crop, gate,
            "sign-rr crop judged against the gate null under rr"
        );
        assert!(
            refs.rr_raw.is_none(),
            "no raw bank under rr: the fixed 4.5 rule stands alone and rr_raw_state is never computed"
        );
    }

    /// REVIEW ("not established"): the CLI guards, asserted in prose, now asserted in tests —
    /// the whole truth table of `check_v4_options`.
    #[test]
    fn v4_option_guards() {
        use super::check_v4_options as chk;
        let mk = |design: NullDesign, aa: Option<usize>, rr: Option<usize>| Opts {
            samples: 4800,
            out: std::path::PathBuf::from("unused"),
            json_only: false,
            null_sessions: 20,
            null_design: design,
            aa_repeats: aa,
            rr_sessions: rr,
        };
        // rr: both options refused by PRESENCE, even at default-looking values.
        assert!(chk(&mk(NullDesign::Rr, None, None)).is_ok());
        assert!(chk(&mk(NullDesign::Rr, Some(1), None)).is_err());
        assert!(chk(&mk(NullDesign::Rr, Some(20), None)).is_err());
        assert!(chk(&mk(NullDesign::Rr, None, Some(20))).is_err());
        // zero = a reference from no sessions.
        assert!(chk(&mk(NullDesign::Ss, Some(0), None)).is_err());
        assert!(chk(&mk(NullDesign::Ss, Some(20), Some(0))).is_err());
        // ss REQUIRES aa-repeats >= 2 (S2: the bank is the repeats only).
        assert!(chk(&mk(NullDesign::Ss, None, None)).is_err());
        assert!(chk(&mk(NullDesign::Ss, Some(1), None)).is_err());
        assert!(chk(&mk(NullDesign::Ss, Some(2), None)).is_ok());
        assert!(chk(&mk(NullDesign::Ss, Some(20), Some(20))).is_ok());
    }

    /// The v4 validation run reads exactly one number (METHODOLOGY-v4 §2); it must be the SAMPLE
    /// sd, and a wrong divisor would shift the pre-registered 1.25 / 1.60 decision lines.
    #[test]
    fn sample_sd_uses_n_minus_one() {
        // Known: for 2, 4, 4, 4, 5, 5, 7, 9 the population sd is 2 and the sample sd is 2.13809.
        let xs = [2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0];
        let got = sample_sd(&xs).expect("8 observations");
        assert!((got - 2.138_089_935_299_395).abs() < 1e-12, "got {got}");
        assert!(
            sample_sd(&[1.0, 1.0, 1.0]).expect("3 observations").abs() < 1e-12,
            "no spread → 0, which is a real measurement"
        );
    }

    /// **The reading must be unavailable, not zero, on fewer than two sessions.** Returning 0.0
    /// would put `METHODOLOGY-v4.md` §2's only decision ("≤ 1.25 → proceed") in its proceed band
    /// on no data — a check that cannot fail. The null loop breaks on the first session that
    /// cannot run, so a session dying after one null reaches this path for real.
    #[test]
    fn sample_sd_is_undefined_below_two_observations() {
        assert_eq!(
            sample_sd(&[3.0]),
            None,
            "one observation is not a spread of zero"
        );
        assert_eq!(
            sample_sd(&[]),
            None,
            "no observations is not a spread of zero"
        );
        assert!(
            sample_sd(&[3.0]).is_none_or(|sd| sd > 1.25),
            "an undefined sd must never read as the '<= 1.25 proceed' band"
        );
    }
}
