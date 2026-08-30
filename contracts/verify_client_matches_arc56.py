#!/usr/bin/env python3
"""The generated typed client must embed the COMMITTED contract spec — verbatim.

Found 2026-08-27, the hard way: the coverage map had a hole exactly one file wide.
`verify_teal_matches_source.py` proves source -> TEAL; the TestNet follow-up
(`testnet-followup.yml`) proves committed TEAL -> deployed TestNet app; but the
LocalNet test suite deploys through
`trelyan_client.py`, whose `_APP_SPEC_JSON` is frozen at GENERATION time — and nothing
compared it to `contracts/out/TrelyanInscription.arc56.json`. The client was last generated
in June; the zero-address and TCE-76 guards landed after; result: the whole contract suite
was exercising a stale program. Three tests failed honestly the day the suite finally ran —
this check makes the drift a one-line CI failure instead of a debugging session.

The comparison covers the BEHAVIORAL keys only — byteCode, methods, state, bareActions,
structs, name, arcs — because the generator legitimately drops or rewrites build metadata
(compilerInfo, sourceInfo) when embedding, and demanding equality there would make this
check fail forever on a freshly generated client (observed on first run, 2026-08-27).
byteCode is the key that caught the original drift: it IS the program the suite deploys.

Regenerate with:
    algokit generate client contracts/out/TrelyanInscription.arc56.json \
        --output contracts/trelyan_client.py

Exit codes: 0 = match; 1 = drift (regenerate the client); 2 = could not even compare —
treated as failure because a comparison that cannot run must never count as a pass.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLIENT = HERE / "trelyan_client.py"
ARC56 = HERE / "out" / "TrelyanInscription.arc56.json"


def main() -> int:
    try:
        client_text = CLIENT.read_text(encoding="utf-8")
        arc = json.loads(ARC56.read_text(encoding="utf-8"))
    except OSError as e:
        print(f"CANNOT COMPARE: {e}", file=sys.stderr)
        return 2

    m = re.search(r'^_APP_SPEC_JSON = r?"""(.*?)"""', client_text, re.M | re.S)
    if not m:
        print(
            "CANNOT COMPARE: _APP_SPEC_JSON not found in trelyan_client.py — the generator "
            "layout changed; update this check's extraction, do not delete it.",
            file=sys.stderr,
        )
        return 2
    try:
        embedded = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        print(f"CANNOT COMPARE: embedded spec is not valid JSON: {e}", file=sys.stderr)
        return 2

    material = ["byteCode", "methods", "state", "bareActions", "structs", "name", "arcs"]
    drifted = [k for k in material if embedded.get(k) != arc.get(k)]
    if not drifted:
        print("client-matches-arc56: OK (byteCode, methods, state, bareActions, structs, name, arcs all match)")
        return 0

    for k in drifted:
        print(f"DRIFT in behavioral key {k!r}", file=sys.stderr)
    print(
        "trelyan_client.py embeds a DIFFERENT contract spec than contracts/out/"
        "TrelyanInscription.arc56.json. The test suite deploys the client's copy, so a "
        "stale client silently tests a stale program. Regenerate:\n"
        "    algokit generate client contracts/out/TrelyanInscription.arc56.json "
        "--output contracts/trelyan_client.py",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
