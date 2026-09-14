#!/usr/bin/env python3
"""Verify a deployed application against the committed artifacts, one component at a time.

Compared - each on its own output line, and MATCH only if every one of them matches:

    approval program      deployed bytes  ==  contracts/out/TrelyanInscription.approval.teal, assembled
    clear-state program   deployed bytes  ==  contracts/out/TrelyanInscription.clear.teal, assembled
    global-state-schema   deployed {num-uint, num-byte-slice}  ==  ARC-56 state.schema.global {ints, bytes}
    local-state-schema    deployed {num-uint, num-byte-slice}  ==  ARC-56 state.schema.local {ints, bytes}
    extra-program-pages   deployed value  ==  the minimum the two assembled programs require

NOT compared: the application's global-state CONTENTS (including the admin address), its box
contents, and its creator. A MATCH says the deployed app runs the committed programs under the
committed schemas and page count. It says nothing about who created the app or what state it
has accumulated since.

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
    contracts/out/TrelyanInscription.approval.teal   .clear.teal   .arc56.json   [committed artifacts]
        |  algod /v2/teal/compile (deterministic       |                |  state.schema
        |  assembly for a given AVM version)           |                |
        v                                              v                v
    expected approval bytes        expected clear-state bytes     expected schemas
        |                                              |                |
        +-- total size -> expected extra-program-pages |                |
                          ==?                          ==?              ==?
    algod /v2/applications/{id} --> deployed approval / clear-state bytes, schemas, extra-program-pages

WHERE THE EXPECTED extra-program-pages COMES FROM. Neither artifact declares a value. The ARC-56
spec has no field for it (the committed TrelyanInscription.arc56.json carries none), and
contracts/deploy_testnet.py creates the app with `factory.send.create.create()` without passing
`extra_program_pages`. algokit-utils v4 then fills it in with `calculate_extra_program_pages`:
max(0, (len(approval) + len(clear) - 1) // 2048), the minimum the protocol accepts for those two
programs (2048 B per page). So the committed artifacts fix the value through their assembled sizes,
and this script applies the same formula to the same bytes. A deployed value above that minimum
is reported as drift: it is not what the deploy script creates.

MISSING FIELDS. A missing field must never produce MATCH or DRIFT by accident:
  * no `params`, `approval-program`, `clear-state-program`, `global-state-schema` or
    `local-state-schema` in the algod response -> exit 2 (could not check);
  * a schema object that is present but lacks `num-uint` or `num-byte-slice` -> that count is 0;
    likewise a missing `ints` / `bytes` inside the ARC-56 state.schema.global / .local objects;
  * `extra-program-pages` absent -> 0 (algod omits it when it is zero);
  * no state.schema, or no global / local object inside it, in the ARC-56 file -> exit 2.

Trust note for reviewers: by default the same algod service both assembles the
committed TEAL and serves the deployed application, so a dishonest endpoint could
lie consistently across both. Pass --compile-url pointing at an independent
node (or a local `goal clerk compile`) to split that trust; it is used for BOTH
assemblies. The comparison is only as strong as the weaker of the two sources.

Exit codes:  0 every compared component of the deployed application equals what the committed artifacts produce
             1 DRIFT - at least one compared component differs (every differing component is named)
             2 could not complete the check (network, missing artifact, missing field, ...)
"""

from __future__ import annotations

import argparse
import base64
import binascii
import hashlib
import json
import pathlib
import subprocess
import tempfile
import sys
import urllib.error
import urllib.request
from collections.abc import Sequence

REPO_ROOT = pathlib.Path(__file__).resolve().parent
DEFAULT_TEAL = REPO_ROOT / "out" / "TrelyanInscription.approval.teal"
DEFAULT_CLEAR_TEAL = REPO_ROOT / "out" / "TrelyanInscription.clear.teal"
DEFAULT_ARC56 = REPO_ROOT / "out" / "TrelyanInscription.arc56.json"
DEFAULT_SOURCE = REPO_ROOT / "inscription.py"

# TestNet deployment under review. Not a security constant - changing it only
# changes which application is inspected, never what "correct" means.
DEFAULT_APP_ID = 770964251
DEFAULT_ALGOD = "https://testnet-api.algonode.cloud"

# Bytes per program page: algosdk.constants.APP_PAGE_MAX_SIZE, the consensus MaxAppProgramLen,
# and the page size algokit-utils' calculate_extra_program_pages divides by.
PROGRAM_PAGE_BYTES = 2048

APPROVAL = "approval program"
CLEAR_STATE = "clear-state program"
GLOBAL_SCHEMA = "global-state-schema"
LOCAL_SCHEMA = "local-state-schema"
EXTRA_PAGES = "extra-program-pages"


class CheckError(Exception):
    """The check could not be completed (as distinct from completing and failing)."""


class Component:
    """One compared property: the value the committed artifacts produce and the deployed one.

    A plain class, not a @dataclass: the tests (and test_testnet_drift_banner.py) load this file
    with importlib.util.spec_from_file_location without registering it in sys.modules, and
    @dataclass under `from __future__ import annotations` looks its module up there and crashes.
    """

    __slots__ = ("name", "expected", "actual", "expected_text", "actual_text")

    def __init__(self, name: str, expected: object, actual: object,
                 expected_text: str, actual_text: str) -> None:
        self.name = name
        self.expected = expected
        self.actual = actual
        self.expected_text = expected_text
        self.actual_text = actual_text

    @property
    def matches(self) -> bool:
        return self.expected == self.actual


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


def fetch_app_params(app_id: int, algod: str, timeout: int) -> dict:
    """The `params` object of GET /v2/applications/{id}. Absent or malformed -> could not check."""
    body = _get_json(f"{algod.rstrip('/')}/v2/applications/{app_id}", timeout)
    params = body.get("params") if isinstance(body, dict) else None
    if not isinstance(params, dict):
        raise CheckError(f"application {app_id} returned no params object")
    return params


def deployed_program(params: dict, key: str, app_id: int) -> bytes:
    """A deployed program's bytes. A missing, empty or non-base64 field is 'could not check'."""
    raw = params.get(key)
    if not isinstance(raw, str) or not raw:
        raise CheckError(f"application {app_id} returned no {key}")
    try:
        program = base64.b64decode(raw, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise CheckError(f"application {app_id} returned a {key} that is not valid base64") from exc
    if not program:
        raise CheckError(f"application {app_id} returned an empty {key}")
    return program


def _count(obj: dict, key: str, where: str) -> int:
    """A schema count or page count. Missing means 0; anything but a non-negative int is an error."""
    value = obj.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CheckError(f"{where}: {key} is {value!r}, not a non-negative integer")
    return value


def deployed_schema(params: dict, key: str, app_id: int) -> tuple[int, int]:
    """(num-uint, num-byte-slice) of a deployed state schema. The object itself must be present."""
    obj = params.get(key)
    if not isinstance(obj, dict):
        raise CheckError(f"application {app_id} returned no {key}")
    where = f"application {app_id} {key}"
    return _count(obj, "num-uint", where), _count(obj, "num-byte-slice", where)


def arc56_schemas(arc56: pathlib.Path) -> dict[str, tuple[int, int]]:
    """{global-state-schema: (ints, bytes), local-state-schema: (ints, bytes)} from an ARC-56 spec."""
    try:
        spec = json.loads(arc56.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CheckError(f"artifact not found: {arc56}") from exc
    except (OSError, ValueError) as exc:
        raise CheckError(f"cannot read {arc56} as JSON: {exc}") from exc
    state = spec.get("state") if isinstance(spec, dict) else None
    schema = state.get("schema") if isinstance(state, dict) else None
    if not isinstance(schema, dict):
        raise CheckError(f"{arc56} has no state.schema")
    out: dict[str, tuple[int, int]] = {}
    for side, name in (("global", GLOBAL_SCHEMA), ("local", LOCAL_SCHEMA)):
        obj = schema.get(side)
        if not isinstance(obj, dict):
            raise CheckError(f"{arc56} has no state.schema.{side}")
        where = f"{arc56.name} state.schema.{side}"
        out[name] = (_count(obj, "ints", where), _count(obj, "bytes", where))
    return out


def required_extra_pages(approval: bytes, clear: bytes) -> int:
    """The extra-program-pages a create with these programs gets from deploy_testnet.py.

    Same formula as algokit-utils' calculate_extra_program_pages, which fills the value in because
    the deploy script does not pass one: the minimum page count that fits both programs.
    """
    return max(0, (len(approval) + len(clear) - 1) // PROGRAM_PAGE_BYTES)


def _program_text(program: bytes) -> str:
    return f"{len(program)} B sha512_256 {sha512_256(program)}"


def _schema_text(schema: tuple[int, int]) -> str:
    return f"num-uint {schema[0]}, num-byte-slice {schema[1]}"


def build_components(*, expected_approval: bytes, expected_clear: bytes,
                     expected_schemas: dict[str, tuple[int, int]], params: dict,
                     app_id: int) -> list[Component]:
    """Read every deployed component out of `params` and pair it with its expected value.

    Every read happens here, before any verdict is printed, so a missing field aborts with
    'could not check' instead of producing a partial report.
    """
    deployed_approval = deployed_program(params, "approval-program", app_id)
    deployed_clear = deployed_program(params, "clear-state-program", app_id)
    deployed_global = deployed_schema(params, GLOBAL_SCHEMA, app_id)
    deployed_local = deployed_schema(params, LOCAL_SCHEMA, app_id)
    deployed_pages = _count(params, EXTRA_PAGES, f"application {app_id}")
    pages_note = "" if EXTRA_PAGES in params else " (field absent; algod omits zero)"
    expected_pages = required_extra_pages(expected_approval, expected_clear)
    total = len(expected_approval) + len(expected_clear)
    return [
        Component(APPROVAL, expected_approval, deployed_approval,
                  _program_text(expected_approval), _program_text(deployed_approval)),
        Component(CLEAR_STATE, expected_clear, deployed_clear,
                  _program_text(expected_clear), _program_text(deployed_clear)),
        Component(GLOBAL_SCHEMA, expected_schemas[GLOBAL_SCHEMA], deployed_global,
                  _schema_text(expected_schemas[GLOBAL_SCHEMA]), _schema_text(deployed_global)),
        Component(LOCAL_SCHEMA, expected_schemas[LOCAL_SCHEMA], deployed_local,
                  _schema_text(expected_schemas[LOCAL_SCHEMA]), _schema_text(deployed_local)),
        Component(EXTRA_PAGES, expected_pages, deployed_pages,
                  f"{expected_pages} (required by {total} B of assembled program)",
                  f"{deployed_pages}{pages_note}"),
    ]


def _read_artifact(path: pathlib.Path) -> bytes:
    try:
        return path.read_bytes()
    except FileNotFoundError as exc:
        raise CheckError(f"artifact not found: {path}") from exc
    except OSError as exc:
        raise CheckError(f"cannot read {path}: {exc}") from exc


def _shown(path: pathlib.Path) -> pathlib.Path:
    """Repo-relative when the artifact is in the repo, absolute otherwise.

    An artifact supplied from elsewhere is a legitimate use (comparing an out-of-tree build),
    so this must not raise.
    """
    try:
        return path.resolve().relative_to(REPO_ROOT.parent)
    except ValueError:
        return path.resolve()


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


def check_recompile(args: argparse.Namespace, compile_url: str) -> int:
    """--recompile: the committed approval TEAL, clear-state TEAL and ARC-56 state.schema must be
    what a fresh puya compile of the source produces. 0 = all three agree, 1 = at least one differs."""
    print(f"[0] re-deriving the committed artifacts from {args.source.name} via puya")
    committed_approval = _read_artifact(args.teal)
    committed_clear = _read_artifact(args.clear_teal)
    committed_schemas = arc56_schemas(args.arc56)

    # Compile into a TEMPORARY directory, never over the committed artifacts.
    #
    # This previously passed `args.teal.parent`, i.e. contracts/out/, so a tool whose whole
    # job is to VERIFY the committed artifacts silently rewrote five of them (both .teal,
    # both .puya.map, and the .arc56.json) as a side effect of being run. A verifier that
    # mutates its subject cannot be run safely on a clean tree, and its second run compares
    # the output against itself.
    with tempfile.TemporaryDirectory(prefix="trelyan-recompile-") as tmp:
        fresh_dir = pathlib.Path(tmp)
        recompile_from_source(args.source, fresh_dir, _committed_avm_version(args.teal))
        fresh_approval = _read_artifact(fresh_dir / args.teal.name)
        fresh_clear = _read_artifact(fresh_dir / args.clear_teal.name)
        fresh_schemas = arc56_schemas(fresh_dir / args.arc56.name)

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
    failed: list[str] = []
    for label, committed, fresh in (("approval TEAL", committed_approval, fresh_approval),
                                    ("clear-state TEAL", committed_clear, fresh_clear)):
        if assemble(committed, compile_url, args.timeout) != assemble(fresh, compile_url, args.timeout):
            print(f"    FAIL  committed {label} does not assemble to the same program as a fresh compile")
            failed.append(label)
        elif committed != fresh:
            print(f"    ok    committed {label} assembles identically to a fresh compile")
            print("          (the TEAL TEXT differs - comment/source-map formatting or line endings; "
                  "the program bytes are the same)")
        else:
            print(f"    ok    committed {label} matches a fresh compile of the source, byte for byte")

    if committed_schemas != fresh_schemas:
        print(f"    FAIL  committed ARC-56 state.schema differs from a fresh compile: "
              f"committed {committed_schemas}, fresh {fresh_schemas}")
        failed.append("ARC-56 state.schema")
    else:
        print("    ok    committed ARC-56 state.schema matches a fresh compile")

    if failed:
        print(f"\nDRIFT - the committed artifacts are not what {args.source.name} compiles to: "
              f"{', '.join(failed)}")
        return 1
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--app-id", type=int, default=DEFAULT_APP_ID)
    parser.add_argument("--algod", default=DEFAULT_ALGOD, help="node used to read the deployed application")
    parser.add_argument("--compile-url", default=None,
                        help="independent node used to assemble BOTH committed TEAL files (defaults to "
                             "--algod; set this to a different provider to avoid trusting one endpoint "
                             "for both halves)")
    parser.add_argument("--teal", type=pathlib.Path, default=DEFAULT_TEAL,
                        help="committed approval TEAL")
    parser.add_argument("--clear-teal", type=pathlib.Path, default=DEFAULT_CLEAR_TEAL,
                        help="committed clear-state TEAL")
    parser.add_argument("--arc56", type=pathlib.Path, default=DEFAULT_ARC56,
                        help="committed ARC-56 spec (its state.schema is compared)")
    parser.add_argument("--source", type=pathlib.Path, default=DEFAULT_SOURCE)
    parser.add_argument("--recompile", action="store_true",
                        help="first re-derive the approval TEAL, clear-state TEAL and ARC-56 state.schema "
                             "from inscription.py (requires puya)")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args(argv)

    compile_url = args.compile_url or args.algod

    try:
        if args.recompile:
            rc = check_recompile(args, compile_url)
            if rc:
                return rc

        approval_teal = _read_artifact(args.teal)
        clear_teal = _read_artifact(args.clear_teal)
        expected_schemas = arc56_schemas(args.arc56)
        print("[1] committed artifacts")
        print(f"    approval TEAL      {_shown(args.teal)}  ({len(approval_teal)} B TEAL)")
        print(f"    clear-state TEAL   {_shown(args.clear_teal)}  ({len(clear_teal)} B TEAL)")
        print(f"    ARC-56 spec        {_shown(args.arc56)}  (state.schema)")

        expected_approval = assemble(approval_teal, compile_url, args.timeout)
        expected_clear = assemble(clear_teal, compile_url, args.timeout)
        print(f"[2] both TEAL files assembled via {compile_url}")

        params = fetch_app_params(args.app_id, args.algod, args.timeout)
        components = build_components(
            expected_approval=expected_approval,
            expected_clear=expected_clear,
            expected_schemas=expected_schemas,
            params=params,
            app_id=args.app_id,
        )
        print(f"[3] deployed app {args.app_id} read via {args.algod}")

    except CheckError as exc:
        print(f"\nCOULD NOT CHECK: {exc}", file=sys.stderr)
        return 2

    print("[4] components: committed artifacts | deployed app")
    for component in components:
        verdict = "MATCH" if component.matches else "DRIFT"
        print(f"    {verdict}  {component.name:<20} committed {component.expected_text} | "
              f"deployed {component.actual_text}")

    differing = [component.name for component in components if not component.matches]
    print()
    if not differing:
        print(f"MATCH - application {args.app_id}: "
              f"{', '.join(component.name for component in components)} "
              f"all equal what the committed artifacts produce.")
        print("  Not compared: global-state contents (including the admin address), box contents, creator.")
        return 0

    approval = components[0]
    print_awaiting_redeploy(
        app_id=args.app_id,
        expected_hash=sha512_256(approval.expected),
        expected_len=len(approval.expected),
        deployed_hash=sha512_256(approval.actual),
        deployed_len=len(approval.actual),
        differing=differing,
    )
    return 1


def print_awaiting_redeploy(
    *,
    app_id: int,
    expected_hash: str,
    expected_len: int,
    deployed_hash: str,
    deployed_len: int,
    differing: Sequence[str] = (APPROVAL,),
) -> None:
    """Print the documented drift finding. Always a failure, never a skip.

    `differing` names every component that did not match; the per-component lines printed just
    before this banner carry both sides of each. The approval program's hashes and sizes are
    repeated here when it is among them, because that is the drift this banner was first written
    for. App 763809096 cannot be patched in place (Update/Delete are blocked, I1/I5).
    The one-shot checklist is BLOCKERS.md.
    """
    print(f"DRIFT - application {app_id} is NOT what the committed artifacts produce.")
    print(f"  differing: {', '.join(differing)}")
    if APPROVAL in differing:
        print(f"  approval program - committed TEAL assembles to: {expected_hash}  ({expected_len} B)")
        print(f"  approval program - chain is actually serving  : {deployed_hash}  ({deployed_len} B)")
    print()
    print(f"AWAITING TESTNET REDEPLOY of app {app_id}.")
    print("  This is not a silent skip. The live application differs from the committed")
    print("  artifacts in the component(s) named above. Update/Delete are blocked, so this")
    print("  app cannot be patched in place. Deploy a NEW TestNet app from the committed")
    print("  artifacts, then retarget APP_ID / PINNED_ON_CHAIN_SHA512_256 /")
    print("  PINNED_CLEAR_STATE_SHA512_256. Checklist: BLOCKERS.md")
    print("  Local source-to-TEAL gates can stay green; chain match cannot until then.")
    print()
    print("  Do not treat any review of this source as a review of the live app until the")
    print("  follow-up workflow is green. Even then, what is compared is the approval and")
    print("  clear-state programs, both state schemas and extra-program-pages; global-state")
    print("  contents (including the admin address), box contents and the creator are not.")


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
