# TRELYAN — Threat Model & Invariant→Test Traceability (1 June 2026)

Companion to `LOCALNET_VALIDATION_2026-06-01.md`. Built at the council's request so a formal auditor
does not spend week one reconstructing the trust surface, the invariant→test mapping, or the
reproduction steps. **Scope honesty up front:** the 20-test suite *exercises* the listed execution
paths and *rejects the exercised attack vectors* on a live localnet AVM. It does **not** constitute a
proof of the invariants over all histories, encodings, or upgrade paths — that inductive/exhaustive
argument is exactly what we are engaging Runtime Verification to provide.

---

## 1. Actors & trust boundaries

| Actor | Power | Trust assumption |
| --- | --- | --- |
| **Admin / Foundation** | `register_cell` only (mint a cell, set its controlling_owner + committed Falcon key). NO power over existing inscriptions. | Trusted at mint; custody is Stiftung multisig (see GOVERNANCE doc). Compromise blast radius = mis-minting *unregistered* cells only. |
| **Controlling owner** (per cell) | The sole address allowed to `inscribe` that cell, and to `update_owner` it (pre-inscription). Recorded immutably at mint, moved only by the prior owner. | A normal Algorand account; authenticates via the transaction signature. |
| **Falcon-1024 key holder** | Produces the signature over the domain-separated message M. The key is committed in full at mint. | The post-quantum authority for the cell. Key loss ⇒ cell permanently un-inscribable (by design). |
| **Inscriber** (txn sender) | Submits `inscribe`. C1 forces `sender == controlling_owner`, so the recorded inscriber is necessarily the authorized owner. | Same key as the controlling owner. |
| **Off-chain signer** (`falcon_det1024.py`) | Builds M and signs it; byte-identical to the on-chain `_build_message`. | Runs on the owner's machine; not part of the on-chain TCB. |
| **Artifact host** (IPFS/Arweave) | Stores the artifact bytes. | Untrusted for availability; integrity is content-addressed via `artifact_hash`. |

**Boundaries crossed by an inscribe:** (a) the Algorand transaction-signature layer (authenticates the
sender = controlling owner and freezes all call args, including `payload_uri`); (b) the Falcon
signature layer (authenticates the committed key's authorization of `cell_id + artifact_hash + app +
network`); (c) on-chain box state (write-once record). Artifact bytes live entirely outside the TCB.

---

## 2. Attack surface → control → test

| Attack | Control | Localnet test |
| --- | --- | --- |
| Forge / tamper a signature | `falcon_verify` against the committed key (C4) | `test_inscribe_rejects_tampered_sig`, `test_inscribe_rejects_wrong_key` |
| Inscribe a cell you don't control | C1: hold the ASA **and** be the recorded controlling_owner | `test_flash_custody_rejected` |
| Re-inscribe / overwrite a record | C2 write-once (`assert cid not in inscriptions`) | `test_double_inscribe_rejected_separate_txns`, `test_double_inscribe_SAME_GROUP_rejected` |
| Replay a signature onto another cell | M binds `cell_id` (and `app_id` + genesis) | `test_cross_cell_replay_rejected` |
| Replay across networks | M binds native `Global.genesis_hash` (A2) | (binding present; cross-network not localnet-testable — RV/TestNet) |
| Replace the approval program | `on_update` rejects all UpdateApplication (I5) | `test_rejects_update` |
| Delete the app / erase inscriptions | `on_delete` rejects all DeleteApplication (I1/I5) | `test_rejects_delete` |
| Mint under a fake / non-NFT id | `register_cell` binds a real pure-NFT ASA created by admin | `test_register_rejects_non_nft` |
| Seize/freeze a cell to game C1 | register rejects clawback/freeze/manager-bearing ASAs | `test_register_rejects_clawback_cell` |
| Commit a malformed key (brick a cell) | exact 1793 B length checked at register | `test_register_rejects_bad_pubkey_length` |
| Re-register / rebind a cell | register-once (`cid not in committed_pubkey/controlling_owner`) | `test_reregister_rejected` |
| Non-admin mints | admin-only `register_cell` | `test_register_only_admin` |
| Oversized inputs (DoS / box bloat) | sig ≤ 1423 B, payload_uri ≤ 128 B (cheap, pre-verify) | `test_sig_too_large_rejected`, `test_payload_uri_too_long_rejected` |
| Steal inscription rights via owner change | `update_owner` only by current owner, only pre-inscription | `test_update_owner_only_owner`, `test_update_owner_after_inscribed_rejected` |

---

## 3. Invariant / check → test → code

| ID | Statement | Test(s) | Contract location |
| --- | --- | --- | --- |
| **I1** | Inscriptions are write-once & permanent | `test_double_inscribe_*`, `test_rejects_delete` | `inscribe` C2 assert; `on_delete` |
| **I2** | Message integrity — M binds app, cell, artifact, network | `test_cross_cell_replay_rejected`, `test_inscribe_rejects_tampered_sig` | `_build_message`; `inscribe` C4 |
| **I3** | Public re-verifiability of the record | `test_inscribe_accepts_valid` (read-back), `test_get_inscription_missing_raises` | `get_inscription` |
| **I4** | Key committed at mint, immutable | `test_register_rejects_bad_pubkey_length`, `test_reregister_rejected`, `test_inscribe_rejects_wrong_key` | `register_cell`; `committed_pubkey` box |
| **I5** | Non-upgradable & non-deletable | `test_rejects_update`, `test_rejects_delete` | `on_update`, `on_delete` |
| **C1** | Ownership (holds ASA ∧ recorded owner) | `test_flash_custody_rejected`, `test_update_owner_then_inscribe` | `inscribe` C1 |
| **C2** | Single-use / write-once | `test_double_inscribe_*` | `inscribe` C2 |
| **C3** | M reconstructed on-chain | `test_inscribe_accepts_valid`, `test_cross_cell_replay_rejected` | `_build_message` |
| **C4** | Falcon-1024 signature valid | `test_inscribe_accepts_valid`, `_rejects_tampered_sig`, `_rejects_wrong_key` | `inscribe` C4 (`op.falcon_verify`) |
| **C5** | Key is the one committed at mint | `test_inscribe_rejects_wrong_key`, `test_inscribe_accepts_valid` | `inscribe` reads `committed_pubkey[cid]` |

**Not covered by localnet tests (left to RV / static / TestNet):** the 1,024-cell cap (enforced by
`cells_registered < TOTAL_CELLS`; testing it needs 1,024 real ASAs); write-once / immutability across
*arbitrary* prior histories and any future-AVM upgrade path; cross-network replay; consensus / fee
divergence between localnet and TestNet/MainNet.

---

## 4. Reproduction (pinned)

**Toolchain:** PuyaPy 5.8.1 + algorand-python 3.5.0 on **Python 3.13** (PuyaPy does not support 3.14);
algokit localnet (Docker); algokit-utils v4; deterministic Falcon-1024 via the `algorand/falcon`
C library (`libfalcondet1024.so`, built with `cc`), AVM target **v12**.

```
# 1. Build the deterministic Falcon lib (once, Linux/WSL) and self-test the off-chain signer (A8):
cc -O3 -fPIC -shared -o libfalcondet1024.so codec.c common.c falcon.c fft.c fpr.c keygen.c rng.c shake.c sign.c vrfy.c deterministic.c
export FALCON_DET1024_LIB="$PWD/libfalcondet1024.so"
python crypto/contracts/falcon_det1024.py        # keygen -> sign -> verify round-trip

# 2. Compile the contract (Python 3.13 venv), targeting AVM v12:
puyapy crypto/contracts/inscription.py --out-dir crypto/contracts/out --target-avm-version 12

# 3. Generate the typed client from the ARC-56 spec (re-run after every recompile):
algokit generate client crypto/contracts/out/TrelyanInscription.arc56.json --output crypto/contracts/trelyan_client.py

# 4. Start localnet and run the suite:
algokit localnet start
python -m pytest crypto/contracts/test_inscription.py -v     # expect 20 passed
```

(The repo ships `compile_contract.ps1` which builds the isolated 3.13 venv and runs step 2 on
Windows.) A pinned `requirements.txt` for the test venv (algokit-utils, pytest, the Falcon lib path)
is the one packaging item still to add.

---

## 5. TestNet rollout checklist (next milestone after this handoff)

1. Fund a deployer + the app account (committed-key boxes need ~0.72 ALGO/cell; budget the funding
   policy — see residuals).
2. Deploy via the typed factory `create()` (binds the real TestNet `Global.genesis_hash` natively).
3. Register a handful of real pure-NFT Cell ASAs (clawback/freeze/manager cleared).
4. Run an end-to-end inscribe with the off-chain `falcon_det1024` signer against the live opcode.
5. Confirm the A4 same-group behaviours on TestNet; capture txids for RV.
6. Re-confirm fee/opcode-budget behaviour (OpUp inner txns) matches localnet.

---

## 6. Residuals (full detail in LOCALNET_VALIDATION §5)

App-account MBR funding policy (~737 ALGO if fully minted; user-paid-at-register is an option worth
evaluating); lost-key cells irrecoverable by design (disclose to holders); admin mis-mint limited to
*unregistered* cells (Stiftung multisig custody); committed pubkey + inscriber permanent on-chain
(GDPR DPIA at the Foundation layer — the inscriber address is inherent to any Algorand transaction);
1,024 cap left to static verification; OpUp fees drawn from the caller's own surplus.
