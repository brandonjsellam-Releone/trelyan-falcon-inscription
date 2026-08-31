#!/usr/bin/env python3
"""Prompt for the deployer mnemonic without it touching a terminal, a file, or a shell history.

WHY THIS EXISTS
---------------
`contracts/deploy_testnet.py` reads `DEPLOYER_MNEMONIC` from the environment. Every obvious way
of getting it there leaks it somewhere durable:

  * `set` / `export DEPLOYER_MNEMONIC=...`  -> shell history, and the process list on some systems
  * `setx DEPLOYER_MNEMONIC ...`           -> HKCU\\Environment, i.e. the Windows registry, for
                                              every process this user ever starts, forever
  * a `.env` file                          -> on disk, surviving until someone deletes it, and one
                                              `git add -f` away from a public repository

This asks for it with `getpass`, which does not echo and does not go through readline history,
puts it in THIS process's environment only, and hands that environment to the deploy script as a
child. When the process exits the mnemonic is gone. Nothing writes it down.

It is deliberately thin. It prompts, it sanity-checks the shape, it execs the real script. Any
logic beyond that belongs in `contracts/deploy_testnet.py`, which is the audited path.

USAGE
-----
    python scripts/deploy_testnet_secure.py

Set FALCON_DET1024_LIB first, or let this script find `build/falcon/falcondet1024.dll` (or `.so`)
if you built it with the command in this file's BUILD note.

BUILD note - the shared library this needs, built exactly as CI builds it:

    mkdir -p build/falcon && cp third_party/falcon-det1024/src/*.c \\
        third_party/falcon-det1024/src/*.h build/falcon/ && cd build/falcon
    cc -O3 -fPIC -DFALCON_UNALIGNED=0 -fno-strict-aliasing -shared \\
        -o falcondet1024.dll codec.c common.c falcon.c fft.c fpr.c keygen.c \\
        rng.c shake.c sign.c vrfy.c deterministic.c

Never add -ffast-math, -DFALCON_FPNATIVE=1, -DFALCON_AVX2=1 or -DFALCON_FMA=1: see
third_party/falcon-det1024/PROVENANCE.md. Verify the result before trusting it:

    FALCON_DET1024_LIB=$PWD/build/falcon/falcondet1024.dll TRELYAN_REQUIRE_KAT=1 \\
        python -m pytest sdk/tests/test_signature_kat.py

TRELYAN_REQUIRE_KAT=1 is not optional. Without it the byte-identity tests SKIP and the run still
reports green, which is how a wrong library gets trusted.
"""

from __future__ import annotations

import getpass
import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent
DEPLOY = REPO / "contracts" / "deploy_testnet.py"
WORDS = 25


def find_falcon_lib() -> str | None:
    """An already-set FALCON_DET1024_LIB wins; otherwise look where the BUILD note puts it."""
    already = os.environ.get("FALCON_DET1024_LIB")
    if already:
        return already
    for name in ("falcondet1024.dll", "libfalcondet1024.so", "libfalcondet1024.dylib"):
        candidate = REPO / "build" / "falcon" / name
        if candidate.is_file():
            return str(candidate)
    return None


def main() -> int:
    if not DEPLOY.is_file():
        print(f"not found: {DEPLOY}", file=sys.stderr)
        return 2

    lib = find_falcon_lib()
    if not lib:
        print(
            "FALCON_DET1024_LIB is not set and no library was found under build/falcon/.\n"
            "Build it with the command in this file's BUILD note, then run the KAT before using\n"
            "it. Refusing to prompt for a mnemonic for a run that would fail at keygen anyway.",
            file=sys.stderr,
        )
        return 2

    print(f"falcon library: {lib}")
    print("mnemonic input is hidden and is never written to disk, history, or the registry.")

    mnemonic = getpass.getpass("25-word TestNet deployer mnemonic: ").strip()
    count = len(mnemonic.split())
    if count != WORDS:
        # The count is all that is checked here. Validating the checksum would mean parsing the
        # seed in this script, and the fewer places that touch it the better - the SDK does it
        # properly a moment later, and its error is the authoritative one.
        print(
            f"that is {count} words, not {WORDS}. Nothing was run and nothing was stored.",
            file=sys.stderr,
        )
        return 2

    env = dict(os.environ)
    env["DEPLOYER_MNEMONIC"] = mnemonic
    env["FALCON_DET1024_LIB"] = lib
    del mnemonic

    print(f"running {DEPLOY.relative_to(REPO)} ...\n")
    return subprocess.call([sys.executable, str(DEPLOY)], cwd=str(REPO), env=env)


if __name__ == "__main__":
    raise SystemExit(main())
