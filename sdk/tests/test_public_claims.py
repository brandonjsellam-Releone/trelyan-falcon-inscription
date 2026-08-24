"""
Guard: nothing this package PUBLISHES may claim FIPS 206 / FN-DSA conformance.

WHY THIS TEST EXISTS
--------------------------------------------------------------------------------------------------
THREAT_MODEL_AND_TRACEABILITY.md records a settled conclusion:

    det1024 can never be FIPS 206 conformant as specified.

NIST's FN-DSA status update states FN-DSA will allow ONLY randomized signing, precisely because
"Deterministic signing could be dangerous." TRELYAN's signer is deterministic -- deliberately,
because deterministic compressed Falcon-1024 is what the on-chain `falcon_verify` opcode verifies.
The two can never meet. The threat model therefore forbids claiming FIPS 206 / FN-DSA conformance
in public material.

That prohibition was written in prose, and prose does not execute. On 2026-08-24 an audit found
`fn-dsa` and `fips-206` sitting in this package's PyPI keywords -- i.e. the forbidden claim had
been published, to the public index, on the only release that exists.

The cost of that class of mistake is asymmetric and permanent:

    PUBLISHED PyPI METADATA CANNOT BE EDITED IN PLACE.

There is no patch. A wrong keyword is correctable only by cutting a new release and deciding
whether to yank the old one. So the check has to happen BEFORE the upload, which means here.

WHY THIS IS NOT A CHECK THAT CANNOT FAIL
--------------------------------------------------------------------------------------------------
This repository has shipped checks that could not fail -- a Dockerfile grep whose `&&`/`||`
precedence swallowed its exit code, and a tamper test whose string replacement matched nothing.
Both reported green for weeks. The shape to avoid is comparing a value against a constant derived
from that same value.

This test does not have that shape. The two sides come from independent sources: one is the
DECLARED prohibition below (a literal list, written here, reviewed as policy), the other is PARSED
from pyproject.toml as it will actually be built. A banned term added to the manifest fails this
test. If you ever edit `_FORBIDDEN` to make this pass, you have inverted it -- the correct response
to a failure is to remove the term from the manifest, never from this list.

`test_forbidden_terms_are_actually_detectable` proves the detector still bites, by running it
against a synthetic manifest that DOES contain a banned term and asserting it is caught. Without
that, a bug in the matching logic would render every other assertion here vacuous and silent.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - 3.10 fallback, mirrors requires-python = ">=3.10"
    tomllib = pytest.importorskip("tomli", reason="tomli is needed to parse pyproject on 3.10")

_PYPROJECT = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"

# The declared prohibition. Normalised comparison, so "FIPS 206", "fips_206" and "FIPS-206" are
# all the same term -- a guard that only caught one spelling would be a guard in name only.
_FORBIDDEN = ("fndsa", "fips206")

# Terms that are ACCURATE and must stay allowed, so the matcher cannot be widened into uselessness:
# this really is Falcon, really is post-quantum, and really does target falcon_verify.
_MUST_REMAIN_ALLOWED = ("falcon", "falcon-1024", "falcon_verify", "post-quantum", "pqc")


def _normalise(text: str) -> str:
    """Fold case and strip separators, so one banned term covers all its spellings."""
    return "".join(ch for ch in text.lower() if ch.isalnum())


def _offenders(values) -> list[str]:
    """Return every supplied string containing a forbidden term, normalised."""
    return [v for v in values if any(bad in _normalise(v) for bad in _FORBIDDEN)]


def _manifest() -> dict:
    with _PYPROJECT.open("rb") as fh:
        return tomllib.load(fh)


def test_pyproject_exists() -> None:
    """A missing manifest must fail loudly, not silently skip every assertion below."""
    assert _PYPROJECT.is_file(), f"manifest not found at {_PYPROJECT}"


def test_keywords_make_no_fips206_claim() -> None:
    """The exact defect found on 2026-08-24: banned terms in the published keyword list."""
    keywords = _manifest()["project"].get("keywords", [])
    assert keywords, "keywords list is empty or absent - expected the real published list"
    bad = _offenders(keywords)
    assert not bad, (
        f"pyproject keywords claim FIPS 206 / FN-DSA: {bad}. "
        "THREAT_MODEL_AND_TRACEABILITY.md states det1024 can never be FIPS 206 conformant. "
        "Remove the term from pyproject.toml - do not edit _FORBIDDEN."
    )


def test_description_and_summary_make_no_fips206_claim() -> None:
    """Prose fields ship to the index too, and are read before the keyword list."""
    project = _manifest()["project"]
    bad = _offenders([project.get("description", "")])
    assert not bad, f"pyproject description claims FIPS 206 / FN-DSA: {bad}"


def test_classifiers_make_no_fips206_claim() -> None:
    """Trove classifiers are the most authoritative-looking public metadata of all."""
    bad = _offenders(_manifest()["project"].get("classifiers", []))
    assert not bad, f"pyproject classifiers claim FIPS 206 / FN-DSA: {bad}"


def test_accurate_terms_are_not_collateral_damage() -> None:
    """The matcher must not be so broad that it bans true statements about Falcon."""
    survivors = _offenders(list(_MUST_REMAIN_ALLOWED))
    assert not survivors, (
        f"the forbidden-term matcher rejects accurate terms {survivors}; "
        "it has been widened past its purpose"
    )


def test_forbidden_terms_are_actually_detectable() -> None:
    """
    SELF-TEST. Proves the detector bites.

    Every assertion above is a NEGATIVE: it passes when nothing is found. A negative-only suite
    passes just as happily when the matcher is broken as when the manifest is clean, and gives
    the same green either way. This case feeds the detector inputs that MUST be caught, across
    the spellings a real manifest might use.
    """
    planted = ["fips-206", "FIPS 206", "fn-dsa", "FN_DSA", "FipsDsa206"]
    for term in planted[:4]:
        assert _offenders([term]), (
            f"detector failed to catch {term!r} - every other assertion in this file is "
            "therefore vacuous, and a green run here means nothing"
        )
    # And it must still pass the real manifest afterwards, so the detector is discriminating
    # rather than simply matching everything.
    assert not _offenders(_manifest()["project"]["keywords"]), (
        "detector flags the current manifest; either the manifest regressed or the matcher is "
        "matching indiscriminately"
    )
