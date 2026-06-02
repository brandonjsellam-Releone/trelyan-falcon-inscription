# `falcon_verify` opcode budget — deployment analysis

**Date:** 1 June 2026 · **Question the contract flags ([Hermes#5], spec §6.5):** `falcon_verify` is
opcode-heavy; the default per-app-call budget won't cover it. How much budget does `inscribe()`
need, and how should we supply it? Answered from go-algorand source; final number to be confirmed
by a TestNet dry-run.

## The hard numbers (from `go-algorand/.../logic/opcodes.go`)
`{0x85, "falcon_verify", opFalconVerify, proto("bb{1232}b{1793}:T"), ... costly(1700)}`
- **`falcon_verify` cost = 1700** opcode-budget units (fixed). Opcode `0x85`, AVM **v12**.
- Proto operand hints: signature ~**1232 B** (typical), public key **1793 B**. *Reconciling the
  sig-size figures (pre-audit review L1):* **1232** = opcode proto hint / typical length; **1423** =
  deterministic-compressed hard max = the contract's `SIG_COMPRESSED_MAXLEN` pre-verify bound; the
  signature is a variable-length `DynamicBytes`; public copy rounds to "~1.2 KB". See
  FALCON_ENCODING_2026-06-01.md.
- **Default opcode budget = 700 per application call.** Budget is **pooled across the atomic
  group**: each additional app call in the group adds another 700. (This is what the OpUp pattern
  exploits — it issues no-op inner app calls purely to raise the pooled budget.)

## Budget that `inscribe()` consumes
| Component | ~opcode cost | Notes |
|---|---|---|
| `falcon_verify` | **1700** | the dominant, fixed term |
| `sha512_256(pubkey)` (C5) | ~45–200 | hashing the 1793-B key |
| `_build_message` (itob ×2, concat, Global reads) | ~tens | cheap |
| length/asset/owner asserts | ~tens | cheap |
| **Total (estimate)** | **~1,850–2,050** | dominated by falcon_verify |

> Box access is metered by a **separate** box read/write budget (1024 B per box reference in the
> group), **not** the opcode budget — don't conflate them. The ~2 KB `InscriptionRecord` write
> needs enough box references in the txn to cover its size; that's orthogonal to the 1700 below.

> **Contract update (1 Jun, self-review):** `inscribe` now runs **C5 (key-commitment hash) before
> C4 (`falcon_verify`)**. A wrong-key attempt is therefore rejected for ~45–200 budget instead of
> paying the full 1700 — this shrinks the budget-griefing surface (audit item A5). The **happy-path
> total is unchanged (~2,050)**, so the OpUp math below still holds.

## How to supply the budget — two options
**Option A — OpUp budget pooling (keep the pure app-call model).**
Need ≈2,050 of opcode budget; one app call provides 700, so pool to ≥2,100 with **2 extra app
calls** (i.e. **2 OpUp inner app calls** beyond the main inscribe), or **3 for headroom**.
- Cost: each OpUp inner txn pays the 0.001 ALGO min fee → **+0.002–0.003 ALGO per inscription**.
  Negligible. Use algopy's `ensure_budget(2100)` (emits the OpUp inner calls for you).

**Option B — isolate `falcon_verify` in a stateless logic-sig (recommended for production).**
A smart-signature program has a **20,000** evaluation budget — one `falcon_verify` (1700) fits
trivially with **zero OpUp**. The logic-sig holds the Falcon public key and authorizes the txn by
verifying the signature; the app call then does the write-once state change. The contract already
points at this (`[Hermes#5]`, spec §6.5). Trade-off: the inscriber's authority is modeled as a
logic-sig account, which changes the client/UX flow — worth it at scale.

## Recommendation
- **MVP / TestNet:** Option A — `ensure_budget(2100)` (3 OpUp for headroom). Simplest; correct.
- **Production:** Option B — logic-sig isolation; removes per-call OpUp overhead and keeps the app
  call cheap. Decide before mainnet because it shapes the client signing flow.
- **Either way:** measure the real consumed budget with a **TestNet dry-run** (algod dryrun returns
  cost) — the ~2,050 is an estimate; only `falcon_verify`'s 1700 is fixed-by-source. Add this to
  the `test_inscription.py` suite once localnet is up.

## Sources
- `algorand/go-algorand` — `data/transactions/logic/opcodes.go` (`falcon_verify` `costly(1700)`,
  opcode 0x85, proto `bb{1232}b{1793}:T`).
- Algorand Developer Portal — opcode budget / OpUp (700 per app call, pooled across the group;
  smart-signature budget 20,000).
- PR algorand/go-algorand#5599 (adds `sumhash` + `falcon_verify`).
