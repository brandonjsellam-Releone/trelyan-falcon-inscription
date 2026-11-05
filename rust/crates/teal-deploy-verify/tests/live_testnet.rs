//! The one test that talks to the real network: Algorand `TestNet`, read-only, through the system
//! curl, with the defaults the CLI uses. Ignored by default so `cargo test` stays offline; run it
//! with
//!
//! ```text
//! cargo test -p teal-deploy-verify --test live_testnet -- --ignored --nocapture
//! ```

#![allow(clippy::expect_used, clippy::unwrap_used, clippy::panic)]

mod common;

use teal_deploy_verify::curl::CurlTransport;
use teal_deploy_verify::{Network, Verdict, run};

#[test]
#[ignore = "network: reads Algorand TestNet (testnet-api.algonode.cloud) through the system curl; \
            run with `cargo test -p teal-deploy-verify --test live_testnet -- --ignored`"]
fn live_testnet_default_app_runs_the_committed_teal() {
    let mut out = Vec::new();
    let report = run(
        &common::default_config(),
        &CurlTransport::system(),
        &mut out,
    )
    .unwrap();
    let text = String::from_utf8(out).unwrap();
    println!("{text}");
    assert_eq!(report.network, Ok(Network::TestNet), "{text}");
    assert_eq!(report.approval.verdict(), Verdict::Match, "{text}");
    assert_eq!(report.clear_state.verdict(), Verdict::Match, "{text}");
    assert_eq!(report.verdict(), Verdict::Match, "{text}");
    // What was observed on 2026-11-05; a change here is a finding, not test noise.
    assert_eq!(
        report.clear_state.actual,
        Ok(vec![0x0c, 0x81, 0x01, 0x43]),
        "{text}"
    );
    assert_eq!(
        report.approval.actual.as_ref().map(Vec::len),
        Ok(709),
        "{text}"
    );
}
