# Coverage-guided fuzzing — TRELYAN verifier / encoder

Reference / UNAUDITED. These harnesses go **beyond** the existing seeded fuzz
(`sdk/tests/test_signature_fuzz.py`, seed `1469`, 300 iters) by adding **coverage feedback**:
the fuzzer evolves an input corpus toward new code paths instead of replaying fixed mutations of a
single golden signature. They are a superset in breadth, not a replacement — keep both.

| Harness | Layer | Engine | Targets |
|---|---|---|---|
| `fuzz_encoding_atheris.py` | pure-python / ctypes | Atheris (libFuzzer for CPython) | `build_message()` construction/parsing, the `0xBA` header + salt-version + `<=1423` length envelope, and `FalconDet1024.verify()` |
| `fuzz_falcon_verify.cc` | C | libFuzzer + ASan/UBSan | the C `falcon_det1024_verify_compressed` decoder (memory safety) on mutated sig / pubkey / message bytes |

Both use the **real** API: `trelyan_pq.build_message`, `trelyan_pq.FalconDet1024.verify`, the
constants `DET_COMPRESSED_HEADER` (0xBA), `CURRENT_SALT_VERSION` (0), `SIG_COMPRESSED_MAXSIZE`
(1423), `MESSAGE_LEN` (102), `PUBKEY_LEN` (1793), and the C symbol `falcon_det1024_verify_compressed`.

---

## 1. Python encoder/verify fuzzer — `fuzz_encoding_atheris.py`

Drives three surfaces and asserts their contracts on every input:

- **`build_message(app_id, cell_id, artifact_hash, genesis_hash)`** — must return exactly a
  102-byte (`MESSAGE_LEN`) message starting with `DOMAIN_TAG`, or raise the documented `ValueError`
  for non-32-byte hashes / out-of-range ids. Any other exception, or a wrong-length message, is a
  finding.
- **The compressed-signature envelope** — header `0xBA`, salt-version `0x00`, total length
  `<= 1423`. Malformed envelopes (and total garbage) must be **rejected**, never accepted.
- **`FalconDet1024.verify(sig, pubkey, message)`** — for arbitrary attacker bytes it must return a
  `bool`, never raise, and **never return `True`** (the harness never feeds a genuine signature, so
  a `True` is a critical finding).

### Run

```bash
pip install atheris

# Pure-python legs (build_message + envelope) run with NO compiler / NO Falcon lib.
python sdk/tests/fuzz/fuzz_encoding_atheris.py -atheris_runs=2000000

# To also fuzz the verify leg, build the Falcon lib (pinned recipe) and point the env var at it:
export FALCON_DET1024_LIB=/abs/path/to/libfalcon_det1024.so   # .dylib macOS / .dll Windows

# Evolve and persist a corpus (recommended):
mkdir -p sdk/tests/fuzz/corpus_encoding
python sdk/tests/fuzz/fuzz_encoding_atheris.py sdk/tests/fuzz/corpus_encoding
```

If `FALCON_DET1024_LIB` is unset or the lib won't load, the verify leg is **skipped automatically**
and the harness still fuzzes the pure-python encoder surface (so it runs on a box with no compiler).

---

## 2. C verifier fuzzer — `fuzz_falcon_verify.cc`

Fuzzes the decoder that historically harbors out-of-bounds reads — the compressed-signature
bit-unpacking inside `falcon_det1024_verify_compressed` — under AddressSanitizer +
UndefinedBehaviorSanitizer. It is **memory-safety only**; accept/reject correctness is covered by
`test_signature_kat.py` and `test_signature_fuzz.py`.

Compile the **pinned** Falcon C sources *together with* the harness (not a prebuilt `.so`) so the
sanitizers instrument the verifier. Source: `algorand/falcon @
ce15e75bceb372867daf6b8e81918ab6978686eb`, fetched via the GitHub **tarball** (LF endings — a git
clone corrupts the digest via autocrlf).

### Build

```bash
FALCON_SRC=/path/to/algorand-falcon          # extracted tarball root

clang -g -O1 -std=c11 \
  -fsanitize=fuzzer,address,undefined \
  -fno-sanitize-recover=undefined \
  -DFALCON_UNALIGNED=0 -DFALCON_FPEMU=1 -DFALCON_FPNATIVE=0 \
  -fno-strict-aliasing \
  -I"$FALCON_SRC" \
  sdk/tests/fuzz/fuzz_falcon_verify.cc \
  "$FALCON_SRC"/codec.c "$FALCON_SRC"/common.c "$FALCON_SRC"/falcon.c \
  "$FALCON_SRC"/fft.c   "$FALCON_SRC"/fpr.c    "$FALCON_SRC"/keygen.c \
  "$FALCON_SRC"/rng.c   "$FALCON_SRC"/shake.c  "$FALCON_SRC"/sign.c \
  "$FALCON_SRC"/vrfy.c  "$FALCON_SRC"/deterministic.c \
  -o fuzz_falcon_verify
```

The `.c` list and the FP-backend flags (`FALCON_FPEMU=1 FALCON_FPNATIVE=0`,
`-DFALCON_UNALIGNED=0 -fno-strict-aliasing`) match the pinned build recipe in
`contracts/falcon_det1024.py`. If the link errors on a missing symbol, add the `.c` that defines it;
on a duplicate `main()`, you pulled in a falcon test file — drop it (this harness supplies its own
`LLVMFuzzerTestOneInput`).

### Run

```bash
mkdir -p sdk/tests/fuzz/corpus_verify
./fuzz_falcon_verify -max_len=4096 sdk/tests/fuzz/corpus_verify

# Reproduce a saved crash artifact:
./fuzz_falcon_verify crash-<sha1>
```

---

## Caveats

- `fuzz_encoding_atheris.py` needs **atheris** (`pip install atheris`). Atheris wheels target
  Linux/macOS; on Windows run it under WSL or a Linux container. The verify leg additionally needs
  the built Falcon lib via `FALCON_DET1024_LIB`.
- `fuzz_falcon_verify.cc` needs **clang** with libFuzzer + the ASan/UBSan runtimes and the pinned
  Falcon C sources on disk. It is a self-contained harness; the normal (python) SDK test run does
  not compile it.
- These complement, and do not replace, the **seeded** corpus in `sdk/tests/test_signature_fuzz.py`
  and the byte-identity KAT in `sdk/tests/test_signature_kat.py`. Seed any corpus directory with a
  known-good signature/message pair to give the coverage-guided fuzzers a fast start.
- The C harness asserts memory safety only (no forgery-resistance / never-accept assertion); the
  python harness asserts never-accept on attacker bytes because it controls all inputs.
