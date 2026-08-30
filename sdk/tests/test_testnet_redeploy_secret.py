"""The keyed TestNet redeploy must fail closed on a missing secret name.

It must never print the secret value, never require ALGOD_*, and never be an
automatic push/PR job (that would spend TestNet ALGO on every commit).
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
REQUIRE = REPO / "contracts" / "require_testnet_deploy_secret.py"
WORKFLOW = REPO / ".github" / "workflows" / "testnet-redeploy.yml"
# Stand-ins used only to prove the helper never echoes them. Not a real mnemonic.
FAKE_SECRET = "test-secret-value-must-never-appear-in-stdout-xyz"
INVALID_25 = " ".join(f"xx{i:02d}" for i in range(25))


def _load_require():
    spec = importlib.util.spec_from_file_location("trelyan_require_testnet_secret", REQUIRE)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _run_require(env: dict[str, str], extra_args: list[str] | None = None) -> subprocess.CompletedProcess[str]:
    clean = {k: v for k, v in os.environ.items() if k != "DEPLOYER_MNEMONIC"}
    clean.update(env)
    return subprocess.run(
        [sys.executable, str(REQUIRE), *(extra_args or [])],
        env=clean,
        capture_output=True,
        text=True,
        check=False,
    )


def _assert_secret_not_printed(out: str, secret: str) -> None:
    assert secret not in out
    for token in secret.split():
        if len(token) >= 4:
            assert token not in out


def test_missing_secret_lists_exact_name_and_hides_any_value():
    result = _run_require({})
    assert result.returncode == 1
    out = result.stdout + result.stderr
    assert "BLOCKED" in out
    assert "DEPLOYER_MNEMONIC" in out
    assert "ALGOD_URL" in out
    assert "ALGOD_TOKEN" in out
    assert "not required" in out.lower() or "Not required" in out
    assert FAKE_SECRET not in out
    # Windows CI is cp1252: a single non-ASCII glyph in this banner
    # UnicodeEncodeError'd after the secret name and failed the KAT job.
    out.encode("ascii")
    result.stderr.encode("ascii")


def test_wrong_word_count_fails_without_printing_the_value():
    result = _run_require({"DEPLOYER_MNEMONIC": FAKE_SECRET})
    assert result.returncode == 1
    out = result.stdout + result.stderr
    assert "25 words" in out
    _assert_secret_not_printed(out, FAKE_SECRET)
    out.encode("ascii")


def test_present_25_word_secret_is_not_printed():
    result = _run_require({"DEPLOYER_MNEMONIC": INVALID_25})
    assert result.returncode == 0
    out = result.stdout + result.stderr
    assert "present" in out
    _assert_secret_not_printed(out, INVALID_25)


def test_parse_invalid_mnemonic_never_prints_the_word_list():
    result = _run_require({"DEPLOYER_MNEMONIC": INVALID_25}, extra_args=["--parse"])
    out = result.stdout + result.stderr
    _assert_secret_not_printed(out, INVALID_25)
    out.encode("ascii")
    try:
        import algosdk.mnemonic  # noqa: F401
    except ImportError:
        assert result.returncode == 2
        assert "COULD NOT CHECK" in out
    else:
        assert result.returncode == 1
        assert "not a valid Algorand mnemonic" in out
        assert "ValueError" not in out


def test_whitespace_only_secret_is_treated_as_missing():
    result = _run_require({"DEPLOYER_MNEMONIC": "   "})
    assert result.returncode == 1
    assert "DEPLOYER_MNEMONIC" in result.stdout


def test_missing_required_helper_matches_env():
    mod = _load_require()
    old = os.environ.pop("DEPLOYER_MNEMONIC", None)
    try:
        assert mod.missing_required() == ["DEPLOYER_MNEMONIC"]
        os.environ["DEPLOYER_MNEMONIC"] = "x"
        assert mod.missing_required() == []
    finally:
        if old is None:
            os.environ.pop("DEPLOYER_MNEMONIC", None)
        else:
            os.environ["DEPLOYER_MNEMONIC"] = old


def test_workflow_is_dispatch_only_and_never_echoes_the_mnemonic():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text
    assert "DEPLOYER_MNEMONIC" in text
    assert "secrets.DEPLOYER_MNEMONIC" in text
    assert "require_testnet_deploy_secret.py" in text
    assert "--parse" in text
    assert "deploy_testnet.py" in text
    assert "verify_deployment.py" in text
    assert "Type TESTNET" in text or '!= "TESTNET"' in text
    # Must not auto-run on push/PR/schedule — that would spend on every commit.
    for trigger in ("push:", "pull_request:", "schedule:"):
        assert trigger not in text
    # Never dump the secret. `set -x` would print the environment.
    lowered = text.lower()
    assert "echo $deployer_mnemonic" not in lowered
    assert "echo ${deployer_mnemonic}" not in lowered
    assert "print(os.environ" not in lowered
    assert "set -x" not in text
    assert "mainnet is forbidden" in lowered


def test_deploy_script_refuses_mainnet_and_writes_only_numeric_ids():
    text = (REPO / "contracts" / "deploy_testnet.py").read_text(encoding="utf-8")
    assert "_write_github_output" in text
    assert 'name not in {"app_id", "cell_id"}' in text
    assert "TESTNET_GENESIS_B64" in text
    assert "Refusing to deploy: connected node is not Algorand TestNet." in text
    assert "AlgorandClient.testnet()" in text
    assert "not a valid Algorand mnemonic" in text
    assert "The value is not printed" in text


def test_existing_e2e_job_also_fails_closed_on_the_same_secret():
    text = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "require_testnet_deploy_secret.py" in text
    assert "--parse" in text
    assert "secrets.DEPLOYER_MNEMONIC" in text


def test_blockers_lists_the_exact_secret_names():
    text = (REPO / "BLOCKERS.md").read_text(encoding="utf-8")
    assert "`DEPLOYER_MNEMONIC`" in text
    assert "`ALGOD_URL`" in text
    assert "`ALGOD_TOKEN`" in text
    assert "must not be set" in text
    assert "testnet-redeploy.yml" in text
    assert "TestNet redeploy" in text
