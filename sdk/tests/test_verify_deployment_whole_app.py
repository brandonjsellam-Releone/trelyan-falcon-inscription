"""verify_deployment.py compares the whole application, and every comparison it prints can FAIL.

Until 2026-09-14 the script compared the approval program only. It now also compares the
clear-state program, both state schemas and extra-program-pages, and exits 0 only when all five
match. These tests pin that contract without a network: the module is loaded the same way as
test_testnet_drift_banner.py, and `assemble` (algod /v2/teal/compile) and `fetch_app_params`
(algod /v2/applications/{id}) are replaced with stubs. `urllib.request.urlopen` is also replaced
with one that raises, so a stub that stopped being used would fail the test instead of quietly
reaching the network.

The committed artifacts are read from contracts/out/ for real, so the default --teal,
--clear-teal and --arc56 wiring is exercised too. The deployed side is synthetic.
"""

from __future__ import annotations

import base64
import importlib.util
import io
import json
import shutil
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "contracts" / "out"
APPROVAL_TEAL = (OUT / "TrelyanInscription.approval.teal").read_bytes()
CLEAR_TEAL = (OUT / "TrelyanInscription.clear.teal").read_bytes()
ARC56_SCHEMA = json.loads((OUT / "TrelyanInscription.arc56.json").read_text(encoding="utf-8"))[
    "state"
]["schema"]

# Synthetic application id. Deliberately not shaped like a TestNet id, so this file stays out of
# test_app_id_references_are_coherent.py's LIVE_CLAIM / FROZEN partition.
APP_ID = 4242

# Stand-ins for what the committed TEAL assembles to. Sizes mirror the real programs (709 B, 4 B);
# the bytes only need to be distinct and deterministic.
APPROVAL_BYTES = bytes([0x0C]) + bytes(range(256)) * 2 + bytes(196)
CLEAR_BYTES = bytes([0x0C, 0x81, 0x01, 0x43])  # pushint 1; return
OTHER_CLEAR_BYTES = bytes([0x0C, 0x81, 0x00, 0x43])  # pushint 0; return


def _load_verify_deployment():
    path = REPO / "contracts" / "verify_deployment.py"
    spec = importlib.util.spec_from_file_location("trelyan_verify_deployment_whole_app", path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def _matching_params() -> dict:
    """Deployed params that equal the committed artifacts. extra-program-pages is absent, as on
    the live app, where algod omits the zero value."""
    return {
        "approval-program": _b64(APPROVAL_BYTES),
        "clear-state-program": _b64(CLEAR_BYTES),
        "global-state-schema": {
            "num-uint": ARC56_SCHEMA["global"]["ints"],
            "num-byte-slice": ARC56_SCHEMA["global"]["bytes"],
        },
        "local-state-schema": {
            "num-uint": ARC56_SCHEMA["local"]["ints"],
            "num-byte-slice": ARC56_SCHEMA["local"]["bytes"],
        },
    }


def _assembler(calls: list, extra: dict | None = None):
    table = {APPROVAL_TEAL: APPROVAL_BYTES, CLEAR_TEAL: CLEAR_BYTES, **(extra or {})}

    def assemble(teal: bytes, url: str, timeout: int) -> bytes:
        calls.append((teal, url))
        if teal not in table:
            raise AssertionError(f"assemble() called with unexpected TEAL ({len(teal)} B)")
        return table[teal]

    return assemble


def _run(monkeypatch, params: dict, argv: tuple[str, ...] = (), extra_teal: dict | None = None,
         recompile=None):
    mod = _load_verify_deployment()
    if recompile is not None:
        monkeypatch.setattr(mod, "recompile_from_source", recompile)

    def no_network(*_a, **_k):
        raise AssertionError("verify_deployment.py reached the network despite the stubs")

    calls: list = []
    monkeypatch.setattr("urllib.request.urlopen", no_network)
    monkeypatch.setattr(mod, "assemble", _assembler(calls, extra_teal))
    monkeypatch.setattr(mod, "fetch_app_params", lambda app_id, algod, timeout: params)
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = mod.main(["--app-id", str(APP_ID), *argv])
    return rc, out.getvalue(), err.getvalue(), calls


def _component_line(out: str, name: str) -> str:
    lines = [line for line in out.splitlines() if f"  {name} " in line and "committed " in line]
    assert len(lines) == 1, f"expected one component line for {name!r}, got {lines!r}\n{out}"
    return lines[0].strip()


def _differing(out: str) -> str:
    lines = [line.strip() for line in out.splitlines() if line.strip().startswith("differing: ")]
    assert len(lines) == 1, out
    return lines[0]


ALL_COMPONENTS = (
    "approval program",
    "clear-state program",
    "global-state-schema",
    "local-state-schema",
    "extra-program-pages",
)


def test_all_components_match_exits_0(monkeypatch):
    rc, out, err, _ = _run(monkeypatch, _matching_params())
    assert rc == 0, out + err
    for name in ALL_COMPONENTS:
        assert _component_line(out, name).startswith("MATCH"), out
    assert f"MATCH - application {APP_ID}:" in out
    assert "Not compared: global-state contents" in out
    assert "DRIFT" not in out


def test_clear_state_differs_while_approval_matches_exits_1(monkeypatch):
    params = _matching_params()
    params["clear-state-program"] = _b64(OTHER_CLEAR_BYTES)
    rc, out, err, _ = _run(monkeypatch, params)
    assert rc == 1, out + err
    assert _component_line(out, "approval program").startswith("MATCH"), out
    assert _component_line(out, "clear-state program").startswith("DRIFT"), out
    assert _differing(out) == "differing: clear-state program"
    assert "AWAITING TESTNET REDEPLOY" in out
    assert "MATCH - application" not in out


@pytest.mark.parametrize(
    ("schema_key", "count_key"),
    [
        ("global-state-schema", "num-uint"),
        ("global-state-schema", "num-byte-slice"),
        ("local-state-schema", "num-uint"),
        ("local-state-schema", "num-byte-slice"),
    ],
)
def test_schema_differs_exits_1(monkeypatch, schema_key, count_key):
    params = _matching_params()
    params[schema_key][count_key] += 1
    rc, out, err, _ = _run(monkeypatch, params)
    assert rc == 1, out + err
    assert _component_line(out, schema_key).startswith("DRIFT"), out
    assert _differing(out) == f"differing: {schema_key}"


def test_extra_program_pages_differ_exits_1(monkeypatch):
    params = _matching_params()
    params["extra-program-pages"] = 1
    rc, out, err, _ = _run(monkeypatch, params)
    assert rc == 1, out + err
    assert _component_line(out, "extra-program-pages").startswith("DRIFT"), out
    assert _differing(out) == "differing: extra-program-pages"


def test_clear_state_program_missing_from_params_exits_2(monkeypatch):
    params = _matching_params()
    del params["clear-state-program"]
    rc, out, err, _ = _run(monkeypatch, params)
    assert rc == 2, out + err
    assert "COULD NOT CHECK" in err and "clear-state-program" in err, err
    assert "MATCH - application" not in out and "DRIFT" not in out, out


def test_a_zero_count_omitted_from_a_schema_object_reads_as_zero(monkeypatch):
    """The documented missing-key rule, on the side where it can matter: local {0, 0} as `{}`."""
    assert ARC56_SCHEMA["local"] == {"ints": 0, "bytes": 0}, "fixture premise changed"
    params = _matching_params()
    params["local-state-schema"] = {}
    rc, out, err, _ = _run(monkeypatch, params)
    assert rc == 0, out + err


def test_compile_url_is_used_for_both_assemblies(monkeypatch):
    rc, out, err, calls = _run(
        monkeypatch, _matching_params(), argv=("--compile-url", "https://independent.example")
    )
    assert rc == 0, out + err
    assert sorted(teal for teal, _ in calls) == sorted([APPROVAL_TEAL, CLEAR_TEAL])
    assert {url for _, url in calls} == {"https://independent.example"}


@pytest.mark.parametrize("clear_changed", [False, True])
def test_recompile_covers_the_clear_state_program(monkeypatch, clear_changed):
    """--recompile compares the fresh clear-state TEAL too, not only the approval TEAL."""
    fresh_clear = CLEAR_TEAL + b"\n// fresh compile\n" if clear_changed else CLEAR_TEAL
    mod_holder: dict = {}

    def fake_recompile(source, out_dir, avm_version):
        shutil.copy(OUT / "TrelyanInscription.approval.teal", out_dir)
        shutil.copy(OUT / "TrelyanInscription.arc56.json", out_dir)
        (out_dir / "TrelyanInscription.clear.teal").write_bytes(fresh_clear)
        mod_holder["called"] = avm_version

    extra = {fresh_clear: OTHER_CLEAR_BYTES} if clear_changed else None
    rc, out, err, _ = _run(
        monkeypatch, _matching_params(), argv=("--recompile",), extra_teal=extra,
        recompile=fake_recompile,
    )
    assert mod_holder.get("called") == "12"
    if clear_changed:
        assert rc == 1, out + err
        assert "FAIL  committed clear-state TEAL" in out, out
        assert "clear-state TEAL" in out.splitlines()[-1], out
    else:
        assert rc == 0, out + err
        assert "ok    committed clear-state TEAL" in out, out


@pytest.mark.parametrize(
    ("approval_len", "clear_len", "pages"),
    [(0, 0, 0), (2044, 4, 0), (2045, 4, 1), (4096, 0, 1), (4096, 1, 2), (8192, 0, 3)],
)
def test_required_extra_pages_is_the_minimum_that_fits(approval_len, clear_len, pages):
    mod = _load_verify_deployment()
    assert mod.required_extra_pages(bytes(approval_len), bytes(clear_len)) == pages
