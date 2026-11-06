//! `teal-deploy-verify` — a READ-ONLY check that a deployed Algorand application runs the
//! bytecode this repository's committed TEAL assembles to.
//!
//! This is a Rust port of `contracts/verify_deployment.py`, written spec-first with the Python
//! script as the oracle: same question, same defaults ([`DEFAULT_APP_ID`] on Algorand
//! `TestNet`, [`DEFAULT_ALGOD`], [`DEFAULT_TIMEOUT`]), same exit codes — and `tests/oracle_coherence.rs`
//! fails if those defaults ever stop being the Python's:
//!
//! | exit | verdict           | meaning                                                              |
//! |------|-------------------|----------------------------------------------------------------------|
//! | 0    | `MATCH`           | every compared program is byte-for-byte what the committed TEAL assembles to |
//! | 1    | `DRIFT`           | a deployed program differs from what the committed TEAL assembles to |
//! | 2    | `COULD NOT CHECK` | the comparison did not complete — never agreement, never drift       |
//!
//! Chain of derivation. Every value is recomputed on every run; none is stored:
//!
//! ```text
//! contracts/out/TrelyanInscription.{approval,clear}.teal        [committed artifacts]
//!     |  algod POST /v2/teal/compile   (deterministic assembly for a given AVM version)
//!     v
//! expected bytecode --sha512_256--> expected fingerprint
//!                                       ==?   the verdict compares the BYTES; hashes are for display
//! algod GET /v2/applications/{id} --> deployed bytecode --sha512_256--> actual fingerprint
//! ```
//!
//! Where this goes further than the Python, every difference is a tightening, and each one is
//! printed or documented rather than silent:
//!
//! * **Both programs.** The Python compares the approval program only ("clear-state is not
//!   compared"). This compares the approval program AND the clear-state program; a `DRIFT` in
//!   either is a `DRIFT`.
//! * **Strict responses.** The application response's `id` must be the application asked for;
//!   base64 must be canonical; an empty program is not a program; a non-2xx status is never
//!   parsed. Each failure is `COULD NOT CHECK`, never a `MATCH` and never a `DRIFT`.
//! * **The network is read, not assumed.** `GET /versions` supplies the genesis id and hash, and
//!   the report names the network from them. That line is display-only: the verdict, as in the
//!   Python, is about bytecode.
//! * **Transport policy.** No redirects are followed; plain `http://` is refused except to a
//!   loopback node; see [`url`] and [`curl`].
//!
//! Trust note (carried over from the Python, and printed on every run): by default ONE algod
//! service both assembles the committed TEAL and serves the deployed program, so a dishonest
//! endpoint could lie consistently across both halves. `--compile-url` splits that trust across
//! two endpoints; the comparison is only as strong as the weaker of the two sources.
//!
//! What it does NOT prove: anything about `MainNet`; anything beyond bytecode identity (it is not an
//! audit of the contract); and it is not an independent review of Falcon signature verification,
//! because the AVM `falcon_verify` opcode and this repository's signer are built from the same
//! upstream `algorand/falcon` code. det1024 is Algorand's deterministic Falcon-1024 variant; no
//! FIPS 206 / FN-DSA claim is made or implied.

#![forbid(unsafe_code)]

pub mod curl;
pub mod url;

use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::time::Duration;

use base64::Engine as _;
use base64::engine::general_purpose::STANDARD as BASE64;
use serde_json::{Map, Value};
use sha2::{Digest, Sha512_256};
use thiserror::Error;

// ── defaults (identical to contracts/verify_deployment.py) ────────────────────────────────────

/// The `TestNet` application under review.
///
/// The same value as `DEFAULT_APP_ID` in `contracts/verify_deployment.py`, which
/// `tests/oracle_coherence.rs` enforces. Not a security constant: changing it only changes which
/// application is inspected, never what "correct" means.
///
/// For whoever retargets after a redeploy: clippy's `unreadable_literal` requires the digit
/// separators, so the app-id scan in `sdk/tests/test_app_id_references_are_coherent.py` (a
/// `7\d{8}` regex) does NOT see this literal. The oracle-coherence test is what ties it to the
/// Python's live claim; this is the ONLY place the Rust code spells the id.
pub const DEFAULT_APP_ID: u64 = 770_964_251;
/// The algod service used when `--algod` is not given.
pub const DEFAULT_ALGOD: &str = "https://testnet-api.algonode.cloud";
/// Per-request timeout when `--timeout` is not given.
pub const DEFAULT_TIMEOUT: Duration = Duration::from_secs(30);
/// The committed approval TEAL, relative to the repository root.
pub const APPROVAL_TEAL: &str = "contracts/out/TrelyanInscription.approval.teal";
/// The committed clear-state TEAL, relative to the repository root.
pub const CLEAR_TEAL: &str = "contracts/out/TrelyanInscription.clear.teal";
/// Largest response body accepted from algod. The real ones are a few kilobytes.
pub const MAX_RESPONSE_BYTES: usize = 16 * 1024 * 1024;
/// How much of an error body is quoted back to the operator.
const EXCERPT_CHARS: usize = 300;

/// Algorand `TestNet` genesis id and hash, as served by `GET /versions`.
pub const TESTNET_GENESIS: (&str, &str) = (
    "testnet-v1.0",
    "SGO1GKSzyE7IEPItTxCByw9x8FmnrCDexi9/cOUJOiI=",
);
/// Algorand `MainNet` genesis id and hash — recognised only so it can be named loudly.
pub const MAINNET_GENESIS: (&str, &str) = (
    "mainnet-v1.0",
    "wGHE2Pwdvd7S12BL5FaOP20EGYesN73ktiC1qzkkit8=",
);

// ── verdicts ────────────────────────────────────────────────────────────────────────────────

/// Outcome of one comparison, or of the whole run.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Verdict {
    /// The deployed bytes equal the assembled bytes.
    Match,
    /// Both sides were obtained and they differ.
    Drift,
    /// At least one side could not be obtained. Never agreement, never drift.
    CouldNotCheck,
}

impl Verdict {
    /// The process exit code, identical to `contracts/verify_deployment.py`.
    #[must_use]
    pub const fn exit_code(self) -> u8 {
        match self {
            Self::Match => 0,
            Self::Drift => 1,
            Self::CouldNotCheck => 2,
        }
    }

    /// The word printed at the start of a verdict line.
    #[must_use]
    pub const fn label(self) -> &'static str {
        match self {
            Self::Match => "MATCH",
            Self::Drift => "DRIFT",
            Self::CouldNotCheck => "COULD NOT CHECK",
        }
    }

    /// Overall verdict of several independent comparisons.
    ///
    /// `DRIFT` dominates: a difference that was actually observed is a finding even if another
    /// comparison could not complete, and reporting it as "could not check" would hide it. Then
    /// `COULD NOT CHECK` dominates `MATCH`. And an EMPTY set of comparisons is `COULD NOT CHECK`,
    /// not `MATCH`: comparing nothing is not agreement.
    #[must_use]
    pub fn combine(verdicts: impl IntoIterator<Item = Self>) -> Self {
        let mut seen_any = false;
        let mut incomplete = false;
        for verdict in verdicts {
            seen_any = true;
            match verdict {
                Self::Drift => return Self::Drift,
                Self::CouldNotCheck => incomplete = true,
                Self::Match => {}
            }
        }
        if incomplete || !seen_any {
            Self::CouldNotCheck
        } else {
            Self::Match
        }
    }
}

/// Which of the application's two programs.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Program {
    /// The approval program.
    Approval,
    /// The clear-state program — the one the Python verifier does not compare.
    ClearState,
}

impl Program {
    /// Both programs, in report order.
    pub const ALL: [Self; 2] = [Self::Approval, Self::ClearState];

    /// "approval program" / "clear-state program".
    #[must_use]
    pub const fn name(self) -> &'static str {
        match self {
            Self::Approval => "approval program",
            Self::ClearState => "clear-state program",
        }
    }

    /// "approval" / "clear-state".
    #[must_use]
    pub const fn short(self) -> &'static str {
        match self {
            Self::Approval => "approval",
            Self::ClearState => "clear-state",
        }
    }

    /// The field of `GET /v2/applications/{id}` → `params` that carries this program.
    #[must_use]
    pub const fn json_field(self) -> &'static str {
        match self {
            Self::Approval => "approval-program",
            Self::ClearState => "clear-state-program",
        }
    }
}

// ── transport ───────────────────────────────────────────────────────────────────────────────

/// An HTTP response as the transport received it. The library decides what the status means.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct HttpResponse {
    /// HTTP status code.
    pub status: u16,
    /// Response body, unmodified.
    pub body: Vec<u8>,
}

/// The request produced no HTTP response at all (process not started, DNS, TLS, timeout, ...).
#[derive(Debug, Clone, PartialEq, Eq, Error)]
#[error("{0}")]
pub struct TransportError(pub String);

/// The two read-only calls this tool makes. Nothing else: no signing, no transactions.
///
/// Production uses [`curl::CurlTransport`]; tests inject recorded responses.
pub trait Transport {
    /// One line identifying the transport, printed in the report.
    fn describe(&self) -> String;

    /// `GET url`, expecting JSON.
    ///
    /// # Errors
    ///
    /// [`TransportError`] when no HTTP response was obtained. A non-2xx status is NOT an error
    /// here; it is returned and judged by the caller.
    fn get(&self, url: &str, timeout: Duration) -> Result<HttpResponse, TransportError>;

    /// `POST url` with `teal` as the body, `Content-Type: text/plain` (algod's TEAL compile call).
    ///
    /// # Errors
    ///
    /// As for [`Transport::get`].
    fn post_teal(
        &self,
        url: &str,
        teal: &[u8],
        timeout: Duration,
    ) -> Result<HttpResponse, TransportError>;
}

// ── errors: every way the check can fail to complete ────────────────────────────────────────

/// Why one side of a comparison could not be obtained. Every variant means exit 2.
#[derive(Debug, Clone, PartialEq, Eq, Error)]
pub enum CheckError {
    /// The committed TEAL file is missing, unreadable or empty.
    #[error("committed artifact {path}: {reason}")]
    Artifact {
        /// The path as shown to the operator.
        path: String,
        /// What is wrong with it.
        reason: String,
    },
    /// The URL was refused by the policy in [`url`] before any request was made.
    #[error("refused URL {url}: {reason}")]
    Url {
        /// The refused URL.
        url: String,
        /// Why it was refused.
        reason: String,
    },
    /// No HTTP response was obtained.
    #[error("{request} failed: {reason}")]
    Transport {
        /// The request, e.g. `GET https://…/v2/applications/{id}`.
        request: String,
        /// What the transport reported.
        reason: String,
    },
    /// The server answered with a status outside 2xx (including redirects, which are not
    /// followed).
    #[error("{request} -> HTTP {status}: {excerpt}")]
    Status {
        /// The request.
        request: String,
        /// The HTTP status.
        status: u16,
        /// The start of the body, sanitised for the terminal.
        excerpt: String,
    },
    /// A 2xx response whose body is not what the algod API documents.
    #[error("{request}: unexpected response: {reason}")]
    Response {
        /// The request.
        request: String,
        /// What was wrong with the body.
        reason: String,
    },
}

// ── configuration ───────────────────────────────────────────────────────────────────────────

/// A committed TEAL file, and how its path is shown in the report.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TealFile {
    /// Where to read it.
    pub path: PathBuf,
    /// How to print it (repository-relative when it is the default).
    pub shown: String,
}

impl TealFile {
    /// A file given explicitly by the operator; shown as given.
    #[must_use]
    pub fn new(path: impl Into<PathBuf>) -> Self {
        let path = path.into();
        let shown = path.display().to_string();
        Self { path, shown }
    }

    /// A repository file, shown by its repository-relative path.
    #[must_use]
    pub fn in_repo(root: &Path, relative: &str) -> Self {
        Self {
            path: root.join(relative),
            shown: relative.to_owned(),
        }
    }
}

/// Everything one run needs. Defaults mirror `contracts/verify_deployment.py`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Config {
    /// Application id to inspect.
    pub app_id: u64,
    /// algod that serves the deployed programs (and, unless `compile_url` is set, assembles).
    pub algod: String,
    /// Optional independent algod that assembles the committed TEAL.
    pub compile_url: Option<String>,
    /// The committed approval TEAL.
    pub approval_teal: TealFile,
    /// The committed clear-state TEAL.
    pub clear_teal: TealFile,
    /// Per-request timeout.
    pub timeout: Duration,
}

impl Config {
    /// The defaults, with the TEAL files taken from the repository rooted at `root`.
    #[must_use]
    pub fn for_repo(root: &Path) -> Self {
        Self {
            app_id: DEFAULT_APP_ID,
            algod: DEFAULT_ALGOD.to_owned(),
            compile_url: None,
            approval_teal: TealFile::in_repo(root, APPROVAL_TEAL),
            clear_teal: TealFile::in_repo(root, CLEAR_TEAL),
            timeout: DEFAULT_TIMEOUT,
        }
    }

    /// The endpoint that assembles the committed TEAL.
    #[must_use]
    pub fn compile_endpoint(&self) -> &str {
        self.compile_url.as_deref().unwrap_or(&self.algod)
    }

    /// Whether assembling and serving come from two different endpoints. When in doubt this
    /// says "no" — the weaker claim.
    #[must_use]
    pub fn trust_is_split(&self) -> bool {
        normalise_endpoint(self.compile_endpoint()) != normalise_endpoint(&self.algod)
    }

    /// The TEAL file for `program`.
    #[must_use]
    pub const fn teal(&self, program: Program) -> &TealFile {
        match program {
            Program::Approval => &self.approval_teal,
            Program::ClearState => &self.clear_teal,
        }
    }
}

fn normalise_endpoint(url: &str) -> String {
    url.trim_end_matches('/').to_ascii_lowercase()
}

/// The nearest ancestor of `start` (inclusive) that contains the committed approval TEAL.
#[must_use]
pub fn discover_repo_root(start: &Path) -> Option<PathBuf> {
    start
        .ancestors()
        .find(|dir| dir.join(APPROVAL_TEAL).is_file())
        .map(Path::to_path_buf)
}

// ── the committed side ──────────────────────────────────────────────────────────────────────

/// A committed TEAL file as read from disk.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Teal {
    /// The exact bytes; sent to algod unmodified.
    pub bytes: Vec<u8>,
    /// The AVM version from a leading `#pragma version N` line, if there is one. Display only.
    pub pragma_version: Option<String>,
}

/// Read a committed TEAL file.
///
/// # Errors
///
/// [`CheckError::Artifact`] if the file cannot be read or is empty (or whitespace only): there is
/// nothing to assemble, and assembling nothing must not be allowed to look like a result.
pub fn read_teal(file: &TealFile) -> Result<Teal, CheckError> {
    let artifact = |reason: String| CheckError::Artifact {
        path: file.shown.clone(),
        reason,
    };
    let bytes = match std::fs::read(&file.path) {
        Ok(bytes) => bytes,
        Err(e) if e.kind() == io::ErrorKind::NotFound => {
            return Err(artifact("not found".to_owned()));
        }
        Err(e) => return Err(artifact(format!("cannot be read: {e}"))),
    };
    if bytes.iter().all(u8::is_ascii_whitespace) {
        return Err(artifact(format!(
            "is empty ({} B, no TEAL to assemble)",
            bytes.len()
        )));
    }
    let pragma_version = bytes
        .split(|&b| b == b'\n')
        .next()
        .and_then(|line| line.strip_prefix(b"#pragma version "))
        .map(|v| String::from_utf8_lossy(v).trim().to_owned())
        .filter(|v| !v.is_empty() && v.bytes().all(|b| b.is_ascii_digit()));
    Ok(Teal {
        bytes,
        pragma_version,
    })
}

// ── the network side ────────────────────────────────────────────────────────────────────────

/// `base` + `path`, with trailing slashes on `base` removed (as the Python's `rstrip('/')`).
#[must_use]
pub fn endpoint(base: &str, path: &str) -> String {
    format!("{}{path}", base.trim_end_matches('/'))
}

/// Assemble TEAL to bytecode with algod `POST /v2/teal/compile`.
///
/// # Errors
///
/// Any [`CheckError`] except `Artifact`: refused URL, no response, non-2xx status, or a body
/// without a canonical-base64, non-empty `result`.
pub fn assemble(
    transport: &dyn Transport,
    compile_base: &str,
    program: Program,
    teal: &[u8],
    timeout: Duration,
) -> Result<Vec<u8>, CheckError> {
    let url = endpoint(compile_base, "/v2/teal/compile");
    let request = format!("POST {url} ({} TEAL)", program.short());
    let body = request_json(&request, &url, |u| transport.post_teal(u, teal, timeout))?;
    let result = body.get("result").and_then(Value::as_str).ok_or_else(|| {
        response_error(
            &request,
            "no string field \"result\" in the compile response",
        )
    })?;
    decode_program(&request, "result", result)
}

/// The two deployed programs, each obtained or not.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Deployed {
    /// `params.approval-program`, decoded.
    pub approval: Result<Vec<u8>, CheckError>,
    /// `params.clear-state-program`, decoded.
    pub clear_state: Result<Vec<u8>, CheckError>,
}

/// Fetch both deployed programs with ONE `GET /v2/applications/{id}`.
#[must_use]
pub fn fetch_deployed(
    transport: &dyn Transport,
    algod: &str,
    app_id: u64,
    timeout: Duration,
) -> Deployed {
    let url = endpoint(algod, &format!("/v2/applications/{app_id}"));
    let request = format!("GET {url}");
    let params = request_json(&request, &url, |u| transport.get(u, timeout))
        .and_then(|body| application_params(&request, app_id, body));
    match params {
        Ok(params) => Deployed {
            approval: deployed_program(&request, app_id, &params, Program::Approval),
            clear_state: deployed_program(&request, app_id, &params, Program::ClearState),
        },
        Err(e) => Deployed {
            approval: Err(e.clone()),
            clear_state: Err(e),
        },
    }
}

fn application_params(
    request: &str,
    app_id: u64,
    mut body: Map<String, Value>,
) -> Result<Map<String, Value>, CheckError> {
    // algod's Application object requires `id`. Checking it closes a hole the Python leaves open:
    // a proxy or endpoint that answers for a DIFFERENT application would otherwise be compared
    // as if it were this one.
    match body.get("id").and_then(Value::as_u64) {
        Some(id) if id == app_id => {}
        Some(other) => {
            return Err(response_error(
                request,
                &format!("algod answered for application {other}, not {app_id}"),
            ));
        }
        None => return Err(response_error(request, "no numeric \"id\" field")),
    }
    match body.remove("params") {
        Some(Value::Object(params)) => Ok(params),
        _ => Err(response_error(request, "no \"params\" object")),
    }
}

fn deployed_program(
    request: &str,
    app_id: u64,
    params: &Map<String, Value>,
    program: Program,
) -> Result<Vec<u8>, CheckError> {
    let field = program.json_field();
    match params.get(field).and_then(Value::as_str) {
        Some(b64) if !b64.is_empty() => decode_program(request, field, b64),
        _ => Err(response_error(
            request,
            &format!("application {app_id} returned no {field}"),
        )),
    }
}

/// Which network an algod says it serves, from `GET /versions`.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum Network {
    /// Genesis id AND hash are `TestNet`'s.
    TestNet,
    /// Genesis id AND hash are `MainNet`'s.
    MainNet,
    /// Anything else (`LocalNet`, `BetaNet`, or a mismatched id/hash pair).
    Other {
        /// `genesis_id` as served.
        genesis_id: String,
        /// `genesis_hash_b64` as served.
        genesis_hash: String,
    },
}

impl Network {
    /// Classify a genesis id/hash pair. Both must match for a named network: an id alone is
    /// trivially chosen by whoever runs a network.
    #[must_use]
    pub fn classify(genesis_id: &str, genesis_hash: &str) -> Self {
        match (genesis_id, genesis_hash) {
            pair if pair == TESTNET_GENESIS => Self::TestNet,
            pair if pair == MAINNET_GENESIS => Self::MainNet,
            _ => Self::Other {
                genesis_id: genesis_id.to_owned(),
                genesis_hash: genesis_hash.to_owned(),
            },
        }
    }
}

/// Ask algod which network it serves (`GET /versions`). Display only; never changes a verdict.
///
/// # Errors
///
/// As for [`assemble`], when the call fails or lacks `genesis_id` / `genesis_hash_b64`.
pub fn fetch_network(
    transport: &dyn Transport,
    algod: &str,
    timeout: Duration,
) -> Result<Network, CheckError> {
    let url = endpoint(algod, "/versions");
    let request = format!("GET {url}");
    let body = request_json(&request, &url, |u| transport.get(u, timeout))?;
    let field = |name: &str| {
        body.get(name)
            .and_then(Value::as_str)
            .ok_or_else(|| response_error(&request, &format!("no string field \"{name}\"")))
    };
    Ok(Network::classify(
        field("genesis_id")?,
        field("genesis_hash_b64")?,
    ))
}

fn request_json(
    request: &str,
    url: &str,
    send: impl FnOnce(&str) -> Result<HttpResponse, TransportError>,
) -> Result<Map<String, Value>, CheckError> {
    url::check(url).map_err(|reason| CheckError::Url {
        url: url.to_owned(),
        reason,
    })?;
    let response = send(url).map_err(|e| CheckError::Transport {
        request: request.to_owned(),
        reason: e.0,
    })?;
    if !(200..300).contains(&response.status) {
        return Err(CheckError::Status {
            request: request.to_owned(),
            status: response.status,
            excerpt: excerpt(&response.body),
        });
    }
    if response.body.len() > MAX_RESPONSE_BYTES {
        return Err(response_error(
            request,
            &format!(
                "body is {} B, over the {MAX_RESPONSE_BYTES} B limit",
                response.body.len()
            ),
        ));
    }
    match serde_json::from_slice::<Value>(&response.body) {
        Ok(Value::Object(map)) => Ok(map),
        Ok(_) => Err(response_error(request, "body is JSON but not an object")),
        Err(e) => Err(response_error(
            request,
            &format!("body is not valid JSON ({e})"),
        )),
    }
}

fn decode_program(request: &str, field: &str, b64: &str) -> Result<Vec<u8>, CheckError> {
    let bytes = BASE64.decode(b64).map_err(|e| {
        response_error(
            request,
            &format!("field \"{field}\" is not canonical base64 ({e})"),
        )
    })?;
    if bytes.is_empty() {
        return Err(response_error(
            request,
            &format!("field \"{field}\" decodes to zero bytes, which is not an AVM program"),
        ));
    }
    Ok(bytes)
}

fn response_error(request: &str, reason: &str) -> CheckError {
    CheckError::Response {
        request: request.to_owned(),
        reason: reason.to_owned(),
    }
}

// ── the check ───────────────────────────────────────────────────────────────────────────────

/// One program: the committed TEAL, what it assembles to, and what is deployed.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProgramReport {
    /// Which program.
    pub program: Program,
    /// The committed TEAL file.
    pub teal_file: TealFile,
    /// The committed TEAL as read.
    pub teal: Result<Teal, CheckError>,
    /// The committed TEAL, assembled by the compile endpoint.
    pub expected: Result<Vec<u8>, CheckError>,
    /// The program the application actually serves.
    pub actual: Result<Vec<u8>, CheckError>,
}

impl ProgramReport {
    /// `MATCH` only when both sides were obtained and are byte-for-byte equal.
    #[must_use]
    pub fn verdict(&self) -> Verdict {
        match (&self.expected, &self.actual) {
            (Ok(expected), Ok(actual)) if expected == actual => Verdict::Match,
            (Ok(_), Ok(_)) => Verdict::Drift,
            _ => Verdict::CouldNotCheck,
        }
    }

    /// Why this program could not be checked, if it could not.
    #[must_use]
    pub fn problem(&self) -> Option<&CheckError> {
        self.expected
            .as_ref()
            .err()
            .or_else(|| self.actual.as_ref().err())
    }
}

/// Everything one run found.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Report {
    /// Application inspected.
    pub app_id: u64,
    /// Endpoint that served the deployed programs.
    pub algod: String,
    /// Endpoint that assembled the committed TEAL.
    pub compile_endpoint: String,
    /// Whether those are two different endpoints.
    pub trust_split: bool,
    /// The transport's self-description.
    pub transport: String,
    /// What algod said about its network (display only).
    pub network: Result<Network, CheckError>,
    /// The approval program.
    pub approval: ProgramReport,
    /// The clear-state program.
    pub clear_state: ProgramReport,
}

impl Report {
    /// Both program reports, in order.
    #[must_use]
    pub const fn programs(&self) -> [&ProgramReport; 2] {
        [&self.approval, &self.clear_state]
    }

    /// The overall verdict: [`Verdict::combine`] over BOTH programs.
    #[must_use]
    pub fn verdict(&self) -> Verdict {
        Verdict::combine(self.programs().map(ProgramReport::verdict))
    }

    /// The first reason a program could not be checked.
    #[must_use]
    pub fn first_problem(&self) -> Option<(Program, &CheckError)> {
        self.programs()
            .into_iter()
            .find_map(|p| p.problem().map(|e| (p.program, e)))
    }
}

/// Run the comparison. Makes exactly four read-only requests: two compiles, one application
/// read, one `/versions` read. Never signs, never sends a transaction.
#[must_use]
pub fn check(config: &Config, transport: &dyn Transport) -> Report {
    let compile = config.compile_endpoint();
    // Same order as the Python: assemble the committed side first, then read the chain.
    let [
        (approval_teal, approval_expected),
        (clear_teal, clear_expected),
    ] = Program::ALL.map(|program| {
        let teal = read_teal(config.teal(program));
        let expected = teal
            .as_ref()
            .map_err(Clone::clone)
            .and_then(|teal| assemble(transport, compile, program, &teal.bytes, config.timeout));
        (teal, expected)
    });
    let deployed = fetch_deployed(transport, &config.algod, config.app_id, config.timeout);
    let network = fetch_network(transport, &config.algod, config.timeout);
    Report {
        app_id: config.app_id,
        algod: config.algod.clone(),
        compile_endpoint: compile.to_owned(),
        trust_split: config.trust_is_split(),
        transport: transport.describe(),
        network,
        approval: ProgramReport {
            program: Program::Approval,
            teal_file: config.approval_teal.clone(),
            teal: approval_teal,
            expected: approval_expected,
            actual: deployed.approval,
        },
        clear_state: ProgramReport {
            program: Program::ClearState,
            teal_file: config.clear_teal.clone(),
            teal: clear_teal,
            expected: clear_expected,
            actual: deployed.clear_state,
        },
    }
}

/// [`check`], then [`render`] to `out`.
///
/// # Errors
///
/// Only if writing the report fails. The caller should then exit 2: a result nobody saw has
/// not been reported.
pub fn run(config: &Config, transport: &dyn Transport, out: &mut dyn Write) -> io::Result<Report> {
    let report = check(config, transport);
    render(&report, out)?;
    Ok(report)
}

// ── presentation ────────────────────────────────────────────────────────────────────────────

/// Algorand's program hash: SHA-512/256 (not SHA-256), lowercase hex.
#[must_use]
pub fn sha512_256_hex(bytes: &[u8]) -> String {
    hex(&Sha512_256::digest(bytes))
}

fn hex(bytes: &[u8]) -> String {
    const DIGITS: &[u8; 16] = b"0123456789abcdef";
    let mut out = String::with_capacity(bytes.len() * 2);
    for &b in bytes {
        out.push(char::from(DIGITS[usize::from(b >> 4)]));
        out.push(char::from(DIGITS[usize::from(b & 0x0f)]));
    }
    out
}

/// Index of the first byte at which `a` and `b` differ (the shorter length if one is a prefix
/// of the other), or `None` if they are equal.
#[must_use]
pub fn first_difference(a: &[u8], b: &[u8]) -> Option<usize> {
    if a == b {
        return None;
    }
    Some(
        a.iter()
            .zip(b)
            .position(|(x, y)| x != y)
            .unwrap_or_else(|| a.len().min(b.len())),
    )
}

/// Make text from the network safe to print: control characters (including ESC, so no terminal
/// escape sequences) and bidirectional-override characters are shown escaped, not interpreted.
#[must_use]
pub fn sanitize(text: &str) -> String {
    let mut out = String::with_capacity(text.len());
    for c in text.chars() {
        if c.is_control() || is_bidi_control(c) {
            out.extend(c.escape_default());
        } else {
            out.push(c);
        }
    }
    out
}

const fn is_bidi_control(c: char) -> bool {
    matches!(c, '\u{061C}' | '\u{200E}' | '\u{200F}' | '\u{202A}'..='\u{202E}' | '\u{2066}'..='\u{2069}')
}

fn excerpt(body: &[u8]) -> String {
    let text = String::from_utf8_lossy(body);
    let mut shown: String = text.chars().take(EXCERPT_CHARS).collect();
    if text.chars().nth(EXCERPT_CHARS).is_some() {
        shown.push_str("...");
    }
    sanitize(shown.trim_end())
}

const RULE: &str = "------------------------------------------------------------------------------";

const BANNER: &str = "\
TRELYAN verify-deployment  (Rust port of contracts/verify_deployment.py)
READ-ONLY: two TEAL compiles and two GETs. No keys, no signing, no transactions.
";

/// Indent of continuation lines in the header.
const PAD: &str = "             ";

// NB: no `\` line continuation on these three: it would also strip the first line's indent.
const TRUST_ONE_ENDPOINT: &str =
    "             ONE endpoint does both halves, so a dishonest endpoint could lie
             consistently across both. Pass --compile-url <independent node> to
             split that trust.
";

const TRUST_SPLIT: &str =
    "             Two different endpoints: a consistent lie would need both of them.\n";

const REDEPLOY: &str =
    "        AWAITING TESTNET REDEPLOY. Update/Delete are blocked (I1/I5), so the app
        cannot be patched in place: deploy a NEW TestNet app from the committed
        TEAL, then retarget the app id. Checklist: BLOCKERS.md. Until this is
        green, a review of this source is not a review of the live app.
";

const SCOPE: &str = "\
SCOPE   Bytecode identity only. It says nothing about MainNet, it is not an audit
        of the contract, and it is not an independent review of Falcon signatures:
        the AVM falcon_verify opcode and this repo's signer are built from the same
        upstream algorand/falcon code. det1024 is Algorand's deterministic Falcon
        variant; no FIPS 206 / FN-DSA claim is made.
";

/// Write the human-readable report. ASCII only, so it survives any console or log.
///
/// Every `MATCH` / `DRIFT` / `COULD NOT CHECK` word in it comes from [`ProgramReport::verdict`]
/// and [`Report::verdict`], i.e. from an actual byte comparison or an actual failure.
///
/// # Errors
///
/// Any error from `out`.
pub fn render(report: &Report, out: &mut dyn Write) -> io::Result<()> {
    writeln!(out, "{RULE}")?;
    out.write_all(BANNER.as_bytes())?;
    writeln!(out, "{RULE}")?;
    render_network(report, out)?;
    render_endpoints(report, out)?;
    writeln!(out)?;
    render_sides(report, out)?;
    writeln!(out)?;
    for program in report.programs() {
        render_verdict_line(program, out)?;
    }
    writeln!(out)?;
    render_result(report, out)?;
    writeln!(out)?;
    out.write_all(SCOPE.as_bytes())?;
    writeln!(out, "{RULE}")
}

fn network_phrase(report: &Report) -> String {
    match &report.network {
        Ok(Network::TestNet) => format!("TestNet application {}", report.app_id),
        Ok(Network::MainNet) => format!("MAINNET application {}", report.app_id),
        Ok(Network::Other { genesis_id, .. }) => {
            format!(
                "application {} on network '{}'",
                report.app_id,
                sanitize(genesis_id)
            )
        }
        Err(_) => format!("application {} (network unconfirmed)", report.app_id),
    }
}

fn render_network(report: &Report, out: &mut dyn Write) -> io::Result<()> {
    let source = format!(
        "{PAD}(per GET {})",
        sanitize(&endpoint(&report.algod, "/versions"))
    );
    let (headline, id, hash) = match &report.network {
        Ok(Network::TestNet) => (
            "Algorand TestNet -- NOT MainNet",
            TESTNET_GENESIS.0.to_owned(),
            TESTNET_GENESIS.1.to_owned(),
        ),
        Ok(Network::MainNet) => (
            "Algorand MAINNET -- WARNING: this tool's default target is TestNet",
            MAINNET_GENESIS.0.to_owned(),
            MAINNET_GENESIS.1.to_owned(),
        ),
        Ok(Network::Other {
            genesis_id,
            genesis_hash,
        }) => (
            "NOT TestNet and NOT MainNet",
            sanitize(genesis_id),
            sanitize(genesis_hash),
        ),
        Err(e) => {
            writeln!(
                out,
                "  network    UNCONFIRMED: {}",
                sanitize(&e.to_string())
            )?;
            return writeln!(
                out,
                "{PAD}(display only: the verdict is about bytecode, as in the Python)"
            );
        }
    };
    writeln!(out, "  network    {headline}")?;
    writeln!(out, "{PAD}genesis {id} {hash}")?;
    writeln!(out, "{source}")
}

fn render_endpoints(report: &Report, out: &mut dyn Write) -> io::Result<()> {
    let compile = sanitize(&report.compile_endpoint);
    let algod = sanitize(&report.algod);
    writeln!(out, "  app        {}", report.app_id)?;
    writeln!(out, "  compares   approval program AND clear-state program")?;
    writeln!(
        out,
        "{PAD}(contracts/verify_deployment.py compares the approval program only)"
    )?;
    writeln!(out, "  transport  {}", sanitize(&report.transport))?;
    writeln!(
        out,
        "  trust      assembled by  {compile}  (POST /v2/teal/compile)"
    )?;
    writeln!(
        out,
        "{PAD}served by     {algod}  (GET /v2/applications/{})",
        report.app_id
    )?;
    writeln!(
        out,
        "{PAD}Both are algod endpoints chosen by the operator, not by this tool."
    )?;
    let trust = if report.trust_split {
        TRUST_SPLIT
    } else {
        TRUST_ONE_ENDPOINT
    };
    out.write_all(trust.as_bytes())?;
    writeln!(
        out,
        "{PAD}The result is only as strong as the weaker of the two sources."
    )
}

fn render_sides(report: &Report, out: &mut dyn Write) -> io::Result<()> {
    let width = report
        .programs()
        .iter()
        .map(|p| p.teal_file.shown.len())
        .max()
        .unwrap_or(0);
    writeln!(out, "[1] committed TEAL (read from disk)")?;
    for p in report.programs() {
        let name = p.program.short();
        let path = sanitize(&p.teal_file.shown);
        match &p.teal {
            Ok(teal) => {
                let pragma = teal.pragma_version.as_ref().map_or_else(
                    || "no #pragma version line".to_owned(),
                    |v| format!("#pragma version {v}"),
                );
                let len = teal.bytes.len();
                writeln!(out, "    {name:<12} {path:<width$}  {len:>6} B  {pragma}")?;
            }
            Err(e) => writeln!(out, "    {name:<12} UNUSABLE: {}", sanitize(&e.to_string()))?,
        }
    }
    let compile = sanitize(&report.compile_endpoint);
    writeln!(
        out,
        "[2] expected bytecode = committed TEAL assembled by {compile}"
    )?;
    for p in report.programs() {
        render_bytes(p.program, &p.expected, "NOT ASSEMBLED", out)?;
    }
    let algod = sanitize(&report.algod);
    writeln!(
        out,
        "[3] actual bytecode = deployed app {} served by {algod}",
        report.app_id
    )?;
    for p in report.programs() {
        render_bytes(p.program, &p.actual, "NOT FETCHED", out)?;
    }
    Ok(())
}

fn render_bytes(
    program: Program,
    side: &Result<Vec<u8>, CheckError>,
    failed: &str,
    out: &mut dyn Write,
) -> io::Result<()> {
    let name = program.short();
    match side {
        Ok(bytes) => {
            let (len, hash) = (bytes.len(), sha512_256_hex(bytes));
            writeln!(out, "    {name:<12} {len:>6} B  sha512_256 {hash}")
        }
        Err(e) => writeln!(out, "    {name:<12} {failed}: {}", sanitize(&e.to_string())),
    }
}

fn render_verdict_line(p: &ProgramReport, out: &mut dyn Write) -> io::Result<()> {
    let verdict = p.verdict();
    let label = verdict.label();
    let name = p.program.name();
    match (verdict, &p.expected, &p.actual) {
        (Verdict::Match, Ok(expected), Ok(actual)) => {
            let (deployed, assembled) = (actual.len(), expected.len());
            writeln!(
                out,
                "{label}  {name:<19}  deployed {deployed} B == {assembled} B assembled from the committed TEAL"
            )
        }
        (Verdict::Drift, Ok(expected), Ok(actual)) => {
            let (deployed, assembled) = (actual.len(), expected.len());
            let at = first_difference(expected, actual).unwrap_or_default();
            writeln!(
                out,
                "{label}  {name:<19}  deployed {deployed} B != {assembled} B assembled from the committed TEAL"
            )?;
            writeln!(out, "       {:<19}  first difference at byte {at}", "")
        }
        _ => {
            let why = p
                .problem()
                .map_or_else(|| "unknown".to_owned(), |e| sanitize(&e.to_string()));
            writeln!(out, "{label}  {name}: {why}")
        }
    }
}

fn render_result(report: &Report, out: &mut dyn Write) -> io::Result<()> {
    let verdict = report.verdict();
    let (label, code, subject) = (verdict.label(), verdict.exit_code(), network_phrase(report));
    writeln!(out, "RESULT  {label} (exit {code}) for {subject}:")?;
    match verdict {
        Verdict::Match => {
            writeln!(
                out,
                "        the deployed approval AND clear-state programs are byte-for-byte"
            )?;
            writeln!(out, "        what the committed TEAL assembles to.")
        }
        Verdict::Drift => {
            let drifted: Vec<&str> = report
                .programs()
                .into_iter()
                .filter(|p| p.verdict() == Verdict::Drift)
                .map(|p| p.program.name())
                .collect();
            writeln!(
                out,
                "        the deployed bytecode is NOT what the committed TEAL assembles to"
            )?;
            writeln!(out, "        (drifted: {}).", drifted.join(" and "))?;
            out.write_all(REDEPLOY.as_bytes())
        }
        Verdict::CouldNotCheck => {
            writeln!(
                out,
                "        the comparison did not complete. This is neither agreement nor"
            )?;
            writeln!(out, "        drift.")
        }
    }
}

#[cfg(test)]
mod tests {
    #![allow(clippy::expect_used, clippy::unwrap_used, clippy::panic)]

    use super::*;

    #[test]
    fn sha512_256_known_answers() {
        // FIPS 180-4 example for SHA-512/256 ("abc") and the empty string. A SHA-256 slipped in
        // here would print ba7816bf… for "abc" instead.
        assert_eq!(
            sha512_256_hex(b"abc"),
            "53048e2681941ef99b2e29b76b4c7dabe4c2d0c634fc6d46e0e2f13107e7af23"
        );
        assert_eq!(
            sha512_256_hex(b""),
            "c672b8d1ef56ed28ab87c3622c5114069bdd3ad7b8f9737498d0c01ecef0967a"
        );
    }

    #[test]
    fn combine_precedence_and_the_empty_case() {
        use Verdict::{CouldNotCheck as C, Drift as D, Match as M};
        assert_eq!(Verdict::combine([M, M]), M);
        assert_eq!(Verdict::combine([M, D]), D);
        assert_eq!(Verdict::combine([D, M]), D);
        assert_eq!(Verdict::combine([M, C]), C);
        assert_eq!(Verdict::combine([C, M]), C);
        assert_eq!(Verdict::combine([C, D]), D);
        assert_eq!(Verdict::combine([D, C]), D);
        assert_eq!(Verdict::combine([C, C]), C);
        // Comparing nothing is not agreement.
        assert_eq!(Verdict::combine([]), C);
    }

    #[test]
    fn exit_codes_are_the_pythons() {
        assert_eq!(Verdict::Match.exit_code(), 0);
        assert_eq!(Verdict::Drift.exit_code(), 1);
        assert_eq!(Verdict::CouldNotCheck.exit_code(), 2);
    }

    #[test]
    fn first_difference_finds_the_byte() {
        assert_eq!(first_difference(b"abc", b"abc"), None);
        assert_eq!(first_difference(b"abc", b"abd"), Some(2));
        assert_eq!(first_difference(b"abc", b"ab"), Some(2));
        assert_eq!(first_difference(b"", b"x"), Some(0));
    }

    #[test]
    fn sanitize_neutralises_terminal_escapes_and_bidi_overrides() {
        let hostile = "ok\u{1b}[2J\u{1b}]0;pwned\u{7}\r\nMATCH\u{202e}reversed";
        let shown = sanitize(hostile);
        assert!(
            !shown.chars().any(|c| c.is_control() || is_bidi_control(c)),
            "{shown:?}"
        );
        assert!(shown.contains("\\u{1b}[2J"), "{shown}");
        assert!(shown.contains("\\r\\nMATCH"), "{shown}");
        assert!(shown.contains("\\u{202e}"), "{shown}");
        // Idempotent: escaping already-escaped text changes nothing.
        assert_eq!(sanitize(&shown), shown);
    }

    #[test]
    fn excerpt_truncates_and_sanitises() {
        let long = vec![b'x'; EXCERPT_CHARS + 50];
        let shown = excerpt(&long);
        assert_eq!(shown.len(), EXCERPT_CHARS + 3);
        assert!(shown.ends_with("..."));
        assert_eq!(excerpt(b"{\"message\":\"bad\"}\n"), "{\"message\":\"bad\"}");
    }

    #[test]
    fn network_needs_both_genesis_id_and_hash() {
        assert_eq!(
            Network::classify(TESTNET_GENESIS.0, TESTNET_GENESIS.1),
            Network::TestNet
        );
        assert_eq!(
            Network::classify(MAINNET_GENESIS.0, MAINNET_GENESIS.1),
            Network::MainNet
        );
        // A network that merely CALLS itself testnet-v1.0 is not TestNet.
        assert!(matches!(
            Network::classify(TESTNET_GENESIS.0, MAINNET_GENESIS.1),
            Network::Other { .. }
        ));
    }

    #[test]
    fn endpoint_strips_trailing_slashes_like_rstrip() {
        assert_eq!(
            endpoint("https://a.example//", "/v2/x"),
            "https://a.example/v2/x"
        );
        assert_eq!(
            endpoint("https://a.example", "/v2/x"),
            "https://a.example/v2/x"
        );
    }

    #[test]
    fn trust_split_is_only_claimed_for_really_different_endpoints() {
        let mut config = Config::for_repo(Path::new("."));
        assert!(!config.trust_is_split());
        config.compile_url = Some(format!("{DEFAULT_ALGOD}/"));
        assert!(
            !config.trust_is_split(),
            "a trailing slash is the same endpoint"
        );
        config.compile_url = Some("https://mainnet-api.example".to_owned());
        assert!(config.trust_is_split());
    }

    #[test]
    fn pragma_is_read_from_the_first_line_only() {
        let dir = std::env::temp_dir().join(format!("tdv-pragma-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let file = |name: &str, body: &[u8]| {
            let path = dir.join(name);
            std::fs::write(&path, body).unwrap();
            read_teal(&TealFile::new(path))
        };
        assert_eq!(
            file("a.teal", b"#pragma version 12\nint 1\n")
                .unwrap()
                .pragma_version
                .as_deref(),
            Some("12")
        );
        assert_eq!(
            file("b.teal", b"#pragma version 12\r\nint 1\r\n")
                .unwrap()
                .pragma_version
                .as_deref(),
            Some("12")
        );
        assert_eq!(
            file("c.teal", b"int 1\n#pragma version 12\n")
                .unwrap()
                .pragma_version,
            None
        );
        assert!(matches!(
            file("d.teal", b""),
            Err(CheckError::Artifact { .. })
        ));
        assert!(matches!(
            file("e.teal", b" \n\t\r\n"),
            Err(CheckError::Artifact { .. })
        ));
        std::fs::remove_dir_all(&dir).unwrap();
    }
}
