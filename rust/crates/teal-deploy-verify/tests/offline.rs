//! Offline behaviour of the verifier, driven by RECORDED algod responses injected through the
//! `Transport` trait (see `common/mod.rs` for where each fixture came from).
//!
//! Every test pins three things, so a wrong exit code for the right reason, or the right exit code
//! for the wrong reason, both fail:
//!   1. the exit code (`report.verdict().exit_code()`, the value `main` returns);
//!   2. the per-program verdicts and, for exit 2, the KIND of failure;
//!   3. the line an operator reads (`MATCH  …` / `DRIFT  …` / `COULD NOT CHECK  …` / `RESULT …`).

#![allow(clippy::expect_used, clippy::unwrap_used, clippy::panic)]

mod common;

use common::{
    FakeAlgod, RECORDED_APP_ID, Reply, TempDir, app_with, app_with_program, assert_line,
    assert_no_line, fixture, flipped_last, program_in, recorded_config, rendered,
};
use teal_deploy_verify::{
    CheckError, Config, Network, Program, TealFile, Verdict, check, sha512_256_hex,
};

/// SHA-512/256 of the approval program the README publishes (709 B, `6fa5cee1…`), computed
/// independently of this crate with `openssl dgst -sha512-256` over the base64-decoded
/// `result` of `compile_approval.json`, and equal to the fingerprint the Python verifier printed
/// on 2026-11-05.
const PUBLISHED_APPROVAL_SHA512_256: &str =
    "6fa5cee145762e4a0c2ba93738a0e6f51e93b02c71f23e4e663ac6d73b981c4b";
/// The clear-state program observed on chain on 2026-11-05: `DIEBQw==` = 0c 81 01 43
/// (`#pragma version 12`, `pushint 1`, `return`).
const DEPLOYED_CLEAR_STATE: [u8; 4] = [0x0c, 0x81, 0x01, 0x43];

fn exit_code(algod: &FakeAlgod, config: &Config) -> (u8, teal_deploy_verify::Report) {
    let report = check(config, algod);
    (report.verdict().exit_code(), report)
}

// ── 0: MATCH ────────────────────────────────────────────────────────────────────────────────

#[test]
fn both_programs_match_exit_0() {
    let algod = FakeAlgod::recorded();
    let (code, report) = exit_code(&algod, &recorded_config());
    let text = rendered(&report);
    assert_eq!(code, 0, "{text}");
    assert_eq!(report.approval.verdict(), Verdict::Match);
    assert_eq!(report.clear_state.verdict(), Verdict::Match);
    assert_line(
        &text,
        "MATCH  approval program     deployed 709 B == 709 B assembled",
    );
    assert_line(
        &text,
        "MATCH  clear-state program  deployed 4 B == 4 B assembled",
    );
    assert_line(
        &text,
        &format!("RESULT  MATCH (exit 0) for TestNet application {RECORDED_APP_ID}:"),
    );
    assert_no_line(&text, "DRIFT");
    assert_no_line(&text, "COULD NOT CHECK");
}

#[test]
fn recorded_fixtures_reproduce_the_published_fingerprints() {
    // Ties the fixtures and the hash function to values computed OUTSIDE this crate.
    let approval = program_in(&fixture("compile_approval.json"), "/result");
    assert_eq!(approval.len(), 709);
    assert_eq!(sha512_256_hex(&approval), PUBLISHED_APPROVAL_SHA512_256);
    let clear = program_in(
        &fixture("application_recorded.json"),
        "/params/clear-state-program",
    );
    assert_eq!(clear, DEPLOYED_CLEAR_STATE);
    assert_eq!(
        program_in(&fixture("compile_clear.json"), "/result"),
        DEPLOYED_CLEAR_STATE
    );
}

#[test]
fn report_states_testnet_the_trust_note_and_all_four_fingerprints() {
    let report = check(&recorded_config(), &FakeAlgod::recorded());
    let text = rendered(&report);
    assert_eq!(report.network, Ok(Network::TestNet));
    assert_line(&text, "  network    Algorand TestNet -- NOT MainNet");
    assert_line(
        &text,
        "             genesis testnet-v1.0 SGO1GKSzyE7IEPItTxCByw9x8FmnrCDexi9/cOUJOiI=",
    );
    assert_line(
        &text,
        "  compares   approval program AND clear-state program",
    );
    // The trust note, every line of it indented under the header (a `\` string continuation
    // once silently stripped the first line's indent).
    assert_line(
        &text,
        "             ONE endpoint does both halves, so a dishonest endpoint could lie",
    );
    assert_line(
        &text,
        "             consistently across both. Pass --compile-url <independent node> to",
    );
    assert_line(
        &text,
        "             The result is only as strong as the weaker of the two sources.",
    );
    assert_line(
        &text,
        "SCOPE   Bytecode identity only. It says nothing about MainNet",
    );
    assert!(
        text.contains("no FIPS 206 / FN-DSA claim is made"),
        "{text}"
    );
    // Expected AND actual fingerprints for BOTH programs: 2 x 2 lines.
    let approval_lines = text
        .lines()
        .filter(|l| l.starts_with("    approval        709 B  sha512_256 "))
        .filter(|l| l.ends_with(PUBLISHED_APPROVAL_SHA512_256))
        .count();
    assert_eq!(approval_lines, 2, "{text}");
    let clear_hash = sha512_256_hex(&DEPLOYED_CLEAR_STATE);
    let clear_lines = text
        .lines()
        .filter(|l| l.starts_with("    clear-state       4 B  sha512_256 "))
        .filter(|l| l.ends_with(&clear_hash))
        .count();
    assert_eq!(clear_lines, 2, "{text}");
    assert!(
        text.is_ascii(),
        "the report must be ASCII so no console can mangle it"
    );
}

// ── 1: DRIFT ────────────────────────────────────────────────────────────────────────────────

#[test]
fn approval_drift_exit_1() {
    let deployed = program_in(
        &fixture("application_recorded.json"),
        "/params/approval-program",
    );
    let algod = FakeAlgod {
        app: Reply::ok(app_with_program(
            "approval-program",
            &flipped_last(deployed),
        )),
        ..FakeAlgod::recorded()
    };
    let (code, report) = exit_code(&algod, &recorded_config());
    let text = rendered(&report);
    assert_eq!(code, 1, "{text}");
    assert_eq!(report.approval.verdict(), Verdict::Drift);
    assert_eq!(report.clear_state.verdict(), Verdict::Match);
    assert_line(
        &text,
        "DRIFT  approval program     deployed 709 B != 709 B assembled",
    );
    assert_line(
        &text,
        "                            first difference at byte 708",
    );
    assert_line(&text, "MATCH  clear-state program");
    assert_line(
        &text,
        &format!("RESULT  DRIFT (exit 1) for TestNet application {RECORDED_APP_ID}:"),
    );
    assert!(text.contains("(drifted: approval program)."), "{text}");
    assert!(text.contains("AWAITING TESTNET REDEPLOY"), "{text}");
}

#[test]
fn clear_state_drift_only_exit_1() {
    // THE NEW CHECK. The Python verifier compares the approval program only, so for this exact
    // deployment it would print MATCH and exit 0. The port must say DRIFT and exit 1.
    let drifted_clear = vec![0x0c, 0x81, 0x00, 0x43]; // pushint 0: a clear-state that rejects
    let algod = FakeAlgod {
        app: Reply::ok(app_with_program("clear-state-program", &drifted_clear)),
        ..FakeAlgod::recorded()
    };
    let (code, report) = exit_code(&algod, &recorded_config());
    let text = rendered(&report);
    assert_eq!(
        report.approval.verdict(),
        Verdict::Match,
        "approval is untouched"
    );
    assert_eq!(report.clear_state.verdict(), Verdict::Drift, "{text}");
    assert_eq!(report.verdict(), Verdict::Drift, "{text}");
    assert_eq!(code, 1, "{text}");
    assert_line(&text, "MATCH  approval program");
    assert_line(
        &text,
        "DRIFT  clear-state program  deployed 4 B != 4 B assembled",
    );
    assert_line(
        &text,
        "                            first difference at byte 2",
    );
    assert!(text.contains("(drifted: clear-state program)."), "{text}");
}

#[test]
fn both_programs_drifting_names_both() {
    let algod = FakeAlgod {
        app: Reply::ok(app_with(|v| {
            v["params"]["approval-program"] = "AQ==".into();
            v["params"]["clear-state-program"] = "Ag==".into();
        })),
        ..FakeAlgod::recorded()
    };
    let (code, report) = exit_code(&algod, &recorded_config());
    let text = rendered(&report);
    assert_eq!(code, 1, "{text}");
    assert!(
        text.contains("(drifted: approval program and clear-state program)."),
        "{text}"
    );
}

#[test]
fn swapped_teal_files_are_drift_not_match() {
    // Each committed file is posted to the compile endpoint and the result compared with the
    // MATCHING deployed program. Hand the files over crossed and both comparisons must fail —
    // a port that compared "any assembled program" to "any deployed program" would not notice.
    let mut config = recorded_config();
    std::mem::swap(&mut config.approval_teal, &mut config.clear_teal);
    let (code, report) = exit_code(&FakeAlgod::recorded(), &config);
    let text = rendered(&report);
    assert_eq!(code, 1, "{text}");
    assert_eq!(report.approval.verdict(), Verdict::Drift);
    assert_eq!(report.clear_state.verdict(), Verdict::Drift);
}

#[test]
fn drift_is_reported_even_when_the_other_program_could_not_be_checked() {
    // An observed difference is a finding; it must not be downgraded to "could not check"
    // because the OTHER program's compile failed.
    let deployed = program_in(
        &fixture("application_recorded.json"),
        "/params/approval-program",
    );
    let mut algod = FakeAlgod {
        app: Reply::ok(app_with_program(
            "approval-program",
            &flipped_last(deployed),
        )),
        ..FakeAlgod::recorded()
    };
    algod.compile[1].1 = Reply::Http(400, fixture("compile_error_400.json"));
    let (code, report) = exit_code(&algod, &recorded_config());
    let text = rendered(&report);
    assert_eq!(report.approval.verdict(), Verdict::Drift);
    assert_eq!(report.clear_state.verdict(), Verdict::CouldNotCheck);
    assert_eq!(code, 1, "{text}");
    assert_line(&text, "DRIFT  approval program");
    assert_line(&text, "COULD NOT CHECK  clear-state program: POST ");
}

// ── 2: COULD NOT CHECK ──────────────────────────────────────────────────────────────────────

#[track_caller]
fn assert_could_not_check(
    algod: &FakeAlgod,
    config: &Config,
) -> (teal_deploy_verify::Report, String) {
    let (code, report) = exit_code(algod, config);
    let text = rendered(&report);
    assert_eq!(code, 2, "{text}");
    assert_line(&text, "RESULT  COULD NOT CHECK (exit 2)");
    assert!(text.contains("This is neither agreement nor"), "{text}");
    assert_no_line(&text, "RESULT  MATCH");
    assert_no_line(&text, "RESULT  DRIFT");
    (report, text)
}

#[test]
fn app_without_approval_program_exit_2() {
    let algod = FakeAlgod {
        app: Reply::ok(app_with(|v| {
            v["params"]
                .as_object_mut()
                .unwrap()
                .remove("approval-program");
        })),
        ..FakeAlgod::recorded()
    };
    let (report, text) = assert_could_not_check(&algod, &recorded_config());
    assert!(
        matches!(&report.approval.actual, Err(CheckError::Response { reason, .. })
            if *reason == format!("application {RECORDED_APP_ID} returned no approval-program")),
        "{:?}",
        report.approval.actual
    );
    assert_eq!(
        report.clear_state.verdict(),
        Verdict::Match,
        "the other program is still checked"
    );
    assert_line(&text, "COULD NOT CHECK  approval program: GET ");
}

#[test]
fn app_without_clear_state_program_exit_2() {
    let algod = FakeAlgod {
        app: Reply::ok(app_with(|v| v["params"]["clear-state-program"] = "".into())),
        ..FakeAlgod::recorded()
    };
    let (report, _) = assert_could_not_check(&algod, &recorded_config());
    assert_eq!(report.approval.verdict(), Verdict::Match);
    assert!(matches!(
        report.clear_state.actual,
        Err(CheckError::Response { .. })
    ));
}

#[test]
fn compile_endpoint_error_exit_2() {
    // The recorded HTTP 400 algod returns for TEAL it cannot assemble.
    let mut algod = FakeAlgod::recorded();
    for entry in &mut algod.compile {
        entry.1 = Reply::Http(400, fixture("compile_error_400.json"));
    }
    let (report, text) = assert_could_not_check(&algod, &recorded_config());
    for p in report.programs() {
        assert!(
            matches!(&p.expected, Err(CheckError::Status { status: 400, excerpt, .. })
                if excerpt.contains("unknown opcode: not_an_opcode")),
            "{:?}",
            p.expected
        );
    }
    // The newline inside algod's message is shown escaped, never as a raw line break.
    assert!(text.contains("unknown opcode: not_an_opcode\\n"), "{text}");
}

#[test]
fn malformed_json_from_algod_exit_2() {
    let algod = FakeAlgod {
        app: Reply::ok(format!("{{\"id\":{RECORDED_APP_ID},\"params\":").into_bytes()),
        ..FakeAlgod::recorded()
    };
    let (report, _) = assert_could_not_check(&algod, &recorded_config());
    for p in report.programs() {
        assert!(
            matches!(&p.actual, Err(CheckError::Response { reason, .. }) if reason.starts_with("body is not valid JSON")),
            "{:?}",
            p.actual
        );
        assert!(p.expected.is_ok(), "the compile side is unaffected");
    }
}

#[test]
fn malformed_json_from_compile_exit_2() {
    let mut algod = FakeAlgod::recorded();
    algod.compile[0].1 = Reply::ok(b"<html>502 Bad Gateway</html>".to_vec());
    let (report, _) = assert_could_not_check(&algod, &recorded_config());
    assert!(matches!(
        report.approval.expected,
        Err(CheckError::Response { .. })
    ));
}

#[test]
fn json_that_is_not_an_object_exit_2() {
    let algod = FakeAlgod {
        app: Reply::ok(b"[\"approval-program\"]".to_vec()),
        ..FakeAlgod::recorded()
    };
    let (report, _) = assert_could_not_check(&algod, &recorded_config());
    assert!(
        matches!(&report.approval.actual, Err(CheckError::Response { reason, .. }) if reason == "body is JSON but not an object")
    );
}

#[test]
fn transport_failure_exit_2_never_match() {
    let algod = FakeAlgod::unreachable("curl exited with code 7 (could not connect)");
    let (report, text) = assert_could_not_check(&algod, &recorded_config());
    for p in report.programs() {
        assert!(
            matches!(p.expected, Err(CheckError::Transport { .. })),
            "{:?}",
            p.expected
        );
        assert!(
            matches!(p.actual, Err(CheckError::Transport { .. })),
            "{:?}",
            p.actual
        );
        assert_eq!(p.verdict(), Verdict::CouldNotCheck);
    }
    assert!(matches!(report.network, Err(CheckError::Transport { .. })));
    assert_line(
        &text,
        "  network    UNCONFIRMED: GET https://testnet-api.algonode.cloud/versions failed",
    );
    assert_no_line(&text, "MATCH");
    assert_no_line(&text, "DRIFT");
}

#[test]
fn app_not_found_404_exit_2() {
    let algod = FakeAlgod {
        app: Reply::Http(404, fixture("app_not_found_404.json")),
        ..FakeAlgod::recorded()
    };
    let (report, text) = assert_could_not_check(&algod, &recorded_config());
    assert!(matches!(
        report.approval.actual,
        Err(CheckError::Status { status: 404, .. })
    ));
    assert!(
        text.contains("HTTP 404: {\"message\":\"application does not exist\"}"),
        "{text}"
    );
}

#[test]
fn redirect_is_not_followed_and_is_exit_2() {
    let algod = FakeAlgod {
        app: Reply::Http(302, Vec::new()),
        ..FakeAlgod::recorded()
    };
    let (report, _) = assert_could_not_check(&algod, &recorded_config());
    assert!(matches!(
        report.approval.actual,
        Err(CheckError::Status { status: 302, .. })
    ));
}

#[test]
fn algod_answering_for_another_application_exit_2() {
    // Same programs, wrong application id: a proxy mix-up must not be compared as this app.
    let algod = FakeAlgod {
        app: Reply::ok(app_with(|v| v["id"] = 1.into())),
        ..FakeAlgod::recorded()
    };
    let (report, _) = assert_could_not_check(&algod, &recorded_config());
    assert!(
        matches!(&report.approval.actual, Err(CheckError::Response { reason, .. })
            if *reason == format!("algod answered for application 1, not {RECORDED_APP_ID}")),
        "{:?}",
        report.approval.actual
    );
    let algod = FakeAlgod {
        app: Reply::ok(app_with(|v| {
            v.as_object_mut().unwrap().remove("id");
        })),
        ..FakeAlgod::recorded()
    };
    assert_could_not_check(&algod, &recorded_config());
}

#[test]
fn non_canonical_base64_exit_2() {
    for junk in ["DIEBQw", "DIEB Qw==", "DIEBQw==\n", "!!!!"] {
        let algod = FakeAlgod {
            app: Reply::ok(app_with(|v| {
                v["params"]["clear-state-program"] = junk.into();
            })),
            ..FakeAlgod::recorded()
        };
        let (report, _) = assert_could_not_check(&algod, &recorded_config());
        assert!(
            matches!(&report.clear_state.actual, Err(CheckError::Response { reason, .. }) if reason.contains("not canonical base64")),
            "{junk:?}: {:?}",
            report.clear_state.actual
        );
    }
}

#[test]
fn compile_result_that_decodes_to_nothing_exit_2() {
    let mut algod = FakeAlgod::recorded();
    algod.compile[1].1 = Reply::ok(b"{\"hash\":\"X\",\"result\":\"\"}".to_vec());
    let (report, _) = assert_could_not_check(&algod, &recorded_config());
    assert!(
        matches!(&report.clear_state.expected, Err(CheckError::Response { reason, .. }) if reason.contains("zero bytes")),
        "{:?}",
        report.clear_state.expected
    );
}

#[test]
fn empty_teal_file_exit_2_and_it_is_never_sent() {
    let dir = TempDir::new("empty");
    let mut config = recorded_config();
    config.clear_teal = dir.teal("TrelyanInscription.clear.teal", b"");
    let algod = FakeAlgod::recorded();
    let (report, text) = assert_could_not_check(&algod, &config);
    assert!(matches!(
        report.clear_state.teal,
        Err(CheckError::Artifact { .. })
    ));
    assert!(matches!(
        report.clear_state.expected,
        Err(CheckError::Artifact { .. })
    ));
    assert_eq!(report.approval.verdict(), Verdict::Match);
    assert!(
        text.contains("is empty (0 B, no TEAL to assemble)"),
        "{text}"
    );
    // Nothing empty was posted: exactly one compile request, carrying the approval TEAL.
    let posts: Vec<_> = algod
        .requests()
        .into_iter()
        .filter(|r| r.method == "POST")
        .collect();
    assert_eq!(posts.len(), 1);
    assert_eq!(posts[0].body, fixture(common::RECORDED_APPROVAL_TEAL));
}

#[test]
fn missing_teal_file_exit_2() {
    let dir = TempDir::new("missing");
    let mut config = recorded_config();
    config.approval_teal = TealFile::new(dir.path().join("does-not-exist.teal"));
    let (report, text) = assert_could_not_check(&FakeAlgod::recorded(), &config);
    assert!(
        matches!(&report.approval.teal, Err(CheckError::Artifact { reason, .. }) if reason == "not found"),
        "{:?}",
        report.approval.teal
    );
    assert_line(
        &text,
        "COULD NOT CHECK  approval program: committed artifact ",
    );
}

#[test]
fn refused_url_is_exit_2_and_never_reaches_the_transport() {
    let mut config = recorded_config();
    config.algod = "http://testnet-api.algonode.cloud".to_owned();
    let algod = FakeAlgod::recorded();
    let (report, _) = assert_could_not_check(&algod, &config);
    assert!(matches!(
        report.approval.actual,
        Err(CheckError::Url { .. })
    ));
    assert!(matches!(
        report.approval.expected,
        Err(CheckError::Url { .. })
    ));
    assert!(algod.requests().is_empty(), "{:?}", algod.requests());
}

#[test]
fn hostile_error_body_cannot_inject_terminal_escapes() {
    let body = b"\x1b[2J\x1b]0;owned\x07\r\nMATCH  approval program  (forged)\xe2\x80\xae".to_vec();
    let algod = FakeAlgod {
        app: Reply::Http(500, body),
        ..FakeAlgod::recorded()
    };
    let (_, text) = assert_could_not_check(&algod, &recorded_config());
    assert!(
        !text.chars().any(|c| c.is_control() && c != '\n'),
        "{text:?}"
    );
    assert!(!text.contains('\u{202e}'), "{text:?}");
    assert_no_line(&text, "MATCH");
    assert!(text.contains("\\u{1b}[2J"), "{text}");
}

// ── what is sent where ──────────────────────────────────────────────────────────────────────

#[test]
fn exactly_four_read_only_requests_with_the_exact_teal_bytes() {
    let algod = FakeAlgod::recorded();
    let _ = check(&recorded_config(), &algod);
    let requests = algod.requests();
    let summary: Vec<(&str, &str)> = requests
        .iter()
        .map(|r| (r.method, r.url.as_str()))
        .collect();
    let application =
        format!("https://testnet-api.algonode.cloud/v2/applications/{RECORDED_APP_ID}");
    assert_eq!(
        summary,
        [
            ("POST", "https://testnet-api.algonode.cloud/v2/teal/compile"),
            ("POST", "https://testnet-api.algonode.cloud/v2/teal/compile"),
            ("GET", application.as_str()),
            ("GET", "https://testnet-api.algonode.cloud/versions"),
        ]
    );
    assert_eq!(requests[0].body, fixture(common::RECORDED_APPROVAL_TEAL));
    assert_eq!(requests[1].body, fixture(common::RECORDED_CLEAR_TEAL));
}

#[test]
fn compile_url_splits_trust_across_the_two_endpoints() {
    let mut config = recorded_config();
    config.algod = "https://reader.example/".to_owned();
    config.compile_url = Some("https://assembler.example".to_owned());
    let algod = FakeAlgod::recorded();
    let report = check(&config, &algod);
    assert_eq!(report.verdict(), Verdict::Match);
    for r in algod.requests() {
        match r.method {
            "POST" => assert!(r.url.starts_with("https://assembler.example/v2/"), "{r:?}"),
            _ => assert!(r.url.starts_with("https://reader.example/"), "{r:?}"),
        }
    }
    let text = rendered(&report);
    assert!(report.trust_split);
    assert_line(
        &text,
        "             Two different endpoints: a consistent lie would need both of them.",
    );
    assert_no_line(&text, "             ONE endpoint does both halves");
}

// ── the network line is read, not assumed, and never changes the verdict ───────────────────

#[test]
fn network_line_is_derived_from_the_genesis_and_is_display_only() {
    let mainnet = br#"{"genesis_id":"mainnet-v1.0","genesis_hash_b64":"wGHE2Pwdvd7S12BL5FaOP20EGYesN73ktiC1qzkkit8="}"#;
    let algod = FakeAlgod {
        versions: Reply::ok(mainnet.to_vec()),
        ..FakeAlgod::recorded()
    };
    let report = check(&recorded_config(), &algod);
    let text = rendered(&report);
    assert_eq!(report.network, Ok(Network::MainNet));
    assert_line(&text, "  network    Algorand MAINNET -- WARNING");
    assert_line(
        &text,
        &format!("RESULT  MATCH (exit 0) for MAINNET application {RECORDED_APP_ID}:"),
    );
    assert_no_line(&text, "  network    Algorand TestNet");

    let algod = FakeAlgod {
        versions: Reply::Http(503, Vec::new()),
        ..FakeAlgod::recorded()
    };
    let report = check(&recorded_config(), &algod);
    assert_eq!(
        report.verdict(),
        Verdict::Match,
        "an unreadable /versions is not a bytecode problem"
    );
    let text = rendered(&report);
    assert_line(&text, "  network    UNCONFIRMED");
    assert_line(
        &text,
        &format!("RESULT  MATCH (exit 0) for application {RECORDED_APP_ID} (network unconfirmed):"),
    );
}

#[test]
fn program_names_and_fields_are_the_algod_ones() {
    assert_eq!(Program::Approval.json_field(), "approval-program");
    assert_eq!(Program::ClearState.json_field(), "clear-state-program");
}
