//! `trelyan-pq-core` — the safe Rust surface over TRELYAN's pinned deterministic Falcon-1024.
//!
//! This is the crate the rest of TRELYAN uses. It is `#![forbid(unsafe_code)]`; every FFI call
//! lives in `trelyan-pq-ffi`, whose build script refuses to compile anything but the pinned
//! `algorand/falcon@ce15e75b` tree. What this crate adds on top of the raw calls is exactly the
//! policy the audited Python SDK (`trelyan_pq.falcon`) enforces, ported line for line in intent:
//!
//! * **Key material is a type, not a byte slice.** [`SecretKey`] is zeroized on drop, has no
//!   `Debug`/`Display`/`Serialize`, and exposes its bytes through one greppable accessor.
//! * **Signatures are checked at the boundary.** [`Signature::from_bytes`] refuses anything that
//!   is not a deterministic-compressed Falcon-1024 signature in the encoding the AVM's
//!   `falcon_verify` opcode accepts: header byte `0xBA`, salt-version byte `0x00`, length within
//!   `[2, 1423]`. Verification then runs the reference verifier on top of that.
//! * **Determinism is a property, not a hope.** [`sign`] over the same key and message yields
//!   identical bytes — asserted by tests against the committed goldens in
//!   `sdk/tests/vectors/det1024_kat.json` (byte identity with the Python SDK and, transitively,
//!   with what the chain verifies).
//!
//! What this crate does **not** do, on purpose: it does not build TRELYAN inscription messages
//! (that layout is `trelyan_pq.message` today and will be ported separately), and it does not
//! claim constant-time behaviour for the reference signer. The constitution's §2.2 discipline
//! is measured, not asserted — see the `falcon-ct` evidence work in the R&D plan.

#![forbid(unsafe_code)]

use core::fmt;

use thiserror::Error;
use zeroize::{Zeroize, ZeroizeOnDrop};

pub use trelyan_pq_ffi::{
    CURRENT_SALT_VERSION, PRIVKEY_SIZE, PUBKEY_SIZE, SIG_COMPRESSED_HEADER, SIG_COMPRESSED_MAXSIZE,
};

/// The pinned upstream commit this crate's signer is built from. Exposed so a caller can bind
/// its own KAT fixtures to the same pin (`det1024_kat.json` → `pinned_commit`).
pub const PINNED_FALCON_COMMIT: &str = "ce15e75bceb372867daf6b8e81918ab6978686eb";

// ── errors ─────────────────────────────────────────────────────────────────────────────────

/// Why a signature was rejected before or during verification.
#[derive(Debug, Error, Clone, Copy, PartialEq, Eq)]
#[non_exhaustive]
pub enum VerifyError {
    /// The signature bytes are not a deterministic-compressed Falcon-1024 signature: wrong
    /// header, wrong salt version, or a length outside `[2, SIG_COMPRESSED_MAXSIZE]`.
    #[error("malformed signature encoding: {0}")]
    Encoding(EncodingError),
    /// The signature is well-formed but does not verify under this key and message.
    #[error("signature does not verify")]
    BadSignature,
    /// The reference verifier reported a code other than BADSIG/FORMAT (never observed; kept
    /// so it cannot be mistaken for success).
    #[error("falcon reference verifier returned error code {0}")]
    Reference(i32),
}

/// The precise encoding rule a signature broke. Each variant is one row of the SDK's
/// "encoding rejection matrix" test, so a rejection names the rule, not just "bad".
#[derive(Debug, Error, Clone, Copy, PartialEq, Eq)]
#[non_exhaustive]
pub enum EncodingError {
    /// Fewer than two bytes: no room for header + salt version.
    #[error("too short ({len} bytes; need at least 2)")]
    TooShort { len: usize },
    /// Longer than `FALCON_DET1024_SIG_COMPRESSED_MAXSIZE`.
    #[error("too long ({len} bytes; max {SIG_COMPRESSED_MAXSIZE})")]
    TooLong { len: usize },
    /// Byte 0 is not `0xBA` (deterministic | compressed | n = 1024).
    #[error("header byte {found:#04x}, expected {SIG_COMPRESSED_HEADER:#04x}")]
    Header { found: u8 },
    /// Byte 1 is not the current salt version.
    #[error("salt version {found}, expected {CURRENT_SALT_VERSION}")]
    SaltVersion { found: u8 },
}

/// Why signing failed. The reference signer only fails on a malformed key or an internal error;
/// both are surfaced, neither is silently retried.
#[derive(Debug, Error, Clone, Copy, PartialEq, Eq)]
#[non_exhaustive]
pub enum SignError {
    /// The secret key bytes do not decode as a Falcon-1024 private key.
    #[error("secret key does not decode as Falcon-1024 (reference code {0})")]
    KeyFormat(i32),
    /// Any other reference-signer failure code.
    #[error("falcon reference signer returned error code {0}")]
    Reference(i32),
}

/// Why key generation failed.
#[derive(Debug, Error, Clone, Copy, PartialEq, Eq)]
#[non_exhaustive]
pub enum KeygenError {
    /// The operating system CSPRNG could not be read.
    #[error("operating-system RNG unavailable (reference code {0})")]
    Rng(i32),
    /// Any other reference-keygen failure code.
    #[error("falcon reference keygen returned error code {0}")]
    Reference(i32),
}

// ── keys ───────────────────────────────────────────────────────────────────────────────────

/// A Falcon-1024 public key: exactly [`PUBKEY_SIZE`] (1793) bytes, first byte `0x0A`
/// (`0x00 | logn`), as the AVM opcode expects it.
#[derive(Clone, PartialEq, Eq)]
pub struct PublicKey([u8; PUBKEY_SIZE]);

impl PublicKey {
    /// Wrap 1793 bytes. No structural validation beyond the length the type enforces: the
    /// reference verifier decodes the key on every use and rejects a malformed one as
    /// [`VerifyError::Reference`] with `FALCON_ERR_FORMAT` (−3).
    #[must_use]
    pub const fn from_bytes(bytes: [u8; PUBKEY_SIZE]) -> Self {
        Self(bytes)
    }

    /// The raw encoding, e.g. to place in an inscription box.
    #[must_use]
    pub const fn as_bytes(&self) -> &[u8; PUBKEY_SIZE] {
        &self.0
    }
}

impl fmt::Debug for PublicKey {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        // Public, but 1793 bytes of hex is noise; show the length and a prefix.
        write!(
            f,
            "PublicKey({} bytes, {:02x}{:02x}{:02x}{:02x}…)",
            PUBKEY_SIZE, self.0[0], self.0[1], self.0[2], self.0[3]
        )
    }
}

/// A Falcon-1024 secret key: exactly [`PRIVKEY_SIZE`] (2305) bytes.
///
/// Zeroized on drop. Deliberately implements neither `Debug`, `Display`, `Clone` nor any
/// serialisation: the only way to read the bytes is [`SecretKey::expose`], which is greppable in
/// review. **Scope, stated exactly:** zeroization covers this struct's own bytes. The reference
/// signer's C stack temporaries and any caller-side copies made before construction are outside
/// this guarantee (the same inventory the SDK's `seal` module states for its side).
#[derive(Zeroize, ZeroizeOnDrop)]
pub struct SecretKey([u8; PRIVKEY_SIZE]);

impl SecretKey {
    /// Wrap 2305 bytes the caller already holds (deserialisation, KAT fixtures). Callers should
    /// zeroize their own copy afterwards; this type owns only what it was given.
    ///
    /// **No structural validation is performed, and none is cheap:** the reference decodes only
    /// the header byte. Bytes whose header says Falcon-1024 but whose body is not a valid NTRU
    /// basis will make [`sign`] **hang** (the reference signer's retry loop has no iteration cap;
    /// finding 2026-08-18, see `trelyan-pq-ffi/tests/negative_inputs.rs`), not fail. Only wrap
    /// bytes that came from [`keygen`] or from a store whose integrity you have already checked
    /// (e.g. an authenticated container, or a self-KAT sign+verify performed on a *known-good*
    /// copy). A corrupted key file is an availability hazard here, by design of the reference.
    #[must_use]
    pub const fn from_bytes(bytes: [u8; PRIVKEY_SIZE]) -> Self {
        Self(bytes)
    }

    /// Borrow the raw key. The one read path — keep call sites few and obvious.
    #[must_use]
    pub const fn expose(&self) -> &[u8; PRIVKEY_SIZE] {
        &self.0
    }
}

/// Generate a fresh keypair from the operating system's CSPRNG (constitution §2.4).
///
/// # Errors
/// [`KeygenError::Rng`] if the OS RNG cannot be read; [`KeygenError::Reference`] otherwise.
pub fn keygen() -> Result<(SecretKey, PublicKey), KeygenError> {
    let mut rng = trelyan_pq_ffi::prng_from_system().map_err(KeygenError::Rng)?;
    keygen_with(&mut rng)
}

/// Generate a keypair from a caller-supplied seed — **tests and reproducible fixtures only.**
///
/// The keys are exactly as secret as `seed`. Production key generation is [`keygen`].
///
/// # Errors
/// [`KeygenError::Reference`] on a reference-keygen failure.
pub fn keygen_from_seed_for_tests(seed: &[u8]) -> Result<(SecretKey, PublicKey), KeygenError> {
    let mut rng = trelyan_pq_ffi::prng_from_seed(seed);
    keygen_with(&mut rng)
}

fn keygen_with(
    rng: &mut trelyan_pq_ffi::Shake256Context,
) -> Result<(SecretKey, PublicKey), KeygenError> {
    let mut sk = [0u8; PRIVKEY_SIZE];
    let mut pk = [0u8; PUBKEY_SIZE];
    match trelyan_pq_ffi::keygen(rng, &mut sk, &mut pk) {
        Ok(()) => Ok((SecretKey::from_bytes(sk), PublicKey::from_bytes(pk))),
        Err(code) => {
            // Wipe whatever partial state the failed call may have left behind.
            sk.zeroize();
            Err(if code == trelyan_pq_ffi::ERR_RANDOM {
                KeygenError::Rng(code)
            } else {
                KeygenError::Reference(code)
            })
        }
    }
}

// ── signatures ─────────────────────────────────────────────────────────────────────────────

/// A deterministic-compressed Falcon-1024 signature in the AVM encoding: `0xBA`, salt-version
/// `0x00`, then the compressed signature body. Length is variable, at most
/// [`SIG_COMPRESSED_MAXSIZE`].
///
/// Constructed only by [`sign`] or by [`Signature::from_bytes`], which checks the encoding —
/// so holding a `Signature` means the boundary checks have already run.
#[derive(Clone, PartialEq, Eq)]
pub struct Signature(Vec<u8>);

impl Signature {
    /// Parse and CHECK signature bytes: length in `[2, SIG_COMPRESSED_MAXSIZE]`, header `0xBA`,
    /// salt version `0x00`. This is the SDK's encoding rejection matrix, as a constructor.
    ///
    /// # Errors
    /// The specific [`EncodingError`] rule that was broken.
    pub fn from_bytes(bytes: &[u8]) -> Result<Self, EncodingError> {
        let len = bytes.len();
        if len < 2 {
            return Err(EncodingError::TooShort { len });
        }
        if len > SIG_COMPRESSED_MAXSIZE {
            return Err(EncodingError::TooLong { len });
        }
        if bytes[0] != SIG_COMPRESSED_HEADER {
            return Err(EncodingError::Header { found: bytes[0] });
        }
        if bytes[1] != CURRENT_SALT_VERSION {
            return Err(EncodingError::SaltVersion { found: bytes[1] });
        }
        Ok(Self(bytes.to_vec()))
    }

    /// The raw encoding — what goes on-chain.
    #[must_use]
    pub fn as_bytes(&self) -> &[u8] {
        &self.0
    }

    /// Length in bytes.
    #[must_use]
    pub const fn len(&self) -> usize {
        self.0.len()
    }

    /// Always `false` for a constructed value (the constructor rejects `< 2` bytes); provided
    /// because clippy asks for it alongside `len`.
    #[must_use]
    pub const fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    /// The salt-version byte (byte 1). Always [`CURRENT_SALT_VERSION`] for a value built by
    /// [`sign`] or [`Signature::from_bytes`].
    #[must_use]
    pub fn salt_version(&self) -> u8 {
        self.0[1]
    }
}

impl fmt::Debug for Signature {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "Signature({} bytes, header {:#04x})",
            self.0.len(),
            self.0[0]
        )
    }
}

/// Deterministically sign `message` (the RAW message bytes — do not pre-hash) with `sk`.
///
/// Same key + same message ⇒ identical bytes, on every platform the pinned build supports.
///
/// # Errors
/// [`SignError::KeyFormat`] if `sk` does not decode; [`SignError::Reference`] otherwise.
pub fn sign(sk: &SecretKey, message: &[u8]) -> Result<Signature, SignError> {
    let mut buf = [0u8; SIG_COMPRESSED_MAXSIZE];
    let n = trelyan_pq_ffi::sign_compressed(sk.expose(), message, &mut buf).map_err(|code| {
        if code == trelyan_pq_ffi::ERR_FORMAT {
            SignError::KeyFormat(code)
        } else {
            SignError::Reference(code)
        }
    })?;
    // The reference signer wrote `n` bytes starting with the header; re-check through the same
    // constructor every external signature goes through, so the two paths cannot drift.
    Signature::from_bytes(&buf[..n]).map_err(|_| SignError::Reference(trelyan_pq_ffi::ERR_INTERNAL))
}

/// Verify `sig` over `message` under `pk`.
///
/// Encoding checks already ran when `sig` was constructed; this runs the reference verifier.
///
/// # Errors
/// [`VerifyError::BadSignature`] if the signature does not verify; [`VerifyError::Encoding`] if
/// the reference verifier rejects the encoding at a level the constructor does not check
/// (`FALCON_ERR_FORMAT`); [`VerifyError::Reference`] for any other code.
pub fn verify(pk: &PublicKey, message: &[u8], sig: &Signature) -> Result<(), VerifyError> {
    match trelyan_pq_ffi::verify_compressed(sig.as_bytes(), pk.as_bytes(), message) {
        Ok(()) => Ok(()),
        Err(code) if code == trelyan_pq_ffi::ERR_BADSIG => Err(VerifyError::BadSignature),
        Err(code) if code == trelyan_pq_ffi::ERR_FORMAT => Err(VerifyError::Encoding(
            // The constructor guarantees header/salt/length, so a FORMAT here is the body.
            // Report the header row so the caller still gets a specific, non-success answer.
            EncodingError::Header {
                found: sig.as_bytes()[0],
            },
        )),
        Err(code) => Err(VerifyError::Reference(code)),
    }
}

/// Convenience: parse raw signature bytes and verify in one step. Never accepts what
/// [`Signature::from_bytes`] would reject.
///
/// # Errors
/// As [`Signature::from_bytes`] then [`verify`].
pub fn verify_bytes(pk: &PublicKey, message: &[u8], sig: &[u8]) -> Result<(), VerifyError> {
    let sig = Signature::from_bytes(sig).map_err(VerifyError::Encoding)?;
    verify(pk, message, &sig)
}

#[cfg(test)]
mod tests {
    // Tests panic by design; the constitution's deny applies to library code.
    #![allow(clippy::expect_used, clippy::unwrap_used, clippy::panic)]

    use super::*;

    #[test]
    fn keygen_sign_verify_roundtrip_and_determinism() {
        let (sk, pk) = keygen_from_seed_for_tests(b"trelyan-pq-core unit seed 1").expect("keygen");
        let msg = b"the raw message, not a hash";
        let s1 = sign(&sk, msg).expect("sign");
        let s2 = sign(&sk, msg).expect("sign again");
        assert_eq!(s1, s2, "deterministic signing must be byte-identical");
        assert_eq!(s1.as_bytes()[0], SIG_COMPRESSED_HEADER);
        assert_eq!(s1.salt_version(), CURRENT_SALT_VERSION);
        assert!(s1.len() <= SIG_COMPRESSED_MAXSIZE);
        verify(&pk, msg, &s1).expect("verifies");
    }

    #[test]
    fn wrong_message_and_wrong_key_are_rejected() {
        let (sk, pk) = keygen_from_seed_for_tests(b"seed A").expect("keygen");
        let (_, pk_other) = keygen_from_seed_for_tests(b"seed B").expect("keygen");
        let s = sign(&sk, b"m").expect("sign");
        assert_eq!(verify(&pk, b"m2", &s), Err(VerifyError::BadSignature));
        assert_eq!(verify(&pk_other, b"m", &s), Err(VerifyError::BadSignature));
    }

    #[test]
    fn a_flipped_byte_is_rejected() {
        let (sk, pk) = keygen_from_seed_for_tests(b"seed C").expect("keygen");
        let s = sign(&sk, b"m").expect("sign");
        let mut raw = s.as_bytes().to_vec();
        let mid = raw.len() / 2;
        raw[mid] ^= 0xFF;
        assert!(verify_bytes(&pk, b"m", &raw).is_err());
    }

    #[test]
    fn encoding_rejection_matrix() {
        // Each row names the rule, matching the SDK's test_sdk_encoding_rejection_matrix.
        assert_eq!(
            Signature::from_bytes(&[]),
            Err(EncodingError::TooShort { len: 0 })
        );
        assert_eq!(
            Signature::from_bytes(&[0xBA]),
            Err(EncodingError::TooShort { len: 1 })
        );
        let too_long = vec![0xBA; SIG_COMPRESSED_MAXSIZE + 1];
        assert_eq!(
            Signature::from_bytes(&too_long),
            Err(EncodingError::TooLong {
                len: SIG_COMPRESSED_MAXSIZE + 1
            })
        );
        // 0x3A is the RANDOMISED compressed header — the liboqs/pqcrypto shape the AVM rejects.
        assert_eq!(
            Signature::from_bytes(&[0x3A, 0x00, 1, 2, 3]),
            Err(EncodingError::Header { found: 0x3A })
        );
        assert_eq!(
            Signature::from_bytes(&[0xBA, 0x01, 1, 2, 3]),
            Err(EncodingError::SaltVersion { found: 1 })
        );
        // Well-formed prefix passes the constructor (verification is a separate question).
        assert!(Signature::from_bytes(&[0xBA, 0x00, 1, 2, 3]).is_ok());
    }

    #[test]
    fn a_seeded_key_reproduces_and_seeds_differ() {
        let (sk1, pk1) = keygen_from_seed_for_tests(b"same").expect("keygen");
        let (sk2, pk2) = keygen_from_seed_for_tests(b"same").expect("keygen");
        let (_, pk3) = keygen_from_seed_for_tests(b"different").expect("keygen");
        assert_eq!(pk1, pk2);
        assert_eq!(sk1.expose(), sk2.expose());
        assert_ne!(pk1, pk3);
    }

    #[test]
    fn os_rng_keygen_works_and_public_key_has_the_logn_header() {
        let (sk, pk) = keygen().expect("OS RNG keygen");
        assert_eq!(
            pk.as_bytes()[0],
            0x0A,
            "Falcon-1024 public key header is 0x00 | logn(10)"
        );
        let s = sign(&sk, b"x").expect("sign");
        verify(&pk, b"x", &s).expect("verify");
    }

    #[test]
    fn debug_never_prints_secret_key_bytes() {
        // SecretKey has no Debug at all — this is a compile-time property; assert the public
        // types' Debug is bounded so a log line cannot become a key dump by accident.
        let (_, pk) = keygen_from_seed_for_tests(b"dbg").expect("keygen");
        let d = format!("{pk:?}");
        assert!(d.len() < 64, "{d}");
    }
}
