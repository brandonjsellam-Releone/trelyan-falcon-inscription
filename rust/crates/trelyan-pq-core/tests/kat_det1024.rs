//! Byte-identity KAT: the Rust signer must reproduce the committed det1024 goldens exactly.
//!
//! The goldens in `sdk/tests/vectors/det1024_kat.json` were produced by the Python SDK's ctypes
//! binding over the SAME pinned C tree this crate compiles (`pinned_commit` in the fixture must
//! equal the crate's `PINNED_FALCON_COMMIT`), with the emulated FP backend. If this test passes,
//! the Rust core, the Python SDK, and — because those signatures were accepted on the Algorand
//! test network by `falcon_verify` — the chain all agree byte for byte. That is the property that makes a Rust
//! port safe to introduce: not "it verifies", but "it produces the same bytes".
//!
//! Constitution §2.5: KATs first. This file is the first test that must be green before any
//! other test in this workspace matters.

#![allow(clippy::expect_used, clippy::unwrap_used, clippy::panic)]

use std::path::PathBuf;

use serde::Deserialize;
use sha2::{Digest, Sha512_256};
use trelyan_pq_core::{
    PINNED_FALCON_COMMIT, PRIVKEY_SIZE, PUBKEY_SIZE, PublicKey, SecretKey, Signature, VerifyError,
    sign, verify, verify_bytes,
};

#[derive(Deserialize)]
struct Fixture {
    #[serde(rename = "_status")]
    status: String,
    #[serde(rename = "_fp_backend")]
    fp_backend: String,
    pinned_commit: String,
    deterministic_c_sha512_256: String,
    pubkey_hex: String,
    privkey_hex: String,
    vectors: Vec<Vector>,
}

#[derive(Deserialize)]
struct Vector {
    name: String,
    message_hex: String,
    sig_len: usize,
    sig_hex: String,
    sig_sha512_256: String,
}

fn fixture_path() -> PathBuf {
    // rust/crates/trelyan-pq-core → repo root is three levels up.
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
        .join("..")
        .join("sdk")
        .join("tests")
        .join("vectors")
        .join("det1024_kat.json")
}

fn load() -> Fixture {
    let path = fixture_path();
    let text = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("cannot read KAT fixture {}: {e}", path.display()));
    serde_json::from_str(&text).expect("KAT fixture is valid JSON with the expected fields")
}

/// Hand-rolled hex decode: a dev-only helper is not worth a dependency (constitution §3).
fn unhex(s: &str) -> Vec<u8> {
    assert!(s.len().is_multiple_of(2), "odd-length hex");
    (0..s.len())
        .step_by(2)
        .map(|i| u8::from_str_radix(&s[i..i + 2], 16).expect("hex digit"))
        .collect()
}

fn hex(bytes: &[u8]) -> String {
    use std::fmt::Write as _;
    bytes
        .iter()
        .fold(String::with_capacity(bytes.len() * 2), |mut acc, b| {
            let _ = write!(acc, "{b:02x}");
            acc
        })
}

fn keys(f: &Fixture) -> (SecretKey, PublicKey) {
    let sk: [u8; PRIVKEY_SIZE] = unhex(&f.privkey_hex)
        .try_into()
        .expect("fixture private key is exactly 2305 bytes");
    let pk: [u8; PUBKEY_SIZE] = unhex(&f.pubkey_hex)
        .try_into()
        .expect("fixture public key is exactly 1793 bytes");
    (SecretKey::from_bytes(sk), PublicKey::from_bytes(pk))
}

#[test]
fn fixture_is_populated_and_bound_to_the_same_pin_this_crate_compiles() {
    let f = load();
    assert_eq!(
        f.status, "POPULATED",
        "the KAT fixture is still the sentinel"
    );
    assert_eq!(
        f.pinned_commit, PINNED_FALCON_COMMIT,
        "the goldens were produced from a different Falcon commit than this crate compiles"
    );
    assert!(
        f.fp_backend.contains("FALCON_FPEMU=1"),
        "goldens must come from the emulated FP backend: {}",
        f.fp_backend
    );
    // The fixture pins deterministic.c's digest; the ffi build script pins the whole tree,
    // which contains that file. Assert the fixture's value is the known pinned one so a
    // fixture regenerated from a drifted tree cannot pass silently.
    assert_eq!(
        f.deterministic_c_sha512_256,
        "601390dc53521fc1b00eb962ea63d64c2d65bfe774450cf4ec59a3478e0a54a4"
    );
    assert!(!f.vectors.is_empty(), "no vectors");
}

#[test]
fn signatures_are_byte_identical_to_the_committed_goldens() {
    let f = load();
    let (sk, pk) = keys(&f);
    for v in &f.vectors {
        let msg = unhex(&v.message_hex);
        let golden = unhex(&v.sig_hex);
        assert_eq!(
            golden.len(),
            v.sig_len,
            "{}: fixture sig_len disagrees with sig_hex",
            v.name
        );
        assert_eq!(
            hex(&Sha512_256::digest(&golden)),
            v.sig_sha512_256,
            "{}: fixture sig_sha512_256 disagrees with sig_hex",
            v.name
        );

        let produced = sign(&sk, &msg).unwrap_or_else(|e| panic!("{}: sign failed: {e}", v.name));
        assert_eq!(
            produced.as_bytes(),
            golden.as_slice(),
            "{}: Rust signer output differs from the golden (first differing byte at {:?})",
            v.name,
            produced
                .as_bytes()
                .iter()
                .zip(golden.iter())
                .position(|(a, b)| a != b)
        );

        // And the golden verifies under the fixture public key through the checked path.
        verify(&pk, &msg, &produced).unwrap_or_else(|e| panic!("{}: verify failed: {e}", v.name));
        verify_bytes(&pk, &msg, &golden)
            .unwrap_or_else(|e| panic!("{}: verify_bytes: {e}", v.name));
    }
}

#[test]
fn goldens_do_not_verify_under_a_changed_message_or_a_flipped_byte() {
    let f = load();
    let (_, pk) = keys(&f);
    let v = &f.vectors[0];
    let msg = unhex(&v.message_hex);
    let golden = Signature::from_bytes(&unhex(&v.sig_hex)).expect("golden parses");

    let mut other = msg.clone();
    let last = other.len() - 1;
    other[last] ^= 0x01;
    assert_eq!(verify(&pk, &other, &golden), Err(VerifyError::BadSignature));

    let mut flipped = golden.as_bytes().to_vec();
    let mid = flipped.len() / 2;
    flipped[mid] ^= 0xFF;
    assert!(verify_bytes(&pk, &msg, &flipped).is_err());
}

#[test]
fn a_golden_with_the_randomised_header_is_rejected_before_the_verifier_runs() {
    // 0x3A is the RANDOMISED compressed header — what liboqs / pqcrypto emit and the AVM rejects.
    let f = load();
    let (_, pk) = keys(&f);
    let v = &f.vectors[0];
    let msg = unhex(&v.message_hex);
    let mut wrong_header = unhex(&v.sig_hex);
    wrong_header[0] = 0x3A;
    assert!(matches!(
        verify_bytes(&pk, &msg, &wrong_header),
        Err(VerifyError::Encoding(_))
    ));
}
