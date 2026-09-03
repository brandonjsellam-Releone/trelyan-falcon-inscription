"""Every mention of the TestNet app id is either a LIVE CLAIM or FROZEN EVIDENCE, and this says which.

WHY THIS FILE EXISTS
--------------------
`contracts/verify_deployment.py` reports DRIFT: live app 763809096 serves bytecode that predates
the committed contract. The fix is a redeploy — and a redeploy issues a **new** app id, because
the contract blocks Update and Delete (invariants I1/I5), so 763809096 cannot be patched in place.

The app id is written down in roughly two dozen places. Retargeting them is mechanical, and that
is exactly the problem: `sed -i s/763809096/<new>/g` over the repository is the obvious move and it
is **wrong**, because two of those places are not claims about the current deployment at all.

    sdk/tests/vectors/det1024_kat.json
        Each vector's `app_id` is encoded into `message_hex` as `000000002d86cd48`, and the golden
        `sig_hex` is a signature OVER that message. The vectors exist to prove a freshly built
        Falcon library reproduces known bytes; they are not about any deployment.

    sdk/tests/test_build_message_differential.py
        `_LIVE_M_HEX` is the exact message the chain accepted, read out of the live inscription
        record. Its own comment says it: "it is not what either implementation says M should be,
        it is what the chain took." It is a historical observation.

Both would break LOUDLY under a blanket retarget, which is good. The danger is the response: the
natural way to make a red KAT green again is to regenerate the vectors, and regenerating them
destroys the byte-identity reference the whole signature gate rests on. A green suite would then
prove only that the signer agrees with itself.

So this test states the partition, and fails on a reference belonging to neither side — because
the reference nobody classified is the one that gets retargeted by accident.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# The id the live deployment had when this partition was written. FROZEN references must keep
# saying this forever; it is the subject of a signature and of a historical observation.
HISTORICAL_APP_ID = 763809096

# Directories that are not source: virtualenvs, build output, git internals, caches.
SKIP_DIRS = {
    ".git", ".venv", ".venv-contracts", "build", "__pycache__", ".pytest_cache",
    "node_modules", ".mypy_cache", ".ruff_cache", "target", "out", ".venv-compile",
}

TEXT_SUFFIXES = {".py", ".md", ".yml", ".yaml", ".toml", ".json", ".rs", ".txt", ".sh", ".ps1"}

# Files whose app-id mentions are FROZEN EVIDENCE. Never retarget these.
FROZEN = {
    "sdk/tests/vectors/det1024_kat.json",
    "sdk/tests/test_build_message_differential.py",
    # The KAT GENERATOR. Its app id is baked into every vector's signed message, so changing it
    # and re-running produces a wholly different golden set. Its own comment called the value
    # "not load-bearing", which is the opposite of true and was corrected on 2026-08-30.
    "sdk/tests/vectors/gen_det1024_kat.py",
    # This file: it names the historical id in order to talk about it.
    "sdk/tests/test_app_id_references_are_coherent.py",
    # Synthetic fixture, not a live claim. It calls print_awaiting_redeploy() with hardcoded
    # arguments to lock the drift banner's TEXT, so a later edit cannot turn a mismatch into a
    # silent skip. Kept after the 2026-09-03 redeploy precisely as a regression guard: if drift
    # ever recurs the banner must still name the app and both sizes.
    "sdk/tests/test_testnet_drift_banner.py",
    # The record of the drift that was closed on 2026-09-03. It must keep quoting the measured
    # 660 B / d24d9071 and 709 B / 6fa5cee1 values -- test_testnet_drift_banner.py asserts they
    # are still there -- so its app id is a historical observation, not a live claim.
    "BLOCKERS.md",
    # A dated validation record. It says what was true on 2026-06-01 and must not be rewritten.
    "LOCALNET_VALIDATION_2026-06-01.md",
}

# Files whose app-id mentions are LIVE CLAIMS. These must agree with the deployment under test,
# and every one of them has to be updated in the same commit as a redeploy.
LIVE_CLAIM = {
    "contracts/verify_deployment.py",
    "sdk/examples/verify_trelyan.py",
    "sdk/tests/test_isolated_signer.py",
    "sdk/tests/test_seal.py",
    "sdk/tests/test_interop_algo_pqc_kit_kat.py",
    "README.md",
    "REVIEWER.md",
    "ROADMAP.md",
    "AUDIT_READINESS.md",
    "sdk/docs/DEMO.md",
    "sdk/docs/tutorials/01-quickstart.md",
    "sdk/docs/tutorials/04-end-to-end-inscribe-verify.md",
    ".github/workflows/ci.yml",
    "scripts/verify_all.sh",
    "CONTRIBUTING.md",
    ".github/workflows/testnet-followup.yml",
    ".github/workflows/testnet-redeploy.yml",
}

# An Algorand TestNet application id: 9 digits in the 7xxxxxxxx range.
#
# The lookarounds are not decoration. `\b7\d{8}\b` matched `726415094` inside the float
# `7968333.726415094` in four constant-time evidence reports, and reported them as unclassified
# app-id references. A digit or a decimal point on either side means this is part of a longer
# number, not an application id.
APP_ID_RE = re.compile(r"(?<![\d.])(7\d{8})(?![\d.])")


def _source_files() -> list[Path]:
    out: list[Path] = []
    for path in REPO.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(REPO).parts):
            continue
        out.append(path)
    return out


def _mentions() -> dict[str, set[int]]:
    """Relative path -> the set of app-id-shaped numbers it mentions."""
    found: dict[str, set[int]] = {}
    for path in _source_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        ids = {int(m) for m in APP_ID_RE.findall(text)}
        # The asset id sits one or two above the app id and is not an application. Drop anything
        # that is not either the historical app id or the id under test.
        if ids:
            found[path.relative_to(REPO).as_posix()] = ids
    return found


def _deployment_app_id() -> int:
    src = (REPO / "contracts" / "verify_deployment.py").read_text(encoding="utf-8")
    m = re.search(r"^DEFAULT_APP_ID\s*=\s*(\d+)", src, re.MULTILINE)
    assert m, "contracts/verify_deployment.py no longer declares DEFAULT_APP_ID"
    return int(m.group(1))


def test_the_scan_finds_something():
    """Without this, every assertion below is satisfied by a regex that matches nothing."""
    mentions = _mentions()
    assert len(mentions) >= 10, (
        f"only {len(mentions)} files mention an app id; the scan is broken, not the repository"
    )


def test_every_app_id_mention_is_classified():
    """A reference in neither set is the one a blanket retarget silently gets wrong."""
    unclassified = sorted(set(_mentions()) - FROZEN - LIVE_CLAIM)
    assert not unclassified, (
        "these files mention an application id and are in neither FROZEN nor LIVE_CLAIM:\n  "
        + "\n  ".join(unclassified)
        + "\n\nDecide which it is. A LIVE CLAIM describes the current deployment and must be "
        "updated when the app is redeployed. FROZEN EVIDENCE is a signature input or a record of "
        "what the chain did, and must never be updated — see this file's docstring."
    )


def test_live_claims_all_name_the_same_deployment():
    """A half-finished retarget leaves docs and tests disagreeing about which app is real."""
    expected = _deployment_app_id()
    mentions = _mentions()
    disagreeing = {
        rel: sorted(ids)
        for rel, ids in mentions.items()
        if rel in LIVE_CLAIM and ids != {expected} and expected not in ids
    }
    assert not disagreeing, (
        f"these files claim to describe the live deployment but do not mention app {expected}, "
        f"which is what contracts/verify_deployment.py targets:\n"
        + "\n".join(f"  {rel}: {ids}" for rel, ids in sorted(disagreeing.items()))
        + "\n\nA redeploy updates all of them in one commit."
    )


def test_the_kat_vectors_still_sign_the_historical_app_id():
    """The goldens are a signature reference, not a description of a deployment.

    If a redeploy ever makes this fail, the correct response is to REVERT the change to the
    vectors — never to regenerate them. Regenerating produces vectors that agree with whatever
    signer produced them, which is exactly the property the KAT exists to disprove.
    """
    fixture = json.loads(
        (REPO / "sdk" / "tests" / "vectors" / "det1024_kat.json").read_text(encoding="utf-8")
    )
    vectors = fixture.get("vectors") or []
    assert vectors, "the KAT fixture has no vectors; this test would pass vacuously"

    for v in vectors:
        assert v["app_id"] == HISTORICAL_APP_ID, (
            f"vector {v['name']!r} was retargeted to app {v['app_id']}. The app id is encoded "
            f"inside message_hex and the golden signature signs it, so this vector no longer "
            f"matches its own signature. REVERT this — do not regenerate the goldens."
        )
        # And the id really is inside the signed message, so the claim above is not folklore.
        assert f"{HISTORICAL_APP_ID:016x}" in v["message_hex"], (
            f"vector {v['name']!r}: app id {HISTORICAL_APP_ID} is not encoded in message_hex, so "
            f"the layout changed and this test's reasoning no longer holds"
        )


def test_the_live_message_anchor_is_what_the_chain_took():
    """`_LIVE_M_HEX` records an observation. Retargeting it would falsify a record."""
    src = (REPO / "sdk" / "tests" / "test_build_message_differential.py").read_text(
        encoding="utf-8"
    )
    m = re.search(r"^_LIVE_APP_ID\s*=\s*(\d+)", src, re.MULTILINE)
    assert m, "test_build_message_differential.py no longer declares _LIVE_APP_ID"
    assert int(m.group(1)) == HISTORICAL_APP_ID, (
        f"_LIVE_APP_ID was changed to {m.group(1)}. It is not a configuration value: it names the "
        f"app whose on-chain record _LIVE_M_HEX was read from. Changing it makes the file assert "
        f"that a different application accepted a message it never saw."
    )
    assert f"{HISTORICAL_APP_ID:016x}" in src, (
        "the big-endian app id no longer appears in this file's _LIVE_M_HEX, so the anchor and "
        "the constant have drifted apart"
    )


@pytest.mark.parametrize("rel", sorted(FROZEN | LIVE_CLAIM))
def test_every_classified_file_still_exists(rel: str):
    """A classification list that names files nobody has is a list that has stopped being read."""
    assert (REPO / rel).is_file(), (
        f"{rel} is classified in this file but does not exist. Prune it in the same commit that "
        f"removed it, so the partition does not rot into a description of a repository that was."
    )


def test_the_kat_generator_still_targets_the_historical_app_id():
    """The generator and the goldens must agree, or a regeneration silently rewrites every vector.

    `gen_det1024_kat.py` documented its app id as "not load-bearing - just a fixed, realistic
    value". It is load-bearing: `build_message` encodes it into the message each golden signature
    signs. Someone reading that comment would have felt free to change it, regenerate, and replace
    the entire byte-identity reference without anything objecting.
    """
    src = (REPO / "sdk" / "tests" / "vectors" / "gen_det1024_kat.py").read_text(encoding="utf-8")
    m = re.search(r"^APP_ID\s*=\s*(\d+)", src, re.MULTILINE)
    assert m, "gen_det1024_kat.py no longer declares APP_ID"
    assert int(m.group(1)) == HISTORICAL_APP_ID, (
        f"the KAT generator targets app {m.group(1)} while the committed vectors were produced "
        f"for {HISTORICAL_APP_ID}. Re-running it now would replace every golden signature. If a "
        f"regeneration is genuinely intended, the byte-identity claim is being reset and that is "
        f"a decision to record, not a side effect."
    )
    assert "not load-bearing" not in src, (
        "gen_det1024_kat.py has gone back to describing its app id as not load-bearing. It is "
        "encoded into every message the goldens sign."
    )
