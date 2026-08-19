//! `falcon-ct` — run the pre-registered constant-time evidence session against the pinned
//! Falcon-1024 det1024 signer and write `report.json` + one raw CSV per experiment.
//!
//! Usage:
//!   falcon-ct [--samples N] [--out DIR] [--json-only]
//!
//! `--samples N` is measurements PER EXPERIMENT (both classes together; default 8000, i.e. ~4000
//! per class, above the 2 000 minimum). `--out DIR` (default `evidence/ct/out`) receives
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
    ExperimentResult, RawSamples, Verdict, apply_controls, judge, judge_v2, measure,
    null_from_sessions, to_csv,
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
    build-specific.";

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
    /// The worst gated Falcon-experiment verdict after controls (v2 §1–§2).
    session_verdict: Verdict,
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
}

#[derive(Serialize)]
struct Judged {
    #[serde(flatten)]
    result: ExperimentResult,
    /// Verdict after the control rule.
    verdict: Verdict,
    /// Whether this experiment participates in the session verdict (keygen and verify do not).
    gated: bool,
}

struct Opts {
    samples: usize,
    out: PathBuf,
    json_only: bool,
    null_sessions: usize,
}

fn parse_opts() -> Result<Opts> {
    let mut o = Opts {
        samples: DEFAULT_SAMPLES,
        out: PathBuf::from("evidence/ct/out"),
        json_only: false,
        null_sessions: DEFAULT_NULL_SESSIONS,
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
            "-h" | "--help" => {
                println!("falcon-ct [--samples N] [--null-sessions N] [--out DIR] [--json-only]");
                std::process::exit(0);
            }
            other => return Err(anyhow!("unknown option {other}")),
        }
        i += 1;
    }
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
    let (ka, kb) = &f.aa;
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
            result: aa,
        },
        raw,
        flat_for_rule,
    )
}

/// The Falcon experiments in METHODOLOGY-v2 §2 order, each judged (v2) against the controls
/// and the empirical null.
fn falcon_experiments(
    f: &Fixtures,
    samples: usize,
    bits: &mut ClassBits,
    controls: &Controls,
    log: &dyn Fn(&str),
) -> (Vec<Judged>, Vec<(String, RawSamples)>) {
    type Runner = fn(&Fixtures, usize, &mut ClassBits) -> RawSamples;
    let mut judged = Vec::new();
    let mut raws = Vec::new();

    // v3.1 A/A layout control, before anything else is judged (see `run_aa_control`).
    let (aa_judged, aa_raw, flat_for_rule) = run_aa_control(f, samples, bits, controls, log);
    judged.push(aa_judged);
    raws.push(("sign-aa".to_owned(), aa_raw));

    let mut push = |id: String, description: &str, gated: bool, raw: RawSamples| {
        let r = judge_v2(&id, description, &raw, &controls.null_crop_stats);
        judged.push(Judged {
            verdict: apply_controls(
                r.isolated_verdict,
                flat_for_rule,
                controls.leaky.isolated_verdict,
            ),
            gated,
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
        );
    }
    log("running sign-rr (gated) …");
    let raw = run_sign_rr(f, samples, bits);
    push(
        "sign-rr".to_owned(),
        "sign_compressed: fixed message M0; key from pool A vs key from pool B — symmetric \
         mixture control (v2)",
        true,
        raw,
    );

    // ── screening / informational (v1 designs, demoted in v2) ──────────────────────────────
    let plan: [(&str, &str, bool, Runner); 4] = [
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
    ];
    for (id, description, gated, run) in plan {
        log(&format!(
            "running {id}{} …",
            if gated { "" } else { " (informational)" }
        ));
        let raw = run(f, samples, bits);
        push(id.to_owned(), description, gated, raw);
    }
    (judged, raws)
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
    log(&format!(
        "running {} pool-vs-pool null sessions (real operation; fresh pools each) …",
        opts.null_sessions
    ));
    let mut null_results = Vec::with_capacity(opts.null_sessions);
    for k in 0..opts.null_sessions {
        let raw = match run_null_rr(rng, opts.samples, bits) {
            Ok(r) => r,
            Err(e) => {
                log(&format!("null session {k} could not run: {e}"));
                break;
            }
        };
        null_results.push(judge(
            &format!("null-rr-{k}"),
            "sign_compressed: fixed message; fresh pool A vs fresh pool B (null session)",
            &raw,
        ));
    }
    let null_crop_stats = if null_results.len() == opts.null_sessions {
        null_from_sessions(&null_results)
    } else {
        Err(format!(
            "only {} of {} null sessions ran",
            null_results.len(),
            opts.null_sessions
        ))
    };
    let (null_ok, null_crop_stats, null_reason) = match null_crop_stats {
        Ok(v) => (true, v, String::from("OK")),
        Err(reason) => (false, Vec::new(), format!("NOT OK — {reason}")),
    };
    log(&format!(
        "null: {} pool-vs-pool sessions, raw|t| max {:.2}, crop-stat range {:.2}..{:.2} → {}",
        null_results.len(),
        null_results
            .iter()
            .map(|r| r.raw_t.abs())
            .fold(0.0_f64, f64::max),
        null_crop_stats
            .iter()
            .copied()
            .fold(f64::INFINITY, f64::min),
        null_crop_stats.iter().copied().fold(0.0_f64, f64::max),
        null_reason
    ));

    log("running control-flat …");
    let flat_raw = run_control_flat(opts.samples, bits);
    let flat = judge_v2(
        "control-flat",
        "identical synthetic work for both classes",
        &flat_raw,
        &null_crop_stats,
    );
    log("running control-leaky …");
    let leaky_raw = run_control_leaky(opts.samples, bits);
    let leaky = judge_v2(
        "control-leaky",
        "class-dependent synthetic work (40k vs 60k iterations)",
        &leaky_raw,
        &null_crop_stats,
    );
    // v2: the flat control must PASS on the raw statistic (SHAPE would also mean the null is
    // not representative → treat as not ok), the leaky control must FAIL on the raw statistic,
    // and the null itself must be ok.
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
            affinity_pinned: false,
            null_detail: null_results,
            // Filled in after `run_aa_control`; the block is built before the experiments run.
            aa_verdict: None,
            aa_ok: None,
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
    let (experiments, mut raws) =
        falcon_experiments(&fixtures, opts.samples, &mut bits, &controls, &log);
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
    let session_verdict = kk_combined.worse(rr);
    log(&format!(
        "sign-kk combined (>=2 of 3 rule): {kk_combined:?} from {kk:?}; sign-rr: {rr:?}"
    ));

    let report = Report {
        methodology: METHODOLOGY,
        // 4: every experiment carries `se_ns` / `mde80_ns` / `mde90_ns` (v3.1 power addendum).
        // Additive and `#[serde(default)]`, so a schema-3 reader still parses these reports; the
        // bump is how a reader tells "this session published its resolution" from one that could
        // not. Decision rules are unchanged from v3.
        schema_version: 4,
        samples_per_experiment: opts.samples,
        key_pool: KEY_POOL,
        message_len: MSG_LEN,
        environment: Environment::current(),
        controls,
        experiments,
        session_verdict,
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
