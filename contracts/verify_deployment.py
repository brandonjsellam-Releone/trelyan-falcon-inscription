#!/usr/bin/env python3
"""Verify that the deployed application is what the committed source builds.

This check is deliberately capable of FAILING. Its predecessor was not: the
reviewer example pinned a constant that had been copied from the deployed
program itself and compared it to the chain. Because the contract blocks
Update and Delete (invariants I1/I5), the deployed bytecode is immutable, so
that comparison was guaranteed to pass forever and could never observe the
source diverging from the deployment. A check that cannot fail is not a check.

Chain of derivation - every value is recomputed, none is stored:

    contracts/inscription.py
        |  puya  (only re-run when --recompile is passed; needs the toolchain)
        v
    contracts/out/TrelyanInscription.approval.teal          [committed artifact]
        |  algod /v2/teal/compile  (deterministic assembly for a given AVM version)
        v
    expected bytecode --sha512_256--> expected fingerprint
                                          ==?
    algod /v2/applications/{id} --> deployed bytecode --sha512_256--> actual fingerprint

Trust note for reviewers: by default the same algod service both assembles the
committed TEAL and serves the deployed program, so a dishonest endpoint could
lie consistently across both. Pass --compile-url pointing at an independent
node (or a local `goal clerk compile`) to split that trust. The comparison is
only as strong as the weaker of the two sources.

Exit codes:  0 deployment matches committed source
             1 DRIFT - deployment differs from committed source
             2 could not complete the check (network, missing artifact, ...)
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import pathlib
import subprocess
import tempfile
import sys
import urllib.error
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parent
DEFAULT_TEAL = REPO_ROOT / "out" / "TrelyanInscription.approval.teal"
DEFAULT_SOURCE = REPO_ROOT / "inscription.py"

# TestNet deployment under review. Not a security constant - changing it only
# changes which application is inspected, never what "correct" means.
DEFAULT_APP_ID = 770964251
DEFAULT_ALGOD = "https://testnet-api.algonode.cloud"


class CheckError(Exception):
    """The check could not be completed (as distinct from completing and failing)."""


def sha512_256(data: bytes) -> str:
    """Algorand's program hash. Note this is SHA-512/256, not SHA-256."""
    digest = hashlib.new("sha512_256")
    digest.update(data)
    return digest.hexdigest()


def _get_json(url: str, timeout: int) -> dict:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise CheckError(f"GET {url} -> HTTP {exc.code}: {exc.read()[:200]!r}") from exc
    except OSError as exc:
        raise CheckError(f"GET {url} failed: {exc}") from exc


def assemble(teal: bytes, algod: str, timeout: int) -> bytes:
    """Assemble TEAL to bytecode via algod. Deterministic for a given AVM version."""
    url = f"{algod.rstrip('/')}/v2/teal/compile"
    request = urllib.request.Request(url, data=teal, headers={"Content-Type": "text/plain"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return base64.b64decode(json.load(response)["result"])
    except urllib.error.HTTPError as exc:
        raise CheckError(f"assemble via {url} -> HTTP {exc.code}: {exc.read()[:300]!r}") from exc
    except OSError as exc:
        raise CheckError(f"assemble via {url} failed: {exc}") from exc


def fetch_deployed(app_id: int, algod: str, timeout: int) -> bytes:
    params = _get_json(f"{algod.rstrip('/')}/v2/applications/{app_id}", timeout).get("params", {})
    program = params.get("approval-program")
    if not program:
        raise CheckError(f"application {app_id} returned no approval-program")
    return base64.b64decode(program)


def _committed_avm_version(teal: pathlib.Path) -> str:
    """Read the AVM target out of the committed artifact's own `#pragma version` line.

    Derived rather than hard-coded on purpose. A literal here could drift from the artifact it is
    meant to reproduce, and a recompile check whose target disagrees with its subject compares two
    different things — which is the defect class this whole script exists to catch.
    """
    first = teal.read_text(encoding="utf-8", errors="replace").splitlines()[:1]
    if not first or not first[0].startswith("#pragma version "):
        raise CheckError(
            f"{teal} does not begin with a '#pragma version' line, so the AVM target cannot be "
            f"derived; refusing to guess"
        )
    return first[0].removeprefix("#pragma version ").strip()


def recompile_from_source(source: pathlib.Path, out_dir: pathlib.Path,
                          avm_version: str) -> None:
    """Re-derive the committed TEAL from inscription.py, so the artifact is not
    trusted either. Requires puya; callers treat absence as 'could not check'.

    `--target-avm-version` is REQUIRED, not optional. The contract calls `op.falcon_verify`, which
    is an AVM 12 opcode; puyapy's default target is lower, so without the flag compilation FAILS
    outright:

        assert op.falcon_verify(m, falcon_sig.native, pubkey), "falcon signature invalid"
               ^~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

    This function omitted it, so `--recompile` could never complete — the branch that exists to
    prove the committed artifact was not trusted has never once run to completion.
    `contracts/requirements.txt` documented the correct invocation the whole time.
    """
    try:
        subprocess.run(
            [sys.executable, "-m", "puyapy", str(source),
             "--out-dir", str(out_dir),
             "--target-avm-version", avm_version],
            check=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise CheckError("puya not available; omit --recompile or install contracts/requirements.txt") from exc
    except subprocess.CalledProcessError as exc:
        # puyapy writes its diagnostics to STDOUT, not stderr — measured: on a failing compile
        # stderr is 0 bytes and stdout carries all 848. Reporting only stderr produced the
        # message "puya failed:" with nothing after it, so an operator hitting the bug above got
        # a failure with no reason at all. Prefer stdout, fall back to stderr.
        detail = (exc.stdout or b"").decode(errors="replace").strip()
        if not detail:
            detail = (exc.stderr or b"").decode(errors="replace").strip()
        raise CheckError(
            f"puya failed (exit {exc.returncode}): {detail[:800] or '<no output on either stream>'}"
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--app-id", type=int, default=DEFAULT_APP_ID)
    parser.add_argument("--algod", default=DEFAULT_ALGOD, help="node used to read the deployed program")
    parser.add_argument("--compile-url", default=None,
                        help="independent node used to assemble the committed TEAL (defaults to --algod; "
                             "set this to a different provider to avoid trusting one endpoint for both halves)")
    parser.add_argument("--teal", type=pathlib.Path, default=DEFAULT_TEAL)
    parser.add_argument("--source", type=pathlib.Path, default=DEFAULT_SOURCE)
    parser.add_argument("--recompile", action="store_true",
                        help="re-derive the TEAL artifact from inscription.py first (requires puya)")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    compile_url = args.compile_url or args.algod

    try:
        if args.recompile:
            print(f"[0] re-deriving TEAL from {args.source.name} via puya")
            if not args.teal.exists():
                raise CheckError(f"committed artifact not found: {args.teal}")

            # Compile into a TEMPORARY directory, never over the committed artifacts.
            #
            # This previously passed `args.teal.parent`, i.e. contracts/out/, so a tool whose whole
            # job is to VERIFY the committed artifacts silently rewrote five of them (both .teal,
            # both .puya.map, and the .arc56.json) as a side effect of being run. A verifier that
            # mutates its subject cannot be run safely on a clean tree, and its second run compares
            # the output against itself.
            with tempfile.TemporaryDirectory(prefix="trelyan-recompile-") as tmp:
                recompile_from_source(args.source, pathlib.Path(tmp),
                                      _committed_avm_version(args.teal))
                fresh = (pathlib.Path(tmp) / args.teal.name).read_bytes()

            committed = args.teal.read_bytes()

            # Compare ASSEMBLED BYTECODE, not TEAL text.
            #
            # Text comparison reported "stale" on a contract that is in fact perfectly reproducible.
            # Measured against puyapy 5.8.1 / algorand-python 3.5.0 at AVM 12: the committed TEAL is
            # 17,559 bytes and a fresh compile is 18,179 — 620 bytes apart, and NOT a line-ending
            # artifact (LF-normalising both does not close the gap). Yet both assemble to the same
            # 667-byte program, sha256 308cfa75…. The difference is comment and source-map
            # formatting emitted by a different compiler build.
            #
            # Bytecode is what gets deployed and what the drift check further down compares, so it
            # is the only comparison that answers the question being asked. Comparing text made the
            # check fail on compiler-version noise while claiming the source and artifact disagreed.
            if assemble(committed, compile_url, args.timeout) != assemble(fresh, compile_url, args.timeout):
                print("    FAIL  committed TEAL does not assemble to the same program as a fresh compile")
                return 1
            if committed != fresh:
                print("    ok    committed TEAL assembles identically to a fresh compile")
                print("          (the TEAL TEXT differs — comment/source-map formatting from a "
                      "different puyapy build; the program bytes are the same)")
            else:
                print("    ok    committed TEAL matches a fresh compile of the source, byte for byte")

        if not args.teal.exists():
            raise CheckError(f"committed artifact not found: {args.teal}")

        teal = args.teal.read_bytes()
        # Display repo-relative when it is in the repo, absolute otherwise. An artifact
        # supplied from elsewhere is a legitimate use (comparing an out-of-tree build),
        # so this must not raise.
        try:
            shown = args.teal.resolve().relative_to(REPO_ROOT.parent)
        except ValueError:
            shown = args.teal.resolve()
        print(f"[1] committed artifact  {shown}  ({len(teal)} B TEAL)")

        expected = assemble(teal, compile_url, args.timeout)
        expected_hash = sha512_256(expected)
        print(f"[2] assembled via       {compile_url}")
        print(f"    expected bytecode   {len(expected)} B   sha512_256 {expected_hash}")

        deployed = fetch_deployed(args.app_id, args.algod, args.timeout)
        deployed_hash = sha512_256(deployed)
        print(f"[3] deployed app {args.app_id} via {args.algod}")
        print(f"    actual bytecode     {len(deployed)} B   sha512_256 {deployed_hash}")

    except CheckError as exc:
        print(f"\nCOULD NOT CHECK: {exc}", file=sys.stderr)
        return 2

    print()
    if expected == deployed:
        print(f"MATCH - application {args.app_id} is running the committed source.")
        return 0

    print_awaiting_redeploy(
        app_id=args.app_id,
        expected_hash=expected_hash,
        expected_len=len(expected),
        deployed_hash=deployed_hash,
        deployed_len=len(deployed),
    )
    return 1


def print_awaiting_redeploy(
    *,
    app_id: int,
    expected_hash: str,
    expected_len: int,
    deployed_hash: str,
    deployed_len: int,
) -> None:
    """Print the documented drift finding. Always a failure, never a skip.

    App 763809096 cannot be patched in place (Update/Delete are blocked, I1/I5).
    The one-shot checklist is BLOCKERS.md.
    """
    print(f"DRIFT - application {app_id} is NOT running the committed source.")
    print(f"  committed source builds to : {expected_hash}  ({expected_len} B)")
    print(f"  chain is actually serving  : {deployed_hash}  ({deployed_len} B)")
    print()
    print(f"AWAITING TESTNET REDEPLOY of app {app_id}.")
    print("  This is not a silent skip. The live program predates the committed")
    print("  contract. Update/Delete are blocked, so this app cannot be patched")
    print("  in place. Deploy a NEW TestNet app from the committed TEAL, then")
    print("  retarget APP_ID / PINNED_ON_CHAIN_SHA512_256. Checklist: BLOCKERS.md")
    print("  Local source-to-TEAL gates can stay green; chain match cannot until then.")
    print()
    print("  Do not treat any review of this source as a review of the live")
    print("  application until the follow-up workflow is green.")


if __name__ == "__main__":
    # An unexpected crash must exit 2 ("could not check"), never 1 ("drift"). A CI gate
    # that reports a bug in this script as a deployment mismatch would burn real time
    # chasing a finding that does not exist.
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(2)
    except Exception as exc:  # noqa: BLE001 - deliberately broad; see comment above
        print(f"\nCOULD NOT CHECK: unexpected {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(2)
