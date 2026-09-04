"""Every line these scripts can print must survive a default Windows console (cp1252).

This is not a cosmetic style rule. `contracts/verify_deployment.py` printed a U+2194 inside the
DRIFT branch. On a cp1252 console that raises UnicodeEncodeError *after* the comparison has
already run and correctly found the mismatch — so the process died in its own failure report and
exited **2 ("could not complete the check")** instead of **1 ("DRIFT")**.

That is the worst possible place for a crash. A real finding was downgraded to an inconclusive
one, by a decoration, and only on the platform where the maintainer actually works.

It stayed invisible because it needs TWO conditions at once, and CI supplies only one of them.
The drift branch did run -- it ran on every push while the live app diverged -- but it ran on
Linux CI, where the stream is UTF-8 and U+2194 encodes fine. A green run cannot reach the line
at all. So the uncovered case was never "the failure path"; it was "the failure path on a
cp1252 stream", which is precisely the maintainer's console and nobody else's.

The exit codes are a contract (see verify_deployment.py's docstring): 0 match, 1 drift, 2 could
not check. A reviewer who sees 2 concludes "the tooling failed", not "the deployment diverged".

Scope: characters that cp1252 cannot encode, on lines that print. Em dash (U+2014) and ellipsis
(U+2026) are deliberately allowed — they ARE in cp1252 and are used throughout these reports.
"""

from __future__ import annotations

import io
import unicodedata
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# Scripts a reviewer is told to run directly, whose output must survive any console. These are the
# ones whose exit code is read as a verdict.
REPORTING_SCRIPTS = [
    "contracts/verify_deployment.py",
    "sdk/examples/verify_trelyan.py",
]


def _unencodable(text: str) -> list[tuple[int, str, str]]:
    """(line number, char, unicode name) for printable lines cp1252 would reject."""
    out: list[tuple[int, str, str]] = []
    for lineno, line in enumerate(text.split("\n"), 1):
        if "print(" not in line:
            continue
        for ch in line:
            if ord(ch) < 128:
                continue
            try:
                ch.encode("cp1252")
            except UnicodeEncodeError:
                out.append((lineno, ch, unicodedata.name(ch, "?")))
                break
    return out


@pytest.mark.parametrize("rel", REPORTING_SCRIPTS)
def test_no_print_line_would_crash_a_cp1252_console(rel: str) -> None:
    path = REPO / rel
    assert path.is_file(), f"{rel} no longer exists; update REPORTING_SCRIPTS"
    offenders = _unencodable(io.open(path, encoding="utf-8").read())
    assert not offenders, (
        f"{rel} prints characters a default Windows console cannot encode:\n"
        + "\n".join(f"  line {n}: U+{ord(c):04X} {name}" for n, c, name in offenders)
        + "\n\nOn cp1252 this raises UnicodeEncodeError mid-report. If the line sits in a failure "
        "branch, the script dies after finding the problem and exits 2 (could not check) instead "
        "of 1 (drift) — a real finding reported as tooling trouble. Use ASCII in printed text."
    )


def test_the_scan_can_actually_fail() -> None:
    """A guard that cannot fail is not a guard.

    The bug this file exists for was invisible precisely because it lived on a branch that only
    runs when something is wrong. So prove the detector fires, rather than trusting that a green
    parametrised run above means anything.
    """
    assert _unencodable('print("Local source↔TEAL gates")'), (
        "the detector did not flag U+2194 in a print line — it would not have caught the original "
        "bug either"
    )
    assert not _unencodable('print("Local source-to-TEAL gates")'), "false positive on plain ASCII"
    assert not _unencodable('print("committed — deployed …")'), (
        "em dash and ellipsis are valid cp1252 and are used throughout these reports; flagging "
        "them would make this guard unusable and it would be deleted"
    )
