//! Raw bindings to the pinned, vendored deterministic Falcon-1024 (`det1024`) reference.
//!
//! **This is the only crate in the workspace permitted to contain `unsafe`** (constitution §3:
//! `#![forbid(unsafe_code)]` everywhere except a dedicated ffi crate). It does three things and
//! nothing else:
//!
//! 1. declares the C symbols exactly as `third_party/falcon-det1024/src/{falcon.h,deterministic.h}`
//!    declare them (the build script has already proven that tree is the pinned tree);
//! 2. fixes the buffer sizes those headers define as Rust constants;
//! 3. wraps each call in a safe function whose **argument types are the memory-safety proof** —
//!    fixed-size arrays for every buffer whose length the C side assumes rather than checks.
//!
//! Two of those assumptions are worth naming, because the C does NOT check them and the Rust
//! type must:
//!
//! * `falcon_det1024_sign_compressed` writes up to [`SIG_COMPRESSED_MAXSIZE`] bytes into `sig`
//!   and reports the length it used through `*sig_len` — it never reads the caller's capacity.
//!   A caller passing a shorter buffer gets a heap/stack overwrite, silently. Here `sig` is
//!   `&mut [u8; SIG_COMPRESSED_MAXSIZE]`, so a shorter buffer does not type-check.
//! * `falcon_det1024_get_salt_version` reads `sig[1]` unconditionally. Here it is only called
//!   after checking `sig.len() >= 2`.
//!
//! No policy lives here: no key types, no zeroization, no encoding checks. Those belong to
//! `trelyan-pq-core`, which is `#![forbid(unsafe_code)]` and is the crate the rest of TRELYAN
//! uses. Nothing here logs, prints, or formats key material.
//!
//! **Miri:** the constitution asks for Miri coverage of `unsafe` blocks. Miri cannot execute
//! foreign function calls, so these blocks are covered instead by the byte-identity KATs in
//! `trelyan-pq-core` (which exercise every wrapper end to end against committed goldens) and by
//! the SDK CI's ASan/UBSan sanitizer gate on the same C sources. Stated here so the gap is
//! visible rather than implied away.

#![deny(unsafe_op_in_unsafe_fn)]

use core::ffi::{c_int, c_void};

// ── sizes fixed by the pinned headers (logn = 10) ───────────────────────────────────────────

/// `FALCON_DET1024_LOGN` — Falcon-1024.
pub const LOGN: u32 = 10;
/// `FALCON_DET1024_PUBKEY_SIZE` = `FALCON_PUBKEY_SIZE(10)`.
pub const PUBKEY_SIZE: usize = 1793;
/// `FALCON_DET1024_PRIVKEY_SIZE` = `FALCON_PRIVKEY_SIZE(10)`.
pub const PRIVKEY_SIZE: usize = 2305;
/// `FALCON_DET1024_SIG_COMPRESSED_MAXSIZE` = `FALCON_SIG_COMPRESSED_MAXSIZE(10)` (1462) − 40-byte
/// salt + 1 salt-version byte. The C signer writes at most this many bytes.
pub const SIG_COMPRESSED_MAXSIZE: usize = 1423;
/// `FALCON_DET1024_SIG_CT_SIZE` = `FALCON_SIG_CT_SIZE(10)` (1577) − 40 + 1. Fixed length.
pub const SIG_CT_SIZE: usize = 1538;
/// `FALCON_DET1024_SIG_COMPRESSED_HEADER` = `0x3A | 0x80`: deterministic, compressed, n = 1024.
pub const SIG_COMPRESSED_HEADER: u8 = 0xBA;
/// `FALCON_DET1024_SIG_CT_HEADER` = `0x5A | 0x80`.
pub const SIG_CT_HEADER: u8 = 0xDA;
/// `FALCON_DET1024_CURRENT_SALT_VERSION`. Byte 1 of every signature this library produces.
pub const CURRENT_SALT_VERSION: u8 = 0;

// ── error codes (falcon.h) ──────────────────────────────────────────────────────────────────

/// `FALCON_ERR_RANDOM` — the system RNG could not be used.
pub const ERR_RANDOM: c_int = -1;
/// `FALCON_ERR_SIZE` — a provided buffer is too small.
pub const ERR_SIZE: c_int = -2;
/// `FALCON_ERR_FORMAT` — an external object (key/signature) has an invalid encoding.
pub const ERR_FORMAT: c_int = -3;
/// `FALCON_ERR_BADSIG` — the signature does not verify.
pub const ERR_BADSIG: c_int = -4;
/// `FALCON_ERR_BADARG` — an argument is out of range.
pub const ERR_BADARG: c_int = -5;
/// `FALCON_ERR_INTERNAL` — an internal computation failed.
pub const ERR_INTERNAL: c_int = -6;

/// `shake256_context` — `typedef struct { uint64_t opaque_contents[26]; } shake256_context;`
/// (falcon.h). Opaque to Rust; only ever handed back to the C functions below.
#[repr(C)]
#[derive(Clone)]
pub struct Shake256Context {
    opaque_contents: [u64; 26],
}

impl Shake256Context {
    /// An all-zero context, valid only as a target for `shake256_init` /
    /// `shake256_init_prng_from_system` — never use it before one of those has run.
    #[must_use]
    pub const fn zeroed() -> Self {
        Self {
            opaque_contents: [0; 26],
        }
    }
}

// Deliberately no `Debug`: the PRNG state seeds key generation.

unsafe extern "C" {
    fn shake256_init(sc: *mut Shake256Context);
    fn shake256_inject(sc: *mut Shake256Context, data: *const c_void, len: usize);
    fn shake256_flip(sc: *mut Shake256Context);
    fn shake256_extract(sc: *mut Shake256Context, out: *mut c_void, len: usize);
    fn shake256_init_prng_from_system(sc: *mut Shake256Context) -> c_int;

    fn falcon_det1024_keygen(
        rng: *mut Shake256Context,
        privkey: *mut c_void,
        pubkey: *mut c_void,
    ) -> c_int;
    fn falcon_det1024_sign_compressed(
        sig: *mut c_void,
        sig_len: *mut usize,
        privkey: *const c_void,
        data: *const c_void,
        data_len: usize,
    ) -> c_int;
    fn falcon_det1024_verify_compressed(
        sig: *const c_void,
        sig_len: usize,
        pubkey: *const c_void,
        data: *const c_void,
        data_len: usize,
    ) -> c_int;
    fn falcon_det1024_get_salt_version(sig: *const c_void) -> c_int;
}

/// A SHAKE256 PRNG seeded from the operating system's CSPRNG — the same path the
/// ctypes SDK uses (`getentropy` / `/dev/urandom` / `BCryptGenRandom` per `config.h`).
///
/// # Errors
/// [`ERR_RANDOM`] if the OS RNG could not be read.
pub fn prng_from_system() -> Result<Shake256Context, c_int> {
    let mut sc = Shake256Context::zeroed();
    // SAFETY: `sc` is a live, correctly sized `#[repr(C)]` shake256_context that the callee
    // fully initialises; the pointer is valid for the duration of the call.
    let rc = unsafe { shake256_init_prng_from_system(&raw mut sc) };
    if rc == 0 { Ok(sc) } else { Err(rc) }
}

/// A SHAKE256 PRNG seeded deterministically from `seed`: `init`, `inject(seed)`, `flip`.
///
/// For tests and reproducible fixtures ONLY. Keys derived from a caller-chosen seed are exactly
/// as secret as that seed; production key generation uses [`prng_from_system`].
#[must_use]
pub fn prng_from_seed(seed: &[u8]) -> Shake256Context {
    let mut sc = Shake256Context::zeroed();
    // SAFETY: `sc` is live and correctly sized for all three calls; `seed.as_ptr()` is valid
    // for `seed.len()` bytes and the C side only reads it. Sequence init→inject→flip is the
    // documented protocol (falcon.h) and the one CI's sanitizer probe uses.
    unsafe {
        shake256_init(&raw mut sc);
        shake256_inject(&raw mut sc, seed.as_ptr().cast::<c_void>(), seed.len());
        shake256_flip(&raw mut sc);
    }
    sc
}

/// `shake256_extract`: draw `out.len()` pseudo-random bytes from a FLIPPED context.
///
/// Only valid on a context produced by [`prng_from_system`] or [`prng_from_seed`] (both leave the
/// context in output mode). Used by the constant-time evidence harness for class selection and
/// random messages, so that the harness needs no RNG dependency of its own and draws from the
/// same pinned SHAKE PRNG the signer's key generation uses.
pub fn prng_extract(sc: &mut Shake256Context, out: &mut [u8]) {
    // SAFETY: `sc` is a live, correctly sized context that one of the two constructors flipped
    // into output mode; `out` is exclusively borrowed and valid for `out.len()` bytes, which is
    // exactly the length passed. The C side only writes within that range.
    unsafe { shake256_extract(&raw mut *sc, out.as_mut_ptr().cast::<c_void>(), out.len()) }
}

/// `falcon_det1024_keygen`: fill `privkey` and `pubkey` from `rng`.
///
/// # Errors
/// The C error code on failure (typically [`ERR_RANDOM`] or [`ERR_INTERNAL`]).
pub fn keygen(
    rng: &mut Shake256Context,
    privkey: &mut [u8; PRIVKEY_SIZE],
    pubkey: &mut [u8; PUBKEY_SIZE],
) -> Result<(), c_int> {
    // SAFETY: the two output buffers are exactly FALCON_DET1024_PRIVKEY_SIZE and
    // FALCON_DET1024_PUBKEY_SIZE bytes — the sizes the C side writes without checking — and
    // are exclusively borrowed for the call; `rng` is a live context from one of the two
    // constructors above.
    let rc = unsafe {
        falcon_det1024_keygen(
            &raw mut *rng,
            privkey.as_mut_ptr().cast::<c_void>(),
            pubkey.as_mut_ptr().cast::<c_void>(),
        )
    };
    if rc == 0 { Ok(()) } else { Err(rc) }
}

/// `falcon_det1024_sign_compressed`: deterministically sign `data` with `privkey` into `sig`.
///
/// Returns the number of bytes of `sig` that were written (≤ [`SIG_COMPRESSED_MAXSIZE`]). The
/// C side does not consult the buffer's capacity — the array type is the guarantee that it is
/// large enough.
///
/// **Only ever pass key bytes produced by [`keygen`] or read from a trusted, integrity-checked
/// store.** A key whose header byte says Falcon-1024 but whose body is not a valid NTRU basis
/// makes the reference signer's retry loop (`do_sign_dyn`, `for (;;)`, no iteration cap in the
/// pinned source) spin without bound — the call never returns (finding 2026-08-18, pinned by
/// `tests/negative_inputs.rs`). A corrupted key file is therefore a hang, not a clean error.
/// The vendored C is not patched for this; the guard is at the caller.
///
/// # Errors
/// The C error code: [`ERR_FORMAT`] if `privkey`'s header does not decode as a Falcon-1024 key,
/// or an internal failure.
pub fn sign_compressed(
    privkey: &[u8; PRIVKEY_SIZE],
    data: &[u8],
    sig: &mut [u8; SIG_COMPRESSED_MAXSIZE],
) -> Result<usize, c_int> {
    let mut sig_len: usize = SIG_COMPRESSED_MAXSIZE;
    // SAFETY: `sig` is exactly FALCON_DET1024_SIG_COMPRESSED_MAXSIZE bytes, the documented upper
    // bound of what the C signer writes; `sig_len` is a live out-parameter; `privkey` is exactly
    // FALCON_DET1024_PRIVKEY_SIZE bytes and read-only; `data` is valid for `data.len()` bytes and
    // read-only. All borrows outlive the call.
    let rc = unsafe {
        falcon_det1024_sign_compressed(
            sig.as_mut_ptr().cast::<c_void>(),
            &raw mut sig_len,
            privkey.as_ptr().cast::<c_void>(),
            data.as_ptr().cast::<c_void>(),
            data.len(),
        )
    };
    if rc != 0 {
        return Err(rc);
    }
    // Belt and braces: the C contract bounds this, but a wrong bound would otherwise become an
    // out-of-range slice at the caller. Report it as the C would if it checked.
    if sig_len > SIG_COMPRESSED_MAXSIZE {
        return Err(ERR_SIZE);
    }
    Ok(sig_len)
}

/// `falcon_det1024_verify_compressed`: verify `sig` over `data` under `pubkey`.
///
/// # Errors
/// [`ERR_BADSIG`] for a wrong signature, [`ERR_FORMAT`] for a malformed one, or another C code.
pub fn verify_compressed(sig: &[u8], pubkey: &[u8; PUBKEY_SIZE], data: &[u8]) -> Result<(), c_int> {
    // SAFETY: `sig` is valid for `sig.len()` bytes and passed with that exact length; `pubkey`
    // is exactly FALCON_DET1024_PUBKEY_SIZE bytes (the size the C side reads without checking);
    // `data` is valid for `data.len()` bytes. All read-only, all outlive the call.
    let rc = unsafe {
        falcon_det1024_verify_compressed(
            sig.as_ptr().cast::<c_void>(),
            sig.len(),
            pubkey.as_ptr().cast::<c_void>(),
            data.as_ptr().cast::<c_void>(),
            data.len(),
        )
    };
    if rc == 0 { Ok(()) } else { Err(rc) }
}

/// `falcon_det1024_get_salt_version`: byte 1 of a deterministic signature.
///
/// The C reads `sig[1]` unconditionally, so this refuses anything shorter than two bytes.
///
/// # Errors
/// [`ERR_SIZE`] if `sig.len() < 2`.
pub fn salt_version(sig: &[u8]) -> Result<u8, c_int> {
    if sig.len() < 2 {
        return Err(ERR_SIZE);
    }
    // SAFETY: `sig` has at least two bytes (checked above), which is all the C reads.
    let v = unsafe { falcon_det1024_get_salt_version(sig.as_ptr().cast::<c_void>()) };
    u8::try_from(v).map_err(|_| ERR_INTERNAL)
}
