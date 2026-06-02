# Pre-Audit Independent Review — Findings & Dispositions

**Date:** 1 June 2026 · **Scope:** `inscription.py` + `TRELYAN_PROTOCOL_SPEC_v0.2.md` +
the Falcon/metadata/budget memos + the three off-chain Python files. An independent review
(separate reviewer, fresh read) was run **before** handing to Runtime Verification, to catch
errors and doc-vs-code mismatches ourselves. This logs what it found and what we did — so RV sees
the full provenance and changelog.

## Verdict
**No CRITICAL findings.** The reviewer confirmed: no reachable path writes an inscription box
(`self.inscriptions[cid] = …`) without passing all of C1–C5; the four off-chain message builders
are **byte-identical** to the contract's `_build_message`; `op.falcon_verify(m, sig, pubkey)`
argument order is correct; and both recent edits (the sig-length bound and the C5-before-C4
reorder) are provably safe (no change to the success set). The issues below are real but are
documentation-vs-code mismatches and missing guards, not forgery/bypass.

## Findings & dispositions
| ID | Sev | Finding | Disposition |
|----|-----|---------|-------------|
| H1 | HIGH | Spec §4 described the genesis field as `uint64_be` (8 B); the contract signs the full **32 B**. Doc misdescribes the signed message M. | **FIXED** — spec §4 now `genesis_id_hash (32B)`. Code was already self-consistent across all 4 builders, so signatures were never affected. |
| H2 | HIGH | `register_cell` took a bare `uint64` id; the I4/M1 "key committed atomically to the ASA at mint" claim was an off-chain convention, not contract-enforced (admin could register under an arbitrary/nonexistent id). | **FIXED** — `register_cell` now takes `cell: Asset` and asserts `total==1 ∧ decimals==0 ∧ creator==admin`, binding the registration to a real admin-created Cell ASA (same id space as `inscribe`). Call sites (test scaffold, mint driver) updated. |
| M1 | MED | Spec C1 promised a `close-remainder`/`rekey` *exclusivity* proof; the code enforces recorded controlling-owner + `balance==1`. | **FIXED** — spec C1 reworded to the implemented recorded-owner mechanism (reviewer judged it reasonable/stronger vs flash-custody). Audit to confirm transient ASA custody cannot satisfy C1. |
| M3 | MED | `payload_uri` was the only input field with no length bound; spec said ≤128 B; an oversized URI inflates the write-once box past the budgeted ~2 KB. | **FIXED** — contract asserts `payload_uri.bytes.length <= URI_MAXLEN(128)`; spec note advisory→contract-enforced. |
| M2 | MED | `update_owner` can set `controlling_owner` to an address that doesn't hold the ASA. | **ACCEPTED / disclosed** — not exploitable (inscribe still requires `balance==1`); a deliberate degree of freedom (authority pointer vs custody). Audit may add a holder check. |
| M4 | MED | Box stores the full 1793 B pubkey, redundant with `committed_key_hash`. | **KEPT by design** — lets I3 read the pubkey from chain state without the JSON; the ~1793 B/inscription cost is acknowledged in `FALCON_BUDGET`. |
| L1 | LOW | Sig-size figures (1232 / 1280 / 1423 / 1222) appear across docs without reconciliation. | **FIXED** — `FALCON_BUDGET` now states 1232 = proto hint/typical, 1423 = hard-max contract bound, sig is variable-length. |
| L2 | LOW | `INS_VERSION = UInt64(1)` is stored into an `arc4.UInt8` field — silent truncation if ever > 255. | **NOTED** — value is 1; add an explicit width comment/cast at the next contract pass. |
| L3 | LOW | `create()` accepts any `genesis_id_hash`, unvalidated vs the live chain. | Already **AUDIT-NOTE A2** (switch to native `Global.genesis_hash`); auditor to treat as pre-mainnet. |
| N1 | NIT | Stale line references in `COMPILE_REVIEW` / `A1_RESOLUTION` / inline notes after edits. | To refresh; notes use "~" since line numbers shift per edit. |
| N3 | NIT | The pack's I3 one-liner undersold what re-verification needs (also the `k_` box + the JSON's signature). | **FIXED** — pack I3 row now cites the `k_`/`i_` boxes + the inscription JSON. |

## What remains open (legitimately needs a live run)
`A4` (intra-group write visibility), `A8` (sig-encoding round-trip on-chain), `A2` (native genesis
source), and budget-mode confirmation — all require a localnet/TestNet run, which awaits the
contract compiling (dev VM is down this week). These are disclosed in `AUDIT_READINESS_PACK.md` §5.

## Bottom line
The cryptographic core is sound and the contract's authorization gate is complete and correctly
ordered. The pre-audit review's value was in catching spec-vs-code mismatches an external reviewer
would flag as rigor concerns — now fixed — and in adding two missing guards (`register_cell`
ASA-binding, `payload_uri` length). Ship to RV after this pass; residual risk is the disclosed
live-AVM items.

## Addendum — threat-model & public-claims pass (second review)
A focused second pass over spec §6 (threat model), the economic/governance design, and the **live
website claims** found:
- **T1 (HIGH — FIXED on site):** `status.html` claimed the contract enforces "fee-burn · 24-month
  timestamp lock · emergency pause · foundation Cell non-transferable." The reference contract
  enforces **none** of these — they are ASA-level (transfer-lock / non-transferable via
  freeze/clawback), planned, or (pause) **deliberately absent** because a pause contradicts I5
  non-upgradability. The status row now separates contract-enforced vs ASA-level vs by-design-absent.
- **T2 (MED — FIXED on site):** "Genesis pipeline … Built" + "localnet dress-rehearsal" overclaimed
  (no compile yet; VM down). Reworded to "Designed / pending compile." "MBR computed empirically" →
  "estimated, confirm on localnet."
- **T3 (note for the auditor / governance doc):** admin-key compromise during the **mint phase** — a
  compromised admin could `register_cell` for not-yet-registered ids with an attacker key+owner (it
  cannot touch already-registered or inscribed cells; register-once + the new ASA-binding bound the
  blast radius). Mitigation is admin-key custody (Stiftung multisig). The contract is non-upgradable
  with **no pause by design** — the no-circuit-breaker trade-off is intentional and should be
  disclosed to buyers alongside I5.
- The core threat model (G1–G6 + lifecycle: key-loss, abandoned cells, governance, wind-down) is
  otherwise sound and honestly disclosed.
