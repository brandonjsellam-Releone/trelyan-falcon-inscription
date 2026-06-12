# TRELYAN — Falcon‑1024 Inscription (open reference)

An open‑source reference implementation of **post‑quantum inscriptions on Algorand**: a smart contract
that verifies a **Falcon‑1024** signature *on‑chain* using Algorand's native `falcon_verify` opcode,
then writes a **write‑once** record. Built so any Algorand developer can fork the pattern for
post‑quantum authorization in their own contract.

> **Live on Algorand TestNet** (2 June 2026): app **`763809096`**, asset `763809098` —
> https://lora.algokit.io/testnet/application/763809096 . The on‑chain `i_` inscription box is written
> only *after* the Falcon‑1024 signature verifies on‑chain and every authorization check passes, so the
> deployment is a real, publicly verifiable post‑quantum inscription. Reproducible via
> `contracts/deploy_testnet.py`.

**Status (honest):** validated **20/20 on localnet** and **deployed + verified on TestNet**. **Not yet
externally audited; not on MainNet.** Treat as a reference, not production‑ready. MIT licensed.

## Why this exists — two integration traps, solved and documented
Algorand ships `falcon_verify` as a live native AVM opcode, but two non‑obvious things will cost the
next team a week. This repo solves both, with the reasoning written down:

1. **The opcode wants *Deterministic* Falcon‑1024, COMPRESSED, header `0xBA`** (`0x3A` is the standard compressed-1024 header; the `| 0x80` high bit selects the deterministic mode Algorand's opcode requires) — not
   generic randomized Falcon (`0x3A`), which is rejected. `contracts/falcon_det1024.py` is an off‑chain
   signer that emits exactly the accepted bytes, byte‑matched to the on‑chain message build.
2. **A single app call's ApplicationArgs total is capped at 2048 bytes**, but a Falcon‑1024 public key
   (1793 B) + compressed signature (≤1423 B) is ~3 KB. The fix: commit the public key into a **box** at
   registration and pass only the signature at inscribe. See `contracts/inscription.py`.

## What's here
- `contracts/inscription.py` — the reference contract (Algorand Python / PuyaPy, AVM v12).
- `contracts/falcon_det1024.py` — off‑chain deterministic Falcon‑1024 signer (ctypes over `algorand/falcon`).
- `contracts/test_inscription.py` — the 20‑test localnet suite.
- `contracts/deploy_testnet.py` — one‑command end‑to‑end TestNet demo (deploy → mint → register → inscribe → verify).
- `TRELYAN_PROTOCOL_SPEC_v0.2.md`, `THREAT_MODEL_AND_TRACEABILITY.md`, `LOCALNET_VALIDATION_2026-06-01.md`,
  `FALCON_ENCODING_2026-06-01.md`, `FALCON_BUDGET_2026-06-01.md` — spec, threat model + invariant→test→code
  matrix, validation record, and the encoding/opcode‑budget notes.

## Reproduce
Toolchain: PuyaPy 5.8.1 + algorand‑python on **Python 3.13** (PuyaPy does not support 3.14); algokit
localnet (Docker); algokit‑utils v4; the deterministic `algorand/falcon` C library built to a shared
object; AVM target **v12**. Full pinned steps are in `THREAT_MODEL_AND_TRACEABILITY.md` §4. In short:

```
# build the deterministic Falcon lib, then self-test the off-chain signer:
python contracts/falcon_det1024.py
# compile the contract + generate the typed client:
puyapy contracts/inscription.py --out-dir contracts/out --target-avm-version 12
algokit generate client contracts/out/TrelyanInscription.arc56.json --output contracts/trelyan_client.py
# run the suite (localnet) or deploy to TestNet:
python -m pytest contracts/test_inscription.py -v          # 20 passed
python contracts/deploy_testnet.py                          # needs DEPLOYER_MNEMONIC + a funded TestNet account
```

## Verify it yourself (one command, no account)

```
pip install trelyan-pq
python sdk/examples/verify_trelyan.py
```

Fourteen read-only checks against the live TestNet deployment (application
`763809096`): package constants, pinned golden vectors, the deployed bytecode
fingerprint, the on-chain Falcon-1024 public key and inscription record, and a
byte-exact local rebuild of the domain-separated message. CI runs the same
verification weekly — see the Actions tab. The deterministic Falcon source we
build from is pinned and reproducible: see `PINNED_BUILD.md`.

## Scope of the claim
Post‑quantum **authorization at the inscription layer** — not total quantum resistance (Algorand's own
consensus‑crypto upgrades are separate). Falcon‑1024 is NIST‑selected and the basis of the forthcoming
**FIPS 206 (FN‑DSA)** standard, **not yet finalized**; this reference tracks the current Falcon spec and
Algorand's opcode and will version when FIPS 206 finalizes.

## Scope & relationship to TRELYAN

This repository is the **post-quantum inscription tooling** — the open primitive:
a contract that verifies a Falcon-1024 signature on-chain and writes a write-once
record, plus the off-chain signer, tests, spec, and threat model. It is
**MIT-licensed and fully open**, and the grant-relevant work happens here, in the open.

- **"Cell" is a technical identifier** — a per-record NFT (`cell_id`) that the
  reference design keys inscriptions to. The reference cap of 1,024 records is a
  parameter of this implementation, **not a sales construct**.
- **This codebase contains no token sale, fundraising, pricing, or commercial
  product.** Any separate TRELYAN non-profit/foundation activity is governed
  elsewhere and is **not required** to build, run, reproduce, or fork anything here.
- **Reuse encouraged:** fork the pattern for post-quantum authorization in any
  Algorand contract. The construction is chain-agnostic in principle; Algorand is
  the reference substrate because its native `falcon_verify` opcode makes on-chain
  verification possible today.

## License
MIT — see `LICENSE`.
