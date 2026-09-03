"""Every document this repository cites must exist, or be declared absent on purpose.

WHY THIS FILE EXISTS
--------------------
On 2026-08-30 a sweep resolved every file citation in every markdown document against the
filesystem. Seven names were cited that exist nowhere — not in the repository and not on the
machine. Two of them mattered:

    third_party/falcon-det1024/PROVENANCE.md
        Cited `FALCON_PIN_BUMP_EVIDENCE_2026-08-11.md` twice: once as the evidence tree that a
        27-file SHA-256 cross-check was made against, and once as the record of why the Falcon pin
        must not be bumped. This is the constitution's §0 provenance record for vendored
        cryptographic source. An auditor asking to see that evidence would have got nothing.
        Also cited `FINDING_falcon-licensing_2026-08-11.md` for an open licensing question.

    TRELYAN_PROTOCOL_SPEC_v0.2.md §8 "Honesty ledger"
        Carried `- [x] Lifecycle policy drafted (GOVERNANCE_AND_LIFECYCLE_POLICY.md)`. The file
        does not exist, and AUDIT_READINESS.md had already established that while this ledger went
        on claiming otherwise. §6.3 of the same spec says key loss "MUST be disclosed to record
        holders", and nothing discloses it.

None of this was reachable by reading, because a citation looks the same whether or not it
resolves. So it is checked.

WHAT THIS DOES NOT DO
---------------------
It does not require every citation to be a valid relative path. Documents here legitimately refer
to files by bare name — `falcon.py`, `report.json`, `ci.yml` — and resolving those to a single
location would be guesswork. The check is deliberately weaker and harder to argue with: the
BASENAME must exist somewhere in the repository, or be listed in KNOWN_ABSENT with a reason.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

SKIP_DIRS = {
    ".git", ".venv", ".venv-contracts", ".venv-compile", "build", "__pycache__",
    ".pytest_cache", "node_modules", ".mypy_cache", ".ruff_cache", "target",
}

# Names that are cited and genuinely do not exist. Each needs a reason, because an entry here is a
# statement that the citation is intentional.
KNOWN_ABSENT: dict[str, str] = {
    # AUDIT_READINESS.md discusses these three in sentences that say they do not exist. Citing a
    # document in order to report its absence is exactly right, and must not be "fixed".
    "AUDITOR_HANDOFF.md": "cited by AUDIT_READINESS.md while reporting that it does not exist",
    "AUDIT_READINESS_PACK.md": "same; also referenced historically by contracts/RED_TEAM_REVIEW",
    "CELL_MINT_SPEC.md": "same; the mint semantics live in TRELYAN_PROTOCOL_SPEC_v0.2.md §4-§5",
    # Named as outstanding work, not as an existing document.
    "GOVERNANCE_AND_LIFECYCLE_POLICY.md": (
        "NOT WRITTEN and now named as such in both AUDIT_READINESS.md and the spec's honesty "
        "ledger. §6.3 requires key-loss irrecoverability to be disclosed to record holders and "
        "nothing does. This entry is a placeholder for real outstanding work, not a dismissal."
    ),
    # A planning document from the constant-time work, referenced by its methodology note.
    "PLAN_RD-AtoZ_2026-08-18.md": "R&D planning note, never in this repository",
    # Named by PROVENANCE.md in the notes recording that their citations were removed. Naming a
    # document in order to report its absence is the same legitimate pattern as above.
    "FALCON_PIN_BUMP_EVIDENCE_2026-08-11.md": (
        "cited by PROVENANCE.md until 2026-08-30 as the source of a 27-file cross-check and of "
        "the do-not-bump reasoning; replaced by an inline reason and a runnable sha256sum check"
    ),
    "FINDING_falcon-licensing_2026-08-11.md": (
        "cited by PROVENANCE.md for the upstream-licensing open item; the finding's whole "
        "substance was already inline, so the citation added nothing"
    ),
}

CITATION = re.compile(r"[`(\[]([A-Za-z0-9_][A-Za-z0-9_/.-]*\.(?:md|py|rs|sh|toml|json|teal|yml))[`)\]]")


def _keep(path: Path) -> bool:
    return not any(part in SKIP_DIRS for part in path.relative_to(REPO).parts)


def _present_basenames() -> set[str]:
    return {p.name for p in REPO.rglob("*") if p.is_file() and _keep(p)}


def _citations() -> dict[str, set[str]]:
    """basename -> the documents that cite it."""
    out: dict[str, set[str]] = {}
    for doc in REPO.rglob("*.md"):
        if not _keep(doc):
            continue
        text = doc.read_text(encoding="utf-8", errors="ignore")
        for raw in set(CITATION.findall(text)):
            if raw.startswith("http"):
                continue
            out.setdefault(raw.rsplit("/", 1)[-1], set()).add(
                doc.relative_to(REPO).as_posix()
            )
    return out


def test_the_sweep_finds_citations():
    """Without this, every assertion below is satisfied by a regex that matches nothing."""
    cites = _citations()
    assert len(cites) >= 50, (
        f"only {len(cites)} distinct documents cited; the scan is broken, not the repository"
    )


def test_every_cited_document_exists_or_is_declared_absent():
    present = _present_basenames()
    cites = _citations()
    phantom = {
        name: sorted(where)
        for name, where in cites.items()
        if name not in present and name not in KNOWN_ABSENT
    }
    assert not phantom, (
        "these documents are cited but exist nowhere in the repository:\n"
        + "\n".join(f"  {n}\n      cited in {', '.join(w)}" for n, w in sorted(phantom.items()))
        + "\n\nEither add the document, remove the citation, or add it to KNOWN_ABSENT with a "
        "reason. A citation that does not resolve reads exactly like one that does, which is how "
        "the Falcon provenance record came to rest on evidence nobody could produce."
    )


def test_known_absent_entries_are_still_absent():
    """A list of missing documents rots the moment one of them is written."""
    present = _present_basenames()
    resurrected = sorted(n for n in KNOWN_ABSENT if n in present)
    assert not resurrected, (
        f"these are listed as KNOWN_ABSENT but now exist: {resurrected}. Remove them from the "
        f"list, and check whether anything still describes them as missing."
    )


def test_the_provenance_record_does_not_rest_on_a_missing_document():
    """The §0 record for vendored cryptographic source is the one that must not be hand-wavy.

    It cited a locally-kept evidence tree for its 27-file cross-check. That tree is gone, so the
    citation was replaced with a command anyone can run: `sha256sum -c SHA256SUMS`.
    """
    prov = (REPO / "third_party" / "falcon-det1024" / "PROVENANCE.md").read_text(encoding="utf-8")

    # The name may appear — the file records that its citation was removed, and saying so is the
    # point. What must never happen is the name appearing as a SOURCE again. So every mention has
    # to sit next to a statement that it does not exist.
    needle = "FALCON_PIN_BUMP_EVIDENCE"
    at = 0
    while True:
        at = prov.find(needle, at)
        if at == -1:
            break
        window = prov[max(0, at - 400) : at + 400]
        assert "does not exist" in window, (
            "PROVENANCE.md mentions FALCON_PIN_BUMP_EVIDENCE_2026-08-11.md without saying it does "
            "not exist, which reads as a citation. This is the provenance record for vendored "
            "cryptographic source; it must not point at something an auditor cannot open. "
            f"context: ...{window.strip()[:300]}..."
        )
        at += len(needle)
    assert "sha256sum -c SHA256SUMS" in prov, (
        "PROVENANCE.md no longer tells a reader how to re-verify the vendored tree themselves"
    )

    # And the command must actually work: the digests file has to cover the tree.
    sums = (REPO / "third_party" / "falcon-det1024" / "SHA256SUMS").read_text(encoding="utf-8")
    listed = [ln.split("*", 1)[1].strip() for ln in sums.splitlines() if "*" in ln]
    assert len(listed) >= 20, f"SHA256SUMS lists only {len(listed)} files"
    missing = [f for f in listed if not (REPO / "third_party" / "falcon-det1024" / f).is_file()]
    assert not missing, (
        f"SHA256SUMS names files that are not in the vendored tree: {missing[:5]}. The cross-check "
        f"the provenance record points at would not run."
    )


def test_the_honesty_ledger_does_not_claim_an_unwritten_document():
    """It said `[x] Lifecycle policy drafted` and named a file that has never existed."""
    spec = (REPO / "TRELYAN_PROTOCOL_SPEC_v0.2.md").read_text(encoding="utf-8")
    for line in spec.splitlines():
        if "GOVERNANCE_AND_LIFECYCLE_POLICY" in line:
            assert not line.lstrip().startswith("- [x]"), (
                "the honesty ledger checks off the lifecycle policy while naming a file that does "
                f"not exist:\n    {line.strip()}"
            )
    assert "MUST be disclosed to record holders" in spec, (
        "the spec no longer says key-loss irrecoverability must be disclosed to holders. That "
        "requirement is what makes the unwritten policy a real gap rather than a tidy-up."
    )
