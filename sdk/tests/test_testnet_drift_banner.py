"""The TestNet drift report must name the redeploy, with sizes — never a silent skip.

The live comparison needs algod and is the TestNet follow-up's job. This test only
locks the failure *text* so a later edit cannot turn the mismatch into a skip or a
vague "something differed".
"""

from __future__ import annotations

import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _load_verify_deployment():
    path = REPO / "contracts" / "verify_deployment.py"
    spec = importlib.util.spec_from_file_location("trelyan_verify_deployment", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_drift_banner_names_redeploy_and_exact_sizes():
    mod = _load_verify_deployment()
    buf = io.StringIO()
    with redirect_stdout(buf):
        mod.print_awaiting_redeploy(
            app_id=763809096,
            expected_hash="6fa5cee145762e4a0c2ba93738a0e6f51e93b02c71f23e4e663ac6d73b981c4b",
            expected_len=709,
            deployed_hash="d24d9071209f526a2075542d9408295d78f83ca5ed4c8cc233000130dcc97d44",
            deployed_len=660,
        )
    out = buf.getvalue()
    assert "AWAITING TESTNET REDEPLOY of app 763809096" in out
    assert "709 B" in out
    assert "660 B" in out
    assert "6fa5cee145762e4a0c2ba93738a0e6f51e93b02c71f23e4e663ac6d73b981c4b" in out
    assert "d24d9071209f526a2075542d9408295d78f83ca5ed4c8cc233000130dcc97d44" in out
    assert "BLOCKERS.md" in out
    assert "not a silent skip" in out
    assert "DRIFT" in out


def test_blockers_md_records_the_measured_drift():
    text = (REPO / "BLOCKERS.md").read_text(encoding="utf-8")
    assert "AWAITING TESTNET REDEPLOY of app 763809096" in text.upper() or (
        "awaiting TestNet redeploy of app 763809096" in text
    )
    assert "6fa5cee145762e4a0c2ba93738a0e6f51e93b02c71f23e4e663ac6d73b981c4b" in text
    assert "d24d9071209f526a2075542d9408295d78f83ca5ed4c8cc233000130dcc97d44" in text
    assert "709 B" in text
    assert "660 B" in text
    assert "deploy_testnet.py" in text
    assert "Required merge gates (local)" in text
