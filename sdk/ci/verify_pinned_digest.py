"""
verify_pinned_digest.py — assert a Falcon source tree matches the pinned build (T2 precondition).

Used by the signature-kat CI job BEFORE building the shared library: if upstream drifted from the
pinned commit, the deterministic.c digest changes and we fail fast (so a divergent signer can never
silently produce the KAT goldens). Also runnable locally.

    python sdk/ci/verify_pinned_digest.py /path/to/falcon-source-tree

Exits 0 on match, non-zero (with a diff) on mismatch. Stdlib only.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys

PINNED_COMMIT = "ce15e75bceb372867daf6b8e81918ab6978686eb"
EXPECTED_TREE = "c6adf4871389dfdbf3ffbd853bd9e5ce15646b821d6dc84e327ab1b3d2adc980"
EXPECTED_DET_C = "601390dc53521fc1b00eb962ea63d64c2d65bfe774450cf4ec59a3478e0a54a4"
EXPECTED_FILE_COUNT = 27


def _h(path: str) -> str:
    d = hashlib.new("sha512_256")
    with open(path, "rb") as f:
        d.update(f.read())
    return d.hexdigest()


def tree_digest(root: str) -> tuple[str, int]:
    files = sorted(
        os.path.join(r, f)
        for r, _dirs, fs in os.walk(root)
        for f in fs
        if ".git" not in r.split(os.sep)
    )
    t = hashlib.new("sha512_256")
    for f in files:
        rel = os.path.relpath(f, root).replace(os.sep, "/")
        t.update((rel + ":" + _h(f) + "\n").encode())
    return t.hexdigest(), len(files)


def check_fp_backend(root: str) -> bool:
    """Determinism precondition: the pinned config.h MUST pin the EMULATED fixed-point FP backend
    (FALCON_FPEMU=1, FALCON_FPNATIVE=0). Native FP / aggressive optimization can make signing
    non-deterministic across platforms — and per config.h's own CRITICAL SECURITY WARNING, two
    different signatures for one message under one key is a catastrophic FORGERY risk. This is what
    makes the cross-platform byte-identity KAT meaningful. (The tree digest already covers config.h;
    this is the legible, targeted check an auditor can read.)"""
    cfg = os.path.join(root, "config.h")
    if not os.path.isfile(cfg):
        print("FAIL: config.h not found (cannot verify FP backend)")
        return False
    with open(cfg, "r", encoding="utf-8", errors="replace") as f:
        txt = f.read()
    emu1 = re.search(r"^\s*#define\s+FALCON_FPEMU\s+1\b", txt, re.M)
    nat0 = re.search(r"^\s*#define\s+FALCON_FPNATIVE\s+0\b", txt, re.M)
    nat1 = re.search(r"^\s*#define\s+FALCON_FPNATIVE\s+1\b", txt, re.M)
    ok = bool(emu1) and bool(nat0) and not nat1
    print(f"config.h FALCON_FPEMU=1    : {'OK' if emu1 else 'MISSING'}")
    print(f"config.h FALCON_FPNATIVE=0 : {'OK' if (nat0 and not nat1) else 'MISMATCH'}")
    if not ok:
        print("FAIL: pinned config.h does not pin the emulated FP backend (determinism precondition)")
    return ok


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    root = argv[1]
    det_c = os.path.join(root, "deterministic.c")
    if not os.path.isfile(det_c):
        print(f"FAIL: deterministic.c not found under {root!r}")
        return 1

    tree, count = tree_digest(root)
    det = _h(det_c)
    ok = True
    print(f"pinned commit     : {PINNED_COMMIT}")
    print(f"file count        : {count} (expected {EXPECTED_FILE_COUNT})")
    print(f"deterministic.c   : {det}")
    print(f"        expected   : {EXPECTED_DET_C}  {'OK' if det == EXPECTED_DET_C else 'MISMATCH'}")
    print(f"tree digest       : {tree}")
    print(f"        expected   : {EXPECTED_TREE}  {'OK' if tree == EXPECTED_TREE else 'MISMATCH'}")
    if det != EXPECTED_DET_C:
        ok = False
        print("FAIL: deterministic.c digest drifted from the pinned build")
    if tree != EXPECTED_TREE:
        ok = False
        print("FAIL: source tree digest drifted from the pinned build")
    if count != EXPECTED_FILE_COUNT:
        print(f"WARN: file count {count} != {EXPECTED_FILE_COUNT} (archive layout may differ)")
    if not check_fp_backend(root):
        ok = False
    print("PINNED BUILD VERIFIED" if ok else "PINNED BUILD VERIFICATION FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
