# TRELYAN — Audit Readiness (TEAL + Falcon path)

**Project:** TRELYAN — Falcon-1024 Inscription (open reference implementation).
**Repo:** `github.com/brandonjsellam-Releone/trelyan-falcon-inscription` · MIT (`LICENSE`).
**Status:** Reference implementation. Validated on localnet (20/20) and deployed to **Algorand TestNet**
(app `763809096`). **UNAUDITED — not for MainNet value.** Falcon here provides a **signature**
(integrity / authenticity), **not** encryption — no confidentiality is claimed.
**Date:** 2026-06-17.

This document is the **scope sheet for an independent security audit of the on-chain (TEAL) contract
and the Falcon signing/verification path.** Primary audit path: **NLnet NGI0 → Radically Open Security
(ROS)**; a paid engagement is the fallback. It is written to be auditor-agnostic and to let a reviewer
start on day one without reconstructing the trust surface.

> **Relationship to existing docs.** This file is the *security-audit* scope sheet (what an external
> firm should attack and confirm). It does **not** replace:
> - `AUDIT_READINESS_PACK.md` / `AUDITOR_HANDOFF.md` — the *formal-verification* brief (the I1–I5 /
>   C1–C5 proof obligations and the A1–A9 known-items ledger). Read that for the proof-of-invariants ask.
> - `THREAT_MODEL_AND_TRACEABILITY.md` — actors, trust boundaries, and the invariant→test→code matrix.
> - `SECURITY.md` — disclosure policy and the in/out-of-scope statement this sheet refines.
> - `REVIEWER.md` — the 5-minute, read-only reproduction (the **reproduction entry**, below).
> Where those go deeper, this sheet links rather than duplicates.

---

## 1. One paragraph (honest)

A Cell holder binds an off-chain artifact to the Algorand ledger by having a smart contract verify a
**deterministic Falcon-1024** signature — via the AVM native `falcon_verify` opcode (`0x85`, AVM v12 /
consensus v41 / go-algorand v4.3.0, published cost `costly(1700)`) — over a domain-separated message,
then writing a **write-once** record into box storage. The Falcon public key is committed once per Cell
at mint and read from chain state at inscribe, so it never rides in the call arguments. The value is
durable, third-party re-verifiable, quantum-resistant attestation. It is a **reference** on TestNet,
not a production system.

---

## 2. In scope (what we are asking the auditor to attack and confirm)

Every item maps to a file and the exact control. Line numbers are against `contracts/inscription.py`
as of 2026-06-17; the invariant/check IDs are stable and match `THREAT_MODEL_AND_TRACEABILITY.md` §3.

### 2.1 Inscription-contract invariants & checks (I1–I5, C1–C5)

| ID | Property | Control in `contracts/inscription.py` | Evidence |
|----|----------|----------------------------------------|----------|
| **I1** | Inscriptions are write-once & tamper-evident | `inscribe` C2 `assert cid not in self.inscriptions` (≈L272); `on_delete` = `assert False` (≈L353–356) | `test_double_inscribe_*`, `test_rejects_delete` |
| **I2** | Message integrity — M binds app, cell, artifact, network | `_build_message` (≈L302–311) | `test_cross_cell_replay_rejected`, `test_inscribe_rejects_tampered_sig` |
| **I3** | Public re-verifiability of the record | `get_inscription` (≈L335–342) + boxes `k_`/`i_` | `test_inscribe_accepts_valid` (read-back), `test_get_inscription_missing_raises` |
| **I4** | Key committed at mint, fixed (no rotation) | `register_cell` writes `committed_pubkey[cid]` once (≈L222–225); register-once asserts (≈L219–220) | `test_register_rejects_bad_pubkey_length`, `test_reregister_rejected`, `test_inscribe_rejects_wrong_key` |
| **I5** | Non-upgradable & non-deletable | `on_update` / `on_delete` = `assert False` (≈L348–356) | `test_rejects_update`, `test_rejects_delete` |
| **C1** | Ownership: holds the ASA ∧ is the recorded controlling owner | `inscribe` C1 (≈L266–269): `AssetHoldingGet` balance==1 **and** `controlling_owner[cid] == Txn.sender` | `test_flash_custody_rejected`, `test_update_owner_then_inscribe` |
| **C2** | Single-use / write-once | `inscribe` C2 (≈L272) | `test_double_inscribe_*` |
| **C3** | M reconstructed on-chain (never caller-supplied) | `_build_message` (≈L302–311), read from `Global.current_application_id` + `Global.genesis_hash` | `test_inscribe_accepts_valid`, `test_cross_cell_replay_rejected` |
| **C4** | Falcon-1024 signature valid (opcode) | `inscribe` (≈L288): `op.falcon_verify(m, falcon_sig.native, pubkey)` | `test_inscribe_accepts_valid`, `_rejects_tampered_sig`, `_rejects_wrong_key` |
| **C5** | Key is the one committed at mint (no substitution) | `inscribe` reads `committed_pubkey[cid]` (≈L278); `inscribe` takes **no** pubkey argument | `test_inscribe_rejects_wrong_key`, `test_inscribe_accepts_valid` |

**Primary audit ask for this block:** confirm that **no reachable path writes an `inscriptions[cid]`
box without passing C1–C5**, and that I1/I4/I5 hold across arbitrary prior histories (not just the 20
exercised paths). The finite localnet suite *exercises* these paths; it is not a proof over all
histories — that gap is exactly the engagement.

### 2.2 The `falcon_verify` opcode trust boundary

- The contract treats `op.falcon_verify(data, signature, public_key) -> bool` as a **trusted platform
  primitive** (see `contracts/A1_RESOLUTION_2026-06-01.md` for argument order/encoding pinning).
- **In scope:** that the contract *calls it correctly* — argument order, that `data` is the on-chain
  rebuilt `M` (not a caller arg), that `signature` is the raw compressed bytes (`.native`, no ARC4
  length prefix), that `public_key` is the committed key read from box state, and that the result is
  asserted (not ignored). Evidence: `contracts/inscription.py` (≈L288), `contracts/A1_RESOLUTION_2026-06-01.md`.
- **Out of scope:** the opcode's internal correctness (see §3).

### 2.3 Deterministic-Falcon encoding & salt handling (off-chain signer ↔ on-chain rebuild)

- Scheme: **round-3 deterministic Falcon-1024** (`falcon_det1024`), **not** FN-DSA / draft FIPS 206.
- Compressed encoding header byte **`0xBA`** (`0x3A | 0x80`, deterministic variant) + a 1-byte salt
  version (`CURRENT_SALT_VERSION = 0`); deterministic signing is RFC-6979 / Ed25519-style
  (`SHAKE256(logn‖privkey‖data)`), **not** a zeroed nonce.
- The message `M` (102 bytes) is signed **raw — do NOT pre-hash** (the opcode hashes internally).
- **In scope:** byte-identity between the off-chain signer and the on-chain rebuild; the header/salt
  assertion path; that the off-chain `falcon_det1024.build_message` matches `_build_message` exactly.
- Evidence: `contracts/falcon_det1024.py`, `sdk/src/trelyan_pq/message.py`,
  `contracts/FALCON_ENCODING_2026-06-01.md`, the 3-OS byte-identity KAT
  (`sdk/tests/test_signature_kat.py`, goldens begin `ba00`), the seeded fuzz/differential oracle
  (`sdk/tests/test_signature_fuzz.py`), and the pinned-build digest (`sdk/ci/verify_pinned_digest.py`).

### 2.4 Key lifecycle

- **Commit-at-mint, fixed:** the full 1793-byte Falcon public key is written once at
  `register_cell` and never rewritten; length (`PUBKEY_LEN = 1793`) and header byte (`0x0A`, logn=10)
  are validated at the **only** point a key enters state (≈L210–215). Evidence: `contracts/inscription.py`,
  `CELL_MINT_SPEC.md`.
- **No rotation / loss is irrecoverable by design** (intentional per I4/I5); disclosed to holders in
  `GOVERNANCE_AND_LIFECYCLE_POLICY.md`.
- **Sign-once-destroy (off-chain, defense-in-depth):** `sdk/src/trelyan_pq/seal.py` generates a
  keypair, signs the one message, and wipes the private-key buffer best-effort. **In scope:** the
  fail-closed ordering (tripwire before keygen; wipe in `finally`; record after self-verify). **Out
  of scope as a hard guarantee:** secure erasure (best-effort only — see £4, item K).
- Evidence: `contracts/inscription.py` register/inscribe paths; `sdk/src/trelyan_pq/seal.py`.

### 2.5 Opcode budget

- `inscribe` self-budgets with `ensure_budget(UInt64(2100), fee_source=OpUpFeeSource.GroupCredit)`
  (≈L286), placed **after** the cheap structural/ownership checks so unauthorized attempts reject
  cheaply (fail-fast), funded from the caller's own fee surplus.
- **In scope:** budget sufficiency for `falcon_verify` (cost 1700), fee-source correctness, and that
  the OpUp inner-txn fees are drawn from the caller (not the app). Evidence:
  `contracts/inscription.py` (≈L283–288), `contracts/FALCON_BUDGET_2026-06-01.md`.

### 2.6 Box-storage authorization

- Three BoxMaps, each keyed by `uint64_be(cell_id)`: `committed_pubkey` (`k_`), `controlling_owner`
  (`o_`), `inscriptions` (`i_`). Layout mirrored off-chain in `sdk/src/trelyan_pq/message.py`.
- **In scope:** register-once (`cid not in committed_pubkey / controlling_owner`, ≈L219–220),
  write-once (≈L272), admin-only `register_cell` (≈L197), the pure-NFT / no-clawback / no-freeze /
  no-manager binding (≈L199–207), `update_owner` authorization (current owner only, pre-inscription,
  ≈L317–329), and BoxMap miss-read semantics (a missing read **raises**, per `AUDIT-NOTE A3`).
- Evidence: `contracts/inscription.py`, `sdk/src/trelyan_pq/message.py`.

---

## 3. Out of scope (named so it is explicit)

- **The `falcon_verify` opcode internals** — platform trust. Soundness reduces to the opcode plus
  Algorand consensus; both are outside this repo's TCB. (`SECURITY.md`, `REVIEWER.md`.)
- **Algorand consensus / the AVM / fee & group semantics at the protocol level** — platform trust.
- **Falcon-1024's own cryptanalytic security** — the literature's: EUF-CMA in the (Q)ROM via a
  **non-tight** reduction on NTRU key-recovery (average-case) + NTRU-SIS. We claim neither SUF-CMA
  nor worst-case hardness. (`REVIEWER.md`, `TRELYAN_PROTOCOL_SPEC_v0.2.md`.)
- **Third-party dependencies** — report upstream; advisories tracked.
- **The off-chain media / website / SEO / generative Cell art** — not part of this codebase and not
  security-relevant to the on-chain record. (`SECURITY.md` out-of-scope clause.)
- **Legal / securities classification of Cells** — counsel's domain, not the audit's.

---

## 4. Known open items (disclosed, with disposition)

These are the residuals a finite localnet suite cannot close. Carried from
`THREAT_MODEL_AND_TRACEABILITY.md` §6 and `AUDIT_READINESS_PACK.md` §5 (A1–A9). We surface them so an
auditor spends week one on the real surface, not rediscovery.

| # | Item | Disposition (2026-06-17) | What the auditor confirms |
|---|------|--------------------------|---------------------------|
| A | **Cross-network replay.** `M` binds the native `Global.genesis_hash`. | Binding present; not localnet-testable. | Confirm sufficiency; exercise on TestNet. Residual: a redeployed app reusing the same app_id on a fork with identical genesis. |
| B | **Intra-group write-visibility** (same-group double-inscribe / flash-custody). | Closed on localnet (`test_double_inscribe_SAME_GROUP_rejected`, `test_flash_custody_rejected`); docs confirm sequential grouped exec + shared box budget. | Formal sign-off on the intra-group state-visibility assumption for this exact pattern (`AUDIT-NOTE A4`). |
| C | **1,024-cell cap** (`cells_registered < TOTAL_CELLS`). | Enforced in code; testing it needs 1,024 real ASAs. | Static confirmation. |
| D | **Write-once / immutability over arbitrary prior histories** and any future-AVM upgrade path. | Exercised, not proven. | The all-histories argument (the core formal ask). |
| E | **Opcode budget on a public network.** | Self-budgets on localnet (`ensure_budget(2100, GroupCredit)`). | Measure real cost/fees on TestNet; confirm fee-source mode. |
| K | **Best-effort key wipe** (sign-once-destroy). | Best-effort `memset` + mlock/VirtualLock; not secure erasure. | Confirm it is correctly scoped as defense-in-depth, not a boundary (`seal.py` docstring). |
| X | **Cross-endianness byte-identity.** | Argued by construction (all CI runners little-endian x86-64), not machine-exercised. | Note as a residual. |
| M | **App-account MBR funding** (~0.72 ALGO/cell; ~737 ALGO if fully minted). | Accepted Foundation cost; funding policy open. | Out of crypto scope; noted. |
| P | **On-chain inscriber address + committed pubkey persist on-chain.** | A public key + an address inherent to any Algorand txn, not PII per se; GDPR DPIA handled at the Foundation layer. | Note; not a contract defect. |

---

## 5. Artifacts the auditor receives

| Artifact | Path | What it gives the auditor |
|----------|------|---------------------------|
| Reference contract | `contracts/inscription.py` | The TEAL-source-of-truth (Algorand Python / PuyaPy 5.8.1 → AVM v12). Inline `AUDIT-NOTE A1–A9`. |
| Compiled output | `contracts/out/` | Approval/clear TEAL + ARC-56 app spec (diff against your own compile). |
| Off-chain signer | `contracts/falcon_det1024.py` | Deterministic Falcon-1024 ctypes signer/verifier; the byte-exact `M` builder. |
| Localnet suite | `contracts/test_inscription.py` | 20 tests: register→inscribe→read-back + attack-rejection vectors. |
| Published SDK | `sdk/src/trelyan_pq/` | `trelyan-pq` 0.1.0 (PyPI): `message.py`, `falcon.py`, `seal.py`. |
| Signature KAT | `sdk/tests/test_signature_kat.py`, `sdk/tests/vectors/det1024_kat.json` | Byte-identity goldens (begin `ba00`); 3-OS reproduction in CI. |
| Seeded fuzz / differential oracle | `sdk/tests/test_signature_fuzz.py` | Off-chain↔on-chain encoding differential (seed 1469, 300 iters). |
| Pinned-build verifier | `sdk/ci/verify_pinned_digest.py` | Recomputes the 27-file tree + `deterministic.c` digests + FP-emulation pin. |
| Read-only on-chain check | `sdk/examples/verify_trelyan.py` | 15/15 PASS against live app `763809096` (2026-06-17). |
| Hermetic checker | `Dockerfile.verify` | Pins python 3.13 + `trelyan-pq` 0.1.0; read-only. |
| CI | `sdk/ci/ci.yml` | wire-format / verify-live / signature-kat (3-OS) / testnet-e2e + a sanitizer (alignment/UBSan) gate. |
| Encoding / budget / arg-order memos | `contracts/FALCON_ENCODING_2026-06-01.md`, `contracts/FALCON_BUDGET_2026-06-01.md`, `contracts/A1_RESOLUTION_2026-06-01.md` | How encoding, opcode cost, and argument order were pinned, with sources. |
| Threat model & traceability | `THREAT_MODEL_AND_TRACEABILITY.md` | Actors, boundaries, invariant→test→code matrix, reproduction, TestNet checklist. |
| Formal-verification brief | `AUDIT_READINESS_PACK.md`, `AUDITOR_HANDOFF.md` | The I1–I5 / C1–C5 proof obligations + A1–A9 ledger. |
| Spec | `TRELYAN_PROTOCOL_SPEC_v0.2.md` | Message (§4), checks (§5), threat model (§6), honesty ledger. |
| Disclosure policy | `SECURITY.md` | Private reporting + the test-vector-key note. |

---

## 6. Pinned target & toolchain

| Item | Value |
|------|-------|
| TestNet application | `763809096` (asset `763809098`) |
| Approval-program fingerprint | `sha512_256 = d24d9071209f526a2075542d9408295d78f83ca5ed4c8cc233000130dcc97d44` (660 B; Update is blocked, so it is fixed) |
| On-chain verifier | AVM native `falcon_verify` (`0x85`, AVM v12 / consensus v41 / go-algorand v4.3.0, cost `costly(1700)`) |
| Pinned Falcon source | `algorand/falcon` commit `ce15e75bceb372867daf6b8e81918ab6978686eb` (GitHub source **tarball**, LF) |
| Source-tree digest | `sha512_256 = c6adf487…` (27 files); `deterministic.c = 601390dc…` |
| FP backend (pinned) | `FALCON_FPEMU=1`, `FALCON_FPNATIVE=0` (integer-only emulated fixed point) |
| Build flags | `-DFALCON_UNALIGNED=0 -fno-strict-aliasing` (proven byte-identical; -D/-f flags, source unchanged) |
| Toolchain | python **3.13** · `trelyan-pq` **0.1.0** · PuyaPy **5.8.1** · algokit-utils **v4** · AVM target **v12** |

---

## 7. Reproduction entry (start here — read-only)

The fast, no-trust path is **`REVIEWER.md`** (≈5 minutes, read-only, from public inputs):

```
pip install trelyan-pq
python3 sdk/examples/verify_trelyan.py          # 15/15 PASS vs live app 763809096 (2026-06-17)
```

Hermetic alternative (pins python 3.13 + `trelyan-pq` 0.1.0):

```
docker build -f Dockerfile.verify -t trelyan-verify . && docker run --rm trelyan-verify
```

Signer byte-identity KAT (build the pinned Falcon lib first — `REVIEWER.md` step 2):

```
FALCON_DET1024_LIB=/path/to/libfalcon_det1024.so python3 -m pytest sdk/tests/test_signature_kat.py -v
```

Pinned-build digest:

```
python3 sdk/ci/verify_pinned_digest.py <path-to-falcon-source-tree>   # -> PINNED BUILD VERIFIED
```

Full contract reproduction (localnet, PuyaPy → AVM v12, 20/20) is in
`THREAT_MODEL_AND_TRACEABILITY.md` §4.

---

## 8. What this does **not** establish (honest boundaries)

- **Not audited.** No third-party security audit has been performed; this is the package *for* one.
- **Verifier correctness is assumed** — soundness reduces to the `falcon_verify` opcode + consensus.
- **Falcon's security is the literature's** — EUF-CMA, non-tight, NTRU-based; no worst-case guarantee.
- **Off-chain key hygiene is best-effort**, not secure erasure, and not a defense against a local
  attacker present during the single signing event.
- **Cross-endianness** byte-identity is argued by construction, not machine-tested.
- The 20 localnet tests *exercise* the paths and *reject* the exercised attack vectors; they are
  **not** a proof of the invariants over all histories, encodings, or upgrade paths.

We would rather an auditor find a claim here too strong than discover it later. Corrections welcome
via `SECURITY.md`.
