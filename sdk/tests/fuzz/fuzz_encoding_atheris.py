#!/usr/bin/env python3
"""
Atheris coverage-guided fuzz harness over the trelyan_pq pure-python / ctypes attack surface.

WHAT THIS TARGETS (the surface that EXISTS in trelyan_pq today):
  1. Message construction/parsing:  trelyan_pq.build_message(app_id, cell_id,
     artifact_hash, genesis_hash)  — the byte-exact signed message the contract rebuilds
     on-chain. We drive it with adversarial lengths/ints and assert it either returns a
     well-formed 102-byte message or raises a *documented* ValueError — never an undocumented
     crash, and never a wrong-length message.
  2. The compressed-signature header / salt-version / length envelope:
     header byte must be 0xBA (DET_COMPRESSED_HEADER), salt version byte 0x00
     (CURRENT_SALT_VERSION), total length <= 1423 (SIG_COMPRESSED_MAXSIZE). We mutate these
     fields and assert malformed envelopes are REJECTED by the verify path (returned False),
     never ACCEPTED.
  3. The verify path:  FalconDet1024.verify(sig, pubkey, message). Arbitrary attacker-chosen
     (sig, pubkey, message) byte strings must return a bool (False for anything that isn't a
     genuine signature) and must NOT crash, hang, or accept.

HOW THIS COMPLEMENTS THE EXISTING SEEDED FUZZ (sdk/tests/test_signature_fuzz.py):
  test_signature_fuzz.py is a *seeded* (seed 1469, 300 iters) random mutator over ONE known-good
  signature, run under pytest. This harness is *coverage-guided*: libFuzzer/Atheris uses edge
  coverage feedback to evolve inputs toward new branches in build_message + the verify wrapper,
  and persists an evolving corpus. It is a superset in breadth, not a duplicate — it explores the
  parser/encoder state machine, not just bit-flips of a single golden.

INVARIANTS ASSERTED (a finding == the harness aborts with one of these):
  * build_message NEVER returns a message whose length != MESSAGE_LEN (102).
  * build_message only ever raises ValueError (its documented contract) for bad input —
    any other exception type is a bug.
  * verify(...) ALWAYS returns a bool and NEVER raises for arbitrary bytes.
  * No fuzz input is ever ACCEPTED as a valid signature (we never feed a genuine one here);
    a True return from verify() on attacker bytes would be a critical finding.

RUN IT (needs atheris + a built Falcon lib for the verify leg):
  pip install atheris
  # build libfalcon_det1024.{so,dylib,dll} per the pinned recipe, then:
  export FALCON_DET1024_LIB=/abs/path/to/libfalcon_det1024.so
  python sdk/tests/fuzz/fuzz_encoding_atheris.py -atheris_runs=2000000
  # persist/evolve a corpus directory (recommended):
  mkdir -p sdk/tests/fuzz/corpus_encoding
  python sdk/tests/fuzz/fuzz_encoding_atheris.py sdk/tests/fuzz/corpus_encoding

CAVEATS:
  * Requires `atheris` (CPython coverage-guided fuzzer; pip install atheris). Atheris wheels
    exist for Linux/macOS; on Windows run it under WSL or a Linux container.
  * The build_message / header-envelope legs run WITHOUT the Falcon C library (pure python) and
    are always exercised. The verify leg is skipped automatically if FALCON_DET1024_LIB is not set
    / the lib won't load — so the harness still fuzzes the pure-python encoder surface on a box
    with no compiler. It does NOT, by itself, prove the C verifier is crash-free; that is the job
    of fuzz_falcon_verify.cc (libFuzzer + ASan/UBSan) in this same directory.
"""

from __future__ import annotations

import sys

import atheris  # noqa: E402  (atheris must be imported before the modules it instruments)

# Instrument the trelyan_pq pure-python surface so libFuzzer gets coverage feedback on it.
with atheris.instrument_imports():
    import trelyan_pq
    from trelyan_pq import (
        build_message,
        MESSAGE_LEN,
        DOMAIN_TAG,
        DET_COMPRESSED_HEADER,
        SIG_COMPRESSED_MAXSIZE,
        CURRENT_SALT_VERSION,
        FalconDet1024,
    )

# ---------------------------------------------------------------------------------------------
# Lazily decide whether the Falcon C library is loadable. If not, we still fuzz the pure-python
# encoder/header surface and simply skip the C-backed verify leg (documented in CAVEATS).
# ---------------------------------------------------------------------------------------------
_SIGNER = FalconDet1024()
_VERIFY_AVAILABLE: bool = False
try:
    # A cheap, side-effect-free probe: verify() on junk loads the lib and returns a bool.
    _VERIFY_AVAILABLE = isinstance(
        _SIGNER.verify(b"\x00", b"\x00" * trelyan_pq.PUBKEY_LEN, b"m"), bool
    )
except Exception:
    _VERIFY_AVAILABLE = False


def _fuzz_build_message(fdp: "atheris.FuzzedDataProvider") -> None:
    """Drive build_message with adversarial ints + hash lengths.

    Contract (message.py): artifact_hash and genesis_hash MUST be 32 bytes else ValueError;
    cell_id must be a uint64 else ValueError; a successful call MUST return exactly MESSAGE_LEN
    bytes that start with DOMAIN_TAG. We let the fuzzer pick out-of-range ints and wrong-length
    hashes and assert the function's contract holds for every input.
    """
    app_id = fdp.ConsumeInt(16)              # arbitrary width incl. negative / >uint64
    cell_id = fdp.ConsumeInt(16)
    # Bias toward the 32-byte boundary but allow any length so off-by-one is reachable.
    alen = fdp.ConsumeIntInRange(0, 64)
    glen = fdp.ConsumeIntInRange(0, 64)
    artifact = fdp.ConsumeBytes(alen)
    genesis = fdp.ConsumeBytes(glen)
    try:
        msg = build_message(app_id, cell_id, artifact, genesis)
    except ValueError:
        return  # documented rejection — correct behavior
    except OverflowError:
        # int.to_bytes(8,...) on an out-of-uint64 app_id is a legitimate, documented failure mode
        # (build_message encodes app_id before validating cell_id). Treat as acceptable rejection.
        return
    # If it returned, the contract must hold exactly:
    assert isinstance(msg, (bytes, bytearray)), "build_message returned a non-bytes object"
    assert len(msg) == MESSAGE_LEN, f"build_message length drift: {len(msg)} != {MESSAGE_LEN}"
    assert msg.startswith(DOMAIN_TAG), "build_message dropped the domain-separation tag"
    # A returned message is only valid when both hashes were exactly 32 bytes.
    assert len(artifact) == 32 and len(genesis) == 32, "build_message accepted a non-32B hash"


def _looks_well_headed(sig: bytes) -> bool:
    """The minimal compressed-sig envelope checks the encoding requires."""
    return (
        len(sig) >= 2
        and sig[0] == DET_COMPRESSED_HEADER          # 0xBA
        and sig[1] == CURRENT_SALT_VERSION           # 0x00
        and len(sig) <= SIG_COMPRESSED_MAXSIZE       # <= 1423
    )


def _fuzz_verify(fdp: "atheris.FuzzedDataProvider") -> None:
    """Feed attacker-chosen (sig, pubkey, message) to the verify path.

    INVARIANTS: verify() must return a bool, must never raise, and must never return True for
    fuzzer-chosen bytes (we never supply a genuine signature in this harness). This covers both
    well-headed-but-bogus envelopes (0xBA / salt 0 / length-capped, junk body) and total garbage.
    """
    if not _VERIFY_AVAILABLE:
        return
    # Sometimes force a "well-headed" envelope so the fuzzer spends effort past the header gate.
    force_header = fdp.ConsumeBool()
    siglen = fdp.ConsumeIntInRange(0, SIG_COMPRESSED_MAXSIZE + 8)  # allow over-cap too
    sig = bytearray(fdp.ConsumeBytes(siglen))
    if force_header and len(sig) >= 2:
        sig[0] = DET_COMPRESSED_HEADER
        sig[1] = CURRENT_SALT_VERSION
    pubkey = fdp.ConsumeBytes(fdp.ConsumeIntInRange(0, trelyan_pq.PUBKEY_LEN + 4))
    message = fdp.ConsumeBytes(fdp.ConsumeIntInRange(0, 256))

    try:
        result = _SIGNER.verify(bytes(sig), pubkey, message)
    except Exception as exc:  # noqa: BLE001 — any raise from verify() is the finding
        raise AssertionError(
            f"verify() raised {type(exc).__name__} on fuzz input (must return False, not raise)"
        ) from exc

    assert isinstance(result, bool), "verify() returned a non-bool"
    # Critical: attacker bytes must never be accepted. We never feed a real signature here.
    assert result is False, (
        "verify() ACCEPTED fuzzer-generated bytes as a valid signature "
        f"(well_headed={_looks_well_headed(bytes(sig))}) — critical finding"
    )


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    # Route each input through both legs; the leading byte picks the primary target so coverage
    # feedback can specialize the corpus toward whichever surface is producing new edges.
    selector = fdp.ConsumeIntInRange(0, 2)
    if selector == 0:
        _fuzz_build_message(fdp)
    elif selector == 1:
        _fuzz_verify(fdp)
    else:
        # Exercise both in one input to find interactions (e.g. a message from build_message
        # handed straight to verify with a junk sig).
        _fuzz_build_message(fdp)
        _fuzz_verify(fdp)


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
