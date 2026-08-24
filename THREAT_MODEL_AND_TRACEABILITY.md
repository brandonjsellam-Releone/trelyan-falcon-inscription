# TRELYAN — Threat Model & Invariant→Test Traceability (1 June 2026)

Companion to `LOCALNET_VALIDATION_2026-06-01.md`. Built at the council's request so a formal auditor
does not spend week one reconstructing the trust surface, the invariant→test mapping, or the
reproduction steps. **Scope honesty up front:** the localnet suite *exercises* the listed execution
paths and *rejects the exercised attack vectors* on a live localnet AVM. It does **not** constitute a
proof of the invariants over all histories, encodings, or upgrade paths — that inductive/exhaustive
argument is exactly the kind of work a formal-methods firm (e.g. Runtime Verification) would
provide. **No such firm is engaged.** No audit or formal-verification engagement has been
scheduled, quoted or paid for; earlier wording here implied an active engagement and did not
survive the 2026-08-24 audit.

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

---

## 7. Addendum (2026-08-10): deterministic-signing / signer key-extraction threat

Everything in §§1–6 concerns the **on-chain** trust surface — forgery, replay, ownership, write-once.
This section adds the one threat that lives entirely **off-chain in the signer** and is the first thing
a cryptographic reviewer will raise about *any* derandomized Falcon deployment. It is a
**private-key-confidentiality** threat, not an on-chain-authorization one, so none of the C1–C5 controls
touch it.

**The attack.** Lin, Tibouchi, Yu & Zhang, *"Do Not Disturb a Sleeping Falcon"*, EUROCRYPT 2025
([eprint 2024/1709](https://eprint.iacr.org/2024/1709)). Falcon's lattice discrete-Gaussian sampler is
sensitive to floating-point discrepancies: given **identical inputs twice**, with a small but
significant probability it returns two **different** lattice points whose difference structurally
exposes the secret key. Correctly-generated *randomized* Falcon includes a fresh per-signature salt, so
sampler inputs never repeat — safe. *Derandomized* variants (like Algorand `det1024`) lack that
protection and, if the two evaluations diverge, face **full private-key recovery**. No fault injection
is needed; natural implementation variation (e.g. Falcon's "dynamic" vs "tree" signing procedures)
suffices. NIST's own FIPS 206 (FN-DSA) status update states FN-DSA will **only allow randomized
signing** precisely because *"Deterministic signing could be dangerous."*

**Why TRELYAN is in this attack's scope at all.** `det1024` signatures are a pure function of
`(key, message)` — the sampler RNG is `SHAKE256(logn ‖ privkey ‖ data)`, no salt. This is not a choice:
Algorand's native `falcon_verify` opcode accepts **only** the deterministic, compressed, 0xBA-header
form, so the on-chain path *cannot* use randomized Falcon. Precondition P1 (derandomized signing) is
therefore met unavoidably.

**Preconditions and current status** (calibrated from an internal adversarial
prosecution/defense/neutral assessment; the paper's own preconditions, mapped onto this repo):

| # | Precondition | Status in TRELYAN |
| --- | --- | --- |
| **P1** | Derandomized signing (reproducible sampler input) | **Met, unavoidably** — required by the AVM opcode. |
| **P2** | The same `(key, message)` is signed twice | **Not met** in the sealed path (`seal.keygen_sign_seal` mints a fresh keypair per seal and signs once). **Met-capable** in the general retained-key API (`keygen()` → `sign(privkey, M)`). |
| **P3** | The two evaluations actually diverge (FP or algorithmic) | **Not met** under the pinned build; **not enforced at runtime**. |
| **P5** | Adversary obtains BOTH signatures | **Not met on-chain** (write-once ⇒ ≤1 signature per cell reaches the ledger); **partially met off-chain** (rejected `inscribe` app calls are still broadcast to relays). |

**Controls, and their real strength — stated honestly because an auditor will test each:**

1. **Fresh-key-per-seal (`seal.keygen_sign_seal`) — strongest, unconditional, but NOT the deployed
   default.** It defeats P2 *structurally* (a re-seal re-keygens, so no `(key, M)` is ever signed
   twice), and survives even a total tripwire-store bypass. **However, it currently has no call sites
   outside `sdk/tests/`** — every example, tutorial, README snippet, and `contracts/deploy_testnet.py`
   uses the retained-key general API. The strongest mitigation is the one users are not shown.
   *Action: make the sealed path the documented default and move examples onto it.*
2. **`FALCON_FPEMU=1` + pinned-tree digest — right target (P3), but the repo over-credits FPEMU
   alone.** The paper is explicit that exposure is possible *even with* integer-emulated FP, because
   its demonstrated discrepancy source is **algorithmic** (dynamic vs tree signing), not merely FP
   rounding. What actually holds is the **conjunction**: emulated FP **+** only the dynamic signing
   path being reachable **+** one digest-pinned source tree **+** the CI alignment/UBSan gate (which
   attacks the *cause* — UB-driven compiler divergence — and is arguably the strongest single piece of
   evidence here). Note also that this is a **build-time, CI-only** control: `FalconDet1024._load()`
   performs no runtime digest or FPEMU attestation, and the seal's post-sign self-verification cannot
   catch an off-pin signer (an off-pin signature is still a *valid* Falcon signature).
3. **On-chain write-once — bounds observation (P5), not a signer mitigation.** ≤1 signature per cell
   reaches the ledger. It does not stop off-chain repeated signing.

**Scoping, to avoid overstatement.** Signing *different* messages under one retained key is **not** the
attack (different M ⇒ different target/tape ⇒ no structured difference). Exposure requires re-signing an
*identical* message under an identical key across two divergent evaluations — in TRELYAN terms,
re-inscribing the identical artifact into the identical cell on the identical network.

**Residual risk, ranked.** (a) **Caller-side retry of `inscribe()`.** This is the most *reachable*
path, because it needs no deliberate re-inscription — only ordinary error handling.
`TrelyanInscriptionClient.inscribe()` signs internally (`inscription.py:136`), so **every call
re-signs**. A caller who wraps it in a retry loop for a network blip or a fee spike re-signs the
identical `(privkey, cell_id, artifact_hash, genesis_hash)`, producing an identical M — precondition
P2, met by accident. Nothing in the docstring warns against this.
*Note the SDK's own two-strategy submit is NOT affected*: `sig` is computed once and the fallback at
`inscription.py:149` re-sends the same `args` tuple rather than re-signing. The exposure is external
retry, not internal fallback. **Fix: document that `inscribe()` must not be wrapped in a retry, and
provide a sign-once/submit-many entry point that caches the signed args and re-submits those bytes.**
(b) An operator who retains a key via the general API and re-signs the same M across two builds that
diverge (different compiler/flags, a caller who built without the FPEMU config, or a future re-pin)
→ key recovery. (c) A caller who loads an arbitrary `.so` at `FALCON_DET1024_LIB` that is not the
pinned FPEMU build, since nothing checks it at runtime.

**Recommended controls (constitution-compliant — Tier 3 SDK Python or the eventual Tier 1 Rust port;
never a forbidden language), in order:** (1) make the sealed sign-once path the documented default and
move all examples onto it; (2) add a fail-closed load-time self-KAT to the signer (sign a known vector,
compare to a golden shipped as package data) so a non-pinned build cannot sign silently — noting the
existing `test_kat_private_key_does_not_leak_into_source` guardrail means the vector must be package
data, not embedded in source; (3) carry both natively into the recommended `trelyan-pq` Rust port
(self-KAT at library init, `zeroize` + `subtle`, `#![forbid(unsafe_code)]` outside the FFI module).

**Standards trajectory (a claims-accuracy consequence, not a bug).** Because FN-DSA will only permit
randomized signing, **`det1024` can never be FIPS 206 conformant as specified.** Algorand owns the
identical problem for its opcode, so any migration is coupled to Algorand's protocol roadmap and is not
TRELYAN's to solve unilaterally. Public materials must therefore **not** claim FIPS 206 / FN-DSA
conformance for the deterministic on-chain path (this repo's `PUBLIC_CLAIMS_HARDENING_2026-06-01.md`
already flags the related "NIST FIPS 206 Falcon-1024" wording).

**Honest limit of this analysis.** The eprint PDF body returns HTTP 403; the experimental section
(which quantifies the per-call divergence probability) has **not** been read. The quantitative
divergence rate is therefore unconfirmed here — which is *why* the 3-vector byte-identity KAT is
corroboration, not proof, and why **no public claim should be made about that rate** until the section
is read. This addendum makes no numeric claim about it.
