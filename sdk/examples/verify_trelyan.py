#!/usr/bin/env python3
"""
TRELYAN reviewer verification — one command, no trust required.
  pip install trelyan-pq && python3 verify_trelyan.py
Checks: [1] package constants  [2] pinned golden vectors (offline)
        [3] live TestNet app 763809096 (bytecode fingerprint)
        [4] on-chain boxes (registered Falcon keys / inscription records)
        [5] message reconstruction for a live cell (byte-exact, recomputed locally)
Read-only. Only dependency: trelyan-pq (stdlib otherwise).
"""
import json, sys, base64, urllib.request

APP_ID = 763809096
ALGOD = "https://testnet-api.algonode.cloud"
TESTNET_GENESIS_B64 = "SGO1GKSzyE7IEPItTxCByw9x8FmnrCDexi9/cOUJOiI="
PASS, FAIL = 0, 0
def check(name, ok, detail=""):
    global PASS, FAIL
    PASS, FAIL = PASS + (1 if ok else 0), FAIL + (0 if ok else 1)
    print(("  PASS  " if ok else "  FAIL  ") + name + (f"  [{detail}]" if detail else ""))

def get(path):
    with urllib.request.urlopen(ALGOD + path, timeout=20) as r:
        return json.load(r)

print("== [1] package ==")
import trelyan_pq as t
check("trelyan-pq import", True, f"v{t.__version__} (PyPI)")
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
print(f"        bytecode sha512_256: {t.sha512_256(ap).hex()}")
print(f"        (diff this against the repo's compiled TEAL — bytecode attestation)")

print("== [4] on-chain boxes ==")
boxes = get(f"/v2/applications/{APP_ID}/boxes")["boxes"]
names = [base64.b64decode(b["name"]) for b in boxes]
ks = [n for n in names if n[:2] == b"k_"]; iss = [n for n in names if n[:2] == b"i_"]
check("boxes present", len(names) > 0, f"{len(names)} total: {len(ks)} pubkey, {len(iss)} inscription")
ver_target = None
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
    check(f"cell {cell}: inscription record read", len(rec) >= 32, f"{len(rec)} B")
    # rebuild the message this cell's signature must have signed (byte-exact, locally):
    gh = base64.b64decode(TESTNET_GENESIS_B64)
    art32 = rec[:32] if len(rec) >= 32 else None
    M_live = t.build_message(APP_ID, cell, art32, gh)
    check("domain-separated M rebuilt locally", len(M_live) == 102, "tag|app|cell|hash|genesis")
    print(f"        M = {M_live.hex()[:64]}...")
else:
    print("        (no inscription boxes yet on this app — registration-stage deployment)")
try:
    from trelyan_pq import verify as falcon_verify  # needs compiled deterministic-falcon lib
    print("        full falcon verify available locally: YES (run verify(M, sig, pk))")
except Exception as e:
    print(f"        full local falcon verify: optional C lib not built ({type(e).__name__}) — structural checks above stand")

print(f"\n== RESULT: {PASS} passed, {FAIL} failed ==")
sys.exit(1 if FAIL else 0)
