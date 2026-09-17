"""sdk/examples/verify_trelyan.py's clear-state checks, run offline against a stubbed algod.

The script is a top-level reviewer script, so it is executed with runpy after
`urllib.request.urlopen` is replaced with a stub that serves the application, its boxes and
/v2/teal/compile. No request reaches the network: an unexpected URL or TEAL raises.

Three cases:
  * the deployed clear-state program is present and equals the committed one -> no FAIL, no SKIP;
  * it is absent or empty -> its three checks are NOT CHECKED (exit 2), with no FAIL line and no
    redeploy banner, and the committed clear-state TEAL is never assembled;
  * it differs -> the pin and assembly checks FAIL (exit 1) and the redeploy banner names it.

The deployed approval program is served as the real bytes (APPROVAL_PROGRAM_B64), so the
script's approval pin passes and only the clear-state program varies between cases.
"""

from __future__ import annotations

import base64
import io
import json
import re
import runpy
from contextlib import redirect_stdout
from pathlib import Path
from urllib.request import Request

import pytest

import trelyan_pq

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "sdk" / "examples" / "verify_trelyan.py"
OUT = REPO / "contracts" / "out"
APPROVAL_TEAL = (OUT / "TrelyanInscription.approval.teal").read_bytes()
CLEAR_TEAL = (OUT / "TrelyanInscription.clear.teal").read_bytes()

# The 709 B approval program the TestNet app serves (read-only GET /v2/applications/{id},
# 2026-09-17). Its sha512_256 is the script's PINNED_ON_CHAIN_SHA512_256; the control case below
# fails if it is not.
APPROVAL_PROGRAM_B64 = (
    "DCAEAAEIICYGBWFkbWluEGNlbGxzX3JlZ2lzdGVyZWQCb18CaV8Ca18DBoEBMRhAAAcoMgNnKSJnMRtBADsxGRRE"
    "MRhBACSCBASbRH39BJ0wDPIErfl1qwSq39/TNhoAjgQAKgDiAewCQQCABExcYbo2GgCOAQAWAIMCBAUxGY4CAAUA"
    "AQAxGEQAMRhEACgxAGcjQzYaAUkVJBJEF0k2GgJJTgIVJRJENhoDSU4CSSJZgQIITBUSRDEAIihlRBJEcQBEIxJB"
    "AIBLAnEBREAAeCNESwJJcQtEIihlRBJESXEKRDIDEkRJcQlEMgMSRElxB0QyAxJESwFXAgBJFYGBDhJESSJVgQoS"
    "RCIpZURJgYAIDEQyA0sFSU8CE0RPAxYnBEsBUEm9RQEURCpPAlBJvUUBFERLAbxITE8Ev0m8SEy/IwgpTGcjQyJC"
    "/4UiRwI2GgFHAhUkEkQXNhoCSU4CFSUSRDYaA0kiWYECCEsBFRJENhoESU4DSSJZgQIISwEVEkRLAhZJTgQnBExQ"
    "SU4EvUUBRExXAgBJTgMVgY8LDkRXAgAVgYABDkQxAExwAEEAoUkjEkEAmyNEKksESU4CUEm9RQFEvkgxABJEK0sB"
    "UElFC71FARRESwO+TEUKRDIIFoAWVFJFTFlBTi1JTlNDUklQVElPTi12MUxQTFBLBlAyEVBFCoG+EDIMDUEAGLGB"
    "BrIQgQWyGScFsh4nBbIfIrIBs0L/30sJSwJLCYVEMgYWMQCAAQFLCVBLCFBPAlBMUIACAFNQSwVQSwlJvEhMvyND"
    "IkL/YjYaAUkVJBJEFzYaAklOAhUlEkRJFipLAVBJTgNJvUUBRL5IMQASRCtMUL1FARREMQBMcABBABpJIxJBABQj"
    "RDIDSwNJTwITREsCSbxITL8jQyJC/+k2GgFJFSQSRBcWK0xQvkSABBUffHVMULAjQw=="
)
APPROVAL_PROGRAM = base64.b64decode(APPROVAL_PROGRAM_B64)
CLEAR_PROGRAM = bytes([0x0C, 0x81, 0x01, 0x43])  # pushint 1; return (what the committed TEAL assembles to)
OTHER_CLEAR_PROGRAM = bytes([0x0C, 0x81, 0x00, 0x43])  # pushint 0; return

CLEAR_CHECKS = (
    "clear-state program fetched",
    "deployed clear-state program matches its 2026-09-14 pin",
    "deployed clear-state program is what the committed clear-state TEAL assembles to",
)
RESULT_RE = re.compile(r"== RESULT: (\d+) passed, (\d+) failed, (\d+) not checked ==")


def _json(obj: object) -> io.BytesIO:
    return io.BytesIO(json.dumps(obj).encode())


def _run(monkeypatch, clear_field: str | None):
    """Execute verify_trelyan.py with algod stubbed. `clear_field` None removes the key."""
    params: dict = {
        "approval-program": APPROVAL_PROGRAM_B64,
        "global-state-schema": {"num-uint": 1, "num-byte-slice": 1},
        "local-state-schema": {},
    }
    if clear_field is not None:
        params["clear-state-program"] = clear_field
    cell_box = b"k_" + (1).to_bytes(8, "big")
    compiled: list[bytes] = []

    def urlopen(target, timeout=None):
        if isinstance(target, Request):
            assert target.full_url.endswith("/v2/teal/compile"), target.full_url
            teal = target.data
            compiled.append(teal)
            table = {APPROVAL_TEAL: APPROVAL_PROGRAM, CLEAR_TEAL: CLEAR_PROGRAM}
            assert teal in table, f"unexpected TEAL ({len(teal)} B)"
            return _json({"result": base64.b64encode(table[teal]).decode()})
        path = target.split("/v2/", 1)[1]
        if m := re.fullmatch(r"applications/(\d+)", path):
            return _json({"id": int(m.group(1)), "params": params})
        if re.fullmatch(r"applications/\d+/boxes", path):
            return _json({"boxes": [{"name": base64.b64encode(cell_box).decode()}]})
        if re.fullmatch(r"applications/\d+/box\?name=.+", path):
            return _json({"value": base64.b64encode(bytes([0x0A]) + bytes(1792)).decode()})
        raise AssertionError(f"unexpected algod request: {target}")

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    monkeypatch.delenv("TRELYAN_COMMITTED_TEAL", raising=False)
    monkeypatch.delenv("TRELYAN_COMMITTED_CLEAR_TEAL", raising=False)
    # The "trelyan-pq import" check fails on an uninstalled source tree (version "+source"), which
    # is a property of the test environment, not of the clear-state path under test.
    monkeypatch.setattr(trelyan_pq, "__version__", "0.0.0-offline-test")
    out = io.StringIO()
    with redirect_stdout(out), pytest.raises(SystemExit) as exit_info:
        runpy.run_path(str(SCRIPT), run_name="__main__")
    text = out.getvalue()
    counts = RESULT_RE.search(text)
    assert counts, text
    passed, failed, not_checked = (int(g) for g in counts.groups())
    return exit_info.value.code, text, (passed, failed, not_checked), compiled


def _lines(text: str, prefix: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.startswith(prefix)]


def test_a_matching_clear_state_program_passes(monkeypatch):
    rc, text, (passed, failed, not_checked), compiled = _run(
        monkeypatch, base64.b64encode(CLEAR_PROGRAM).decode()
    )
    assert (rc, failed, not_checked) == (0, 0, 0), text
    for name in CLEAR_CHECKS:
        assert any(line.startswith(f"PASS  {name}") for line in _lines(text, "  PASS  ")), text
    assert CLEAR_TEAL in compiled
    assert "AWAITING TESTNET REDEPLOY" not in text


@pytest.mark.parametrize("clear_field", [None, ""], ids=["key-absent", "empty-string"])
def test_an_absent_clear_state_program_is_not_checked(monkeypatch, clear_field):
    _, _, (control_passed, _, _), _ = _run(monkeypatch, base64.b64encode(CLEAR_PROGRAM).decode())
    rc, text, (passed, failed, not_checked), compiled = _run(monkeypatch, clear_field)
    assert rc == 2, text
    assert (failed, not_checked) == (0, 3), text
    assert passed == control_passed - 3, text
    skipped = _lines(text, "  SKIP  ")
    assert [line.split("  [")[0].removeprefix("SKIP  ") for line in skipped] == list(CLEAR_CHECKS), text
    assert not _lines(text, "  FAIL  "), text
    assert "AWAITING TESTNET REDEPLOY" not in text
    assert CLEAR_TEAL not in compiled, "nothing was read, so nothing should be assembled to compare"


def test_a_differing_clear_state_program_fails_and_names_the_redeploy(monkeypatch):
    rc, text, (passed, failed, not_checked), _ = _run(
        monkeypatch, base64.b64encode(OTHER_CLEAR_PROGRAM).decode()
    )
    assert (rc, failed, not_checked) == (1, 2, 0), text
    failures = [line.split("  [")[0].removeprefix("FAIL  ") for line in _lines(text, "  FAIL  ")]
    assert failures == list(CLEAR_CHECKS[1:]), text
    assert "AWAITING TESTNET REDEPLOY" in text
    assert "The live clear-state program differs from the" in text
