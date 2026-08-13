"""
Both Falcon loaders must fail closed, and they must not drift apart again.

WHY THIS TEST EXISTS
────────────────────────────────────────────────────────────────────────────────────────────────
There are two ctypes loaders for the same signing core:

    sdk/src/trelyan_pq/falcon.py     used by the SDK and everything that imports trelyan_pq
    contracts/falcon_det1024.py      used by deploy_testnet.py and test_inscription.py

Commit eb67e4a (2026-08-10, "close two local library/module load-path hijack vectors",
pre-audit findings TF-01/TF-02) removed the cwd-relative default from the FIRST one and
touched only `sdk/`. The second kept `os.environ.get("FALCON_DET1024_LIB",
"./libfalcondet1024.so")` and was untouched since the initial commit a806f63.

A dlopen path containing a slash resolves against the process working directory, so the
unfixed copy would load keygen, sign and verify out of whatever `./libfalcondet1024.so`
happened to be sitting in cwd (CWE-426). The copy left unfixed was the one on the documented
TestNet deployment path — README.md tells the operator to run `python
contracts/deploy_testnet.py` from the repo root — and `.gitignore` excludes `*.so`/`*.dylib`/
`*.dll`, so a planted library never shows up in `git status`.

The security fix was therefore applied everywhere except the path that signs real inscriptions.

WHAT THIS TEST DOES
────────────────────────────────────────────────────────────────────────────────────────────────
It plants a decoy `libfalcondet1024.*` in a temp directory, runs each loader from there in a
subprocess with FALCON_DET1024_LIB unset, and requires the loader to refuse BEFORE touching it.
Asserting the source constant is `""` would only prove a literal changed; this proves the
behaviour. A loader that regressed would report a dlopen/ELF error about the decoy instead.

It lives in sdk/tests/ deliberately: that is the directory CI actually runs (`pytest tests`),
and contracts/ has no test job of its own. A parity test parked where nothing executes it is
the very defect it is meant to prevent.
"""

import os
import pathlib
import subprocess
import sys

import pytest

_REPO = pathlib.Path(__file__).resolve().parents[2]
_SDK_SRC = _REPO / "sdk" / "src"
_CONTRACTS = _REPO / "contracts"

# (id, sys.path entry, import statement, call that triggers the load)
_LOADERS = [
    pytest.param(
        str(_SDK_SRC),
        "from trelyan_pq import falcon as m",
        # keygen(), not default_signer(): the loader is lazy (FalconDet1024._lib_ref), so merely
        # constructing the signer loads nothing and would pass this test vacuously.
        "m.keygen()",
        id="sdk/src/trelyan_pq/falcon.py",
    ),
    pytest.param(
        str(_CONTRACTS),
        "import falcon_det1024 as m",
        "m._load()",
        id="contracts/falcon_det1024.py",
    ),
]

_DECOY_NAMES = ("libfalcondet1024.so", "libfalcondet1024.dylib", "falcondet1024.dll")


@pytest.mark.parametrize(("path_entry", "import_stmt", "call"), _LOADERS)
def test_loader_refuses_cwd_without_explicit_path(tmp_path, path_entry, import_stmt, call):
    # A decoy under every platform's name, so the test is meaningful on Linux, macOS and Windows.
    # Deliberately not a valid shared object: if a loader regresses and tries to dlopen it, the
    # resulting error names the decoy, which is exactly what we assert must NOT happen.
    for name in _DECOY_NAMES:
        (tmp_path / name).write_bytes(b"decoy - must never be opened\n")

    env = {k: v for k, v in os.environ.items() if k != "FALCON_DET1024_LIB"}
    env["PYTHONPATH"] = path_entry

    proc = subprocess.run(
        [sys.executable, "-c", f"{import_stmt}\n{call}\n"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert proc.returncode != 0, (
        "the loader succeeded with FALCON_DET1024_LIB unset, in a directory containing a decoy "
        "library - it loaded the signing core from the working directory (CWE-426)"
    )

    err = proc.stderr
    assert "FALCON_DET1024_LIB is not set" in err, (
        "expected a fail-closed refusal naming the missing variable; got:\n" + err[-1500:]
    )
    for name in _DECOY_NAMES:
        assert name not in err, (
            f"the loader reached the decoy {name!r} before refusing, so cwd is still on the "
            "search path:\n" + err[-1500:]
        )


def test_both_loaders_declare_no_cwd_default():
    """Guard the constant as well as the behaviour.

    The subprocess test above proves today's behaviour; this catches a re-introduced relative
    default directly, in the form it took last time, so the diff is obvious in review.
    """
    offenders = []
    for src in (_SDK_SRC / "trelyan_pq" / "falcon.py", _CONTRACTS / "falcon_det1024.py"):
        for lineno, line in enumerate(src.read_text(encoding="utf-8").splitlines(), start=1):
            if "FALCON_DET1024_LIB" not in line or not line.lstrip().startswith(("_LIB_PATH", "_DEFAULT_LIB_PATH")):
                continue
            # The default is the second argument of os.environ.get(...). Anything that is not an
            # empty string re-opens the hijack.
            if '""' not in line and "''" not in line:
                offenders.append(f"{src.relative_to(_REPO)}:{lineno}: {line.strip()}")

    assert not offenders, (
        "a non-empty default for FALCON_DET1024_LIB reintroduces the cwd load path (CWE-426):\n"
        + "\n".join(f"  {o}" for o in offenders)
    )
