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
import sys
import urllib.error
import urllib.request

REPO_ROOT = pathlib.Path(__file__).resolve().parent
DEFAULT_TEAL = REPO_ROOT / "out" / "TrelyanInscription.approval.teal"
DEFAULT_SOURCE = REPO_ROOT / "inscription.py"

# TestNet deployment under review. Not a security constant - changing it only
# changes which application is inspected, never what "correct" means.
DEFAULT_APP_ID = 763809096
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


def recompile_from_source(source: pathlib.Path, out_dir: pathlib.Path) -> None:
    """Re-derive the committed TEAL from inscription.py, so the artifact is not
    trusted either. Requires puya; callers treat absence as 'could not check'."""
    try:
        subprocess.run(
            [sys.executable, "-m", "puyapy", str(source), "--out-dir", str(out_dir)],
            check=True,
            capture_output=True,
        )
    except FileNotFoundError as exc:
        raise CheckError("puya not available; omit --recompile or install contracts/requirements.txt") from exc
    except subprocess.CalledProcessError as exc:
        raise CheckError(f"puya failed: {exc.stderr.decode(errors='replace')[:500]}") from exc


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
            before = args.teal.read_bytes() if args.teal.exists() else None
            recompile_from_source(args.source, args.teal.parent)
            after = args.teal.read_bytes()
            if before is not None and before != after:
                print("    FAIL  committed TEAL artifact is stale with respect to inscription.py")
                return 1
            print("    ok    committed TEAL matches a fresh compile of the source")

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

    print(f"DRIFT - application {args.app_id} is NOT running the committed source.")
    print(f"  committed source builds to : {expected_hash}  ({len(expected)} B)")
    print(f"  chain is actually serving  : {deployed_hash}  ({len(deployed)} B)")
    print()
    print("  The deployed program predates the committed contract. Redeploy from the")
    print("  committed artifact, or explain the divergence before treating any review")
    print("  of this source as a review of the live application.")
    return 1


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
