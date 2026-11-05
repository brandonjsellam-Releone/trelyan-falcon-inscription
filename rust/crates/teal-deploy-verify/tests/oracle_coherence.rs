//! The port and its oracle must describe the same check of the same deployment.
//!
//! `contracts/verify_deployment.py` is the spec this crate was ported from. Its defaults are LIVE
//! CLAIMS (`sdk/tests/test_app_id_references_are_coherent.py` lists it) and change in the commit
//! of a redeploy. These tests read it as TEXT — no Python is run — and fail when the Rust side
//! has not followed, including when a sentence the Rust report PRINTS about the Python stops
//! being true.

#![allow(clippy::expect_used, clippy::unwrap_used, clippy::panic)]

mod common;

use teal_deploy_verify::{APPROVAL_TEAL, DEFAULT_ALGOD, DEFAULT_APP_ID, DEFAULT_TIMEOUT};

fn oracle() -> String {
    std::fs::read_to_string(common::repo_root().join("contracts/verify_deployment.py")).unwrap()
}

/// The right-hand side of a top-level `NAME = value` assignment in the oracle.
fn assignment(src: &str, name: &str) -> String {
    src.lines()
        .find_map(|line| {
            let rest = line.strip_prefix(name)?;
            let rest = rest.strip_prefix(' ').unwrap_or(rest).strip_prefix('=')?;
            Some(rest.trim().to_owned())
        })
        .unwrap_or_else(|| panic!("contracts/verify_deployment.py no longer assigns {name}"))
}

#[test]
fn default_app_id_is_the_oracles() {
    let value = assignment(&oracle(), "DEFAULT_APP_ID");
    assert_eq!(
        value.parse::<u64>().unwrap(),
        DEFAULT_APP_ID,
        "contracts/verify_deployment.py targets app {value} but the Rust port targets \
         {DEFAULT_APP_ID}. A redeploy retargets BOTH (teal_deploy_verify::DEFAULT_APP_ID)."
    );
}

#[test]
fn default_algod_is_the_oracles() {
    assert_eq!(
        assignment(&oracle(), "DEFAULT_ALGOD"),
        format!("\"{DEFAULT_ALGOD}\"")
    );
}

#[test]
fn default_timeout_is_the_oracles() {
    let src = oracle();
    let line = src.lines().find(|l| l.contains("\"--timeout\"")).unwrap();
    assert!(
        line.contains(&format!("default={}", DEFAULT_TIMEOUT.as_secs())),
        "{line}"
    );
}

#[test]
fn approval_artifact_is_the_oracles() {
    assert_eq!(
        assignment(&oracle(), "DEFAULT_TEAL"),
        r#"REPO_ROOT / "out" / "TrelyanInscription.approval.teal""#
    );
    assert_eq!(
        APPROVAL_TEAL,
        "contracts/out/TrelyanInscription.approval.teal"
    );
}

#[test]
fn the_oracle_still_compares_the_approval_program_only() {
    // Every report prints "(contracts/verify_deployment.py compares the approval program only)".
    // That is a claim about another file; this keeps it true. If the Python ever starts reading
    // the clear-state program, this fails and the printed sentence must change with it.
    let src = oracle();
    assert!(
        src.contains("params.get(\"approval-program\")"),
        "the oracle's fetch changed shape"
    );
    assert!(
        !src.contains("clear-state-program"),
        "contracts/verify_deployment.py now reads the clear-state program; update the sentence \
         the Rust report prints about it"
    );
}
