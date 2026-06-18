#!/usr/bin/env sh
# verify_all.sh — TRELYAN: run all verification axes from a clean checkout, in order, and print
# ONE PASS/FAIL summary (non-zero exit on ANY failure).
#
#   Axis A  build the pinned deterministic Falcon-1024 lib   (pinned source + pinned flags)
#   Axis B  pinned-source digest + emulated-FP-backend gate   (ci/verify_pinned_digest.py)
#   Axis C  byte-identity KAT vs the committed golden         (tests/test_signature_kat.py)
#   Axis D  read-only on-chain verify of the deployed app     (examples/verify_trelyan.py) [needs network]
#
# Mirrors the sdk/ci/ci.yml `signature-kat` job recipe EXACTLY: tarball fetch of commit
# ce15e75b... (NOT git clone — autocrlf would corrupt the digest), the digest+FP gate, the
# build flags `-O3 -fPIC -DFALCON_UNALIGNED=0 -fno-strict-aliasing -shared` over the exact
# 11-file source list, and TRELYAN_REQUIRE_KAT=1 so the KAT fails (not skips) if unpopulated.
#
# Compiler: prefers `python -m ziglang cc` (the pinned, portable cc from the PINNED BUILD RECIPE);
# falls back to the system `cc` if ziglang is not installed (ci.yml uses the runner's cc). The
# emulated FP backend (FALCON_FPEMU=1 / FALCON_FPNATIVE=0) is pinned by config.h and asserted by
# Axis B — NOT by any flag here. Do NOT add -ffast-math or -DFALCON_FPNATIVE: either breaks byte-identity.
#
# Usage (from the repo root, after a clean checkout):
#   sh scripts/verify_all.sh                 # all four axes (A-D); D needs read-only network
#   SKIP_ONCHAIN=1 sh scripts/verify_all.sh  # offline only (A-C) — air-gapped reviewers
#   FALCON_COMMIT=... sh scripts/verify_all.sh   # override the pinned commit (not recommended)
#
# UNAUDITED reference build on Algorand TestNet. Not mainnet/production. Falcon = signatures.
set -u

# --- locate the repo root (this script lives in <root>/scripts/) --------------------------------
SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
cd "$ROOT" || { echo "FATAL: cannot cd to repo root"; exit 2; }

FALCON_COMMIT="${FALCON_COMMIT:-ce15e75bceb372867daf6b8e81918ab6978686eb}"
SRC_DIR="$ROOT/falcon-src"
LIB_NAME="libfalcondet1024.so"
case "$(uname -s 2>/dev/null || echo unknown)" in
  Darwin*) LIB_NAME="libfalcondet1024.dylib" ;;
esac
LIB_PATH="$ROOT/$LIB_NAME"   # build artifact OUTSIDE falcon-src, so Axis B's tree digest stays pristine (27 files)

# The exact 11-file source list from ci.yml (order-insensitive but kept identical).
FALCON_SRCS="codec.c common.c falcon.c fft.c fpr.c keygen.c rng.c shake.c sign.c vrfy.c deterministic.c"

# --- result accounting --------------------------------------------------------------------------
PASS_N=0
FAIL_N=0
RESULTS=""
record() { # record <PASS|FAIL> <axis label>
  if [ "$1" = "PASS" ]; then PASS_N=$((PASS_N+1)); else FAIL_N=$((FAIL_N+1)); fi
  RESULTS="${RESULTS}  [$1] $2\n"
  printf '  [%s] %s\n' "$1" "$2"
}
hr() { printf '%s\n' "------------------------------------------------------------"; }

echo "TRELYAN verify_all — hermetic reproduction (repo root: $ROOT)"
echo "pinned Falcon commit: $FALCON_COMMIT"
hr

# --- pick the compiler: pinned ziglang cc preferred, system cc fallback -------------------------
if python -m ziglang version >/dev/null 2>&1; then
  CC="python -m ziglang cc"
  CC_DESC="python -m ziglang cc ($(python -m ziglang version 2>/dev/null))"
elif command -v cc >/dev/null 2>&1; then
  CC="cc"
  CC_DESC="system cc ($(cc --version 2>/dev/null | head -1))"
else
  echo "FATAL: no compiler — install ziglang ('pip install ziglang') or a system cc"; exit 2
fi
echo "compiler: $CC_DESC"
echo "python  : $(python --version 2>&1)"
hr

# ================================================================================================
# Axis A — fetch the PINNED source (tarball, not clone) and BUILD the deterministic Falcon lib
# ================================================================================================
echo "== Axis A: build pinned deterministic Falcon-1024 library =="
A_OK=1
if [ ! -f "$SRC_DIR/deterministic.c" ]; then
  # Fetch via the GitHub source TARBALL: a clone applies core.autocrlf which can rewrite the C
  # sources LF->CRLF and change deterministic.c's digest (e005ebda vs the pinned 601390dc),
  # failing Axis B for a non-substantive reason. The tarball is LF on every OS.
  echo "fetching tarball for $FALCON_COMMIT ..."
  if curl -sL "https://github.com/algorand/falcon/archive/${FALCON_COMMIT}.tar.gz" | tar xz; then
    rm -rf "$SRC_DIR"
    mv "falcon-${FALCON_COMMIT}" "$SRC_DIR" || A_OK=0
  else
    echo "  ERROR: could not fetch the pinned Falcon tarball (network required for first run)"
    A_OK=0
  fi
else
  echo "reusing existing $SRC_DIR (already fetched)"
fi

if [ "$A_OK" = "1" ]; then
  # EXACT ci.yml flags + source list. emulated FP backend comes from config.h (asserted in Axis B).
  ( cd "$SRC_DIR" \
      && $CC -O3 -fPIC -DFALCON_UNALIGNED=0 -fno-strict-aliasing -shared -o "$LIB_PATH" $FALCON_SRCS )
  if [ $? -eq 0 ] && [ -f "$LIB_PATH" ]; then
    export FALCON_DET1024_LIB="$LIB_PATH"
    record PASS "Axis A — built $LIB_NAME (FALCON_DET1024_LIB set)"
  else
    record FAIL "Axis A — compile of $LIB_NAME failed"
  fi
else
  record FAIL "Axis A — pinned source fetch failed"
fi
hr

# ================================================================================================
# Axis B — pinned-source digest + emulated-FP-backend gate
# ================================================================================================
echo "== Axis B: pinned-source digest + FP-backend gate =="
if [ -f "$SRC_DIR/deterministic.c" ]; then
  if python sdk/ci/verify_pinned_digest.py "$SRC_DIR"; then
    record PASS "Axis B — tree/deterministic.c digest + FALCON_FPEMU=1/FPNATIVE=0 match the pin"
  else
    record FAIL "Axis B — pinned-source digest or FP backend drifted from the pin"
  fi
else
  record FAIL "Axis B — no source tree to digest (Axis A did not fetch)"
fi
hr

# ================================================================================================
# Axis C — byte-identity KAT vs the committed golden (lib-gated; REQUIRE so it can't silently skip)
# ================================================================================================
echo "== Axis C: byte-identity KAT (re-sign goldens == committed golden, byte-for-byte) =="
# Install the in-tree SDK with the dev extra if pytest/the package aren't importable yet.
if ! python -c "import trelyan_pq, pytest" >/dev/null 2>&1; then
  echo "installing in-tree SDK (sdk[dev]) ..."
  python -m pip install --quiet -e "sdk[dev]" || echo "  WARN: SDK install reported an error"
fi
# TRELYAN_REQUIRE_KAT=1 makes the KAT FAIL (not skip) if the fixture is still the sentinel.
if TRELYAN_REQUIRE_KAT=1 FALCON_DET1024_LIB="${FALCON_DET1024_LIB:-$LIB_PATH}" \
     python -m pytest sdk/tests/test_signature_kat.py -v; then
  record PASS "Axis C — committed goldens re-sign byte-identically (build-divergence control)"
else
  record FAIL "Axis C — byte-identity KAT failed (build divergence or unpopulated fixture)"
fi
hr

# ================================================================================================
# Axis D — read-only on-chain verification of the deployed app (needs network)
# ================================================================================================
echo "== Axis D: read-only on-chain verify of deployed TestNet app 763809096 =="
if [ "${SKIP_ONCHAIN:-0}" = "1" ]; then
  echo "  SKIP_ONCHAIN=1 set — skipping the on-chain axis (offline run)."
  RESULTS="${RESULTS}  [SKIP] Axis D — on-chain check skipped (SKIP_ONCHAIN=1)\n"
  printf '  [SKIP] %s\n' "Axis D — on-chain check skipped (SKIP_ONCHAIN=1)"
else
  if python sdk/examples/verify_trelyan.py; then
    record PASS "Axis D — deployed app bytecode + on-chain boxes verify (read-only)"
  else
    record FAIL "Axis D — on-chain verification failed (or no network)"
  fi
fi
hr

# --- single summary -----------------------------------------------------------------------------
echo "== SUMMARY =="
printf '%b' "$RESULTS"
hr
if [ "$FAIL_N" -eq 0 ]; then
  echo "RESULT: PASS — $PASS_N axis(es) passed, 0 failed"
  exit 0
else
  echo "RESULT: FAIL — $PASS_N passed, $FAIL_N failed"
  exit 1
fi
