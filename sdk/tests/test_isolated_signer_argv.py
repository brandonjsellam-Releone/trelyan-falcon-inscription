"""The isolated signer must be SPAWNABLE on every interpreter this package supports.

Found 2026-08-16. `keygen_sign_seal_isolated` spawned the worker with `-P`, a CPython 3.11+ flag,
while sdk/pyproject.toml declares requires-python = ">=3.10" and the CI matrix runs 3.10. On 3.10
the interpreter aborts during ARGV PARSING - "Unknown option: -P", exit 2 - before the worker
module is imported at all. The parent then read empty stdout and raised SealVerificationError,
whose docstring attributes the failure to the Falcon build.

WHY NOTHING CAUGHT IT, which is the part worth keeping: every spawning test in
test_isolated_signer.py is `@requires_lib`; the only CI job that builds the Falcon library pins
3.12; and the one pure-Python isolated test pre-seals the cell, so it raises before the spawn is
reached. Deleting `-P` outright would not have failed a single test.

These tests need NO Falcon library and NO subprocess, so they run on every matrix leg - which is
exactly the property the old coverage lacked.
"""

from __future__ import annotations

import subprocess
import sys

import pytest


def _spawn_argv(monkeypatch, version):
    """The argv keygen_sign_seal_isolated would use on `version`, without running anything."""
    import trelyan_pq.seal as seal

    captured = {}

    class _Result:
        returncode = 1
        stdout = b"{}"
        stderr = b"probe"

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _Result()

    monkeypatch.setattr(seal.subprocess, "run", fake_run)
    monkeypatch.setattr(seal.sys, "version_info", version)
    with pytest.raises(Exception):
        seal.keygen_sign_seal_isolated(
            cell_id=1, app_id=1, artifact_hash=b"\x00" * 32, genesis_hash=b"\x00" * 32,
            store=seal.InMemorySealStore(),
        )
    return captured.get("argv", [])


def test_no_311_only_flag_is_passed_on_310(monkeypatch):
    argv = _spawn_argv(monkeypatch, (3, 10, 20))
    assert "-P" not in argv, (
        f"`-P` is CPython 3.11+; on 3.10 the interpreter aborts in argv parsing before the worker "
        f"is imported, and the failure is reported as a broken Falcon build. argv was {argv}"
    )
    assert argv[-2:] == ["-m", "trelyan_pq._seal_worker"], argv


def test_the_flag_is_still_used_where_it_exists(monkeypatch):
    # Dropping it everywhere would be the lazy fix: on 3.11+ it is a real hardening control.
    argv = _spawn_argv(monkeypatch, (3, 12, 0))
    assert "-P" in argv, f"`-P` must still be passed on 3.11+; argv was {argv}"


def test_the_flag_is_actually_rejected_by_this_interpreter_if_it_is_310():
    """Non-vacuity: prove the premise on the interpreter actually running, when it applies."""
    if sys.version_info >= (3, 11):
        pytest.skip("this interpreter accepts -P; the 3.10 premise is asserted by the unit tests")
    rc = subprocess.run([sys.executable, "-P", "-c", "pass"], capture_output=True).returncode
    assert rc != 0, "expected this 3.10 interpreter to reject -P; the premise no longer holds"
