//! Build the vendored, pinned deterministic Falcon-1024 reference into a static library —
//! after proving the bytes are the pinned bytes.
//!
//! Two properties this script enforces, in this order:
//!
//! 1. **The tree is the pin.** Before a single C file is compiled, the script recomputes the
//!    pinned tree digest over `third_party/falcon-det1024/src` — the SAME construction as
//!    `sdk/ci/verify_pinned_digest.py` (sorted relative paths; per file `sha512/256`; digest of
//!    the lines `"<rel>:<hex>\n"`) — and compares it with the pinned value. A drifted tree, a
//!    missing file, or a stray extra file fails the build with the two digests printed. The
//!    constant lives here AND in the Python verifier: two copies of one upstream fact, both
//!    pinned to commit `ce15e75b`; if one is ever changed without the other, CI's
//!    `vendored-falcon-integrity` job disagrees with this script and the build goes red — which
//!    is the correct outcome.
//! 2. **The flags are the proven flags.** The eleven library sources are compiled with the pinned
//!    `config.h` (emulated fixed-point FP backend, `FALCON_FPEMU=1`) plus exactly the flags CI
//!    already proves byte-identical to the KAT goldens: `-DFALCON_UNALIGNED=0` (portable
//!    byte-wise PRNG reads instead of the misaligned-`uint64` fast path) and, on non-MSVC
//!    compilers, `-fno-strict-aliasing` (TBAA-safe type punning). Nothing else. No `-ffast-math`,
//!    no native FP, no AVX2/FMA — any of those can change signature bytes and would fail the
//!    byte-identity KAT by design.
//!
//! This is a build script, so it is allowed to stop the build; it does so with a message and a
//! non-zero exit rather than a panic, so the failure reads as a diagnosis, not a backtrace.

use std::{
    fs,
    path::{Path, PathBuf},
    process::exit,
};

use sha2::{Digest, Sha512_256};

/// Pinned upstream commit of `algorand/falcon`. Mirrors `PINNED_COMMIT` in
/// `sdk/ci/verify_pinned_digest.py` and `pinned_commit` in `sdk/tests/vectors/det1024_kat.json`.
const PINNED_COMMIT: &str = "ce15e75bceb372867daf6b8e81918ab6978686eb";
/// Pinned tree digest — sha512/256 over `"<rel>:<sha512_256(file)>\n"` for every file, sorted.
/// Mirrors `EXPECTED_TREE` in `sdk/ci/verify_pinned_digest.py`.
const EXPECTED_TREE_DIGEST: &str =
    "c6adf4871389dfdbf3ffbd853bd9e5ce15646b821d6dc84e327ab1b3d2adc980";
/// The vendored tree is the complete upstream tree: 27 files (see PROVENANCE.md).
const EXPECTED_FILE_COUNT: usize = 27;

/// The eleven sources every TRELYAN build of the signer compiles — the same list as the SDK's
/// CI (`ci.yml`, "Build shared library"). Order is irrelevant to the output; kept alphabetical
/// with `deterministic.c` last to match the CI line for greppability.
const LIB_SOURCES: [&str; 11] = [
    "codec.c",
    "common.c",
    "falcon.c",
    "fft.c",
    "fpr.c",
    "keygen.c",
    "rng.c",
    "shake.c",
    "sign.c",
    "vrfy.c",
    "deterministic.c",
];

fn fail(msg: &str) -> ! {
    eprintln!("\nerror[trelyan-pq-ffi/build.rs]: {msg}\n");
    exit(1);
}

/// Every file under `root`, as (relative path with '/' separators, absolute path), sorted by
/// relative path — the ordering `verify_pinned_digest.py` uses (`sorted(os.walk(...))` yields
/// the same order for this tree; both sort on the full relative path).
fn walk(root: &Path) -> Vec<(String, PathBuf)> {
    let mut out = Vec::new();
    let mut stack = vec![root.to_path_buf()];
    while let Some(dir) = stack.pop() {
        let Ok(rd) = fs::read_dir(&dir) else {
            fail(&format!("cannot read directory {}", dir.display()));
        };
        for entry in rd.flatten() {
            let p = entry.path();
            if p.is_dir() {
                if p.file_name().is_some_and(|n| n == ".git") {
                    continue;
                }
                stack.push(p);
            } else if p.is_file() {
                let rel = p
                    .strip_prefix(root)
                    .map(|r| r.to_string_lossy().replace('\\', "/"))
                    .unwrap_or_default();
                out.push((rel, p));
            }
        }
    }
    out.sort_by(|a, b| a.0.cmp(&b.0));
    out
}

fn hex(bytes: &[u8]) -> String {
    use std::fmt::Write as _;
    bytes
        .iter()
        .fold(String::with_capacity(bytes.len() * 2), |mut acc, b| {
            // Writing to a String cannot fail; the Result is discarded on purpose.
            let _ = write!(acc, "{b:02x}");
            acc
        })
}

/// `Path::canonicalize` on Windows returns a verbatim (`\\?\C:\…`) path. MinGW's gcc and some
/// MSVC tooling reject that prefix in `-I` and source arguments ("\\codec.c: No such file"), so
/// strip it back to a plain drive path. A no-op everywhere else.
fn strip_verbatim(p: &Path) -> PathBuf {
    let s = p.to_string_lossy();
    s.strip_prefix(r"\\?\")
        .map_or_else(|| p.to_path_buf(), PathBuf::from)
}

fn main() {
    let manifest_dir = PathBuf::from(
        std::env::var("CARGO_MANIFEST_DIR").unwrap_or_else(|_| fail("CARGO_MANIFEST_DIR unset")),
    );
    // rust/crates/trelyan-pq-ffi → repo root is three levels up.
    let vendored = manifest_dir
        .join("..")
        .join("..")
        .join("..")
        .join("third_party")
        .join("falcon-det1024")
        .join("src");
    let vendored = strip_verbatim(&vendored.canonicalize().unwrap_or_else(|_| {
        fail(&format!(
            "vendored Falcon tree not found at {} — expected third_party/falcon-det1024/src \
             (pinned {PINNED_COMMIT}); see third_party/falcon-det1024/PROVENANCE.md",
            vendored.display()
        ))
    }));

    // ── 1. The tree is the pin ─────────────────────────────────────────────────────────────
    let files = walk(&vendored);
    let mut tree = Sha512_256::new();
    for (rel, path) in &files {
        println!("cargo:rerun-if-changed={}", path.display());
        let bytes = fs::read(path)
            .unwrap_or_else(|e| fail(&format!("cannot read {}: {e}", path.display())));
        let file_digest = hex(&Sha512_256::digest(&bytes));
        tree.update(format!("{rel}:{file_digest}\n").as_bytes());
    }
    let tree_digest = hex(&tree.finalize());
    if files.len() != EXPECTED_FILE_COUNT || tree_digest != EXPECTED_TREE_DIGEST {
        fail(&format!(
            "vendored Falcon tree does not match the pin.\n  \
             path      : {}\n  \
             files     : {} (expected {EXPECTED_FILE_COUNT})\n  \
             tree      : {tree_digest}\n  \
             expected  : {EXPECTED_TREE_DIGEST}\n  \
             pinned    : algorand/falcon@{PINNED_COMMIT}\n\
             Refusing to compile a signer that is not the pinned reference. Re-vendor from the \
             pinned tarball (PROVENANCE.md) or, if the pin itself is being changed, update this \
             constant, sdk/ci/verify_pinned_digest.py, PROVENANCE.md, SHA256SUMS and the KAT \
             goldens together in one reviewed diff.",
            vendored.display(),
            files.len()
        ));
    }
    println!(
        "cargo:warning=trelyan-pq-ffi: vendored Falcon tree verified against pin {PINNED_COMMIT} (27 files, tree {})",
        &tree_digest[..12]
    );

    // ── 2. Compile with the proven flags ───────────────────────────────────────────────────
    let mut build = cc::Build::new();
    build.include(&vendored);
    for src in LIB_SOURCES {
        build.file(vendored.join(src));
    }
    // Portable byte-wise PRNG reads instead of the misaligned-uint64 fast path (inner.h). A
    // -D flag, not a source edit: the tree digest above is unaffected. Proven byte-identical
    // to the goldens by the SDK's 3-OS KAT job (FALCON_BUILD_HARDENING §2).
    build.define("FALCON_UNALIGNED", "0");
    build.opt_level(3);
    if !build.get_compiler().is_like_msvc() {
        // Makes the remaining FALCON_LE type-punning casts (rng.c) safe against TBAA
        // mis-compilation. MSVC omits it: cl does not assume strict TBAA. Same as ci.yml.
        build.flag("-fno-strict-aliasing");
    }
    // Upstream compiles with -Wall -Wextra and is clean; do not let cc's defaults promote
    // any warning to an error on a compiler upstream never tested — the reference is
    // consumed, never edited, so a new compiler's opinion must not block the build.
    build.warnings(false);
    build.compile("falcondet1024");

    // rng.c seeds the SHAKE PRNG from the OS: getentropy()/urandom on POSIX, and on Windows the
    // CryptoAPI (`CryptAcquireContextA` / `CryptGenRandom`, config.h FALCON_RAND_WIN32) — which
    // lives in advapi32. Same for MSVC and MinGW targets.
    if std::env::var("CARGO_CFG_TARGET_OS").as_deref() == Ok("windows") {
        println!("cargo:rustc-link-lib=advapi32");
    }

    println!("cargo:rerun-if-changed=build.rs");
}
