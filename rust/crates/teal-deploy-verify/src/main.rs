//! `verify-deployment` — the command-line front end of `teal-deploy-verify`.
//!
//! Exit codes are those of `contracts/verify_deployment.py`: 0 MATCH, 1 DRIFT, 2 COULD NOT CHECK.
//! Usage errors also exit 2, as Python's `argparse` does. An unexpected internal error (a panic)
//! exits 2 as well — never 1, which would report a bug in this program as a deployment mismatch,
//! and never Rust's default 101.

#![forbid(unsafe_code)]

use std::ffi::OsString;
use std::io::{self, Write};
use std::path::PathBuf;
use std::process::ExitCode;
use std::time::Duration;

use teal_deploy_verify::curl::CurlTransport;
use teal_deploy_verify::{
    APPROVAL_TEAL, CLEAR_TEAL, Config, DEFAULT_ALGOD, DEFAULT_APP_ID, DEFAULT_TIMEOUT, TealFile,
    Verdict, discover_repo_root, run, sanitize, url,
};

const HELP: &str = "\
verify-deployment -- READ-ONLY check that a deployed Algorand application runs the committed TEAL

Rust port of contracts/verify_deployment.py. It assembles the committed approval AND clear-state
TEAL with algod (POST /v2/teal/compile), reads the deployed programs (GET /v2/applications/{id})
and the network identity (GET /versions), and compares the bytecode byte for byte. It never
signs, never sends a transaction, and needs no account, key or mnemonic.

Usage: verify-deployment [OPTIONS]

Options:
  --app-id <ID>           application to inspect          [default: {default_app} (TestNet)]
  --algod <URL>           algod that serves the deployed programs
                                                  [default: https://testnet-api.algonode.cloud]
  --compile-url <URL>     independent algod that assembles the committed TEAL
                          [default: same as --algod]. Point it at a different provider (or a
                          local node) so one endpoint is not trusted for both halves.
  --approval-teal <PATH>  committed approval TEAL (alias: --teal)
                          [default: contracts/out/TrelyanInscription.approval.teal, found by
                          walking up from the current directory]
  --clear-teal <PATH>     committed clear-state TEAL
                          [default: contracts/out/TrelyanInscription.clear.teal]
  --timeout <SECONDS>     per-request timeout, 1-600                          [default: 30]
  -h, --help              print this help and exit 0

URLs must be https://, or http:// to localhost / 127.0.0.1 / [::1] only. Redirects are not
followed. HTTPS is done by the system `curl` executable, invoked directly (never via a shell).

Exit codes (same as contracts/verify_deployment.py):
  0  MATCH            both deployed programs are what the committed TEAL assembles to
  1  DRIFT            a deployed program differs from what the committed TEAL assembles to
  2  COULD NOT CHECK  network, missing artifact, bad response, usage or unexpected error;
                      never reported as agreement, never as drift

Trust note: assembling and serving both come from algod endpoints the operator chose. By
default ONE endpoint does both, so a dishonest endpoint could lie consistently across both;
--compile-url splits that trust. The result is only as strong as the weaker of the two sources.

Not ported: --recompile / --source. Re-deriving the TEAL from contracts/inscription.py needs the
puya (Python) toolchain; use `python contracts/verify_deployment.py --recompile`, or see the CI
job teal-matches-source.

Scope: bytecode identity on the network algod reports (TestNet by default). It says nothing
about MainNet, is not an audit of the contract, and is not an independent review of Falcon
signatures (the AVM falcon_verify opcode and this repo's signer share upstream algorand/falcon
code). det1024 is Algorand's deterministic Falcon variant; no FIPS 206 / FN-DSA claim is made.
";

enum Cli {
    Help,
    Run(Box<Config>),
}

fn main() -> ExitCode {
    std::panic::set_hook(Box::new(|info| {
        eprintln!("\nCOULD NOT CHECK: unexpected internal error: {info}");
        std::process::exit(2);
    }));

    let cli = match parse(std::env::args_os().skip(1).collect()) {
        Ok(cli) => cli,
        Err(message) => {
            eprintln!("verify-deployment: {message}\nRun with --help for usage. (exit 2)");
            return ExitCode::from(Verdict::CouldNotCheck.exit_code());
        }
    };
    let config = match cli {
        Cli::Help => {
            print!(
                "{}",
                HELP.replace("{default_app}", &DEFAULT_APP_ID.to_string())
            );
            return ExitCode::SUCCESS;
        }
        Cli::Run(config) => config,
    };

    // Render into memory, then write once: no console lock is held across the network calls.
    let mut buffer = Vec::new();
    let outcome = run(&config, &CurlTransport::system(), &mut buffer).and_then(|report| {
        let mut stdout = io::stdout().lock();
        stdout.write_all(&buffer)?;
        stdout.flush()?;
        Ok(report)
    });
    match outcome {
        Ok(report) => {
            let verdict = report.verdict();
            if verdict == Verdict::CouldNotCheck
                && let Some((program, problem)) = report.first_problem()
            {
                eprintln!(
                    "COULD NOT CHECK: {}: {}",
                    program.name(),
                    sanitize(&problem.to_string())
                );
            }
            ExitCode::from(verdict.exit_code())
        }
        Err(e) => {
            eprintln!("COULD NOT CHECK: the report could not be written: {e}");
            ExitCode::from(Verdict::CouldNotCheck.exit_code())
        }
    }
}

fn parse(args: Vec<OsString>) -> Result<Cli, String> {
    let mut app_id = DEFAULT_APP_ID;
    let mut algod = DEFAULT_ALGOD.to_owned();
    let mut compile_url = None;
    let mut approval: Option<PathBuf> = None;
    let mut clear: Option<PathBuf> = None;
    let mut timeout = DEFAULT_TIMEOUT;

    let mut it = args.into_iter();
    while let Some(raw) = it.next() {
        let arg = raw
            .to_str()
            .ok_or_else(|| format!("argument '{}' is not valid UTF-8", raw.display()))?;
        let (flag, inline) = match arg.split_once('=') {
            Some((flag, value)) if flag.starts_with("--") => (flag, Some(OsString::from(value))),
            _ => (arg, None),
        };
        let mut value = || {
            inline
                .clone()
                .or_else(|| it.next())
                .ok_or_else(|| format!("{flag} needs a value"))
        };
        match flag {
            "-h" | "--help" => return Ok(Cli::Help),
            "--app-id" => app_id = parse_app_id(&utf8(flag, value()?)?)?,
            "--algod" => algod = parse_url(flag, value()?)?,
            "--compile-url" => compile_url = Some(parse_url(flag, value()?)?),
            "--approval-teal" | "--teal" => approval = Some(PathBuf::from(value()?)),
            "--clear-teal" => clear = Some(PathBuf::from(value()?)),
            "--timeout" => timeout = parse_timeout(&utf8(flag, value()?)?)?,
            "--recompile" | "--source" => {
                return Err(format!(
                    "{flag} is not ported: re-deriving the TEAL from contracts/inscription.py \
                     needs the puya (Python) toolchain. Use `python contracts/verify_deployment.py \
                     --recompile`, or see the CI job teal-matches-source."
                ));
            }
            other => return Err(format!("unknown argument '{}'", sanitize(other))),
        }
    }

    let root = if approval.is_none() || clear.is_none() {
        let cwd = std::env::current_dir()
            .map_err(|e| format!("cannot read the current directory: {e}"))?;
        Some(discover_repo_root(&cwd).ok_or_else(|| {
            format!(
                "could not find {APPROVAL_TEAL} in {} or any parent directory; run inside the \
                 repository or pass --approval-teal and --clear-teal",
                cwd.display()
            )
        })?)
    } else {
        None
    };
    let teal = |explicit: Option<PathBuf>, relative: &str| match (explicit, &root) {
        (Some(path), _) => Ok(TealFile::new(path)),
        (None, Some(root)) => Ok(TealFile::in_repo(root, relative)),
        (None, None) => Err(format!("no path for {relative}")),
    };
    Ok(Cli::Run(Box::new(Config {
        app_id,
        algod,
        compile_url,
        approval_teal: teal(approval, APPROVAL_TEAL)?,
        clear_teal: teal(clear, CLEAR_TEAL)?,
        timeout,
    })))
}

fn utf8(flag: &str, value: OsString) -> Result<String, String> {
    value
        .into_string()
        .map_err(|v| format!("{flag} value '{}' is not valid UTF-8", v.display()))
}

fn parse_url(flag: &str, value: OsString) -> Result<String, String> {
    let value = utf8(flag, value)?;
    url::check(&value)
        .map_err(|reason| format!("{flag}: refused URL {}: {reason}", sanitize(&value)))?;
    Ok(value)
}

fn parse_app_id(value: &str) -> Result<u64, String> {
    match value.parse::<u64>() {
        Ok(0) | Err(_) => Err(format!(
            "--app-id '{}' is not an application id (a positive integer)",
            sanitize(value)
        )),
        Ok(id) => Ok(id),
    }
}

fn parse_timeout(value: &str) -> Result<Duration, String> {
    match value.parse::<u64>() {
        Ok(secs @ 1..=600) => Ok(Duration::from_secs(secs)),
        _ => Err(format!(
            "--timeout '{}' must be a whole number of seconds, 1-600",
            sanitize(value)
        )),
    }
}
