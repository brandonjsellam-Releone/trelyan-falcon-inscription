//! Shared test doubles: an in-process fake algod that replays RECORDED responses, a loopback
//! HTTP server for exercising the real `curl` transport, and temp-dir helpers.
//!
//! The fixtures in `tests/fixtures/` were recorded once, read-only, on 2026-11-05 from
//! `https://testnet-api.algonode.cloud` with the system curl. They are a FROZEN, self-consistent
//! record — the two TEAL inputs are copies of `contracts/out/` as committed at `a886b7d`, kept next
//! to what algod answered for them — so the offline suite stays true after any future redeploy
//! and never has to be "updated" to pass:
//!
//! | fixture                     | request                                                       |
//! |-----------------------------|---------------------------------------------------------------|
//! | `application_recorded.json` | `GET /v2/applications/{RECORDED_APP_ID}`                      |
//! | `recorded_approval.teal`    | copy of `contracts/out/TrelyanInscription.approval.teal`      |
//! | `recorded_clear.teal`       | copy of `contracts/out/TrelyanInscription.clear.teal`         |
//! | `compile_approval.json`     | `POST /v2/teal/compile` ← `recorded_approval.teal`            |
//! | `compile_clear.json`        | `POST /v2/teal/compile` ← `recorded_clear.teal`               |
//! | `compile_error_400.json`    | `POST /v2/teal/compile` ← `#pragma version 12\nnot_an_opcode\n` (HTTP 400) |
//! | `versions_testnet.json`     | `GET /versions`                                               |
//! | `app_not_found_404.json`    | `GET /v2/applications/1` (HTTP 404)                           |
//!
//! They are public chain data. No key, account or token was involved in recording them.
//! Every file is byte-for-byte as recorded EXCEPT `application_recorded.json`, from which ONE
//! field was removed afterwards, with `jq -cj 'del(.params["global-state"])'`: gitleaks'
//! `generic-api-key` heuristic fires on its base64 state-variable NAMES (`YWRtaW4=` = `admin`,
//! `Y2VsbHNfcmVnaXN0ZXJlZA==` = `cells_registered` — the same false positive `.gitleaks.toml`
//! documents for the ARC56 spec), and this verifier never reads global state. `id`,
//! `params.approval-program` and `params.clear-state-program` are untouched.
//! `application_recorded.json` necessarily contains the recorded application id; it is FROZEN
//! EVIDENCE in the sense of `sdk/tests/test_app_id_references_are_coherent.py` and must never be
//! retargeted.

#![allow(dead_code, clippy::expect_used, clippy::unwrap_used, clippy::panic)]

use std::cell::RefCell;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU32, Ordering};
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use base64::Engine as _;
use base64::engine::general_purpose::STANDARD as BASE64;
use serde_json::Value;
use teal_deploy_verify::{
    Config, HttpResponse, Report, TealFile, Transport, TransportError, discover_repo_root, render,
};

// ── the frozen recording ────────────────────────────────────────────────────────────────────

/// The application the recording is of. Frozen: a redeploy changes `DEFAULT_APP_ID`, never this.
pub const RECORDED_APP_ID: u64 = 770_964_251;
pub const RECORDED_APPROVAL_TEAL: &str = "recorded_approval.teal";
pub const RECORDED_CLEAR_TEAL: &str = "recorded_clear.teal";

pub fn fixture_path(name: &str) -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures")
        .join(name)
}

pub fn fixture(name: &str) -> Vec<u8> {
    let path = fixture_path(name);
    std::fs::read(&path).unwrap_or_else(|e| panic!("fixture {}: {e}", path.display()))
}

/// The defaults, pointed at the frozen recording: its application and its two TEAL inputs.
pub fn recorded_config() -> Config {
    Config {
        app_id: RECORDED_APP_ID,
        approval_teal: TealFile::new(fixture_path(RECORDED_APPROVAL_TEAL)),
        clear_teal: TealFile::new(fixture_path(RECORDED_CLEAR_TEAL)),
        ..Config::for_repo(&repo_root())
    }
}

pub fn repo_root() -> PathBuf {
    discover_repo_root(Path::new(env!("CARGO_MANIFEST_DIR")))
        .expect("the crate lives inside the repository that holds contracts/out/")
}

/// Decode a program out of a recorded JSON fixture (`result` of a compile response, or a field of
/// an application's `params`).
pub fn program_in(json: &[u8], pointer: &str) -> Vec<u8> {
    let value: Value = serde_json::from_slice(json).unwrap();
    BASE64
        .decode(value.pointer(pointer).and_then(Value::as_str).unwrap())
        .unwrap()
}

/// The recorded application response with one edit applied to its JSON.
pub fn app_with(edit: impl FnOnce(&mut Value)) -> Vec<u8> {
    let mut value: Value = serde_json::from_slice(&fixture("application_recorded.json")).unwrap();
    edit(&mut value);
    serde_json::to_vec(&value).unwrap()
}

/// The recorded application response with one deployed program replaced by `bytes`.
pub fn app_with_program(field: &str, bytes: &[u8]) -> Vec<u8> {
    let encoded = BASE64.encode(bytes);
    app_with(|v| v["params"][field] = Value::String(encoded))
}

/// `bytes` with its last byte flipped: same length, different program.
pub fn flipped_last(mut bytes: Vec<u8>) -> Vec<u8> {
    let last = bytes.last_mut().unwrap();
    *last ^= 0x01;
    bytes
}

// ── temporary directories ──────────────────────────────────────────────────────────────────

pub struct TempDir(PathBuf);

impl TempDir {
    pub fn new(tag: &str) -> Self {
        static SEQ: AtomicU32 = AtomicU32::new(0);
        let n = SEQ.fetch_add(1, Ordering::Relaxed);
        let dir = std::env::temp_dir().join(format!("tdv-{tag}-{}-{n}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        Self(dir)
    }

    pub fn path(&self) -> &Path {
        &self.0
    }

    pub fn teal(&self, name: &str, bytes: &[u8]) -> TealFile {
        let path = self.0.join(name);
        std::fs::write(&path, bytes).unwrap();
        TealFile::new(path)
    }
}

impl Drop for TempDir {
    fn drop(&mut self) {
        let _ = std::fs::remove_dir_all(&self.0);
    }
}

// ── fake algod: recorded responses, injected through the Transport trait ───────────────────

#[derive(Debug, Clone)]
pub enum Reply {
    Http(u16, Vec<u8>),
    Fail(String),
}

impl Reply {
    pub const fn ok(body: Vec<u8>) -> Self {
        Self::Http(200, body)
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Logged {
    pub method: &'static str,
    pub url: String,
    pub body: Vec<u8>,
}

/// Routes by URL; compile requests are routed by their EXACT body, so a test also proves which
/// file was sent where. An unexpected body gets an HTTP 400, i.e. "could not check".
pub struct FakeAlgod {
    pub app: Reply,
    pub versions: Reply,
    pub compile: Vec<(Vec<u8>, Reply)>,
    /// When set, EVERY request fails at the transport level with this reason.
    pub down: Option<String>,
    pub log: RefCell<Vec<Logged>>,
}

impl FakeAlgod {
    /// Every response exactly as recorded from `TestNet`, keyed to the committed TEAL.
    pub fn recorded() -> Self {
        Self {
            app: Reply::ok(fixture("application_recorded.json")),
            versions: Reply::ok(fixture("versions_testnet.json")),
            compile: vec![
                (
                    fixture(RECORDED_APPROVAL_TEAL),
                    Reply::ok(fixture("compile_approval.json")),
                ),
                (
                    fixture(RECORDED_CLEAR_TEAL),
                    Reply::ok(fixture("compile_clear.json")),
                ),
            ],
            down: None,
            log: RefCell::new(Vec::new()),
        }
    }

    /// Every request fails at the transport level.
    pub fn unreachable(reason: &str) -> Self {
        Self {
            down: Some(reason.to_owned()),
            ..Self::recorded()
        }
    }

    pub fn requests(&self) -> Vec<Logged> {
        self.log.borrow().clone()
    }

    fn answer(reply: &Reply) -> Result<HttpResponse, TransportError> {
        match reply {
            Reply::Http(status, body) => Ok(HttpResponse {
                status: *status,
                body: body.clone(),
            }),
            Reply::Fail(reason) => Err(TransportError(reason.clone())),
        }
    }
}

impl Transport for FakeAlgod {
    fn describe(&self) -> String {
        "fake algod (recorded responses)".to_owned()
    }

    fn get(&self, url: &str, _timeout: Duration) -> Result<HttpResponse, TransportError> {
        self.log.borrow_mut().push(Logged {
            method: "GET",
            url: url.to_owned(),
            body: Vec::new(),
        });
        if let Some(reason) = &self.down {
            return Err(TransportError(reason.clone()));
        }
        if url.ends_with("/versions") {
            Self::answer(&self.versions)
        } else if url.contains("/v2/applications/") {
            Self::answer(&self.app)
        } else {
            Ok(HttpResponse {
                status: 404,
                body: b"{\"message\":\"no such route\"}".to_vec(),
            })
        }
    }

    fn post_teal(
        &self,
        url: &str,
        teal: &[u8],
        _timeout: Duration,
    ) -> Result<HttpResponse, TransportError> {
        self.log.borrow_mut().push(Logged {
            method: "POST",
            url: url.to_owned(),
            body: teal.to_vec(),
        });
        if !url.ends_with("/v2/teal/compile") {
            return Ok(HttpResponse {
                status: 404,
                body: b"{\"message\":\"no such route\"}".to_vec(),
            });
        }
        if let Some(reason) = &self.down {
            return Err(TransportError(reason.clone()));
        }
        self.compile
            .iter()
            .find(|(body, _)| body == teal)
            .map_or_else(
                || {
                    Ok(HttpResponse {
                        status: 400,
                        body: b"{\"message\":\"fake algod: unexpected TEAL body\"}".to_vec(),
                    })
                },
                |(_, reply)| Self::answer(reply),
            )
    }
}

pub fn rendered(report: &Report) -> String {
    let mut out = Vec::new();
    render(report, &mut out).unwrap();
    String::from_utf8(out).expect("the report is UTF-8 (ASCII, in fact)")
}

/// Assert that some line of `text` starts with `prefix`.
#[track_caller]
pub fn assert_line(text: &str, prefix: &str) {
    assert!(
        text.lines().any(|l| l.starts_with(prefix)),
        "no line starts with {prefix:?} in:\n{text}"
    );
}

/// Assert that no line of `text` starts with `prefix`.
#[track_caller]
pub fn assert_no_line(text: &str, prefix: &str) {
    assert!(
        !text.lines().any(|l| l.starts_with(prefix)),
        "a line starts with {prefix:?} in:\n{text}"
    );
}

/// The defaults, pointed at the committed TEAL.
pub fn default_config() -> Config {
    Config::for_repo(&repo_root())
}

// ── loopback HTTP server, for the real curl transport ──────────────────────────────────────

#[derive(Debug, Clone)]
pub struct Served {
    pub method: String,
    pub target: String,
    pub headers: Vec<(String, String)>,
    pub body: Vec<u8>,
}

impl Served {
    pub fn header(&self, name: &str) -> Option<&str> {
        self.headers
            .iter()
            .find(|(n, _)| n.eq_ignore_ascii_case(name))
            .map(|(_, v)| v.as_str())
    }
}

pub struct LoopbackServer {
    pub base: String,
    handle: JoinHandle<Vec<Served>>,
}

impl LoopbackServer {
    /// Serve up to `connections` requests on 127.0.0.1, answering each with `respond`. A 3xx
    /// answer carries `Location: https://redirect-target.invalid/`.
    pub fn start(
        connections: usize,
        respond: impl Fn(&Served) -> (u16, Vec<u8>) + Send + 'static,
    ) -> Self {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let base = format!("http://{}", listener.local_addr().unwrap());
        listener.set_nonblocking(true).unwrap();
        let handle = std::thread::spawn(move || {
            let deadline = Instant::now() + Duration::from_secs(60);
            let mut served = Vec::new();
            while served.len() < connections && Instant::now() < deadline {
                match listener.accept() {
                    Ok((stream, _)) => {
                        if let Some(request) = handle_one(stream, &respond) {
                            served.push(request);
                        }
                    }
                    Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => {
                        std::thread::sleep(Duration::from_millis(5));
                    }
                    Err(e) => panic!("accept: {e}"),
                }
            }
            served
        });
        Self { base, handle }
    }

    pub fn finish(self) -> Vec<Served> {
        self.handle.join().unwrap()
    }
}

/// A port nothing listens on (bound, then released).
pub fn closed_port_url() -> String {
    let listener = TcpListener::bind("127.0.0.1:0").unwrap();
    let addr = listener.local_addr().unwrap();
    drop(listener);
    format!("http://{addr}")
}

fn handle_one(
    mut stream: TcpStream,
    respond: &impl Fn(&Served) -> (u16, Vec<u8>),
) -> Option<Served> {
    stream.set_nonblocking(false).unwrap();
    stream
        .set_read_timeout(Some(Duration::from_secs(20)))
        .unwrap();
    let mut raw = Vec::new();
    let mut chunk = [0_u8; 4096];
    let head_end = loop {
        if let Some(i) = raw.windows(4).position(|w| w == b"\r\n\r\n") {
            break i + 4;
        }
        let n = stream.read(&mut chunk).ok()?;
        if n == 0 {
            return None;
        }
        raw.extend_from_slice(&chunk[..n]);
    };
    let head = String::from_utf8_lossy(&raw[..head_end]).into_owned();
    let mut lines = head.split("\r\n");
    let mut request_line = lines.next()?.split(' ');
    let method = request_line.next()?.to_owned();
    let target = request_line.next()?.to_owned();
    let headers: Vec<(String, String)> = lines
        .filter_map(|l| l.split_once(':'))
        .map(|(n, v)| (n.trim().to_owned(), v.trim().to_owned()))
        .collect();
    let length = headers
        .iter()
        .find(|(n, _)| n.eq_ignore_ascii_case("content-length"))
        .map_or(0, |(_, v)| v.parse::<usize>().unwrap());
    let mut body = raw[head_end..].to_vec();
    while body.len() < length {
        let n = stream.read(&mut chunk).ok()?;
        if n == 0 {
            break;
        }
        body.extend_from_slice(&chunk[..n]);
    }
    let served = Served {
        method,
        target,
        headers,
        body,
    };
    let (status, reply) = respond(&served);
    let location = if (300..400).contains(&status) {
        "Location: https://redirect-target.invalid/\r\n"
    } else {
        ""
    };
    let head = format!(
        "HTTP/1.1 {status} X\r\nContent-Type: application/json\r\n{location}Content-Length: {}\r\nConnection: close\r\n\r\n",
        reply.len()
    );
    stream.write_all(head.as_bytes()).ok()?;
    stream.write_all(&reply).ok()?;
    stream.flush().ok()?;
    Some(served)
}

/// An algod stand-in for the loopback server: recorded responses, compile routed by exact body.
pub fn recorded_router(app: Vec<u8>) -> impl Fn(&Served) -> (u16, Vec<u8>) + Send + 'static {
    let approval = fixture(RECORDED_APPROVAL_TEAL);
    let clear = fixture(RECORDED_CLEAR_TEAL);
    move |req: &Served| match (req.method.as_str(), req.target.as_str()) {
        ("GET", "/versions") => (200, fixture("versions_testnet.json")),
        ("GET", t) if t.starts_with("/v2/applications/") => (200, app.clone()),
        ("POST", "/v2/teal/compile") if req.body == approval => {
            (200, fixture("compile_approval.json"))
        }
        ("POST", "/v2/teal/compile") if req.body == clear => (200, fixture("compile_clear.json")),
        ("POST", "/v2/teal/compile") => (400, fixture("compile_error_400.json")),
        _ => (404, b"{\"message\":\"no such route\"}".to_vec()),
    }
}
