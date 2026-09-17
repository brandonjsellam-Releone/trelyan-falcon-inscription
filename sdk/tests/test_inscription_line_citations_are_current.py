"""Every line-number citation into `inscription.py` still points at the construct its sentence names.

WHY THIS FILE EXISTS
--------------------
AUDIT_READINESS.md is the scope sheet an external auditor starts from, and its invariant table
maps each of I1-I5 / C1-C5 to a line range in `contracts/inscription.py`. Before PR #47 the sheet
said those ranges were against the file "as of 2026-06-17". The contract changed after that date
(last in `205d874`, 2026-08-27) and nothing noticed, so the ranges pointed at other code. Two
examples, checked against the file at `205d874`: `(≈L288)` was offered as the `falcon_verify`
call and is the write-once assert; `(≈L353–356)` was offered as `on_delete` and is a comment
inside `update_owner`. PR #47 (merged 2026-09-14) re-pointed the citations to `205d874`.

PR #47 verified its re-pointing with a one-off script. A one-off script protects exactly one
commit. This file is that check, kept in the suite.

Writing the table turned up a stale citation outside AUDIT_READINESS.md: CONTRIBUTING.md,
THREAT_MODEL_AND_TRACEABILITY.md and contracts/verify_teal_matches_source.py said the committed
TEAL carries `// inscription.py:156`. `contracts/out/` stopped carrying that comment when it was
regenerated on 2026-08-27 (`14515d4`), and line 156 of the contract is blank. Those sentences give
the comment's FORM, not a line, so they now say `NNN`, the placeholder the verifier's docstring
already used for the same comment.

WHAT IS CHECKED
---------------
1. Every citation of an `inscription.py` line number, in every form the repository uses, is
   extracted from every text file that names `inscription.py`:
       `contracts/inscription.py:404-412`      path:N and path:N-M
       `_build_message` from `:319`            a bare :N in a file that also has a path:N
       (L288)  (L409–412)  (≈L71-73)           L-numbers, hyphen or en dash
       (C4, line ~194)  Lines 71–79, 100, 207  the word "line", including lists
2. Each one must match exactly one row of LIVE or UNCHECKED, by document, line span, and a quote
   from the citing sentence. A citation with no row fails. A row with no citation fails.
3. For every LIVE row, each of its needles (exact substrings of the target file) must appear
   within the cited line or range. The needles were chosen by reading the sentence: they are the
   construct the sentence names (the assert, the method, the binding), not a token that happens
   to be nearby. Presence alone would let a citation pass on ANOTHER copy of its needle, so a
   single-line row's needle must occur on exactly one line of its target, or the row names which
   occurrence it means and how many there are (`occurrence=(n, of)`, counted from the top), the
   target must hold exactly `of` and the cited line must be the n-th; and a range row must hold
   at least one needle that occurs on exactly one line of its target. Every single-line row fails when its target moves by one line in either
   direction, and every range row fails in at least one direction (a needle sits on its first or
   last line); test_the_check_fails_when_the_contract_moves_by_one_line holds the table to that.
4. AUDIT_READINESS.md says its line numbers are against `contracts/inscription.py` at a named
   commit. The file must still be the blob that commit holds, so the banner cannot go stale
   while every needle happens to survive.
5. The extracted count is non-zero, includes AUDIT_READINESS.md, and equals the table size.

The checks are themselves mutation-tested in this file: a contract whose functions move, a
citation nobody reviewed, a citation that was deleted, another copy of a needle landing on a
cited line, a range whose needles all occur elsewhere too, and an exemption planted in a live
document each make the real test functions above fail (the functions are re-run against
monkeypatched inputs, not re-implemented).

WHAT IS NOT CHECKED
-------------------
* `contracts/out/` is not scanned. Its `// inscription.py:N` comments are emitted by puya, and
  `contracts/verify_teal_matches_source.py` compares all five artifacts against a fresh compile
  in CI, so they cannot drift without that job failing.
* L-numbers and "line N" are only recognised in files that name `inscription.py` somewhere. A
  document that cited `(L304)` without ever naming the file would not be seen.
* A range can move by less than its slack on its un-anchored edge and still pass, because its
  unique needle is still inside the cited span; its other needles may also occur elsewhere. A
  single-line citation cannot move by any number of lines and still pass: its needle occurs on
  one line of the target, or the target holds exactly the number of copies the row names and the
  cited line is the n-th. Copies of a needle that swap places are not detected.
* UNCHECKED rows are reviewed classifications, not checks. Every UNCHECKED row, of either kind,
  must sit in a document whose filename carries a date (`*_YYYY-MM-DD.md`), so this list cannot
  exempt a citation in a live document such as AUDIT_READINESS.md. Whether a row in a dated
  document is classified correctly is a matter of review.
* CI does not run this file when a change touches only root-level documents. The push and
  pull_request path filters in `.github/workflows/ci.yml` name sdk/, contracts/, third_party/,
  scripts/, the two Dockerfiles, ci.yml itself and BLOCKERS.md, so a change confined to root
  documents such as AUDIT_READINESS.md, README.md, REVIEWER.md, CONTRIBUTING.md or
  THREAT_MODEL_AND_TRACEABILITY.md triggers no job; and the two jobs that run `pytest tests`
  (wire-format, signature-kat) skip the Monday schedule. A wrong citation added in such a change
  first fails on the next change that does trigger CI. test_cited_documents_exist.py and
  test_app_id_references_are_coherent.py share the gap.

RELATION TO test_cited_documents_exist.py
-----------------------------------------
That test proves a cited document EXISTS, by basename, and only scans markdown. Its pattern needs
a closing backtick, parenthesis or bracket right after the extension, so
`contracts/inscription.py:297` is not one of its citations; this file covers those, and a
path-qualified citation must name the file its row checks. Both walk the same tree: REPO and SKIP_DIRS are identical, and
test_the_scan_skips_what_the_cited_documents_sweep_skips holds them to that.
"""

from __future__ import annotations

import ast
import hashlib
import re
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import NamedTuple

import pytest

REPO = Path(__file__).resolve().parents[2]
THIS_FILE = Path(__file__).resolve().relative_to(REPO).as_posix()

CONTRACT = "contracts/inscription.py"
SDK_CLIENT = "sdk/src/trelyan_pq/inscription.py"
TARGETS = (CONTRACT, SDK_CLIENT)

SKIP_DIRS = {
    ".git", ".venv", ".venv-contracts", ".venv-compile", "build", "__pycache__",
    ".pytest_cache", "node_modules", ".mypy_cache", ".ruff_cache", "target",
}
TEXT_SUFFIXES = {".py", ".md", ".yml", ".yaml", ".toml", ".json", ".rs", ".txt", ".sh", ".ps1"}
# Compiler output; see "WHAT IS NOT CHECKED" in the module docstring.
SKIP_PREFIXES = ("contracts/out/",)


# ---------------------------------------------------------------------------------------------
# The reviewed table
# ---------------------------------------------------------------------------------------------

class Live(NamedTuple):
    """A citation that must still point at `needles` inside `target`, lines `lines`."""

    doc: str
    lines: str            # "288" or "409-412"
    quote: str            # from the citing line (or the line before it, for a wrapped sentence)
    target: str
    needles: tuple[str, ...]
    # Single-line rows only, and required when the needle occurs on more than one line of the
    # target: (n, of) = the sentence means the n-th, counted from the top, of exactly `of` lines
    # holding the needle. See stale().
    occurrence: tuple[int, int] | None = None


class Unchecked(NamedTuple):
    """A citation-shaped token that is deliberately not checked against the current file."""

    doc: str
    lines: str
    quote: str
    kind: str             # "dated" | "not-a-contract-line"
    why: str


_AR = "AUDIT_READINESS.md"

# Needle constants shared by several rows, so one construct is spelled one way.
_WRITE_ONCE = 'assert cid not in self.inscriptions, "cell already inscribed"'
_FALCON_VERIFY = "assert op.falcon_verify(m, falcon_sig.native, pubkey)"
_ENSURE_BUDGET = "ensure_budget(UInt64(2100), fee_source=OpUpFeeSource.GroupCredit)"
_REGISTER_ONCE = (
    'assert cid not in self.committed_pubkey, "cell already registered"',
    'assert cid not in self.controlling_owner, "cell already registered (owner)"',
)
_ON_UPDATE_AND_ON_DELETE = (
    'allow_actions=["UpdateApplication"]',
    "def on_update(self)",
    'assert False, "contract is non-upgradable (I5)"',
    'allow_actions=["DeleteApplication"]',
    "def on_delete(self)",
    'assert False, "contract is non-deletable (I1/I5)"',
)
_FREEZE_GUARD = 'assert cell.freeze == Global.zero_address, "cell must have no freeze"'

LIVE: tuple[Live, ...] = (
    # --- AUDIT_READINESS.md §2.1, the invariant table -------------------------------------------
    Live(_AR, "288", "`inscribe` C2 `assert cid not in self.inscriptions` (L288)",
         CONTRACT, (_WRITE_ONCE,)),
    Live(_AR, "409-412", "`on_delete` = `assert False` (L409–412)",
         CONTRACT, ('allow_actions=["DeleteApplication"]', "def on_delete(self)",
                    'assert False, "contract is non-deletable (I1/I5)"')),
    # "M binds app, cell, artifact, network": one needle per binding, plus the method itself.
    Live(_AR, "318-327", "M binds app, cell, artifact, network | `_build_message` (L318–327)",
         CONTRACT, ("@subroutine", "def _build_message(", "DOMAIN_TAG",
                    "op.itob(Global.current_application_id.id)", "op.itob(cell_id)",
                    "+ artifact_hash", "+ Global.genesis_hash")),
    Live(_AR, "391-398", "`get_inscription` (L391–398)",
         CONTRACT, ("@arc4.abimethod(readonly=True)", "def get_inscription(",
                    "return self.inscriptions[cell_id.native]")),
    Live(_AR, "239", "`register_cell` writes `committed_pubkey[cid]` once (L239)",
         CONTRACT, ("self.committed_pubkey[cid] = committed_pubkey.native",)),
    Live(_AR, "235-236", "register-once asserts (L235–236)",
         CONTRACT, _REGISTER_ONCE),
    Live(_AR, "404-412", "`on_update` / `on_delete` = `assert False` (L404–412)",
         CONTRACT, _ON_UPDATE_AND_ON_DELETE),
    # "`AssetHoldingGet` balance==1 **and** `controlling_owner[cid] == Txn.sender`"
    Live(_AR, "282-285", "`inscribe` C1 (L282–285)",
         CONTRACT, ("op.AssetHoldingGet.asset_balance(Txn.sender, cell)",
                    'balance == UInt64(1), "sender does not hold the cell"',
                    'self.controlling_owner[cid] == Txn.sender.bytes, "sender not controlling owner"')),
    Live(_AR, "288", "Single-use / write-once | `inscribe` C2 (L288)",
         CONTRACT, (_WRITE_ONCE,)),
    # "read from `Global.current_application_id` + `Global.genesis_hash`"
    Live(_AR, "318-327",
         "`_build_message` (L318–327), read from `Global.current_application_id` + `Global.genesis_hash`",
         CONTRACT, ("@subroutine", "def _build_message(", "Global.current_application_id",
                    "Global.genesis_hash")),
    Live(_AR, "304", "`inscribe` (L304): `op.falcon_verify(m, falcon_sig.native, pubkey)`",
         CONTRACT, (_FALCON_VERIFY,)),
    Live(_AR, "294", "`inscribe` reads `committed_pubkey[cid]` (L294)",
         CONTRACT, ("pubkey = self.committed_pubkey[cid]",)),
    # --- AUDIT_READINESS.md §2.2: the contract calls falcon_verify correctly ----------------------
    Live(_AR, "304", "asserted (not ignored). Evidence: `contracts/inscription.py` (L304)",
         CONTRACT, (_FALCON_VERIFY,)),
    # --- §2.4: length and header byte validated where a key enters state ------------------------
    Live(_AR, "221", "are validated at the **only** point a key enters state (L221, L226)",
         CONTRACT, ('committed_pubkey.native.length == PUBKEY_LEN, "bad committed pubkey length"',)),
    Live(_AR, "226", "are validated at the **only** point a key enters state (L221, L226)",
         CONTRACT, ("op.getbyte(committed_pubkey.native, UInt64(0)) == UInt64(0x0A)",)),
    # --- §2.5: the opcode budget ---------------------------------------------------------------
    Live(_AR, "302", f"`{_ENSURE_BUDGET}` (L302), placed **after** the cheap",
         CONTRACT, (_ENSURE_BUDGET,)),
    Live(_AR, "299-304", "Evidence: `contracts/inscription.py` (L299–304)",
         CONTRACT, ("ensure opcode budget for falcon_verify", _ENSURE_BUDGET, _FALCON_VERIFY)),
    # --- §2.6: box-storage authorization -------------------------------------------------------
    Live(_AR, "235-236", "register-once (`cid not in committed_pubkey / controlling_owner`, L235–236)",
         CONTRACT, _REGISTER_ONCE),
    Live(_AR, "288", "write-once (L288)",
         CONTRACT, (_WRITE_ONCE,)),
    Live(_AR, "208", "admin-only `register_cell` (L208)",
         CONTRACT, ('assert Txn.sender == self.admin, "only admin may register cells"',)),
    Live(_AR, "210-218", "the pure-NFT / no-clawback / no-freeze / no-manager binding (L210–218)",
         CONTRACT, ('"cell must be a pure NFT"', '"cell must have no clawback"',
                    '"cell must have no freeze"', '"cell manager must be cleared (immutable config)"')),
    Live(_AR, "333-385",
         "`update_owner` authorization (current owner only, pre-inscription, L333–385)",
         CONTRACT, ("def update_owner(", '"only controlling owner"',
                    '"already inscribed; owner frozen"', "self.controlling_owner[cid] = new_owner.bytes")),

    # --- README.md: I5 is enforced by the contract ---------------------------------------------
    Live("README.md", "404-412",
         "makes `on_update` and `on_delete` reject unconditionally (`contracts/inscription.py:404-412`)",
         CONTRACT, _ON_UPDATE_AND_ON_DELETE),

    # --- REVIEWER.md: the trust-surface table --------------------------------------------------
    # "On-chain M is rebuilt from chain state ... never from caller args": :297 is the call.
    Live("REVIEWER.md", "297", "`contracts/inscription.py:297` (call)",
         CONTRACT, ("m = self._build_message(cid, art)",)),
    Live("REVIEWER.md", "319", "`_build_message` from `:319`",
         CONTRACT, ("def _build_message(self, cell_id: UInt64, artifact_hash: Bytes) -> Bytes:",)),
    Live("REVIEWER.md", "304", "`contracts/inscription.py:304`; `SECURITY.md`",
         CONTRACT, (_FALCON_VERIFY,)),

    # --- contracts/test_inscription.py docstrings: the three register_cell guards ---------------
    Live("contracts/test_inscription.py", "217", "The freeze guard (inscription.py:217)",
         CONTRACT, (_FREEZE_GUARD,)),
    Live("contracts/test_inscription.py", "216", "so it trips :216 and :217 is never evaluated",
         CONTRACT, ('assert cell.clawback == Global.zero_address, "cell must have no clawback"',)),
    Live("contracts/test_inscription.py", "217", "so it trips :216 and :217 is never evaluated",
         CONTRACT, (_FREEZE_GUARD,)),
    Live("contracts/test_inscription.py", "218", "The manager guard (inscription.py:218)",
         CONTRACT, ('assert cell.manager == Global.zero_address, "cell manager must be cleared',)),

    # --- contracts/FALCON_BUDGET_2026-06-01.md: its 2026-08-15 correction quotes AUDIT-NOTE A9 --
    Live("contracts/FALCON_BUDGET_2026-06-01.md", "71-73",
         "`contracts/inscription.py` (≈L71-73) records the change",
         CONTRACT, ('the prior C5 "reveal pubkey', 'and check sha512_256(pubkey)==committed_hash" is removed',
                    "a security property")),

    # --- The SDK client, sdk/src/trelyan_pq/inscription.py. Same basename, different file: the ----
    # --- sentences are about TrelyanInscriptionClient.inscribe(), not the contract. ---------------
    Live("THREAT_MODEL_AND_TRACEABILITY.md", "137",
         "`TrelyanInscriptionClient.inscribe()` signs internally (`inscription.py:137`)",
         SDK_CLIENT, ("sig = self.signer.sign(privkey, m)",)),
    # "the fallback at :182 re-sends the same `args` tuple rather than re-signing". The client has
    # two `self.app.send.inscribe(` calls: the first attempt, then the fallback this names.
    Live("THREAT_MODEL_AND_TRACEABILITY.md", "182",
         "the fallback at `inscription.py:182` re-sends the same `args` tuple",
         SDK_CLIENT, ("self.app.send.inscribe(",), occurrence=(2, 2)),
    Live("sdk/examples/interop_algo_pqc_kit.py", "136-137",
         "re-derives M and re-signs internally (inscription.py:136-137)",
         SDK_CLIENT, ("m = build_message(self.app_id, cell_id, artifact_hash",
                      "sig = self.signer.sign(privkey, m)")),
    Live("sdk/tests/test_examples_call_sites.py", "136-137",
         "re-derives M and re-signs internally (inscription.py:136-137)",
         SDK_CLIENT, ("m = build_message(self.app_id, cell_id, artifact_hash",
                      "sig = self.signer.sign(privkey, m)")),
)

_DATED_DRAFT = (
    "a 2026-06-01 record written against the pre-compile draft of the contract. It quotes calls "
    "the contract no longer makes in that form (`op.falcon_verify(m, falcon_sig.bytes, pubkey)`; "
    "COMPILE_REVIEW also `asset_balance(Txn.sender, cid)`), so its numbers describe that draft; "
    "RED_TEAM_REVIEW_2026-06-01.md item N1 already records them as stale. Re-pointing them would "
    "attribute a review of old code to the current file."
)
_FINDING_ID = "a finding identifier from the 2026-06-01 red-team table (L = LOW), not a line number"
_WEBSITE = "a line of the website page named in the same phrase, not of inscription.py"

UNCHECKED: tuple[Unchecked, ...] = (
    Unchecked("contracts/A1_RESOLUTION_2026-06-01.md", "194", "`inscription.py` (C4, line ~194)",
              "dated", _DATED_DRAFT),
    Unchecked("contracts/COMPILE_REVIEW_2026-06-01.md", "180", "**Line ~180:**", "dated", _DATED_DRAFT),
    Unchecked("contracts/COMPILE_REVIEW_2026-06-01.md", "98-102", "**Lines 98–102, 142–143, 182–183:**",
              "dated", _DATED_DRAFT),
    Unchecked("contracts/COMPILE_REVIEW_2026-06-01.md", "142-143", "**Lines 98–102, 142–143, 182–183:**",
              "dated", _DATED_DRAFT),
    Unchecked("contracts/COMPILE_REVIEW_2026-06-01.md", "182-183", "**Lines 98–102, 142–143, 182–183:**",
              "dated", _DATED_DRAFT),
    Unchecked("contracts/COMPILE_REVIEW_2026-06-01.md", "194", "**Line ~194:**", "dated", _DATED_DRAFT),
    Unchecked("contracts/COMPILE_REVIEW_2026-06-01.md", "203", "**Lines 203, 214:**", "dated", _DATED_DRAFT),
    Unchecked("contracts/COMPILE_REVIEW_2026-06-01.md", "214", "**Lines 203, 214:**", "dated", _DATED_DRAFT),
    Unchecked("contracts/COMPILE_REVIEW_2026-06-01.md", "204", "**Line 204:**", "dated", _DATED_DRAFT),
    Unchecked("contracts/COMPILE_REVIEW_2026-06-01.md", "71-79", "**Lines 71–79, 100, 207:**",
              "dated", _DATED_DRAFT),
    Unchecked("contracts/COMPILE_REVIEW_2026-06-01.md", "100", "**Lines 71–79, 100, 207:**",
              "dated", _DATED_DRAFT),
    Unchecked("contracts/COMPILE_REVIEW_2026-06-01.md", "207", "**Lines 71–79, 100, 207:**",
              "dated", _DATED_DRAFT),
    Unchecked("contracts/FALCON_BUDGET_2026-06-01.md", "1", "(pre-audit review L1)",
              "not-a-contract-line", _FINDING_ID),
    Unchecked("contracts/RED_TEAM_REVIEW_2026-06-01.md", "1", "| L1 | LOW |",
              "not-a-contract-line", _FINDING_ID),
    Unchecked("contracts/RED_TEAM_REVIEW_2026-06-01.md", "2", "| L2 | LOW |",
              "not-a-contract-line", _FINDING_ID),
    Unchecked("contracts/RED_TEAM_REVIEW_2026-06-01.md", "3", "| L3 | LOW |",
              "not-a-contract-line", _FINDING_ID),
    Unchecked("PUBLIC_CLAIMS_HARDENING_2026-06-01.md", "172", "(status.html line 172)",
              "not-a-contract-line", _WEBSITE),
    Unchecked("PUBLIC_CLAIMS_HARDENING_2026-06-01.md", "106", "**read.html line 106:**",
              "not-a-contract-line", _WEBSITE),
)

# AUDIT_READINESS.md §2 names the commit its line numbers are against. Map that commit to the git
# blob id of contracts/inscription.py there (`git rev-parse 205d874:contracts/inscription.py`).
# When the contract changes: re-verify every LIVE row, update the banner, then add the new pair.
CONTRACT_BLOB_AT: dict[str, str] = {
    "205d874": "44ec1e7555638048cd9d9997d398e496d76dadde",
}
BANNER = re.compile(r"Line numbers are against `contracts/inscription\.py` at `([0-9a-f]{7,40})`")


# ---------------------------------------------------------------------------------------------
# Extraction
# ---------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Citation:
    doc: str
    line: int             # 1-based line in `doc`
    lines: str            # normalised span: "288" or "409-412"
    written: str          # the token as written, for messages
    path: str | None      # the path written before ":N", when there is one
    window: str           # the citing line and the one before it, whitespace collapsed

    def where(self) -> str:
        return f"{self.doc}:{self.line}: {self.written!r}"


_DASH = r"\s*[-–]\s*"
MENTION = re.compile(r"(?<![\w.-])(?:[\w.-]+/)*inscription\.py(?!\w)")
PATH_FORM = re.compile(rf"(?<![\w.-])(?P<path>(?:[\w.-]+/)*inscription\.py):(?P<a>\d+)(?:{_DASH}(?P<b>\d+))?")
BARE_FORM = re.compile(r"(?<=[\s`(]):(?P<a>\d+)(?:[-–](?P<b>\d+))?(?![\w:])")
L_FORM = re.compile(rf"(?<!\w)[≈~]?L(?P<a>\d+)(?:{_DASH}L?(?P<b>\d+))?(?!\w)")
LINE_WORD_FORM = re.compile(
    r"(?<![\w.])[Ll]ines?\s+(?P<items>[≈~]?\s*\d+(?:\s*[-–]\s*\d+)?"
    r"(?:\s*,\s*(?:and\s+)?[≈~]?\s*\d+(?:\s*[-–]\s*\d+)?)*)"
)
LINE_ITEM = re.compile(rf"(?P<a>\d+)(?:{_DASH}(?P<b>\d+))?")


def _span(a: str, b: str | None) -> str:
    return a if b is None or b == a else f"{a}-{b}"


def _collapse(text: str) -> str:
    return " ".join(text.split())


def extract_citations(docs: Mapping[str, str]) -> list[Citation]:
    out: list[Citation] = []
    for doc, text in sorted(docs.items()):
        if not MENTION.search(text):
            continue
        has_path_form = PATH_FORM.search(text) is not None
        lines = text.splitlines()
        for n, line in enumerate(lines, 1):
            window = _collapse((lines[n - 2] if n > 1 else "") + " " + line)
            found: list[tuple[str, str, str | None]] = []   # (span, as written, path)
            found += [(_span(m["a"], m["b"]), m[0], m["path"]) for m in PATH_FORM.finditer(line)]
            if has_path_form:
                found += [(_span(m["a"], m["b"]), m[0], None) for m in BARE_FORM.finditer(line)]
            found += [(_span(m["a"], m["b"]), m[0], None) for m in L_FORM.finditer(line)]
            for m in LINE_WORD_FORM.finditer(line):
                found += [(_span(i["a"], i["b"]), m[0], None) for i in LINE_ITEM.finditer(m["items"])]
            out += [Citation(doc, n, span, written, path, window) for span, written, path in found]
    return out


def _scanned_documents() -> dict[str, str]:
    docs: dict[str, str] = {}
    for path in REPO.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        rel = path.relative_to(REPO)
        name = rel.as_posix()
        if any(part in SKIP_DIRS for part in rel.parts) or name.startswith(SKIP_PREFIXES):
            continue
        if name in TARGETS or name == THIS_FILE:
            continue
        try:
            docs[name] = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
    return docs


def _target_lines() -> dict[str, list[str]]:
    # read_text uses universal newlines, so a CRLF checkout (core.autocrlf=true) reads the same.
    return {t: (REPO / t).read_text(encoding="utf-8").splitlines() for t in TARGETS}


# ---------------------------------------------------------------------------------------------
# Matching and checking
# ---------------------------------------------------------------------------------------------

class Match(NamedTuple):
    pairs: list[tuple[Citation, Live | Unchecked]]          # citations with exactly one row
    unlisted: list[Citation]                                # citations with no row
    ambiguous: list[tuple[Citation, list[Live | Unchecked]]]
    orphaned: list[Live | Unchecked]                        # rows with no citation
    reused: list[tuple[Live | Unchecked, list[Citation]]]   # rows with several citations


def match(citations: Iterable[Citation], rows: Iterable[Live | Unchecked]) -> Match:
    rows = list(rows)
    hits: dict[int, list[Citation]] = {i: [] for i in range(len(rows))}
    result = Match([], [], [], [], [])
    for cite in citations:
        found = [
            i for i, row in enumerate(rows)
            if row.doc == cite.doc and row.lines == cite.lines and _collapse(row.quote) in cite.window
        ]
        if not found:
            result.unlisted.append(cite)
        elif len(found) > 1:
            result.ambiguous.append((cite, [rows[i] for i in found]))
        else:
            hits[found[0]].append(cite)
            result.pairs.append((cite, rows[found[0]]))
    result.orphaned.extend(rows[i] for i, got in hits.items() if not got)
    result.reused.extend((rows[i], got) for i, got in hits.items() if len(got) > 1)
    return result


def stale(row: Live, target_lines: list[str]) -> str | None:
    """None if the cited span of `target_lines` still holds the row's construct, else the reason.

    Every needle must be inside the span. That alone passes when ANOTHER copy of a needle lands on
    the cited line, so a single-line row's needle must also occur on exactly one line of the
    target, or be the n-th of exactly `of` lines holding it, as the row's `occurrence` names; and a
    range must hold at least one needle that occurs on exactly one line of the target.
    """
    a, _, b = row.lines.partition("-")
    first, last = int(a), int(b or a)
    if not 1 <= first <= last <= len(target_lines):
        return f"lines {row.lines} are outside {row.target} ({len(target_lines)} lines)"
    span = target_lines[first - 1:last]
    missing = [needle for needle in row.needles if not any(needle in text for text in span)]
    if missing:
        return f"{row.target}:{row.lines} no longer contains {missing}"
    holders = {
        needle: [n for n, text in enumerate(target_lines, 1) if needle in text] for needle in row.needles
    }
    if first != last:
        if row.occurrence is not None:
            return f"{row.target}:{row.lines} is a range; `occurrence` is for single-line rows only"
        if all(len(at) > 1 for at in holders.values()):
            return (f"every needle of {row.target}:{row.lines} also occurs outside it {holders}; "
                    "add a needle from the construct that occurs on one line only")
        return None
    for needle, at in holders.items():
        if row.occurrence is None:
            if len(at) > 1:
                return (f"{row.target}:{row.lines} holds {needle!r}, which is on lines {at}; name the "
                        "occurrence the sentence means")
            continue
        n, of = row.occurrence
        if len(at) != of or not 1 <= n <= of or at[n - 1] != first:
            return (f"{row.target}:{row.lines} is not occurrence {n} of exactly {of} lines holding "
                    f"{needle!r} (it is on lines {at})")
    return None


def _describe(row: Live | Unchecked) -> str:
    return f"{row.doc} [{row.lines}] quote={row.quote!r}"


# ---------------------------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------------------------

def test_the_scan_finds_exactly_as_many_citations_as_the_table_lists():
    """Without this, every test below passes on a regex that matches nothing."""
    citations = extract_citations(_scanned_documents())
    assert LIVE, "the LIVE table is empty"
    assert citations, "no inscription.py line citations found; the scan is broken, not the repository"
    in_audit_sheet = [c for c in citations if c.doc == _AR]
    assert in_audit_sheet, f"no citations found in {_AR}, the document this test exists for"
    assert len(citations) == len(LIVE) + len(UNCHECKED), (
        f"extracted {len(citations)} citations; the table lists {len(LIVE)} LIVE + "
        f"{len(UNCHECKED)} UNCHECKED = {len(LIVE) + len(UNCHECKED)}. See the other tests for which."
    )


def test_every_citation_is_in_the_table():
    citations = extract_citations(_scanned_documents())
    result = match(citations, LIVE + UNCHECKED)
    assert not result.unlisted, (
        "these line citations are not in the reviewed table:\n"
        + "\n".join(f"  {c.where()}  lines={c.lines}\n      {c.window[:160]}" for c in result.unlisted)
        + "\n\nRead the sentence, open the cited line, and add a LIVE row whose needles are the "
        "construct the sentence names. If it is not a pointer into today's file, add an "
        "UNCHECKED row that says why. Never pick a needle just because it is on that line."
    )
    assert not result.ambiguous, (
        "these citations match more than one row; lengthen the quotes until each is unique:\n"
        + "\n".join(f"  {c.where()}\n" + "\n".join(f"      {_describe(r)}" for r in rows)
                    for c, rows in result.ambiguous)
    )
    # A citation that spells out a path must be checked against that path, not against the other
    # file with the same basename, and must not be exempted as something other than a line.
    wrong_target = [
        f"  {cite.where()} is classified as {row.target if isinstance(row, Live) else row.kind}"
        for cite, row in result.pairs
        if cite.path is not None and "/" in cite.path
        and not (isinstance(row, Live) and row.target == cite.path)
    ]
    assert not wrong_target, "a citation names one file and its row says another:\n" + "\n".join(wrong_target)


def test_every_table_entry_is_still_cited():
    citations = extract_citations(_scanned_documents())
    result = match(citations, LIVE + UNCHECKED)
    assert not result.orphaned, (
        "these rows match no citation any more; the sentence was edited or removed:\n"
        + "\n".join(f"  {_describe(r)}" for r in result.orphaned)
        + "\n\nIf the citation moved, re-point the row and re-check its needles. If it is gone, "
        "delete the row."
    )
    assert not result.reused, (
        "these rows match several citations; each citation needs its own row:\n"
        + "\n".join(f"  {_describe(r)}\n" + "\n".join(f"      {c.where()}" for c in cites)
                    for r, cites in result.reused)
    )
    # Of either kind: a citation in a live document is checked or reported, never classified away.
    undated = [r for r in UNCHECKED if not re.search(r"_\d{4}-\d{2}-\d{2}\.md$", r.doc)]
    assert not undated, (
        "an UNCHECKED row, of either kind, must sit in a dated record (*_YYYY-MM-DD.md); these "
        "are in live documents:\n"
        + "\n".join(f"  {_describe(r)} kind={r.kind}" for r in undated)
    )
    assert {r.kind for r in UNCHECKED} <= {"dated", "not-a-contract-line"}


def test_every_cited_line_still_holds_its_construct():
    targets = _target_lines()
    failures = [(row, why) for row in LIVE if (why := stale(row, targets[row.target])) is not None]
    assert not failures, (
        "these citations no longer point at the construct their sentence names:\n"
        + "\n".join(f"  {_describe(row)}\n      {why}" for row, why in failures)
        + "\n\nFind where the construct lives now, fix the DOCUMENT's line numbers, then the row's "
        "`lines`. Do not edit a needle to fit whatever now sits on the old line."
    )


def test_audit_readiness_names_the_contract_revision_its_lines_are_against():
    """The banner says which revision the numbers belong to. That claim must stay true."""
    sheet = _collapse((REPO / _AR).read_text(encoding="utf-8"))
    found = BANNER.search(sheet)
    assert found, f"{_AR} no longer says which revision of {CONTRACT} its line numbers are against"
    commit = found.group(1)
    assert commit in CONTRACT_BLOB_AT, (
        f"{_AR} says its line numbers are against {commit}, which this test has no blob id for. "
        f"Add `git rev-parse {commit}:{CONTRACT}` to CONTRACT_BLOB_AT after re-verifying every row."
    )
    # A git blob id is sha1("blob <len>\0" + content); the blob is stored with LF line endings.
    content = (REPO / CONTRACT).read_bytes().replace(b"\r\n", b"\n")
    blob = hashlib.sha1(b"blob %d\x00" % len(content) + content).hexdigest()  # noqa: S324 - git's id, not security
    assert blob == CONTRACT_BLOB_AT[commit], (
        f"{CONTRACT} has changed since {commit} (blob {blob}, expected {CONTRACT_BLOB_AT[commit]}), "
        f"but {_AR} still says its line numbers are against {commit}. Re-verify every LIVE row, "
        f"update the banner to the new commit, and record its blob id here."
    )


def test_the_check_fails_when_the_contract_moves_by_one_line():
    """Proves the needle check can fail, for every row, before trusting it to pass."""
    targets = _target_lines()
    survivors = []
    for row in LIVE:
        real = targets[row.target]
        assert stale(row, real) is None, f"precondition: {_describe(row)} must pass unmodified"
        moved_up = real[1:]            # first line deleted: everything moves up by one
        moved_down = [""] + real       # a line inserted at the top: everything moves down by one
        if stale(row, moved_up) is None and stale(row, moved_down) is None:
            survivors.append(_describe(row))
        if "-" not in row.lines:
            assert stale(row, moved_up) and stale(row, moved_down), (
                f"a single-line citation survived a one-line move: {_describe(row)}"
            )
    assert not survivors, (
        "these rows pass whichever way the file moves by one line, so no needle anchors either "
        "edge of the range. Add a needle that sits on its first or last line:\n  "
        + "\n  ".join(survivors)
    )


def test_the_extractor_recognises_every_citation_form():
    """Each written form is extracted with the span it denotes, and an unreviewed one is reported."""
    docs = _scanned_documents()
    baseline = match(extract_citations(docs), LIVE + UNCHECKED)
    assert not (baseline.unlisted or baseline.orphaned), "precondition: the real tree must match"

    planted = dict(docs)
    planted[_AR] = docs[_AR] + (
        "\nPlanted: `contracts/inscription.py:1001`, `inscription.py:1002-1003`, (L1004), "
        "(L1005–1006), (≈L1007-L1008), line ~1009, Lines 1010, 1011–1012.\n"
    )
    planted["REVIEWER.md"] = docs["REVIEWER.md"] + "\nPlanted: `_build_message` from `:1013`.\n"
    result = match(extract_citations(planted), LIVE + UNCHECKED)
    assert sorted((c.doc, c.lines) for c in result.unlisted) == sorted([
        (_AR, "1001"), (_AR, "1002-1003"), (_AR, "1004"), (_AR, "1005-1006"), (_AR, "1007-1008"),
        (_AR, "1009"), (_AR, "1010"), (_AR, "1011-1012"), ("REVIEWER.md", "1013"),
    ]), [c.where() for c in result.unlisted]
    assert not result.orphaned


# ---------------------------------------------------------------------------------------------
# Mutation tests: the real test functions above, re-run against altered inputs, must FAIL.
# ---------------------------------------------------------------------------------------------

_THIS_MODULE = sys.modules[__name__]


def test_mutation_a_moving_a_function_in_the_contract_fails_the_currency_check(monkeypatch):
    """Two lines inserted above `_build_message`, as any edit to the contract above it would do."""
    real = _target_lines()
    contract = real[CONTRACT]
    at = next(i for i, text in enumerate(contract) if "def _build_message(" in text) - 1
    assert contract[at].strip() == "@subroutine", "precondition: the decorator is on the line above"
    shifted = contract[:at] + ["    # inserted line 1", "    # inserted line 2"] + contract[at:]
    first_moved = at + 1  # 1-based: the decorator's line, and everything after it, moved down by two

    monkeypatch.setattr(_THIS_MODULE, "_target_lines", lambda: {**real, CONTRACT: shifted})
    with pytest.raises(AssertionError) as failure:
        test_every_cited_line_still_holds_its_construct()
    report = str(failure.value)

    def first_line(row: Live) -> int:
        return int(row.lines.partition("-")[0])

    def last_line(row: Live) -> int:
        a, _, b = row.lines.partition("-")
        return int(b or a)

    # The rows that cite `_build_message` itself, in both documents, must be reported.
    build_message_rows = [
        r for r in LIVE if r.target == CONTRACT and any("def _build_message(" in n for n in r.needles)
    ]
    assert len(build_message_rows) == 3, [_describe(r) for r in build_message_rows]
    for row in build_message_rows:
        assert stale(row, shifted) is not None and _describe(row) in report, _describe(row)
    # Nothing that ends above the insertion is reported: the check does not fail indiscriminately.
    untouched = [r for r in LIVE if r.target == CONTRACT and last_line(r) < first_moved]
    assert untouched
    assert not [_describe(r) for r in untouched if _describe(r) in report]
    # And every row it does report cites a line that moved.
    reported = [r for r in LIVE if _describe(r) in report]
    assert all(r.target == CONTRACT and first_line(r) >= first_moved for r in reported), report


def test_mutation_b_an_unreviewed_citation_fails_the_table_checks(monkeypatch):
    """A citation added to AUDIT_READINESS.md without a table row fails both table checks."""
    docs = _scanned_documents()
    assert "(L305)" not in docs[_AR]
    planted = {**docs, _AR: docs[_AR] + "\nPlanted: the record write in `inscribe` (L305).\n"}
    monkeypatch.setattr(_THIS_MODULE, "_scanned_documents", lambda: planted)

    with pytest.raises(AssertionError, match=r"not in the reviewed table") as failure:
        test_every_citation_is_in_the_table()
    assert f"{_AR}:" in str(failure.value) and "lines=305" in str(failure.value)
    size = len(LIVE) + len(UNCHECKED)
    with pytest.raises(AssertionError, match=rf"extracted {size + 1} citations; the table lists"):
        test_the_scan_finds_exactly_as_many_citations_as_the_table_lists()


def test_mutation_c_a_deleted_citation_fails_the_table_checks(monkeypatch):
    """A citation removed from the document leaves its row orphaned, and the counts disagree."""
    docs = _scanned_documents()
    assert docs[_AR].count("(L302)") == 1
    removed = {**docs, _AR: docs[_AR].replace("(L302)", "(the budget call)")}
    monkeypatch.setattr(_THIS_MODULE, "_scanned_documents", lambda: removed)

    with pytest.raises(AssertionError, match=r"match no citation any more") as failure:
        test_every_table_entry_is_still_cited()
    assert f"{_AR} [302]" in str(failure.value)
    size = len(LIVE) + len(UNCHECKED)
    with pytest.raises(AssertionError, match=rf"extracted {size - 1} citations; the table lists"):
        test_the_scan_finds_exactly_as_many_citations_as_the_table_lists()


def test_mutation_d_an_empty_scan_fails_instead_of_passing_vacuously(monkeypatch):
    monkeypatch.setattr(_THIS_MODULE, "_scanned_documents", lambda: {})
    with pytest.raises(AssertionError, match=r"no inscription\.py line citations found"):
        test_the_scan_finds_exactly_as_many_citations_as_the_table_lists()


def test_mutation_e_another_copy_of_the_needle_on_the_cited_line_fails(monkeypatch):
    """THREAT_MODEL cites the SDK client's fallback `self.app.send.inscribe(` at :182, and the first
    attempt holds the same text. Lines inserted above the first attempt land IT on :182 while the
    fallback moves away. The needle is still on the cited line, so presence alone passes; the
    occurrence rule must not. Nor may a NEW copy that lands on :182 in front of the fallback."""
    real = _target_lines()
    client = real[SDK_CLIENT]
    needle = "self.app.send.inscribe("
    holders = [n for n, text in enumerate(client, 1) if needle in text]
    assert len(holders) == 2, holders
    (row,) = [r for r in LIVE if r.target == SDK_CLIENT and r.needles == (needle,)]
    assert (row.lines, row.occurrence) == (str(holders[1]), (2, 2))
    cited = holders[1]
    # Without `occurrence`, the row fails on the unmodified client: a repeated needle must be named.
    undeclared = stale(row._replace(occurrence=None), client)
    assert undeclared is not None and "name the occurrence" in undeclared, undeclared

    at = holders[0] - 2   # insert after line holders[0] - 2: below every other SDK client row
    others = [r for r in LIVE if r.target == SDK_CLIENT and r != row]
    assert others and all(int(r.lines.rpartition("-")[2]) <= at for r in others)
    first_attempt_moved_onto_it = client[:at] + ["        # inserted"] * (cited - holders[0]) + client[at:]
    new_copy_in_front = client[:cited - 1] + ["            self.app.send.inscribe(  # inserted"] + client[cited - 1:]
    for shifted in (first_attempt_moved_onto_it, new_copy_in_front):
        # Precondition: a copy that is not the fallback sits on the cited line, so presence passes.
        assert needle in shifted[cited - 1] and "# inserted" not in client[cited - 1]
        with monkeypatch.context() as patch:
            patch.setattr(_THIS_MODULE, "_target_lines", lambda shifted=shifted: {**real, SDK_CLIENT: shifted})
            with pytest.raises(AssertionError) as failure:
                test_every_cited_line_still_holds_its_construct()
        report = str(failure.value)
        assert f"is not occurrence 2 of exactly 2 lines holding {needle!r}" in report, report
        assert [r for r in LIVE if _describe(r) in report] == [row], report


def test_mutation_f_a_range_whose_needles_all_occur_elsewhere_fails(monkeypatch):
    """A range row holding only a needle that also occurs outside the range proves nothing about
    the construct, even while that needle sits inside the range."""
    contract = _target_lines()[CONTRACT]
    needle = "Global.genesis_hash"
    (row,) = [r for r in LIVE if r.doc == _AR and needle in r.needles]
    assert "-" in row.lines and stale(row, contract) is None
    assert sum(needle in text for text in contract) > 1, "precondition: the needle is repeated"
    weakened = row._replace(needles=(needle,))
    monkeypatch.setattr(_THIS_MODULE, "LIVE", (*LIVE, weakened))
    with pytest.raises(AssertionError, match=r"also occurs outside it") as failure:
        test_every_cited_line_still_holds_its_construct()
    assert _describe(weakened) in str(failure.value)


def test_mutation_g_an_exemption_in_a_live_document_fails(monkeypatch):
    """An UNCHECKED row of either kind, planted beside an unreviewed citation in AUDIT_READINESS.md,
    silences the table and count checks; the dated-record rule is what must still fail."""
    docs = _scanned_documents()
    assert "(L306)" not in docs[_AR]
    planted = {**docs, _AR: docs[_AR] + "\nPlanted: the record write (L306).\n"}
    monkeypatch.setattr(_THIS_MODULE, "_scanned_documents", lambda: planted)
    with pytest.raises(AssertionError, match=r"not in the reviewed table"):
        test_every_citation_is_in_the_table()          # negative control: no row, reported

    reviewed = UNCHECKED
    for kind in ("not-a-contract-line", "dated"):
        exemption = Unchecked(_AR, "306", "the record write (L306)", kind, "planted by this test")
        monkeypatch.setattr(_THIS_MODULE, "UNCHECKED", (*reviewed, exemption))
        test_every_citation_is_in_the_table()          # the exemption silences this ...
        test_the_scan_finds_exactly_as_many_citations_as_the_table_lists()   # ... and this
        with pytest.raises(AssertionError, match=r"must sit in a dated record") as failure:
            test_every_table_entry_is_still_cited()
        assert f"{_AR} [306]" in str(failure.value) and f"kind={kind}" in str(failure.value)


def test_the_scan_skips_what_the_cited_documents_sweep_skips():
    """test_cited_documents_exist.py walks the same tree; the two must not disagree about it."""
    sibling = Path(__file__).with_name("test_cited_documents_exist.py")
    source = sibling.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assigned = [
        node.value for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "SKIP_DIRS" for t in node.targets)
    ]
    assert len(assigned) == 1, f"{sibling.name} no longer assigns SKIP_DIRS exactly once"
    assert ast.literal_eval(assigned[0]) == SKIP_DIRS, (
        f"{sibling.name} and this file skip different directories; keep them identical"
    )
    assert "REPO = Path(__file__).resolve().parents[2]" in source, (
        f"{sibling.name} resolves the repository root differently from this file"
    )
