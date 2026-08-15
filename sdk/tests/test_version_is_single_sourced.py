"""The package's reported version must equal the one `pyproject.toml` declares.

Found 2026-08-15. Three numbers disagreed, and nothing compared them:

    sdk/pyproject.toml               version     = "0.2.2"
    sdk/src/trelyan_pq/__init__.py   __version__ = "0.1.0"     <- hand-written, stale
    Dockerfile.verify                trelyan-pq ==  0.1.0

**Only the middle one was a defect, and establishing that took checking PyPI rather than assuming.**
`__version__` was a hand-written literal that had fallen behind `pyproject.toml`, so anyone who
installed 0.2.2 received a package reporting itself as 0.1.0.

The Dockerfile pin is *correct*: PyPI has exactly one published release, 0.1.0, and a hermetic
checker that installs from PyPI can only pin something that exists. A source tree ahead of its last
release is ordinary. My first draft of this file asserted the pin must equal `pyproject.toml` — an
assertion that would have forced pinning a release that does not exist, and broken the checker to
satisfy a test. That is recorded here because it is the same shape of error the register documents:
a check that looks principled while encoding a false premise.

`__version__` is now read from installed distribution metadata, so `pyproject.toml` is the single
source of truth and the two cannot drift by hand-editing. This test closes the remaining gap: it
catches a *stale install*, which the derivation alone cannot — reading metadata correctly reports
whatever was last installed, including something old.

In CI that is automatic (`pip install -e ".[dev]"` runs before pytest). Locally a failure here
means "reinstall", and the message says so.
"""

from __future__ import annotations

import pathlib
import re
import tomllib
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as pkg_version

import pytest

import trelyan_pq

_PYPROJECT = pathlib.Path(__file__).resolve().parents[1] / "pyproject.toml"


def _declared_version() -> str:
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    return str(data["project"]["version"])


def test_reported_version_matches_pyproject() -> None:
    try:
        installed = pkg_version("trelyan-pq")
    except PackageNotFoundError:
        pytest.skip("trelyan-pq is not installed in this environment (running from a source tree)")

    declared = _declared_version()
    assert installed == declared, (
        f"the installed trelyan-pq is {installed} but pyproject.toml declares {declared}. "
        f"Re-install the working tree (`pip install -e .` from sdk/) — a stale install makes "
        f"__version__, and anything that reads it, report the wrong release."
    )
    assert trelyan_pq.__version__ == declared, (
        f"trelyan_pq.__version__ is {trelyan_pq.__version__}, pyproject declares {declared}"
    )


def test_version_is_not_hand_written_in_the_package() -> None:
    """Pin the mechanism, not just the value.

    A future edit could 'fix' a mismatch by hard-coding the literal again, which restores the exact
    defect while making this file's other test pass. Assert the derivation is still in place.
    """
    src = (
        pathlib.Path(trelyan_pq.__file__).resolve()
    ).read_text(encoding="utf-8")
    assert "importlib.metadata" in src, (
        "__version__ must be derived from installed distribution metadata, not written by hand — "
        "a literal here is what let the package report 0.1.0 while pyproject said 0.2.2"
    )
    hand_written = re.search(r'^__version__\s*=\s*[\'"][0-9]', src, re.MULTILINE)
    assert hand_written is None, (
        f"__version__ is assigned a version literal at line "
        f"{src[: hand_written.start()].count(chr(10)) + 1 if hand_written else '?'}; "
        f"derive it from metadata instead"
    )


def test_the_hermetic_checker_pin_is_reconciled_with_the_source_version() -> None:
    """`Dockerfile.verify` installs from PyPI, so it can only pin a PUBLISHED release.

    My first version of this test asserted the pin must equal `pyproject.toml`'s version, and that
    was wrong — it would have forced pinning a release that does not exist. Checked against PyPI:
    only **0.1.0** is published, while this tree declares 0.2.2. A source tree ahead of the last
    release is entirely normal, and a hermetic checker that installs from PyPI is *correct* to pin
    the latest published version rather than an unreleased one.

    So the real risk is not today's divergence — it is that nothing forces the pin to move WHEN a
    release happens. That belongs in the release workflow, which knows the tag, not in a unit test
    that would fail for the whole of normal development.

    What this test does assert is that the divergence is *acknowledged*: the Dockerfile must carry
    a note naming the source version it was reconciled against, so bumping the version cannot
    silently leave the checker behind.
    """
    dockerfile = _PYPROJECT.parents[1] / "Dockerfile.verify"
    if not dockerfile.exists():
        pytest.skip("Dockerfile.verify not present")

    text = dockerfile.read_text(encoding="utf-8")
    pinned = re.search(r"trelyan-pq==([0-9][^\"'\s]*)", text)
    if pinned is None:
        return  # no pin to reconcile

    declared = _declared_version()
    if pinned.group(1) == declared:
        return  # in step; nothing to acknowledge

    assert "PUBLISHED" in text, (
        f"Dockerfile.verify pins trelyan-pq=={pinned.group(1)} while this tree declares {declared}. "
        f"That is legitimate when {declared} is unreleased, but it must be stated: add a note "
        f"explaining that the pin tracks the latest PUBLISHED release and must be bumped when a "
        f"new one ships. Silent divergence is how an auditor ends up verifying a different release "
        f"from the one they are reading."
    )
