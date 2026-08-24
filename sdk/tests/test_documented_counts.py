"""
Guard: a test count written into the documentation must match the suite it describes.

WHY THIS TEST EXISTS
--------------------------------------------------------------------------------------------------
The 2026-08-24 audit found the contract suite described as "22 tests" in seven documents while the
file defined 25, README calling the same suite "the 20-test suite" two paragraphs below its own
"22 tests", and the Rust CI anti-vacuity floor set to 8 on a comment claiming the workspace had 11
tests when it had 48 -- a floor so far below the real count that 40 tests could have vanished
without turning the job red.

Hand-maintained counts rot silently. Every one of those numbers was correct when written. The
failure mode is not carelessness, it is that nothing re-checks them, so the documentation drifts
away from the code at exactly the speed the code changes.

This test re-checks them. It parses the suite and compares against the number the docs claim.

WHY THIS IS NOT A CHECK THAT CANNOT FAIL
--------------------------------------------------------------------------------------------------
The two sides are independently derived: one is COUNTED from the test file's AST, the other is
READ from the prose. Neither is computed from the other. If they disagree the test fails and names
both, and the fix is to correct whichever is actually wrong -- usually the prose.

`test_the_counter_actually_counts` proves the counting logic itself works against a synthetic
module with a known number of tests, so a broken parser cannot make every assertion here vacuous.
"""

from __future__ import annotations

import ast
import pathlib
import re

import pytest

_NL = chr(10)  # newline without a backslash literal; see repo shell-escaping notes
_REPO = pathlib.Path(__file__).resolve().parents[2]
_CONTRACT_SUITE = _REPO / "contracts" / "test_inscription.py"

# Documents that state the contract-suite size, and must agree with it.
_DOCS_CLAIMING_A_COUNT = (
    "README.md",
    "SECURITY.md",
    "ROADMAP.md",
    "CONTRIBUTING.md",
    "AUDIT_READINESS.md",
    "REVIEWER.md",
)

# "25 tests", "25-test", "25 test suite" -- the shapes actually used in this repo.
# Built from chr(92) rather than written as a literal. The first version of this pattern was
# authored through a shell that ate one backslash level, so the trailing word-boundary became a
# literal backspace (0x08) and the regex matched NOTHING. Every assertion below passed, green,
# while a stale count sat in README -- the exact defect this file exists to prevent, inside the
# file that prevents it. test_the_pattern_actually_matches locks it down.
_B = chr(92)
_COUNT_RE = re.compile(
    _B + "*{0,2}(" + _B + "d{1,3})" + _B + "*{0,2}" + _B + "s*[-" + chr(0x2011) + " ]?test(?:s)?",
    re.IGNORECASE,
)


def _count_tests_in_source(source: str) -> int:
    """Count top-level `def test_*` via the AST, not a grep -- a grep also matches strings."""
    tree = ast.parse(source)
    return sum(
        1
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    )


def _count_tests(path: pathlib.Path) -> int:
    return _count_tests_in_source(path.read_text(encoding="utf-8"))


def test_contract_suite_is_parseable() -> None:
    """A missing or unparseable suite must fail loudly, not silently skip the comparisons."""
    assert _CONTRACT_SUITE.is_file(), f"contract suite not found at {_CONTRACT_SUITE}"
    assert _count_tests(_CONTRACT_SUITE) > 0, "parsed the suite but found no tests - parser broken?"


@pytest.mark.parametrize("doc_name", _DOCS_CLAIMING_A_COUNT)
def test_documented_contract_suite_count_is_current(doc_name: str) -> None:
    """Every N-test claim in these documents must equal the real count."""
    doc = _REPO / doc_name
    if not doc.is_file():
        pytest.skip(f"{doc_name} not present")

    actual = _count_tests(_CONTRACT_SUITE)
    text = doc.read_text(encoding="utf-8")

    # Only consider claims in the same sentence as "suite" or "test_inscription", so an unrelated
    # "3-test" mention elsewhere in a long document does not create a false failure.
    stale: list[str] = []
    for line in text.splitlines():
        if not re.search(r"suite|test_inscription", line, re.IGNORECASE):
            continue
        for match in _COUNT_RE.finditer(line):
            claimed = int(match.group(1))
            # Floors ("fails if fewer than 20 execute") are deliberately below the real count and
            # must not be flagged. Scope that exemption to the TEXT IMMEDIATELY BEFORE THIS MATCH,
            # not to the whole line. A per-line skip silently exempted every other count on the
            # same line: AUDIT_READINESS.md:165 states the real count AND the floor in one table
            # cell, so a stale count there was unreachable by this check. Caught by tripping it.
            window = line[max(0, match.start() - 40):match.start()]
            if re.search(r"fewer than|at least|floor|minimum|no less than", window, re.IGNORECASE):
                continue
            if claimed != actual:
                stale.append(f"{doc_name}: claims {claimed}, actual {actual} -- {line.strip()[:110]}")

    assert not stale, (
        "documentation states a contract-suite size that no longer matches the suite:"
        + _NL + "  " + (_NL + "  ").join(stale)
        + _NL + "Update the prose (or the suite), not this test."
    )


def test_the_pattern_actually_matches() -> None:
    """
    SELF-TEST for the matcher itself.

    The counter self-test below proves `_count_tests_in_source` works. It says nothing about
    `_COUNT_RE`, and _COUNT_RE is where this file actually failed: it once compiled to a pattern
    requiring a literal backspace, matched nothing, and reported green against a document that
    was demonstrably stale. A negative-only assertion cannot distinguish "nothing is wrong" from
    "nothing is being checked". These are the positives.
    """
    must_match = {
        "the **22-test** localnet suite": "22",
        "suite is now 22 tests": "22",
        "a 7 test suite": "7",
        "**25**-test suite": "25",
    }
    for text, expected in must_match.items():
        found = [m.group(1) for m in _COUNT_RE.finditer(text)]
        assert expected in found, (
            f"_COUNT_RE failed to find {expected!r} in {text!r} (found {found}); "
            "the matcher is broken and every count assertion in this file is vacuous"
        )

    # And it must not fire on text with no count at all, or it would flag every line.
    assert not list(_COUNT_RE.finditer("the localnet suite runs in CI")), (
        "_COUNT_RE matches text containing no number; it is matching indiscriminately"
    )


def test_the_counter_actually_counts() -> None:
    """
    SELF-TEST. Every assertion above passes when nothing mismatches, which is also exactly what
    a broken counter produces. This feeds the counter source with a known answer.

    Deliberately takes no `tmp_path` fixture: a self-test that cannot run in some environments
    is not a self-test. It parses a string, so it runs anywhere the suite runs.
    """
    sample = _NL.join(
        (
            "def test_one():",
            "    pass",
            "def test_two():",
            "    pass",
            "def helper():",          # not a test
            "    pass",
            "class NotCollected:",    # nested, not top-level
            "    def test_nested(self):",
            "        pass",
        )
    )
    counted = _count_tests_in_source(sample)
    assert counted == 2, (
        f"counter returned {counted} for source with exactly 2 top-level tests; "
        "every other assertion in this file is therefore unreliable"
    )
