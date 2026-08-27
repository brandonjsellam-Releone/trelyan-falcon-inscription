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
| ~~`sha512_256(pubkey)` (C5)~~ | ~~45–200~~ | **REMOVED — see the correction below.** `inscribe` no longer takes a pubkey argument. |
| `_build_message` (itob ×2, concat, Global reads) | ~tens | cheap |
| length/asset/owner asserts | ~tens | cheap |
| **Total (estimate)** | **~1,750–1,800** | dominated by `falcon_verify`; was quoted as ~1,850–2,050 while C5 was still counted |

> Box access is metered by a **separate** box read/write budget (1024 B per box reference in the
> group), **not** the opcode budget — don't conflate them. The ~2 KB `InscriptionRecord` write
> needs enough box references in the txn to cover its size; that's orthogonal to the 1700 below.

> **~~Contract update (1 Jun, self-review): `inscribe` now runs C5 before C4…~~**
>
> **SUPERSEDED — corrected 2026-08-15.** That note described an architecture the contract no longer
> has, and this memo billed opcodes for a step that does not execute.
>
> `contracts/inscription.py` (≈L71-73) records the change: *"the prior C5 'reveal pubkey and check
> `sha512_256(pubkey)==committed_hash`' is removed — it was a storage optimization, not a security
> property"*. The full public key now lives in box state, written once at `register_cell`, and
> `inscribe` READS it rather than accepting it as an argument. The contract contains no
> `sha512_256` call at all (`grep -c sha512_256 contracts/inscription.py` → 2, both in comments or
> a constant's docstring).
>
> **What this changes, precisely:**
> * The opcode total is **lower**, not higher — ~1,750–1,800 rather than ~1,850–2,050. The memo
>   overstated the cost, which is the safe direction, but it is still a number an auditor re-derives.
> * The **A5 claim no longer applies as written.** "A wrong-key attempt is rejected for ~45–200
>   instead of paying the full 1700" described a cheap pre-check on a *supplied* key. There is no
>   supplied key now, so a bad signature pays the full `falcon_verify`. Worth stating plainly rather
>   than leaving a mitigation on the books that the code does not implement — though the exposure is
>   narrow: the caller funds its own OpUp budget, so a failed `inscribe` wastes the caller's fees,
>   not a third party's.
> * The design change was deliberate and is a **stronger** binding, not a weaker one: with the key
>   read from box state, no key argument can be substituted.
>
> **The OpUp conclusion below is unaffected.** 1,700 + overhead still exceeds the 1,400 that two
> extra app calls provide, so three calls (3 × 700 = 2,100) remains the requirement.

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
