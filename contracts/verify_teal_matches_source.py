#!/usr/bin/env python3
"""The committed artifacts must be what `inscription.py` actually compiles to.

WHY THIS EXISTS - the first link of the derivation chain was never checked.
==========================================================================

`verify_deployment.py` documents this chain, and every value in it is recomputed rather
than stored:

    contracts/inscription.py
        |  puya                                   <-- THIS ARROW
        v
    contracts/out/TrelyanInscription.*            [committed artifacts]
        |  algod /v2/teal/compile                      |  algokit generate client
        v                                              v
    expected bytecode --sha512_256--> fingerprint   contracts/trelyan_client.py
                    ==?  deployed program                  <-- AND THIS ONE

Two arrows out of the committed artifact, and neither was checked. The client branch is
the one the tests actually run against: the LocalNet suite deploys the committed TEAL and
drives it through the generated typed client, so a contract whose ABI moved without the
client being regenerated would be exercised by a suite talking to the old interface.

CI only ever ran the part BELOW the committed artifact. The `--recompile` flag that covers
the top arrow exists, but no workflow passed it - verified by grep across
`.github/workflows/`: zero occurrences of "recompile".

The consequence is not subtle. `inscription.py` is the only human-readable artifact in the
chain - it is what a reviewer reads, what an auditor is handed, and what every design
document quotes. Without this check it is not in the verified chain AT ALL. An edit to the
source that changes behaviour, committed without regenerating contracts/out/, passes the
entire suite: the committed TEAL still assembles to the bytecode still on chain, and
nothing anywhere compares the source to the artifact. The reviewer reads one program and
the network runs another, and every gate is green.

That is precisely the failure `verify_deployment.py` warns about in its own output -
"before treating any review of this source as a review of the live application" - arriving
through the door nobody was watching.

WHY NOT SIMPLY RUN `verify_deployment.py --recompile` IN CI?
============================================================

That closes most of the hole and is worth doing as well. It does not close all of it:
after its own repair it compares ASSEMBLED BYTECODE, deliberately, so comment churn cannot
raise a false alarm about behaviour. Sound for its purpose - and it means a stale
`// inscription.py:NNN` reference passes, because the assembler discards comments. It also
checks only the two .teal files, not the source maps or the ARC-56 client contract.

So this check compares all five artifacts as TEXT, and separates two failure modes that
warrant very different responses:

  * BEHAVIOURAL drift - the instruction streams differ. The committed artifact does not
    implement the committed source. A correctness and security finding.

  * TRACEABILITY drift - instructions identical, only comments and source references
    differ. Bytecode is unaffected, so nothing deployed is wrong; but an auditor following
    `// inscription.py:156` lands on the wrong line, and the repository's claim to commit
    "both source and TEAL" (constitution section 5) is no longer true of the tree in front
    of them.

Both exit 1. Neither is waved through as cosmetic, neither is mislabelled as the other.

REPRODUCIBILITY IS INVOCATION-SENSITIVE, AND THE DOCS DID NOT SAY SO
====================================================================

puya records the source path AS GIVEN ON THE COMMAND LINE, and records it in two different
forms in two different places. Getting either wrong produces a large, entirely spurious
diff, so the exact invocation is part of the artifact and is pinned below:

  * The .teal comments carry the path as typed. Compiling from the repository root
    (`puyapy contracts/inscription.py`) emits `// contracts/inscription.py:156`, while the
    committed artifacts carry `// inscription.py:156`. That single difference accounts for
    124 differing lines - all of them cosmetic, none of them a real change.

  * The .puya.map `sources` entry is the source path RELATIVE TO THE OUT-DIR. The committed
    map says `../inscription.py`, which only reproduces when the output directory is a
    SIBLING of `contracts/inscription.py`'s parent - as `contracts/out/` is.

So this check compiles with the working directory set to `contracts/`, passing the bare
filename, into a temporary directory created INSIDE `contracts/` (a sibling of `out/`, so
the relative path in the map is identical). Verified: all five artifacts then reproduce
byte-for-byte.

The temporary directory is never `out/` itself. A verifier that writes over its subject
cannot be run safely on a clean tree, and on a second run compares the artifacts against
themselves.

Three build commands were documented, in README.md, CONTRIBUTING.md and
contracts/requirements.txt, and NONE of them reproduced the committed artifacts - two ran
from the repository root, and the third referenced a `crypto/contracts/` directory that
does not exist in this repository. Following the documentation and committing the result
would have produced a 124-line diff that looked like a change and was not. Those documents
are corrected alongside this file.

Exit codes match `verify_deployment.py` so the two read alike in a log:
    0 = the committed artifacts are exactly what the source compiles to
    1 = drift (the message says which kind)
    2 = COULD NOT CHECK - toolchain or artifact missing. Never reported as agreement.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import sys
import tempfile

# The target AVM version is pinned HERE rather than read from the committed artifact's
# `#pragma version`, and the difference matters. Reading the target out of the file being
# verified would make this check partly circular: the recompile would inherit whatever the
# artifact claimed, emit that same pragma back, and agree with itself. So the constant is
# the authority and the artifact must match it - asserted below, not assumed.
#
# 12 because `inscription.py` calls `op.falcon_verify`, an AVM 12 opcode. puyapy's default
# target is lower and compilation fails outright without this flag.
AVM_TARGET = "12"

# Every artifact puya emits, all five of which are committed. The .puya.map files and the
# ARC-56 JSON encode source positions too, so they go stale in exactly the same way as the
# TEAL and are checked on the same footing. Confirmed to contain no absolute paths, so they
# are reproducible across machines.
ARTIFACTS = (
    "TrelyanInscription.approval.teal",
    "TrelyanInscription.clear.teal",
    "TrelyanInscription.approval.puya.map",
    "TrelyanInscription.clear.puya.map",
    "TrelyanInscription.arc56.json",
)

TEAL_ARTIFACTS = frozenset({
    "TrelyanInscription.approval.teal",
    "TrelyanInscription.clear.teal",
})


class CheckError(Exception):
    """The check could not be completed (as distinct from completing and failing)."""


def _normalise(raw: bytes) -> bytes:
    """Line endings only - nothing about the content.

    The committed artifacts are checked out with CRLF on Windows while puya writes LF, so a
    raw byte comparison reports every line as different on a Windows developer's machine and
    nothing at all on Linux. That is a property of the checkout, not of the contract, and a
    check whose verdict depends on the operating system is not a check.
    """
    return raw.replace(b"\r\n", b"\n")


def _instructions(teal: bytes) -> list[str]:
    """The TEAL instruction stream, with comments and blank lines removed.

    Used ONLY to classify a failure that has already been established, never to decide
    whether one occurred - so a flaw here can mislabel a report but cannot manufacture a
    pass.

    Comment stripping is quote-aware. TEAL comments start with `//`, but `//` can also
    appear inside a double-quoted byte-string literal, and a naive split would truncate the
    instruction and could make two genuinely different programs look identical.
    """
    out: list[str] = []
    for line in _normalise(teal).decode("utf-8", errors="replace").splitlines():
        in_string = False
        cut = len(line)
        i = 0
        while i < len(line):
            char = line[i]
            if char == '"':
                in_string = not in_string
            elif char == "\\" and in_string:
                i += 1  # skip the escaped character
            elif char == "/" and not in_string and line.startswith("//", i):
                cut = i
                break
            i += 1
        code = line[:cut].strip()
        if code:
            out.append(code)
    return out


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


def _compile(source: pathlib.Path, out_dir: pathlib.Path) -> None:
    """Compile exactly the way the committed artifacts were produced.

    `cwd` is the source's directory and the source is passed as a BARE FILENAME, because
    puya writes the path as typed into the .teal comments. See the module docstring.
    """
    try:
        subprocess.run(
            [sys.executable, "-m", "puyapy", source.name,
             "--out-dir", str(out_dir),
             "--target-avm-version", AVM_TARGET],
            cwd=source.parent,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise CheckError(f"could not invoke {sys.executable}: {exc}") from exc
    except subprocess.CalledProcessError as exc:
        # puya reports compilation errors on stdout; stderr is often empty. Preferring
        # stderr here would print nothing and call it a mystery.
        detail = (exc.stdout or "").strip() or (exc.stderr or "").strip() or "no output"
        raise CheckError(f"puya failed (exit {exc.returncode}): {detail}") from exc


def _assert_pragma_matches(committed: pathlib.Path) -> None:
    """The artifact must agree with the pinned target, rather than dictating it."""
    text = _normalise(committed.read_bytes()).decode("utf-8", errors="replace")
    first = text.splitlines()[:1]
    if not first or not first[0].startswith("#pragma version "):
        raise CheckError(f"{committed.name} does not begin with a '#pragma version' line")
    declared = first[0].removeprefix("#pragma version ").strip()
    if declared != AVM_TARGET:
        raise CheckError(
            f"{committed.name} declares '#pragma version {declared}' but this check pins AVM "
            f"{AVM_TARGET} (falcon_verify is an AVM {AVM_TARGET} opcode). Reconcile them "
            f"deliberately - do not edit AVM_TARGET to whatever the artifact happens to say, "
            f"which is the circularity this constant exists to avoid."
        )


def _client_spec_matches(client: pathlib.Path, spec_path: pathlib.Path) -> str | None:
    """The generated typed client must embed the SAME ARC-56 spec that is committed.

    One more link in the same chain, and the one the tests actually run against. The
    LocalNet suite deploys the committed TEAL and drives it through
    `contracts/trelyan_client.py` - an 89 KB generated file stamped "DO NOT MODIFY IT BY
    HAND". CI only ever CONSUMES it; nothing regenerated it and compared. So a contract
    whose ABI moved without the client being regenerated would be exercised by a suite
    talking to the old interface.

    Checked WITHOUT running the generator, deliberately. `algokit generate client` needs
    `algokitgen-py`, which pins the check to a generator version whose formatting churn is
    not a finding - and which is, on the machine this was written on, blocked outright by a
    Windows Application Control policy (os error 4551). The client happens to EMBED the
    full spec it was generated from, in `_APP_SPEC_JSON`, so the meaningful comparison
    needs nothing but the two committed files.

    The comparison is on PARSED JSON, not bytes: the client embeds the spec minified while
    arc56.json is pretty-printed, so a byte comparison would fail always and mean nothing.

    Returns None when in step, or a description of the divergence.
    """
    if not client.exists():
        return f"typed client not found: {client}"
    src = client.read_text(encoding="utf-8", errors="replace")
    match = re.search(r'_APP_SPEC_JSON\s*=\s*r?"""(.*?)"""', src, re.S)
    if match is None:
        return (
            f"{client.name} has no _APP_SPEC_JSON block. The generator's output shape has "
            f"changed, so this check no longer reads what it thinks it reads - repair the "
            f"check rather than deleting it."
        )
    try:
        embedded = json.loads(match.group(1))
    except json.JSONDecodeError as exc:
        return f"the spec embedded in {client.name} is not valid JSON: {exc}"

    committed = json.loads(spec_path.read_text(encoding="utf-8"))
    if embedded == committed:
        return None

    embedded_methods = [m.get("name") for m in embedded.get("methods", [])]
    committed_methods = [m.get("name") for m in committed.get("methods", [])]
    if embedded_methods != committed_methods:
        return (
            f"ABI METHODS DIFFER. client: {embedded_methods}; contract: {committed_methods}. "
            f"The LocalNet suite drives the contract through this client, so it is testing a "
            f"different interface from the one committed."
        )
    differing = sorted(k for k in set(embedded) | set(committed)
                       if embedded.get(k) != committed.get(k))
    return (
        f"the embedded spec differs from {spec_path.name} at: {', '.join(differing)}. "
        f"Method names agree, so this is a signature, struct or metadata change."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify the committed artifacts are what inscription.py compiles to.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    here = pathlib.Path(__file__).resolve().parent
    parser.add_argument("--source", type=pathlib.Path, default=here / "inscription.py")
    parser.add_argument("--out", type=pathlib.Path, default=here / "out")
    parser.add_argument("--client", type=pathlib.Path, default=here / "trelyan_client.py")
    args = parser.parse_args()

    source = args.source.resolve()
    committed_dir = args.out.resolve()
    if not source.exists():
        raise CheckError(f"source not found: {source}")
    if not committed_dir.is_dir():
        raise CheckError(f"committed artifact directory not found: {committed_dir}")

    _assert_pragma_matches(committed_dir / "TrelyanInscription.approval.teal")

    print(f"[0] recompiling {source.name} with puya (target AVM {AVM_TARGET})")

    # The temporary directory is created INSIDE the source's directory, making it a sibling
    # of out/. That is not tidiness: the .puya.map records the source path relative to the
    # out-dir, so an out-dir anywhere else changes `../inscription.py` into a long relative
    # path and the map appears to have changed when nothing has.
    with tempfile.TemporaryDirectory(prefix=".teal-check-", dir=source.parent) as tmp:
        fresh_dir = pathlib.Path(tmp)
        _compile(source, fresh_dir)

        behavioural: list[str] = []
        traceability: list[str] = []

        for name in ARTIFACTS:
            committed_path, fresh_path = committed_dir / name, fresh_dir / name
            if not committed_path.exists():
                raise CheckError(f"committed artifact missing: {committed_path}")
            if not fresh_path.exists():
                raise CheckError(f"puya did not emit {name}; the artifact set has changed")

            committed = _normalise(committed_path.read_bytes())
            fresh = _normalise(fresh_path.read_bytes())

            if committed == fresh:
                print(f"    ok    {name}  ({_digest(committed)})")
                continue

            if name in TEAL_ARTIFACTS and _instructions(committed) != _instructions(fresh):
                behavioural.append(name)
                print(f"    DRIFT {name}  (instruction stream differs)")
            else:
                traceability.append(name)
                print(f"    STALE {name}  (non-executable content differs)")

    client_problem = _client_spec_matches(args.client.resolve(),
                                          committed_dir / "TrelyanInscription.arc56.json")
    if client_problem is None:
        print(f"    ok    {args.client.name}  (embedded ARC-56 spec matches the committed one)")
    else:
        print(f"    DRIFT {args.client.name}  (embedded ARC-56 spec does NOT match)")

    if not behavioural and not traceability and client_problem is None:
        print("\nOK: the committed artifacts are exactly what the source compiles to.")
        return 0

    print()
    if behavioural:
        print("BEHAVIOURAL DRIFT - the committed TEAL does not implement the committed source.")
        print(f"  Instruction streams differ in: {', '.join(behavioural)}")
        print("  The bytecode on chain therefore does not correspond to inscription.py as")
        print("  committed. Treat any review of this source as NOT a review of the deployed")
        print("  application until this is resolved. Do NOT regenerate the artifact to make")
        print("  this pass without first establishing which side is wrong.")
    if traceability:
        if behavioural:
            print()
        print("STALE ARTIFACT - instructions identical; comments and source references are not.")
        print(f"  Differs only in non-executable content: {', '.join(traceability)}")
        print("  Assembled bytecode is unaffected, so nothing deployed is wrong. But puya emits")
        print("  '// inscription.py:NNN' references into these files, and they now point at the")
        print("  wrong lines, so an auditor tracing TEAL back to source is misled.")
    if client_problem is not None:
        if behavioural or traceability:
            print()
        print("CLIENT DRIFT - the typed client does not match the committed ARC-56 spec.")
        print(f"  {client_problem}")
        print("  Regenerate it (the docs say to, after every recompile):")
        print("    algokit generate client contracts/out/TrelyanInscription.arc56.json \\")
        print("      --output contracts/trelyan_client.py")
    if not behavioural and not traceability:
        return 1
    print()
    print("  Regenerate with EXACTLY this invocation - the working directory and the out-dir")
    print("  location are both part of the artifact (see this file's docstring):")
    print("      cd contracts")
    print(f"      puyapy inscription.py --out-dir out --target-avm-version {AVM_TARGET}")
    print("  using the pinned toolchain in contracts/requirements-compile.txt.")
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CheckError as exc:
        print(f"\nCOULD NOT CHECK: {exc}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        sys.exit(2)
