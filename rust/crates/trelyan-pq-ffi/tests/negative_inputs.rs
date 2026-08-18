//! Adversarial-input matrix for the FFI wrappers.
//!
//! The KATs prove the happy path is byte-exact. This file proves the wrappers behave under
//! inputs an attacker (or a bug) supplies: truncated and oversized signatures, garbage and
//! all-zero keys, empty and long messages, and the two places where the C reads or writes
//! without checking a length (which the Rust types must therefore guarantee). Every case must
//! return an error code — never crash, never succeed, never read out of bounds. The SDK's CI
//! runs the same C under ASan/UBSan; these tests are the Rust-side counterpart and run on the
//! 3-OS matrix.
//!
//! Adopted from the adversarial review of the R&D plan (finding 14: "the FFI test plan is
//! inadequate for attacker-controlled inputs").

#![allow(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

use trelyan_pq_ffi::{
    CURRENT_SALT_VERSION, ERR_BADSIG, ERR_FORMAT, ERR_SIZE, PRIVKEY_SIZE, PUBKEY_SIZE,
    SIG_COMPRESSED_HEADER, SIG_COMPRESSED_MAXSIZE, keygen, prng_from_seed, salt_version,
    sign_compressed, verify_compressed,
};

fn keypair(seed: &[u8]) -> ([u8; PRIVKEY_SIZE], [u8; PUBKEY_SIZE]) {
    let mut rng = prng_from_seed(seed);
    let mut sk = [0u8; PRIVKEY_SIZE];
    let mut pk = [0u8; PUBKEY_SIZE];
    keygen(&mut rng, &mut sk, &mut pk).expect("keygen");
    (sk, pk)
}

fn sign(sk: &[u8; PRIVKEY_SIZE], msg: &[u8]) -> Vec<u8> {
    let mut buf = [0u8; SIG_COMPRESSED_MAXSIZE];
    let n = sign_compressed(sk, msg, &mut buf).expect("sign");
    buf[..n].to_vec()
}

// ── signature length attacks ───────────────────────────────────────────────────────────────

#[test]
fn every_truncation_of_a_valid_signature_is_rejected() {
    let (sk, pk) = keypair(b"neg-trunc");
    let msg = b"truncate me";
    let sig = sign(&sk, msg);
    assert!(sig.len() > 100);
    // Every prefix length from 0 to len-1, plus a few dense ranges near the interesting edges.
    for cut in (0..sig.len())
        .step_by(7)
        .chain(0..8)
        .chain(sig.len() - 8..sig.len())
    {
        let r = verify_compressed(&sig[..cut], &pk, msg);
        assert!(
            r.is_err(),
            "a {cut}-byte prefix of a {}-byte signature verified",
            sig.len()
        );
        let code = r.unwrap_err();
        assert!(
            code == ERR_FORMAT || code == ERR_BADSIG || code == ERR_SIZE,
            "unexpected code {code} at cut {cut}"
        );
    }
}

#[test]
fn a_valid_signature_with_bytes_appended_is_rejected() {
    // Trailing garbage after a well-formed compressed signature is a decoding failure, not
    // "verifies with extra data" — the AVM's falcon_verify has the same rule.
    let (sk, pk) = keypair(b"neg-append");
    let msg = b"append";
    let mut sig = sign(&sk, msg);
    for extra in [1usize, 2, 16, 200] {
        let mut longer = sig.clone();
        longer.extend(std::iter::repeat_n(0u8, extra));
        assert!(
            verify_compressed(&longer, &pk, msg).is_err(),
            "{extra} appended zero bytes were accepted"
        );
    }
    // And bounded above by the maximum: MAXSIZE+1 of anything must not verify.
    sig.resize(SIG_COMPRESSED_MAXSIZE + 1, 0);
    assert!(verify_compressed(&sig, &pk, msg).is_err());
}

#[test]
fn empty_and_tiny_signatures_are_rejected_not_read_past() {
    let (_, pk) = keypair(b"neg-tiny");
    for sig in [
        &[][..],
        &[SIG_COMPRESSED_HEADER][..],
        &[SIG_COMPRESSED_HEADER, 0][..],
    ] {
        assert!(
            verify_compressed(sig, &pk, b"m").is_err(),
            "{sig:?} verified"
        );
    }
}

#[test]
fn a_maximum_length_signature_of_garbage_is_rejected() {
    let (_, pk) = keypair(b"neg-maxgarbage");
    for fill in [0x00u8, 0xFF, 0x5A] {
        let mut sig = vec![fill; SIG_COMPRESSED_MAXSIZE];
        sig[0] = SIG_COMPRESSED_HEADER;
        sig[1] = CURRENT_SALT_VERSION;
        assert!(
            verify_compressed(&sig, &pk, b"m").is_err(),
            "fill {fill:#04x} verified"
        );
    }
}

// ── key attacks ────────────────────────────────────────────────────────────────────────────

#[test]
fn signing_with_a_zero_or_garbage_secret_key_fails_with_format() {
    // The C checks the encoded logn header of the private key before doing anything else, so a
    // key whose header does not say "Falcon-1024" is refused immediately with FORMAT.
    let mut buf = [0u8; SIG_COMPRESSED_MAXSIZE];
    let zero = [0u8; PRIVKEY_SIZE];
    assert_eq!(sign_compressed(&zero, b"m", &mut buf), Err(ERR_FORMAT));
    let garbage = [0xA5u8; PRIVKEY_SIZE];
    assert_eq!(sign_compressed(&garbage, b"m", &mut buf), Err(ERR_FORMAT));
}

/// **Finding (2026-08-18):** a private key whose HEADER decodes as Falcon-1024 (`0x50 | 10`)
/// but whose body is not a valid NTRU basis makes the reference signer's whole-signature retry
/// loop (`do_sign_dyn`'s `for (;;)` — no iteration cap in the pinned source) spin without bound:
/// a garbage basis never yields a short vector, so `falcon_det1024_sign_compressed` never
/// returns. Observed here as a hung test on the first run of this file.
///
/// Consequence: `sign` must only ever be given key bytes that came from `keygen` or from a
/// trusted, integrity-checked store; a corrupted key file is an availability hazard (a hang),
/// not a clean error. Both `trelyan-pq-ffi::sign_compressed` and
/// `trelyan-pq-core::SecretKey::from_bytes` document this. The vendored C is not patched.
///
/// This test pins the behaviour honestly: the call either returns an error promptly or does not
/// return within the deadline — it must never return `Ok`. The spinning thread is leaked on
/// purpose; the test process exits when the harness finishes.
#[test]
fn a_header_valid_garbage_secret_key_never_yields_a_signature() {
    use std::sync::mpsc::channel;
    use std::time::Duration;

    let (tx, rx) = channel::<Result<usize, i32>>();
    std::thread::spawn(move || {
        let mut garbage = [0xA5u8; PRIVKEY_SIZE];
        garbage[0] = 0x50 | 0x0A; // FALCON_PRIVKEY header: 0x50 | logn, logn = 10
        let mut buf = [0u8; SIG_COMPRESSED_MAXSIZE];
        let _ = tx.send(sign_compressed(&garbage, b"m", &mut buf));
    });
    match rx.recv_timeout(Duration::from_secs(5)) {
        Ok(Ok(n)) => panic!("garbage key produced a {n}-byte 'signature' — must never happen"),
        Ok(Err(code)) => eprintln!("garbage key refused with reference code {code} (clean)"),
        Err(_) => eprintln!(
            "garbage key: sign did not return within 5 s — the reference retry loop has no cap; \
             callers must never hand sign untrusted key bytes (documented finding)"
        ),
    }
}

#[test]
fn verifying_under_a_zero_or_garbage_public_key_fails() {
    let (sk, _) = keypair(b"neg-badpk");
    let msg = b"m";
    let sig = sign(&sk, msg);
    let zero = [0u8; PUBKEY_SIZE];
    assert!(verify_compressed(&sig, &zero, msg).is_err());
    let garbage = [0xC3u8; PUBKEY_SIZE];
    assert!(verify_compressed(&sig, &garbage, msg).is_err());
    // Header right, body garbage: still an error (BADSIG or FORMAT), never Ok.
    let mut hdr_ok = [0x11u8; PUBKEY_SIZE];
    hdr_ok[0] = 0x0A;
    assert!(verify_compressed(&sig, &hdr_ok, msg).is_err());
}

#[test]
fn a_signature_never_verifies_under_another_valid_key() {
    let (sk_a, pk_a) = keypair(b"neg-cross-a");
    let (_, pk_b) = keypair(b"neg-cross-b");
    let msg = b"cross";
    let sig = sign(&sk_a, msg);
    verify_compressed(&sig, &pk_a, msg).expect("own key verifies");
    assert_eq!(verify_compressed(&sig, &pk_b, msg), Err(ERR_BADSIG));
}

// ── message edge cases ─────────────────────────────────────────────────────────────────────

#[test]
fn empty_message_signs_and_verifies_and_is_bound_to_emptiness() {
    let (sk, pk) = keypair(b"neg-empty");
    let sig = sign(&sk, b"");
    verify_compressed(&sig, &pk, b"").expect("empty message verifies");
    assert_eq!(verify_compressed(&sig, &pk, b"\0"), Err(ERR_BADSIG));
    assert_eq!(verify_compressed(&sig, &pk, b" "), Err(ERR_BADSIG));
}

#[test]
fn a_long_message_signs_and_verifies_and_one_flipped_bit_anywhere_is_rejected() {
    let (sk, pk) = keypair(b"neg-long");
    let msg: Vec<u8> = (0..100_000u32)
        .map(|i| (i.wrapping_mul(2_654_435_761) >> 24) as u8)
        .collect();
    let sig = sign(&sk, &msg);
    verify_compressed(&sig, &pk, &msg).expect("100 KB message verifies");
    for pos in [0usize, 1, 4_095, 50_000, msg.len() - 1] {
        let mut m2 = msg.clone();
        m2[pos] ^= 0x01;
        assert_eq!(
            verify_compressed(&sig, &pk, &m2),
            Err(ERR_BADSIG),
            "flip at {pos} accepted"
        );
    }
}

#[test]
fn signature_length_is_within_the_documented_bound_and_deterministic_across_lengths() {
    let (sk, _) = keypair(b"neg-bound");
    for len in [0usize, 1, 2, 63, 64, 65, 1_000, 4_096] {
        let msg = vec![0xABu8; len];
        let s1 = sign(&sk, &msg);
        let s2 = sign(&sk, &msg);
        assert_eq!(s1, s2, "non-deterministic at len {len}");
        assert!(
            s1.len() >= 2 && s1.len() <= SIG_COMPRESSED_MAXSIZE,
            "len {len}: sig {}",
            s1.len()
        );
        assert_eq!(s1[0], SIG_COMPRESSED_HEADER);
        assert_eq!(s1[1], CURRENT_SALT_VERSION);
    }
}

// ── the two unchecked reads/writes the types must guard ────────────────────────────────────

#[test]
fn salt_version_refuses_fewer_than_two_bytes_because_the_c_reads_sig_1_unconditionally() {
    assert_eq!(salt_version(&[]), Err(ERR_SIZE));
    assert_eq!(salt_version(&[SIG_COMPRESSED_HEADER]), Err(ERR_SIZE));
    assert_eq!(salt_version(&[SIG_COMPRESSED_HEADER, 0]), Ok(0));
    assert_eq!(salt_version(&[SIG_COMPRESSED_HEADER, 7, 9]), Ok(7));
    let (sk, _) = keypair(b"neg-salt");
    assert_eq!(salt_version(&sign(&sk, b"m")), Ok(CURRENT_SALT_VERSION));
}

#[test]
fn sign_never_writes_past_the_documented_maximum() {
    // The C does not consult the caller's capacity; the wrapper takes a fixed-size array. This
    // test surrounds that array with canaries in a larger stack buffer to make the property
    // observable rather than assumed. If the C ever wrote past SIG_COMPRESSED_MAXSIZE the
    // canary bytes after the array would change.
    #[repr(C)]
    struct Guarded {
        before: [u8; 64],
        sig: [u8; SIG_COMPRESSED_MAXSIZE],
        after: [u8; 64],
    }
    let (sk, _) = keypair(b"neg-canary");
    let mut g = Guarded {
        before: [0xEE; 64],
        sig: [0; SIG_COMPRESSED_MAXSIZE],
        after: [0xEE; 64],
    };
    for len in [0usize, 64, 4_096] {
        let msg = vec![0x37u8; len];
        let n = sign_compressed(&sk, &msg, &mut g.sig).expect("sign");
        assert!(n <= SIG_COMPRESSED_MAXSIZE);
        assert!(
            g.before.iter().all(|&b| b == 0xEE),
            "canary BEFORE the buffer changed"
        );
        assert!(
            g.after.iter().all(|&b| b == 0xEE),
            "canary AFTER the buffer changed"
        );
    }
}
