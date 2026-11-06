//! The REAL transport and the REAL binary, against a loopback HTTP server that replays the
//! recorded algod responses. Offline: nothing leaves 127.0.0.1. Requires the system `curl`
//! (Windows 10+, macOS and every CI runner ship one); a missing curl FAILS these tests rather
//! than skipping them, because the binary cannot work without it either.

#![allow(clippy::expect_used, clippy::unwrap_used, clippy::panic)]

mod common;

use std::process::{Command, Output};

use common::{
    LoopbackServer, RECORDED_APP_ID, RECORDED_APPROVAL_TEAL, RECORDED_CLEAR_TEAL, app_with_program,
    closed_port_url, fixture, fixture_path, recorded_config, recorded_router,
};
use teal_deploy_verify::curl::CurlTransport;
use teal_deploy_verify::{CheckError, Config, DEFAULT_APP_ID, Verdict, check};

fn loopback_config(base: &str) -> Config {
    Config {
        algod: base.to_owned(),
        ..recorded_config()
    }
}

// ── the curl transport ──────────────────────────────────────────────────────────────────────

#[test]
fn curl_transport_end_to_end_match_and_what_went_over_the_wire() {
    let server = LoopbackServer::start(4, recorded_router(fixture("application_recorded.json")));
    let report = check(&loopback_config(&server.base), &CurlTransport::system());
    let requests = server.finish();
    assert_eq!(report.verdict(), Verdict::Match, "{report:#?}");
    assert!(
        report.transport.starts_with("system curl "),
        "{}",
        report.transport
    );

    assert_eq!(requests.len(), 4, "{requests:#?}");
    let posts: Vec<_> = requests.iter().filter(|r| r.method == "POST").collect();
    assert_eq!(posts.len(), 2);
    for (post, file) in posts
        .iter()
        .zip([RECORDED_APPROVAL_TEAL, RECORDED_CLEAR_TEAL])
    {
        assert_eq!(post.target, "/v2/teal/compile");
        assert_eq!(post.header("content-type"), Some("text/plain"));
        assert_eq!(post.header("expect"), None, "no 100-continue round trip");
        assert_eq!(post.body, fixture(file), "the TEAL must arrive byte-exact");
    }
    let gets: Vec<_> = requests
        .iter()
        .filter(|r| r.method == "GET")
        .map(|r| r.target.clone())
        .collect();
    assert_eq!(
        gets,
        [
            format!("/v2/applications/{RECORDED_APP_ID}"),
            "/versions".to_owned()
        ]
    );
    for request in &requests {
        assert_eq!(request.header("accept"), Some("application/json"));
    }
}

#[test]
fn curl_transport_http_500_is_could_not_check() {
    let server = LoopbackServer::start(4, |_| (500, b"{\"message\":\"internal\"}".to_vec()));
    let report = check(&loopback_config(&server.base), &CurlTransport::system());
    server.finish();
    assert_eq!(report.verdict(), Verdict::CouldNotCheck);
    for p in report.programs() {
        assert!(
            matches!(p.expected, Err(CheckError::Status { status: 500, .. })),
            "{:?}",
            p.expected
        );
        assert!(
            matches!(p.actual, Err(CheckError::Status { status: 500, .. })),
            "{:?}",
            p.actual
        );
    }
}

#[test]
fn curl_transport_does_not_follow_redirects() {
    // Every request is answered 302 → https://redirect-target.invalid/. Following it would
    // silently move one half of the comparison to another host.
    let server = LoopbackServer::start(4, |_| (302, Vec::new()));
    let report = check(&loopback_config(&server.base), &CurlTransport::system());
    let requests = server.finish();
    assert_eq!(report.verdict(), Verdict::CouldNotCheck);
    assert!(matches!(
        report.approval.actual,
        Err(CheckError::Status { status: 302, .. })
    ));
    assert_eq!(requests.len(), 4, "one request per call, no follow-ups");
}

#[test]
fn curl_transport_connection_refused_is_could_not_check() {
    let report = check(
        &loopback_config(&closed_port_url()),
        &CurlTransport::system(),
    );
    assert_eq!(report.verdict(), Verdict::CouldNotCheck);
    match &report.approval.actual {
        Err(CheckError::Transport { reason, .. }) => {
            assert!(reason.starts_with("curl exited with code 7"), "{reason}");
        }
        other => panic!("expected a transport failure, got {other:?}"),
    }
}

#[test]
fn missing_curl_executable_is_could_not_check() {
    let transport = CurlTransport::with_program("curl-that-does-not-exist-tdv");
    let report = check(&recorded_config(), &transport);
    assert_eq!(report.verdict(), Verdict::CouldNotCheck);
    match &report.approval.expected {
        Err(CheckError::Transport { reason, .. }) => {
            assert!(
                reason.starts_with("could not start 'curl-that-does-not-exist-tdv'"),
                "{reason}"
            );
        }
        other => panic!("expected a transport failure, got {other:?}"),
    }
    assert!(
        report.transport.contains("not runnable"),
        "{}",
        report.transport
    );
}

// ── the binary: exit codes as a CI job sees them ───────────────────────────────────────────

fn verify_deployment(args: &[&str]) -> Output {
    Command::new(env!("CARGO_BIN_EXE_verify-deployment"))
        .args(args)
        // The default TEAL paths are discovered by walking up from the working directory.
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .output()
        .unwrap()
}

/// The binary, pointed at `algod` and at the frozen recording (its app and its TEAL inputs).
fn verify_recorded(algod: &str, extra: &[&str]) -> Output {
    let app = RECORDED_APP_ID.to_string();
    let approval = fixture_path(RECORDED_APPROVAL_TEAL);
    let clear = fixture_path(RECORDED_CLEAR_TEAL);
    let mut args = vec![
        "--algod",
        algod,
        "--app-id",
        &app,
        "--approval-teal",
        approval.to_str().unwrap(),
        "--clear-teal",
        clear.to_str().unwrap(),
    ];
    args.extend_from_slice(extra);
    verify_deployment(&args)
}

fn text(bytes: &[u8]) -> String {
    String::from_utf8_lossy(bytes).into_owned()
}

#[test]
fn binary_exits_0_on_match() {
    let server = LoopbackServer::start(4, recorded_router(fixture("application_recorded.json")));
    let out = verify_recorded(&server.base, &[]);
    server.finish();
    let stdout = text(&out.stdout);
    assert_eq!(
        out.status.code(),
        Some(0),
        "{stdout}\n{}",
        text(&out.stderr)
    );
    assert!(stdout.contains("\nMATCH  approval program "), "{stdout}");
    assert!(stdout.contains("\nMATCH  clear-state program "), "{stdout}");
    assert!(out.stderr.is_empty(), "{}", text(&out.stderr));
}

#[test]
fn binary_exits_1_on_clear_state_drift() {
    let app = app_with_program("clear-state-program", &[0x0c, 0x81, 0x00, 0x43]);
    let server = LoopbackServer::start(4, recorded_router(app));
    let out = verify_recorded(&server.base, &[]);
    server.finish();
    let stdout = text(&out.stdout);
    assert_eq!(
        out.status.code(),
        Some(1),
        "{stdout}\n{}",
        text(&out.stderr)
    );
    assert!(stdout.contains("\nDRIFT  clear-state program "), "{stdout}");
    assert!(stdout.contains("\nMATCH  approval program "), "{stdout}");
}

#[test]
fn binary_exits_2_when_algod_is_unreachable() {
    let out = verify_recorded(&closed_port_url(), &["--timeout", "5"]);
    let stderr = text(&out.stderr);
    assert_eq!(
        out.status.code(),
        Some(2),
        "{}\n{stderr}",
        text(&out.stdout)
    );
    assert!(
        stderr.starts_with("COULD NOT CHECK: approval program: "),
        "{stderr}"
    );
    assert!(text(&out.stdout).contains("RESULT  COULD NOT CHECK (exit 2)"));
}

#[test]
fn binary_defaults_find_the_committed_teal_and_the_default_app() {
    // No --approval-teal / --clear-teal / --app-id: the binary walks up from its working
    // directory to contracts/out/ and targets DEFAULT_APP_ID. Unreachable algod, so exit 2
    // and nothing leaves the machine — this checks WHAT it would compare, not the chain.
    let out = verify_deployment(&["--algod", &closed_port_url(), "--timeout", "5"]);
    let stdout = text(&out.stdout);
    assert_eq!(out.status.code(), Some(2), "{stdout}");
    for needle in [
        "    approval     contracts/out/TrelyanInscription.approval.teal",
        "    clear-state  contracts/out/TrelyanInscription.clear.teal",
        &format!("  app        {DEFAULT_APP_ID}\n"),
    ] {
        assert!(
            stdout.contains(needle),
            "{needle:?} missing from:\n{stdout}"
        );
    }
}

#[test]
fn binary_usage_errors_exit_2_before_any_request() {
    for args in [
        &["--no-such-flag"][..],
        &["--recompile"],
        &["--app-id", "seven"],
        &["--app-id", "0"],
        &["--app-id"],
        &["--timeout", "0"],
        &["--algod", "http://testnet-api.algonode.cloud"],
        &["--compile-url", "ftp://example.com"],
        &["--approval-teal"],
    ] {
        let out = verify_deployment(args);
        assert_eq!(
            out.status.code(),
            Some(2),
            "{args:?}: {}",
            text(&out.stderr)
        );
        assert!(
            out.stdout.is_empty(),
            "{args:?} printed a report: {}",
            text(&out.stdout)
        );
        assert!(
            text(&out.stderr).starts_with("verify-deployment: "),
            "{args:?}"
        );
    }
}

#[test]
fn binary_help_exits_0_and_documents_the_exit_codes() {
    let out = verify_deployment(&["--help"]);
    let stdout = text(&out.stdout);
    assert_eq!(out.status.code(), Some(0));
    for needle in [
        "0  MATCH",
        "1  DRIFT",
        "2  COULD NOT CHECK",
        "--compile-url",
        "Trust note",
        &format!("[default: {DEFAULT_APP_ID} (TestNet)]"),
    ] {
        assert!(
            stdout.contains(needle),
            "{needle} missing from --help:\n{stdout}"
        );
    }
    assert!(
        !stdout.contains("{default_app}"),
        "unfilled placeholder in --help"
    );
}
