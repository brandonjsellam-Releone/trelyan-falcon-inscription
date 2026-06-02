# inscription.py — Pre-Compile Static Review

**Date:** 1 June 2026 · Reviewer: Claude Opus (static, against algopy/PuyaPy API).
**Goal:** catch what would make `algokit project run build` fail BEFORE you spend a compile
cycle. The sandbox VM is down this session so I can't run PuyaPy myself — this is a careful
read against the known algopy API. Apply these, then build locally.

> Severity: 🔴 will fail compile · 🟡 likely fail / version-dependent · 🟢 works but verify.

---

## 🔴 1. `op.AssetHoldingGet.asset_balance` — wrong API surface
**Line ~180:** `bal, has = op.AssetHoldingGet.asset_balance(Txn.sender, cid)`
In current algopy, asset holding is read via **`Account.asset_holding`** or the
`algopy.op.AssetHoldingGet` class whose method is **`.asset_balance(account, asset)`** returning
an `arc4`-style tuple — but the idiomatic, compile-safe form is:
```python
from algopy import Account
bal, has_held = Asset(cid).balance(Txn.sender), ...   # NOT this either
```
**Correct, current-API form:**
```python
balance, exists = op.AssetHoldingGet.asset_balance(Txn.sender, cell)  # pass the Asset, not cid:UInt64
assert exists and balance == UInt64(1), "sender does not hold the cell"
```
Note: pass the **`Asset`** object (`cell`), not the `UInt64` id, to the holding op in recent
algopy. Confirm against your installed `algopy` version's `op.pyi`. **This is the most likely
hard failure.**

## 🔴 2. `BoxMap` membership + assignment with `Bytes` values — confirm value type
**Lines 98–102, 142–143, 182–183:** `BoxMap(UInt64, Bytes, ...)` then `self.x[cid] = some.bytes`
and `self.x[cid] == Txn.sender.bytes`.
- `BoxMap[UInt64, Bytes]` is valid. But `committed_key_hash` stores a 32-byte hash and
  `controlling_owner` stores a 32-byte address — storing them as variable `Bytes` works, but for
  a fixed 32-byte value the cleaner type is `arc4.StaticArray[arc4.Byte, 32]` or `algopy.Bytes`
  with a length assert (you have the asserts). 🟢 leave as Bytes, but **verify `Txn.sender.bytes`
  is the right accessor** — in current algopy it's **`Txn.sender.bytes`** ✅ (Account has `.bytes`).
- `cid in self.committed_key_hash` (membership) — `BoxMap.__contains__` exists ✅.

## ✅ 3. `op.falcon_verify` — argument order + types (A1 — RESOLVED by docs 2026-06-01)
**Line ~194:** `op.falcon_verify(m, falcon_sig.bytes, pubkey)`
- **Resolved:** Algorand's official references confirm the native opcode is
  `falcon_verify(data, signature, public_key) -> bool`, signature in **compressed** Falcon
  encoding (dev.algorand.co `op.falconVerify` + algopy `op.falcon_verify`; algorand.co Falcon
  technical brief). The call's order **(m=data, falcon_sig=signature, pubkey=public_key) is
  correct**. `PUBKEY_LEN=1793` is the right Falcon-1024 pubkey length; the compressed sig is
  variable-length so `falcon_sig: arc4.DynamicBytes` is correct (no fixed-len assert).
- **Residual (do at compile time, belt-and-suspenders):** when the build succeeds, dump the TEAL
  and eyeball the `falcon_verify` operand order; then add a live accept/reject test
  (`test_inscription.py`) and **confirm the off-chain signer's compressed-sig encoding matches
  Algorand's** — an encoding mismatch (not arg order) is now the likeliest remaining failure mode.
  Full writeup: `A1_RESOLUTION_2026-06-01.md`.

## 🟡 4. `Global.round` vs `Global.latest_timestamp` / `Global.current_application_id`
**Lines 203, 214:** `Global.round` and `Global.current_application_id.id`.
- Current algopy: the round is **`Global.round`** ✅ (older code used `Global.latest_timestamp`
  for time). Good.
- `Global.current_application_id` returns an `Application`; `.id` gives `UInt64` ✅. Confirm the
  attribute is `current_application_id` (some versions: `current_application_id` ✅).

## 🟡 5. `arc4.Address(Txn.sender)` constructor
**Line 204:** `inscriber=arc4.Address(Txn.sender)`.
`arc4.Address` is constructed from an `Account` or 32 bytes. `arc4.Address(Txn.sender)` should
work, but if PuyaPy complains, use `arc4.Address.from_bytes(Txn.sender.bytes)`.

## 🟡 6. `InscriptionRecord` with `DynamicBytes` in a BoxMap value
**Lines 71–79, 100, 207:** an `arc4.Struct` containing **two `DynamicBytes`** fields stored in a
`BoxMap`. Dynamic-length structs in boxes are supported but the box must accommodate the max
size. `falcon_pubkey` (1793 B) + `payload_uri` (≤128 B) + fixed fields ≈ 2 KB — fine within a
4 KB box, but confirm PuyaPy doesn't require a fixed-size declaration. If it errors on the
dynamic struct in a BoxMap, fall back to storing the record as raw concatenated `Bytes` and
slicing on read.

## 🟢 7. `key_prefix=b"..."` on BoxMap
Valid ✅. Just ensure prefixes are unique (they are: `k_`, `i_`, `o_`).

## 🟢 8. `assert False` in `on_update`/`on_delete`
**Bottom of file:** `assert False, "..."`. PuyaPy may warn on a constant-false assert; if it
errors, use `algopy.op.err()` or `assert Txn.sender == Global.zero_address, "non-upgradable"`
(which is always false for a real sender) to express "always reject."

---

## Build sequence (do this on your machine)
```bash
pipx install algokit            # if not installed
algokit init                    # choose: Smart Contracts → Python (algopy)
# copy inscription.py into smart_contracts/inscription/contract.py
algokit project run build       # PuyaPy compiles → TEAL + ARC-56 .json
```
Then:
1. Fix whatever PuyaPy reports (paste errors to me — I'll correct the algopy live).
2. Open the generated `*.approval.teal`; find the `falcon_verify` line; confirm operand order
   vs dev.algorand.co (resolves A1).
3. `algokit localnet start` → deploy → write a pytest that inscribes with a real Falcon-1024
   signature (use `pqcrypto` or `falcon.py` off-chain to generate the keypair + sig over the
   reconstructed message M) and asserts accept-valid / reject-tampered.
4. TestNet for real opcode cost + budget.

**Most important:** items 1 and 3. #1 will fail your first build; #3 is the security-critical
confirmation the whole protocol rests on.
