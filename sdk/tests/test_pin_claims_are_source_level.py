"""The Falcon pin is described by what go-algorand's SOURCE resolves, not by what nodes run.

WHY THIS FILE EXISTS
--------------------
Until 2026-09-14 third_party/falcon-det1024/PROVENANCE.md said `ce15e75b` is "the commit
go-algorand's release vendors" and "what the AVM falcon_verify opcode actually runs". Neither was
checked. What was checked is source: go-algorand's go.mod requires github.com/algorand/falcon
v0.1.0, that tag peels to ce15e75b, go.sum pins those bytes, and there is no vendor/ directory.
Which build any TestNet or MainNet node runs was not checked, and PROVENANCE.md now says so.

A review on 2026-09-17 found the same node-level wording in eight more files, by hand. It also
put the old sentence back into PROVENANCE.md and deleted the not-checked bullet: the whole SDK
suite still passed. This file makes that mutation fail.

WHAT THIS DOES NOT DO
---------------------
It matches the retired sentences, not their meaning, so a paraphrase gets through. It is a floor
under the 2026-09-14 and 2026-09-17 corrections, not a proof that no node-level claim exists.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

SKIP_DIRS = {
    ".git", ".venv", ".venv-contracts", ".venv-compile", "build", "__pycache__",
    ".pytest_cache", "node_modules", ".mypy_cache", ".ruff_cache", "target",
}
SUFFIXES = {".md", ".py", ".cc", ".rs", ".yml", ".yaml", ".toml", ".txt"}
VENDORED_SRC = REPO / "third_party" / "falcon-det1024" / "src"

# Each was in the tree and stated node-level execution as fact. Matched after normalisation
# (lower case, backticks dropped, line-leading `>` `//` `#` removed, whitespace collapsed), so a
# sentence re-wrapped across lines or moved into a comment still matches.
RETIRED = (
    "release vendors",
    "go-algorand vendors",
    "opcode actually runs",
    "falcon_verify opcode runs",
    "the release the algorand network itself runs",
    "the network's release",
    "the deployed on-chain verifier",
    "stricter than the deployed verifier",
    "matching what the chain runs",
    "testnet acceptance runs the same pinned",
    "the same algorand/falcon@ce15e75b code this repo pins",
)

# The two records of the pin must keep saying what was NOT checked.
PIN_RECORDS = ("third_party/falcon-det1024/PROVENANCE.md", "PINNED_BUILD.md")

_LEADER = re.compile(r"^\s*(?:>|//+|#+)?\s*", re.MULTILINE)


def _normalise(text: str) -> str:
    return " ".join(_LEADER.sub("", text).replace("`", "").lower().split())


def _files() -> list[Path]:
    this = Path(__file__).resolve()
    out = []
    for p in REPO.rglob("*"):
        if not p.is_file() or p.suffix not in SUFFIXES or p.resolve() == this:
            continue
        rel = p.relative_to(REPO)
        if any(part in SKIP_DIRS for part in rel.parts) or VENDORED_SRC in p.parents:
            continue
        out.append(p)
    return out


def test_the_normaliser_matches_a_rewrapped_comment():
    """Without this, every phrase below could be defeated by a line break."""
    wrapped = "// This is the SAME code path Algorand's native `falcon_verify`\n//   opcode runs on-chain"
    assert "falcon_verify opcode runs" in _normalise(wrapped)
    quoted = "> **This pin is deliberate: it is the release the Algorand network\n> itself runs.**"
    assert "the release the algorand network itself runs" in _normalise(quoted)


def test_no_file_restates_a_retired_node_level_claim():
    files = _files()
    assert len(files) >= 100, f"only {len(files)} files scanned; the walk is broken"
    hits = []
    for p in files:
        body = _normalise(p.read_text(encoding="utf-8", errors="ignore"))
        hits += [f"{p.relative_to(REPO).as_posix()}: {phrase!r}" for phrase in RETIRED if phrase in body]
    assert not hits, (
        "these files state which Falcon code running nodes execute, which nobody checked:\n  "
        + "\n  ".join(sorted(hits))
        + "\nSay what was checked instead: go-algorand's go.mod/go.sum resolve the module its "
        "falcon_verify opcode calls to ce15e75b (third_party/falcon-det1024/PROVENANCE.md)."
    )


def test_the_pin_records_say_node_builds_were_not_checked():
    for rel in PIN_RECORDS:
        body = _normalise((REPO / rel).read_text(encoding="utf-8"))
        windows = [
            body[max(0, m.start() - 200) : m.end() + 200]
            for m in re.finditer(r"not checked", body)
        ]
        assert any("node runs" in w for w in windows), (
            f"{rel} no longer says which build any TestNet or MainNet node runs is not checked. "
            "Every fact it gives about the pin is about source; without that sentence a reader "
            "takes it as a statement about the chain."
        )
