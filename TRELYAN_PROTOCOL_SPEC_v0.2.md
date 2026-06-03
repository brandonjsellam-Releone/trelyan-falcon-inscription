# TRELYAN Protocol — Cryptographic Specification

**Version:** 0.2 (post-Council-review draft for external audit preparation)
**Date:** 1 June 2026
**Status:** DRAFT — not yet audited. Prepared for Runtime Verification review.
**Authors:** TRELYAN Foundation (in formation, Zug, CH), with the TRELYAN AI Council
(Claude Opus, Gemini 3.1 Pro technical-verification seat, Hermes, IBM watsonx, Mistral).

> Informational technical documentation, not a security guarantee. Nothing here is secure
> until an independent formal audit completes and its findings are remediated.

> **Changelog v0.1 → v0.2 (driven by Council review):**
> - **[Gemini]** Corrected the hash-binding argument: the operative property is **collision
>   resistance**, not second-preimage (holder can equivocate). Security margin restated.
> - **[Gemini]** AVM version for `falcon_verify` is **disputed across sources** — now flagged
>   as an explicit open item, not asserted.
> - **[Hermes #3]** `app_id` now bound into the signed message M (cross-deployment replay).
> - **[Hermes #2]** ASA ownership check hardened against temporary-custody (flash-loan) attacks.
> - **[Hermes #1]** Non-upgradability made an explicit deploy-time requirement with verification.
> - **[Hermes #4]** Key commitment moved to mint-atomic immutable storage; front-run closed.
> - **[Hermes #5]** Budget-griefing mitigation (verification isolation / budget pooling).
> - **[watsonx]** Added lifecycle threat model: key loss, abandoned Cells, governance,
>   dispute/winddown — the institutional-audit gaps.

---

## 0. Conventions

Byte strings big-endian. `H(·)` = SHA-512/256 (`sha512_256`). `‖` = concatenation.
Load-bearing security properties are **[INVARIANT]**; dependencies are **[ASSUMPTION]**;
fixes adopted from the Council review are tagged **[FIX]** with attribution.

---

## 1. Primitives and provenance

### 1.1 Falcon-1024 (FN-DSA)
- GPV hash-and-sign over NTRU lattices, FFT trapdoor sampler. Falcon-1024 targets **NIST
  security level V**. **NIST-selected (2022); FN-DSA in the forthcoming FIPS 206 (draft, NOT
  published as of June 2026).** Published PQC FIPS: 203 ML-KEM, 204 ML-DSA, 205 SLH-DSA
  (Aug 2024). Public docs MUST NOT say "FIPS 206 published."
- Parameters: n = 1024, q = 12289, ring Z_q[x]/(x^n+1). Public key ≈ **1793 bytes**
  (1-byte header + 1792-byte encoded polynomial). Signature: **Golomb/Rice-style compressed
  encoding** (not Huffman); variable length, **≈ 1280 bytes average**, padded to a fixed
  length for constant-size transmission in some implementations. **[FIX/Gemini]** v0.1 called
  1280 the "max"; it is the average/target — confirm the exact padded length the AVM opcode
  expects (§8).
- **Security goal:** EUF-CMA in the **(Q)ROM**; the GPV/Falcon QROM reduction is **non-tight**.
  SUF-CMA is plausibly also held (a 2nd valid signature for fixed (message,salt) reduces to
  SIS over the NTRU lattice) but TRELYAN claims only **EUF-CMA** absent a cited source.
- **Hardness:** NTRU key-recovery (average-case; **no clean worst-case→average-case reduction
  for NTRU**) + NTRU-SIS for unforgeability. Ajtai/Regev worst-case results are for
  (Ring-)SIS/LWE over ideal lattices and **do not transfer** to NTRU. Do not claim worst-case
  hardness for Falcon. **[Council: CORRECT — all three reviewing seats affirmed §1.1's
  EUF/QROM/NTRU framing.]**

### 1.2 Algorand `falcon_verify`
- **[ASSUMPTION/PLATFORM]** Native AVM opcode. Stack: `(data, signature, public_key) → bool`.
  Signature = compressed Falcon encoding. Same Falcon code path Algorand uses for State Proofs.
- **[OPEN — version disputed]** Public sources conflict on the AVM version / activation:
  go-algorand PR #5599 ("Adding sumhash and falcon_verify"), a v4.3.0 release reference
  (Sept 2024), "AVM v12," and TRELYAN's prior canonical note ("Nov 2025 consensus upgrade")
  do not agree. **This MUST be pinned against the live AVM opcode reference at implementation
  time and recorded in the audit pack with a URL and the activated consensus version.** Until
  then the protocol states only: "falcon_verify is a live native AVM opcode" — no version
  number in public copy.
- **[ASSUMPTION/PLATFORM]** `falcon_verify` is **opcode-budget-expensive**. One verification
  consumes a large share of the per-program budget; design (§5, §6.5) must account for budget
  pooling and griefing.

### 1.3 SHA-512/256
- Artifact commitment hash. **[FIX/Gemini — operative property corrected]** Because the
  **holder generates the commitment**, the binding must resist **equivocation**: a malicious
  holder who could find two artifacts A, A' with `H(A)=H(A')` could inscribe one and later
  present the other ("I actually inscribed A', not A"). Preventing equivocation requires
  **collision resistance**, giving **~128-bit classical / ~85-bit quantum** (Brassard–Høyer–
  Tapp) margin for SHA-512/256 — still adequate, but the honest figure is the collision bound,
  **not** the 256-bit second-preimage bound claimed in v0.1. An auditor will check this number;
  we state it correctly.

---

## 2. Objects

| Object | On-chain | Notes |
|---|---|---|
| **Record cell** | NFT ASA (total 1, decimals 0). 1,024 total. | Ownership = control of the ASA. |
| **Cell mint record** | Immutable, written atomically at mint. | Holds `committed_key_hash[cell_id]`. **[FIX/Hermes#4]** |
| **Inscription** | Write-once box keyed by `cell_id`. | In the TRELYAN app's box storage. |
| **Artifact** | Off-chain (IPFS/Arweave). | Only `H(artifact)` is on-chain. |

---

## 3. Inscription record (write-once box `INS(cell_id)`)
```
version=1 (uint8) ‖ cell_id (uint64) ‖ artifact_hash (32B)
  ‖ falcon_pubkey (1793B) ‖ inscribed_round (uint64, contract-written)
  ‖ inscriber (32B, contract-written) ‖ payload_uri (≤128B, contract-enforced)
```
**[INVARIANT I1]** Created at most once; immutable after creation; contract exposes no path
that re-writes it.

---

## 4. Signed message (domain-separated)
```
M := "TRELYAN-INSCRIPTION-v1"          (22B domain tag)
   ‖ uint64_be(app_id)                 [FIX/Hermes#3] binds to THIS deployment
   ‖ uint64_be(cell_id)
   ‖ artifact_hash                     (32B)
   ‖ genesis_id_hash                   (32B) pins chain/network
```
**[INVARIANT I2]** Contract reconstructs M on-chain from `Global.currentApplicationID`, the
operated ASA id, and call args. Never accepts caller-supplied M or app_id.

---

## 5. Inscription procedure

**Off-chain:** `artifact_hash=H(A)`; `M` per §4; `sig=Falcon1024.Sign(sk,M)`.

**On-chain `inscribe` — checks in order:**
- **[C1 — ownership, HARDENED]** Sender owns exactly 1 unit of `cell_id` **AND** is the address
  recorded as the Cell's controlling owner (`controlling_owner[cell_id]`). The recorded owner is
  set at `register_cell` (mint) and moves only via `update_owner`, which requires the prior
  owner's authorization — NOT a bare `asset_holding_get` balance > 0. **[FIX/Hermes#2]**
  Rationale: a bare balance check passes for accounts in temporary custody
  (lending/escrow/flash-loan-style group), letting a transient holder inscribe; binding to the
  mint-recorded controlling owner defeats that. *Note (pre-audit review M1): this recorded-owner
  mechanism is the chosen enforcement — it is NOT a close-remainder/rekey exclusivity proof.
  Audit to confirm transient ASA custody cannot satisfy C1.*
- **[C2 — single-use]** `INS(cell_id)` does not exist (enforces I1).
- **[C3 — reconstruct M]** Including `app_id` from `Global.currentApplicationID` (I2).
- **[C4 — signature]** `falcon_verify(M, sig, falcon_pubkey) == 1`.
- **[C5 — key commitment, HARDENED]** `H(falcon_pubkey) == committed_key_hash[cell_id]`, read
  from the **immutable mint record** (not a mutable box). **[FIX/Hermes#4]** Mint MUST write
  `committed_key_hash` atomically with ASA creation so no front-run can substitute a key.
- **Effect:** create `INS(cell_id)`; write record; log event.

**[INVARIANT I3]** Post-inscription, `(app_id, cell_id, artifact_hash, falcon_pubkey)` is
publicly re-verifiable by anyone re-running `falcon_verify` over reconstructed M.

---

## 6. Threat model

### 6.1 Adversary
PPT, optionally quantum. May submit any tx, read all chain state, adaptively obtain
inscription signatures except the target. Goals: G1 forge, G2 mutate, G3 replay, G4 repudiate,
**G5 deny inscription (DoS/grief)**, **G6 economic/governance capture** (new in v0.2).

### 6.2 Goal-by-goal
- **G1 forge:** blocked by C1 ∧ C5 ∧ C4 → reduces to Falcon-1024 EUF-CMA break or key/Cell theft.
- **G2 mutate:** blocked by I1/C2 and **[INVARIANT I5 — non-upgradable, HARDENED]** the app's
  update & clear-state programs are set to always-fail at deploy; verified via `goal app info`
  that no update authority remains, OR upgrade is permanently Stiftung/DAO-gated behind
  re-audit. **[FIX/Hermes#1]** Algorand apps are upgradable by default; this is the single most
  important deploy-time control and an auditor MUST confirm it on the deployed app.
- **G3 replay:** blocked by domain tag + **app_id** + cell_id + genesis_id_hash in M.
- **G4 repudiate:** record + signature is the evidence; `inscriber`/`inscribed_round`
  contract-written.
- **G5 deny/grief:** **[FIX/Hermes#5]** `falcon_verify` is budget-heavy; an attacker spamming
  invalid-signature `inscribe` calls burns budget and can block legitimate calls needing inner
  txns/box writes. Mitigation: (a) require a budget-increase inner txn, or (b) isolate Falcon
  verification in a dedicated stateless logic-sig the caller supplies, so the stateful app only
  does cheap hash + box-existence checks. Also: inscription is per-Cell and gated by ownership,
  so grief surface is bounded to a Cell's own holder. Document the chosen mode.

### 6.3 Lifecycle threats (**[watsonx]** — institutional-audit gaps)
- **Key loss:** a Cell whose inscription `sk` is lost is **permanently un-inscribable** (by
  design — no key, no signature). MUST be disclosed to record holders as a known, accepted property.
  Optionally: a Stiftung-held recovery/attestation path, but that reintroduces trust and must
  be explicitly designed + audited, not bolted on.
- **Abandoned/never-inscribed Cells:** Cells retain membership value un-inscribed; define their
  status, rights, and any reclamation/expiry explicitly (governance doc, not contract magic).
- **Governance:** who can pause, who holds any retained authority, how upgrades (if any) are
  gated — must be defined and match I5. Undefined governance fails institutional audit.
- **Dispute / wind-down:** define dispute handling for contested Cells and a documented
  protocol wind-down path. Regulator/counsel will ask (per watsonx review).

### 6.4 Residual risks (disclosed)
Falcon QROM non-tightness; NTRU no-worst-case reduction; secret-key custody out of protocol
scope; platform trust in AVM `falcon_verify`; SHA-512/256 collision margin (~128-bit classical).

---

## 7. Properties an auditor verifies
I1 immutability · I2 on-chain M reconstruction (incl. app_id) · I3 re-verifiability ·
I4 key-commitment from immutable mint record · I5 non-upgradability on the deployed app ·
C1–C5 present on every state-writing path · hardened C1 rejects transient custody ·
budget mode documented · §1.2 version/cost/byte-format pinned to live reference.

---

## 8. Honesty ledger — confirm before audit
- [ ] **AVM version + opcode cost** for `falcon_verify` — pin to live reference (sources
      conflict: PR #5599 / v4.3.0 Sept 2024 / "AVM v12" / "Nov 2025"). Record URL + consensus ver.
- [ ] **Exact byte layouts** the opcode expects (pubkey, compressed sig, padded length).
- [ ] **Mint atomicity** of `committed_key_hash` (immutable storage; where exactly).
- [ ] **Budget mode** chosen (app-call pooling vs. stateless logic-sig isolation).
- [ ] **I5 mechanism** — exact non-upgradability control + how it's verified on-chain.
- [x] **Lifecycle policy** drafted (`GOVERNANCE_AND_LIFECYCLE_POLICY.md`) — key-loss disclosure,
      abandoned-Cell status, governance (mint-only authority; no-pause/no-upgrade by design),
      wind-down (protocol outlives the Foundation). Pending Stiftung/counsel ratification.

---

*Council-reviewed (Gemini verification seat + Hermes + watsonx, three independent lineages).
For Runtime Verification audit. Not a security guarantee prior to that audit.*
