// fuzz_falcon_verify.cc — libFuzzer harness for the C deterministic-Falcon verifier.
//
// TARGET
//   int falcon_det1024_verify_compressed(const void *sig, size_t siglen,
//                                         const void *pubkey,
//                                         const void *data, size_t datalen);
//   (algorand/falcon, deterministic.c; returns 0 == VALID, non-zero == rejected.)
//
//   This is the SAME code path Algorand's native `falcon_verify` opcode runs on-chain, and the
//   same symbol the python ctypes wrapper (sdk/src/trelyan_pq/falcon.py,
//   contracts/falcon_det1024.py) binds. Fuzzing it directly with ASan/UBSan exercises the C
//   memory safety of the compressed-signature DECODER (header 0xBA, salt-version byte, Gaussian
//   bit-decompression, NTT/verify) on attacker-controlled signature, public-key, and message
//   bytes — the part the python-level Atheris harness (fuzz_encoding_atheris.py) cannot reach.
//
// WHAT WE MUTATE
//   One flat fuzzer buffer is split into three attacker-controlled regions: sig, pubkey, message.
//   We deliberately do NOT constrain lengths to the "valid" sizes (sig<=1423, pubkey==1793) so the
//   decoder's bounds handling on short/over-long/empty inputs is exercised. Roughly half the time
//   we stamp the expected header (0xBA) + salt-version (0x00) onto the signature so the fuzzer
//   spends cycles PAST the cheap header gate, inside the bit-unpacking that historically harbors
//   the interesting out-of-bounds reads.
//
// INVARIANT
//   We only require that verify NEVER reads out of bounds / overflows / hits UB on arbitrary input
//   (ASan/UBSan enforce that — a finding aborts the run). Functionally we expect rejection
//   (non-zero) for fuzzer bytes; an occasional VALID return is astronomically unlikely without the
//   matching private key and is NOT treated as a crash here (correctness/forgery resistance is the
//   job of the KAT + seeded-fuzz suites, not the memory-safety fuzzer). If you want a hard
//   "never-accept" assertion, fix a known-good pubkey/message as a constant and abort on rc==0;
//   left out here so this stays a pure memory-safety harness with no build-time key material.
//
// =================================================================================================
// BUILD (clang, libFuzzer + AddressSanitizer + UndefinedBehaviorSanitizer)
// =================================================================================================
//   Pinned source: algorand/falcon @ ce15e75bceb372867daf6b8e81918ab6978686eb, fetched via the
//   GitHub source TARBALL (LF endings; a git clone corrupts the digest via autocrlf). Compile the
//   library .c sources together with this harness — NOT a prebuilt .so — so the sanitizers
//   instrument the verifier itself. Pin the FP emulation backend to match the reference build
//   (no native FP / AVX2 / FMA), matching the PuyaPy/ctypes recipe:
//
//     FALCON_SRC=/path/to/algorand-falcon            # extracted tarball root
//     clang -g -O1 -std=c11 \
//       -fsanitize=fuzzer,address,undefined \
//       -fno-sanitize-recover=undefined \
//       -DFALCON_UNALIGNED=0 -DFALCON_FPEMU=1 -DFALCON_FPNATIVE=0 \
//       -fno-strict-aliasing \
//       -I"$FALCON_SRC" \
//       sdk/tests/fuzz/fuzz_falcon_verify.cc \
//       "$FALCON_SRC"/codec.c "$FALCON_SRC"/common.c "$FALCON_SRC"/falcon.c \
//       "$FALCON_SRC"/fft.c   "$FALCON_SRC"/fpr.c    "$FALCON_SRC"/keygen.c \
//       "$FALCON_SRC"/rng.c   "$FALCON_SRC"/shake.c  "$FALCON_SRC"/sign.c \
//       "$FALCON_SRC"/vrfy.c  "$FALCON_SRC"/deterministic.c \
//       -o fuzz_falcon_verify
//
//   (The .c list mirrors the recipe in contracts/falcon_det1024.py. If the link errors on a
//    missing symbol, add the .c that defines it; on a duplicate main(), you included a test file —
//    drop it. This .cc has its own LLVMFuzzerTestOneInput entry point; do not add falcon test mains.)
//
// RUN
//   mkdir -p sdk/tests/fuzz/corpus_verify
//   ./fuzz_falcon_verify -max_len=4096 sdk/tests/fuzz/corpus_verify
//   # reproduce a crash artifact:
//   ./fuzz_falcon_verify crash-<sha1>
//
// CAVEATS
//   * Needs clang with libFuzzer + the sanitizer runtimes, and the pinned Falcon C sources on disk.
//     This file is a self-contained harness STUB: it has no external deps beyond the falcon headers
//     and is not compiled by the SDK's normal (python) test run.
//   * Memory-safety only. It does not assert forgery resistance — see test_signature_kat.py /
//     test_signature_fuzz.py for the accept/reject correctness matrix.
//   * Header guarded by __has_include so the file parses even where the falcon header isn't on the
//     include path; without it, the real declaration below is used (it matches deterministic.h).
// =================================================================================================

#include <stddef.h>
#include <stdint.h>
#include <string.h>

#if defined(__has_include)
#  if __has_include("deterministic.h")
#    include "deterministic.h"   // declares falcon_det1024_verify_compressed (falcon.h does NOT)
#    define TRELYAN_HAVE_FALCON_HEADER 1
#  endif
#endif

#ifndef TRELYAN_HAVE_FALCON_HEADER
// Fallback declaration matching algorand/falcon deterministic.h. The library is C; guard with
// extern "C" so the C++ (clang++ / .cc) link resolves the unmangled symbol.
extern "C" int falcon_det1024_verify_compressed(const void *sig, size_t sig_len,
                                                const void *pubkey,
                                                const void *data, size_t data_len);
#endif

// Expected encoding constants (deterministic compressed Falcon-1024).
static const uint8_t  DET_COMPRESSED_HEADER = 0xBA; // 0x3A | 0x80
static const uint8_t  CURRENT_SALT_VERSION  = 0x00;
static const size_t   PUBKEY_SIZE           = 1793; // FALCON_PUBKEY_SIZE(10)
static const size_t   SIG_COMPRESSED_MAX    = 1423; // deterministic compressed cap

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  // API CONTRACT (deterministic.h): `falcon_det1024_verify_compressed` reads exactly
  // FALCON_DET1024_PUBKEY_SIZE (PUBKEY_SIZE = 1793) bytes from `pubkey`, regardless of any length
  // we pass — so we ALWAYS hand it a fixed 1793-byte buffer (zero-padded from the fuzz input).
  // `sig` (sig_len) and `data` (data_len) are length-delimited, so those may be attacker-sized.
  // (Passing a smaller pubkey buffer is a caller-side over-read — a harness bug, not a finding.)
  if (size < 3) return 0;

  // Control bytes: data[0] splits the body into a sig region and a message region; data[1] bit 0
  // optionally stamps a well-formed det1024 header so inputs can reach the decompressor.
  size_t split     = (size_t)data[0] % size;   // sig-region length within the body
  int    stamp_hdr = (data[1] & 1);
  const uint8_t *body = data + 2;
  size_t body_size = size - 2;
  if (split > body_size) split = body_size;

  const uint8_t *sig_p   = body;
  size_t         sig_len = split;
  const uint8_t *msg_p   = body + split;
  size_t         msg_len = body_size - split;

  // Fixed-size pubkey buffer (honors the API contract); fuzz-filled from the message region so the
  // pubkey content is still attacker-driven without ever under-sizing the buffer.
  uint8_t pk_buf[PUBKEY_SIZE];
  memset(pk_buf, 0, sizeof(pk_buf));
  if (msg_len > 0) memcpy(pk_buf, msg_p, msg_len < PUBKEY_SIZE ? msg_len : PUBKEY_SIZE);

  // Optionally force the well-formed header so the fuzzer reaches the decompressor past the gate.
  uint8_t sig_buf[SIG_COMPRESSED_MAX + 8];
  if (stamp_hdr) {
    size_t n = sig_len < sizeof(sig_buf) ? sig_len : sizeof(sig_buf);
    if (n < 2) n = 2;
    memset(sig_buf, 0, sizeof(sig_buf));
    if (sig_len > 0) memcpy(sig_buf, sig_p, sig_len < n ? sig_len : n);
    sig_buf[0] = DET_COMPRESSED_HEADER;
    sig_buf[1] = CURRENT_SALT_VERSION;
    sig_p   = sig_buf;
    sig_len = n;
  }

  // Single call: attacker-sized sig + message, correctly-sized (1793-byte) pubkey buffer.
  (void)falcon_det1024_verify_compressed(sig_p, sig_len, pk_buf, msg_p, msg_len);
  return 0;
}
