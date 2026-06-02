# TRELYAN — Localnet Validation & Council Hardening (1 June 2026)

**Artifact under test:** `contracts/inscription.py`
**Suite:** `contracts/test_inscription.py` — **20 / 20 passing** on Algorand localnet
**Toolchain:** algokit localnet · AVM target v12 · PuyaPy 5.8.1 · deterministic Falcon-1024
(`contracts/falcon_det1024.py`, native `falcon_verify` opcode)

This document records (a) what the on-chain run closes, (b) the full AI-council review of the *tested*
contract and the hardening it produced, (c) two council findings we adjudicated as **not** changes —
with rationale for RV to confirm — and (d) the operational residuals we are NOT closing in code and
ask RV / the Foundation to weigh. It is deliberately honest: treat every claim as unproven until RV
re-derives it.

---

## 1. What the on-chain run closes

**Scope of "closed":** validated on localnet against a live AVM (accept + reject vectors), with the
relevant `AUDIT-NOTE` updated. This is **not** TestNet/MainNet-proven and **not** externally audited —
RV is asked to formally confirm each item, and to supply the all-histories / all-encodings argument a
finite test suite cannot. See §6.

| Item | Was | Now (localnet-validated) |
| --- | --- | --- |
| **A1** falcon_verify operand order + acceptance | resolved by docs, TEAL spot-check pending | **Closed.** A real det1024 compressed sig (header `0xBA`) over the on-chain-rebuilt M verifies; tampered-sig and wrong-key rejected. |
| **A8** signature-encoding compatibility | closed off-chain only | **Closed on-chain.** The off-chain signer's bytes are accepted by the opcode; off-chain `build_message` is byte-identical to on-chain `_build_message` (valid-accept test passes). |
| **A4** same-group composition | OPEN — needed a live group test | **Closed on-chain.** Grouped double-inscribe fails write-once across the atomic group; flash-custody (ASA holder ≠ controlling owner) fails C1. RV still asked to formally confirm intra-group write visibility. |
| **A9** 2048-byte ApplicationArgs limit | discovered during this run | **Closed.** pubkey(1793)+sig(≤1423) overflowed the 2048 B arg cap; fixed by storing the full committed key in a box at register and passing only the signature at inscribe. |
| **A2** network binding | recommendation only | **Closed.** Binds the native `Global.genesis_hash`; `create()` takes no genesis arg, so the chain can never be mis-pinned at deploy. |

The cryptographic core (Falcon-verify path + write-once authorization + ownership) is now validated
end-to-end against a live AVM, not just off-chain.

---

## 2. The 20 tests (what each exercises)

*Each test exercises the listed path on a live AVM and rejects the exercised attack vector; this is
evidence, not a proof over all histories.*

**Signature path (A1/A8/A9):** valid inscribe accepts; tampered signature rejected (C4);
wrong-key rejected (sig by a non-committed key fails `falcon_verify`); separate-txn double-inscribe
rejected (C2 write-once).

**Same-group / custody (A4):** same-group double-inscribe rejected (intra-group write-once);
flash-custody rejected (C1 controlling-owner gate beats bare ASA balance).

**Message integrity (A2/I2):** cross-cell replay rejected — a signature authorizing `cell_a` is
invalid for `cell_b` even under the same committed key, proving `M` binds `cell_id`.

**Non-upgradability (I5):** `UpdateApplication` rejected by `on_update`; `DeleteApplication` rejected
by `on_delete`.

**Register guards:** non-admin register rejected; non-NFT (total≠1) rejected; **clawback-bearing Cell
rejected** (new hardening); wrong-length committed key rejected; re-registration of an existing cell
rejected.

**Inscribe input guards:** `payload_uri` > 128 B rejected; signature > 1423 B rejected (both cheap,
pre-`falcon_verify`).

**update_owner state machine:** non-owner `update_owner` rejected; `update_owner` after inscription
rejected (owner frozen); authorized handoff then successful inscribe by the new owner.

**Read path (I3/A3):** `get_inscription` on a registered-but-not-inscribed cell raises (missing box
read fails — never returns a zero record).

---

## 3. Council hardening applied (full 6-model review of the tested contract)

The contract was reviewed by the full TRELYAN council (Gemini, OpenAI, Hermes, watsonx, Mistral,
Grok) *after* it first reached 12/12. Three concrete changes resulted, now in the 20-test suite:

1. **A2 — native genesis (Mistral, must-fix).** `_build_message` binds `Global.genesis_hash`;
   `create()` no longer takes/stores a genesis argument. Removes the only deploy-time value that could
   silently scope every signature to the wrong network — unrecoverable in a non-upgradable contract.
2. **Clawback/freeze/manager rejected at register (Grok).** `register_cell` now requires the Cell ASA
   to have no clawback, no freeze, and a cleared manager. This closes, at the source, the
   `asset_holding_get` timing vector where a clawback/freeze/close-out could momentarily falsify the
   C1 balance check or grief the rightful owner.
3. **+8 coverage tests (OpenAI / Hermes).** The prior 12 were happy-path-narrow. Added: Update/Delete
   rejection (the existential I5 check — if the app could be replaced, every other invariant is
   bypassable), cross-cell replay, re-registration, both `update_owner` guard failures, and
   `get_inscription` raise-on-missing.

---

## 4. Council findings adjudicated as design decisions (RV to ratify)

The cryptography seat (Gemini) raised two flags we did not turn into code changes. We frame them
precisely — as Algorand-specific design decisions / threat-model assessments, **not** as "nothing to
see" — and ask RV to ratify.

- **`0xBA` header / deterministic Falcon.** Gemini is correct that, measured against the generic NIST
  Falcon submission, the compressed header for n=1024 is `0x3A` (randomized, 40-byte salt). Algorand's
  `falcon_verify` opcode instead implements the **deterministic** variant, header `0xBA = 0x3A | 0x80`
  (`0x80` flags det / salt-version). This is a deliberate **Algorand-specific deviation from the
  generic NIST submission** — not a bug, and explicitly **not** a claim of NIST / FIPS-206 (FN-DSA)
  compliance. Our on-chain accept test confirms the live opcode accepts exactly the `0xBA`
  deterministic bytes our signer emits, and rejects tampered/wrong-key; determinism is
  RFC-6979/Ed25519-style (nonce from message+key), not an RNG-failure surface. **RV/standards note:**
  treat `0xBA`/deterministic as the Algorand opcode's contract, distinct from any future FIPS-206
  finalization. (Per Gemini's own framing.)
- **`payload_uri` / `inscriber` not in the signed `M`.** Assessed **acceptable under the stated threat
  model — RV to ratify** (we state this as an assessment, not a proof). Rationale: the inscribe
  transaction is itself signed by the sender's Algorand key, so a third party cannot alter
  `payload_uri` (or any arg) in flight; C1 requires `sender == controlling_owner`, so the recorded
  `inscriber` is necessarily the authorized owner; and artifact integrity is content-addressed via
  `artifact_hash` (a swapped URI cannot serve content that hashes correctly). Replay is bounded by
  write-once (C2) plus the `app_id` / `cell_id` / genesis binding in `M`, not by a nonce. We ask RV to
  confirm that excluding these fields from `M` does not violate the intended authenticity semantics;
  binding `payload_uri` / `inscriber` in `M` is an easy, reversible hardening if RV prefers it.

---

## 5. Operational residuals (NOT code bugs — RV / Foundation to weigh)

- **App-account minimum balance.** Each committed-key box is 1,793 B → ~0.72 ALGO min-balance per
  cell (~737 ALGO locked across all 1,024 if fully minted), paid by the app account. The Foundation
  funds it; if the app account drops below min-balance, box-writing calls (register / inscribe) fail
  until topped up. Needs an explicit funding policy. *(watsonx, severity 9.)*
- **Lost-key cells are irrecoverable by design.** Immutable commitment, no rotation (I4/I5). An owner
  who loses their Falcon private key can never inscribe that cell. Intentional, but must be disclosed
  to Cell holders. *(watsonx / Grok.)*
- **Admin (Foundation) blast radius.** Admin can register cells and set `controlling_owner` +
  `committed_pubkey`, but has **no** power over existing inscriptions (write-once; no admin mutation
  path). An admin-key compromise can only mis-mint *un*registered cells. *(watsonx.)*
- **On-chain permanence / GDPR.** `committed_pubkey` and `inscriber` are permanent on-chain. A public
  key is not PII in the ordinary sense and the inscriber is a self-selected pseudonymous address, but
  non-upgradability precludes erasure. Foundation to address in disclosures. *(Mistral.)*
- **1,024-cell cap.** Enforced by `cells_registered < TOTAL_CELLS`; not unit-tested (would require
  1,024 real ASAs) — left for RV static verification. *(Hermes.)*
- **OpUp griefing.** `ensure_budget` OpUps draw from the caller's own fee surplus (GroupCredit); a
  caller can only spend their own fee. Low risk. *(Grok / watsonx.)*

---

## 6. Honesty statement

Reviewed by an internal AI council and validated on localnet only — **not** on TestNet/MainNet, and
**not** externally audited. The localnet pass *exercises* the happy paths and the listed rejects on a
live AVM; it does **not** prove the invariants over all histories, all encodings, or any future-AVM
upgrade path, and it does not prove absence of bugs. Supplying that exhaustive/inductive argument —
plus formal eyes on the Falcon-verify path, the A4 intra-group write-visibility assumption, and the §4
adjudications — is exactly why we are engaging RV. See `THREAT_MODEL_AND_TRACEABILITY.md` for the
invariant→test→code matrix and what is explicitly left to RV / static analysis / TestNet.
