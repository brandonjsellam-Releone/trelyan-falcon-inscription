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
    null_from_flat_sessions, to_csv,
};
use serde::Serialize;
use trelyan_pq_ffi::{
    PRIVKEY_SIZE, PUBKEY_SIZE, SIG_COMPRESSED_MAXSIZE, Shake256Context, keygen, prng_extract,
    prng_from_seed, prng_from_system, sign_compressed, verify_compressed,
};

const DEFAULT_SAMPLES: usize = 8_000;
const KEY_POOL: usize = 32;
const MSG_LEN: usize = 64;
/// Number of fixed-key pairs for `sign-kk` (METHODOLOGY-v2 §2: three pairs).
const KK_PAIRS: usize = 3;
/// Flat-control sessions forming the empirical null for the crop statistic (v2 §1: N ≥ 20).
const DEFAULT_NULL_SESSIONS: usize = 24;
const METHODOLOGY: &str = "evidence/ct/METHODOLOGY-v2.md (2026-08-18); v1 = METHODOLOGY.md";
const READING_GUIDE: &str = "v2. PASS = raw Welch |t| < 4.5 AND crop statistic within the \
    session's empirical null (not a proof; machine- and build-specific). SHAPE = raw |t| < 4.5 \
    but crop statistic beyond every null session: distributions differ in shape/scale, not \
    location — never PASS, never FAIL, a call for the source-level reading. FAIL = raw |t| >= \
    4.5 with controls behaved: a LOCATION difference. INCONCLUSIVE = a control or the null \
    misbehaved, or too few samples; never read as PASS. Gated: sign-kk (three pairs) and \
    sign-rr. Screening/informational: sign-key, sign-msg, verify-ctrl, keygen.";

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
    /// v2: the crop statistics of the N flat-control null sessions (the empirical null), or
    /// empty if a null session itself failed the raw statistic (environment too noisy).
    null_sessions: usize,
    null_crop_stats: Vec<f64>,
    null_ok: bool,
    /// v2: whether the harness pinned itself to one CPU. std has no affinity API and the
    /// constitution allows no new dependency for it here, so this is `false` and stated.
    affinity_pinned: bool,
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
    if o.samples < 100 {
        return Err(anyhow!("--samples must be at least 100"));
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

/// v2 sign-kk: fixed message M0; class 0 = key `K_a`, class 1 = key `K_b` (pair `pair`).
fn run_sign_kk(f: &Fixtures, pair: usize, samples: usize, bits: &mut ClassBits) -> RawSamples {
    let (ka, kb) = &f.kk[pair];
    let mut out = [0u8; SIG_COMPRESSED_MAXSIZE];
    measure(
        samples,
        || bits.next(),
        |class| {
            let sk = if class { &kb.sk } else { &ka.sk };
            let _ = std::hint::black_box(sign_compressed(sk, &f.m0, &mut out));
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
    let mut push = |id: String, description: &str, gated: bool, raw: RawSamples| {
        let r = judge_v2(&id, description, &raw, &controls.null_crop_stats);
        judged.push(Judged {
            verdict: apply_controls(
                r.isolated_verdict,
                controls.flat.isolated_verdict,
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
            "sign_compressed: fixed message M0; fixed key K_a vs fixed key K_b — the per-key \
             timing fingerprint measured directly (v2 primary design)",
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
        "  null: {} flat sessions (crop-stat max {:.2}) {} | controls: flat {:?} (raw t {:.2}), leaky {:?} (raw t {:.2}) → {}",
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
    }
    println!("  SESSION VERDICT: {:?}", report.session_verdict);
    println!("  written: {}/report.json + raw-*.csv", opts.out.display());
    Ok(())
}

/// v2 empirical null (N flat-control sessions, each must PASS on the RAW statistic) followed by
/// the two controls. Returns the `Controls` block and the two controls' raw samples.
fn null_and_controls(
    opts: &Opts,
    bits: &mut ClassBits,
    log: &dyn Fn(&str),
) -> (Controls, RawSamples, RawSamples) {
    log(&format!(
        "running {} flat-control null sessions …",
        opts.null_sessions
    ));
    let mut null_results = Vec::with_capacity(opts.null_sessions);
    for k in 0..opts.null_sessions {
        let raw = run_control_flat(opts.samples, bits);
        null_results.push(judge(
            &format!("null-flat-{k}"),
            "flat control (null session)",
            &raw,
        ));
    }
    let null_crop_stats = null_from_flat_sessions(&null_results);
    let null_ok = null_crop_stats.is_some();
    let null_crop_stats = null_crop_stats.unwrap_or_default();
    log(&format!(
        "null: {} sessions, raw|t| max {:.2}, crop-stat range {:.2}..{:.2} → {}",
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
        if null_ok {
            "OK"
        } else {
            "NOT OK — a null session failed the raw statistic; environment too noisy"
        }
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

    let (controls, flat_raw, leaky_raw) = null_and_controls(&opts, &mut bits, &log);

    // ── Falcon ─────────────────────────────────────────────────────────────────────────────
    let (experiments, mut raws) =
        falcon_experiments(&fixtures, opts.samples, &mut bits, &controls, &log);
    let mut all_raws = vec![
        ("control-flat".to_owned(), flat_raw),
        ("control-leaky".to_owned(), leaky_raw),
    ];
    all_raws.append(&mut raws);

    let session_verdict = experiments
        .iter()
        .filter(|j| j.gated)
        .map(|j| j.verdict)
        .fold(Verdict::Pass, Verdict::worse);

    let report = Report {
        methodology: METHODOLOGY,
        schema_version: 2,
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
