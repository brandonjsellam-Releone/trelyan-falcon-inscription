#!/usr/bin/env python3
"""
TRELYAN reviewer verification — one command, no trust required.
  pip install trelyan-pq && python3 verify_trelyan.py
Checks: [1] package constants  [2] pinned golden vectors (offline)
        [3] live TestNet app 763809096 (bytecode fingerprint + source correspondence)
        [4] on-chain boxes (registered Falcon keys / inscription records)
        [5] message reconstruction for a live cell (byte-exact, recomputed locally)
Read-only. Only dependency: trelyan-pq (stdlib otherwise).
"""
import json, os, sys, base64, pathlib, urllib.request

APP_ID = 763809096
# The fingerprint of the program deployed on 2026-06-02, recorded here on 2026-06-17 (660 B).
#
# Read what this constant can and cannot tell you. Because the contract blocks Update and
# Delete (invariants I1/I5) the deployed bytecode is immutable, so comparing it to this value
# can only ever succeed. It is evidence that the application was not replaced; it is NOT
# evidence that the deployment matches contracts/inscription.py, and it was previously
# presented as though it were. Those are separate claims and only the second one matters to a
# reviewer. The second is checked below, and needs the committed artifact to answer.
PINNED_ON_CHAIN_SHA512_256 = "d24d9071209f526a2075542d9408295d78f83ca5ed4c8cc233000130dcc97d44"
# Committed build artifact, when this script is run from a repo clone rather than downloaded
# on its own. sdk/examples/ -> repo root -> contracts/out/.
# Resolved DEFENSIVELY, and it must never raise. `parents[2]` assumed this file sits at
# <repo>/sdk/examples/, which is true in a clone and false in Dockerfile.verify, where the script
# was copied bare into WORKDIR /trelyan. There `parents` is ['/trelyan', '/'] and `parents[2]`
# raised IndexError at MODULE LEVEL - before the first print - so the documented hermetic
# reviewer command (REVIEWER.md, AUDIT_READINESS.md) produced a traceback and ran no checks at
# all. It failed closed, so there was no false assurance, but the docs promise 15/15.
def _find_committed_teal():
    env = os.environ.get("TRELYAN_COMMITTED_TEAL")
    if env:
        return pathlib.Path(env)
    rel = pathlib.Path("contracts") / "out" / "TrelyanInscription.approval.teal"
    here = pathlib.Path(__file__).resolve()
    for base in [here.parent, *here.parents]:
        cand = base / rel
        if cand.exists():
            return cand
    return here.parent / rel          # non-existent path; .exists() is False, which is handled


COMMITTED_TEAL = _find_committed_teal()
ALGOD = "https://testnet-api.algonode.cloud"
TESTNET_GENESIS_B64 = "SGO1GKSzyE7IEPItTxCByw9x8FmnrCDexi9/cOUJOiI="
PASS, FAIL, NOT_CHECKED = 0, 0, 0
def check(name, ok, detail=""):
    global PASS, FAIL
    PASS, FAIL = PASS + (1 if ok else 0), FAIL + (0 if ok else 1)
    print(("  PASS  " if ok else "  FAIL  ") + name + (f"  [{detail}]" if detail else ""))

def not_checked(name, why):
    """A check that did not run is neither a pass nor a failure, and must not be silent.

    Added 2026-08-16. Skipped checks were previously printed as prose and counted as NOTHING,
    so the pass count was IDENTICAL whether or not they ran: from a repo clone this script
    reported 17 passed / 1 failed, and from the advertised hermetic container 17 passed /
    0 failed - green, on the exact divergence the contract-drift CI job is red on, with no
    signal that a check had been dropped. Counting them and exiting 2 mirrors
    contracts/verify_deployment.py, which already separates "could not check" from "agreed".
    """
    global NOT_CHECKED
    NOT_CHECKED += 1
    print("  SKIP  " + name + f"  [{why}]")

def get(path):
    with urllib.request.urlopen(ALGOD + path, timeout=20) as r:
        return json.load(r)

print("== [1] package ==")
import trelyan_pq as t
# Was `check("trelyan-pq import", True, ...)` - a literal True, so it could not fail. The import
# on the line above already succeeded or this file would have raised, so assert something the
# import does NOT guarantee: that the package reports a real released version rather than the
# source-tree fallback.
check("trelyan-pq import",
      bool(getattr(t, "__version__", "")) and not t.__version__.endswith("+source"),
      f"v{t.__version__}")
check("DOMAIN_TAG", t.DOMAIN_TAG == b"TRELYAN-INSCRIPTION-v1")
check("MESSAGE_LEN == 102", t.MESSAGE_LEN == 102)
check("det1024 header 0xBA", t.DET_COMPRESSED_HEADER == 0xBA)
check("sig max 1423 / pk 1793", t.SIG_COMPRESSED_MAXSIZE == 1423 and t.PUBKEY_LEN == 1793)

print("== [2] golden vectors (offline) ==")
check("sha512_256('TRELYAN')", t.sha512_256(b"TRELYAN").hex() == "5a8b372a74e2993ecbcdb6d8fb2276ec72e3060f0e968f06a719eebafb47332e")
art = t.sha512_256(b"hello, after Q-Day")
M = t.build_message(1001, 1, art, bytes(32))
check("build_message(1001,1,...) byte-exact", M.hex().startswith("5452454c59414e2d494e534352495054494f4e2d7631") and len(M) == 102)
check("box names k_/o_/i_", t.committed_pubkey_box_name(1).hex() == "6b5f0000000000000001" and t.inscription_box_name(258).hex() == "695f0000000000000102")

print("== [3] live TestNet app ==")
app = get(f"/v2/applications/{APP_ID}")
check(f"app {APP_ID} exists", app.get("id") == APP_ID)
ap = base64.b64decode(app["params"]["approval-program"])
check("approval program fetched", len(ap) > 0, f"{len(ap)} bytes")
fp = t.sha512_256(ap).hex()
check("deployed app not replaced since 2026-06-17 pin", fp == PINNED_ON_CHAIN_SHA512_256, fp[:16] + "...")
print(f"        bytecode sha512_256: {fp}")

# The claim that actually matters: is the deployed program what the committed contract builds?
# Answering it requires assembling the committed TEAL, so it is only possible from a repo
# clone. When it cannot be answered it is reported as NOT CHECKED and counted as neither a
# pass nor a failure - silently omitting it is how the weaker check above came to stand in for
# this one.
if COMMITTED_TEAL.exists():
    _req = urllib.request.Request(ALGOD + "/v2/teal/compile", data=COMMITTED_TEAL.read_bytes(),
                                  headers={"Content-Type": "text/plain"})
    with urllib.request.urlopen(_req, timeout=20) as _r:
        _built = base64.b64decode(json.load(_r)["result"])
    _built_fp = t.sha512_256(_built).hex()
    check("deployed bytecode matches the committed contract", _built_fp == fp, f"source builds to {_built_fp[:16]}...")
    if _built_fp != fp:
        print(f"        committed source builds to : {_built_fp}  ({len(_built)} B)")
        print(f"        chain is actually serving  : {fp}  ({len(ap)} B)")
        print(f"AWAITING TESTNET REDEPLOY of app {APP_ID}.")
        print("        This is not a silent skip. The live program predates the committed")
        print("        contract (Update/Delete blocked — cannot patch in place).")
        print("        Deploy a NEW TestNet app from the committed TEAL, then retarget")
        print("        APP_ID / PINNED_ON_CHAIN_SHA512_256. Checklist: BLOCKERS.md")
else:
    not_checked("deployed bytecode matches the committed contract",
                f"no committed artifact found at {COMMITTED_TEAL} "
                f"(set TRELYAN_COMMITTED_TEAL to override)")
    print("        Run contracts/verify_deployment.py from a repo clone to compare the deployed")
    print("        program against a fresh assembly of contracts/out/*.teal.")

print("== [4] on-chain boxes ==")
boxes = get(f"/v2/applications/{APP_ID}/boxes")["boxes"]
names = [base64.b64decode(b["name"]) for b in boxes]
ks = [n for n in names if n[:2] == b"k_"]; iss = [n for n in names if n[:2] == b"i_"]
check("boxes present", len(names) > 0, f"{len(names)} total: {len(ks)} pubkey, {len(iss)} inscription")
ver_target = None
if not ks:
    # A loop over an empty list asserts nothing and printed nothing - the vacuous-domain shape.
    not_checked("registered Falcon public keys on-chain", "no k_ boxes returned by algod")
for n in ks[:3]:
    cell = int.from_bytes(n[2:], "big")
    bx = get(f"/v2/applications/{APP_ID}/box?name=" + urllib.parse.quote("b64:" + base64.b64encode(n).decode()))
    pk = base64.b64decode(bx["value"])
    check(f"cell {cell}: registered Falcon pk", len(pk) == 1793 and pk[0] == 0x0A, f"1793 B, header 0x{pk[0]:02x}")
    ver_target = ver_target or (cell, pk)

print("== [5] live record reconstruction ==")
if iss:
    n = iss[0]; cell = int.from_bytes(n[2:], "big")
    bx = get(f"/v2/applications/{APP_ID}/box?name=" + urllib.parse.quote("b64:" + base64.b64encode(n).decode()))
    rec = base64.b64decode(bx["value"])
    # InscriptionRecord is an arc4.Struct, so the artifact hash is NOT at offset 0. The ARC4
    # head packs the fixed-size fields in declaration order (contracts/inscription.py):
    #   version         arc4.UInt8                  rec[0:1]
    #   cell_id         arc4.UInt64                 rec[1:9]
    #   artifact_hash   StaticArray[Byte, 32]       rec[9:41]   <- the 32 bytes that were signed
    #   inscribed_round arc4.UInt64                 rec[41:49]
    #   inscriber       arc4.Address                rec[49:81]
    #   payload_uri     arc4.DynamicBytes           rec[81:83] offset -> tail
    # This previously read rec[0:32], i.e. version || cell_id || the first 23 bytes of the hash,
    # so M was rebuilt from bytes no signature ever covered. It went unnoticed because the only
    # assertion was len(M) == 102, and build_message either raises or returns exactly 102 bytes
    # - it cannot report the wrong hash. The checks below are chosen so they CAN fail.
    check(f"cell {cell}: inscription record read", len(rec) >= 83, f"{len(rec)} B")
    gh = base64.b64decode(TESTNET_GENESIS_B64)
    check("record version == 1", rec[0] == 1, f"0x{rec[0]:02x}")
    # Independent cross-check, and the one that actually validates the offsets above: the cell id
    # inside the record must equal the one in the box NAME. Two sources, one claim. (Note that
    # comparing M's embedded hash against art32 would NOT have caught the old bug - both sides
    # shift together - which is why the layout is pinned by this comparison instead.)
    rec_cell = int.from_bytes(rec[1:9], "big")
    check("record cell_id matches its box name", rec_cell == cell, f"record {rec_cell} vs box {cell}")
    art32 = rec[9:41]
    M_live = t.build_message(APP_ID, cell, art32, gh)
    # Cross-check the SDK's message layout against the spec offsets derived here, so a drift in
    # build_message shows up rather than being absorbed: tag(22)|app(8)|cell(8)|hash(32)|genesis(32).
    check("M matches the spec layout at every field offset",
          M_live[:22] == t.DOMAIN_TAG and M_live[22:30] == APP_ID.to_bytes(8, "big")
          and M_live[38:70] == art32 and M_live[70:] == gh,
          "tag|app|cell|hash|genesis")
    print(f"        artifact_hash (on-chain) = {art32.hex()}")
    print(f"        M = {M_live.hex()[:64]}...")
    print("        note: the signature is not stored on-chain (it is a call argument the AVM")
    print("        verifies), so M is reconstructed here, not checked against a signature.")
else:
    print("        (no inscription boxes yet on this app - registration-stage deployment)")
# Whether a full local signature verification is possible depends on the C LIBRARY loading, not
# on the import succeeding. `verify` is re-exported from trelyan_pq/__init__.py, so the import
# always succeeds and the except below was unreachable: this printed "available locally: YES" on
# machines with no library at all. Force the load and report what actually happened.
try:
    from trelyan_pq import falcon as _falcon
    _falcon.default_signer()._lib_ref()   # private on purpose: the public API is lazy, and a lazy
                                          # probe answers "did the import work", not "is the
                                          # signer usable", which is the question being asked
    print("        full falcon verify available locally: YES")
    print("        (signature order is verify(sig, pubkey, message) - sig FIRST, not the message)")
except Exception as e:
    print(f"        full local falcon verify: NOT available ({type(e).__name__}: {str(e).splitlines()[0][:90]})")
    print("        the structural checks above stand on their own; they do not need the C library")

print(f"\n== RESULT: {PASS} passed, {FAIL} failed, {NOT_CHECKED} not checked ==")
if FAIL:
    sys.exit(1)
if NOT_CHECKED:
    # Exit 2, not 0. "I could not check that" is not "that is fine", and the pass count alone
    # cannot tell them apart - which is exactly how the hermetic container reported green.
    print("   NOT ALL CHECKS RAN. This is not a pass. See the SKIP lines above.")
    sys.exit(2)
sys.exit(0)
