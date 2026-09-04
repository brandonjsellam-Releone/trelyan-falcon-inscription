# TRELYAN — Falcon‑1024 Inscription (open reference)

An open‑source reference implementation of **post‑quantum inscriptions on Algorand**: a smart contract
that verifies a **Falcon‑1024** signature *on‑chain* using Algorand's native `falcon_verify` opcode,
then writes a **write‑once** record. Built so any Algorand developer can fork the pattern for
post‑quantum authorization in their own contract.

> **Live on Algorand TestNet** (3 September 2026): app **`770964251`**, asset `770964264` —
> https://lora.algokit.io/testnet/application/770964251 . The on‑chain `i_` inscription box is written
> only *after* the Falcon‑1024 signature verifies on‑chain and every authorization check passes, so the
> deployment is a real, publicly verifiable post‑quantum inscription.
>
> **The deployed program is byte-for-byte the contract in this repository.** Run
> `python contracts/verify_deployment.py` and it prints `MATCH`: the chain serves 709 B
> (`6fa5cee1…`) and this source assembles to the same 709 B and the same digest. It cannot
> drift away from that silently, *by design* — control **I5 (non-upgradability)** makes
> `on_update` and `on_delete` reject unconditionally (`contracts/inscription.py:404-412`),
> which is enforced by the contract itself, not by deployment convention.
>
> **The history is kept on purpose, including the part that reflects badly on us.** The previous
> app **`763809096`** (deployed 2 June 2026) served 660 B (`d24d9071…`) and did **not** match this
> source: the contract changed after deployment, and I5 forbids patching a deployed app in place.
> The divergence lasted **79 days** — and for the first **58 of them nothing detected it**, because
> the verifier of the day hashed the deployed program and compared it to the chain. That check
> could not fail. `contracts/verify_deployment.py` was rebuilt to be *able* to fail on 2026-08-13
> (#12); the drift it then exposed was split out of the merge gates and left **red in public** on
> 2026-08-30, and closed on 2026-09-03 by deploying a new application from the committed artifact.
> So: 58 days undetected, 21 days from detectable to closed, 4 of those publicly red. Nothing was
> ever silenced, but nothing caught it early either. `763809096` remains on chain, unmodified, as
> the historical record.
>
> **What this means for a reviewer:** reading this source *is* reviewing app `770964251`.
> `sdk/examples/verify_trelyan.py` reports **18 passed, 0 failed**.

**Status (honest):** last localnet validation was **20/20 on 2026-06-01**; the contract changed on
2026-06-16 and the suite is now **22 tests with no recorded localnet run** (see
[`LOCALNET_VALIDATION_2026-06-01.md`](LOCALNET_VALIDATION_2026-06-01.md)). **Deployed on TestNet,
and the deployed app IS this source** — the follow-up job checks the live app's bytecode
fingerprint against the committed TEAL and has passed since the 2026-09-03 redeploy; it is kept
out of the required merge gates only because it needs live algod, and it is never silenced.
**Not yet externally audited; not on MainNet.** Treat as a reference, not production‑ready. MIT licensed.

## Verify it yourself

You don't have to trust us — **[`REVIEWER.md`](REVIEWER.md)** is a 5-minute, read-only independent
verification guide. The short version:

```
pip install trelyan-pq && python3 sdk/examples/verify_trelyan.py        # live TestNet + pinned-bytecode assert
docker build -f Dockerfile.repro -t trelyan-repro . \
  && docker run --rm trelyan-repro sh scripts/verify_all.sh             # full hermetic rebuild, all axes
```

The hermetic build compiles the pinned Falcon source, asserts the source-tree digest, and reproduces the
committed signatures **byte-for-byte**, then verifies the live deployment — read-only, from a clean container.

**Validation:** SDK suite 34/34 (1 env-skip); byte-identity KAT green on Linux / macOS / Windows (3-OS CI);
coverage-guided fuzzing of the encoder (atheris) and the C verifier (libFuzzer · ASan/UBSan) ran 13.8M +
2.07M inputs with zero crashes. Audit scope: [`AUDIT_READINESS.md`](AUDIT_READINESS.md). Supply-chain
provenance (SLSA + cosign) on tagged releases: [`RELEASES.md`](RELEASES.md).

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
# compile the contract + generate the typed client.
# Run from contracts/ with the BARE filename: puya writes the source path as typed into the
# emitted TEAL comments, so compiling from the repo root produces `// contracts/inscription.py`
# instead of the committed `// inscription.py` — 124 differing lines, none of them a real
# change. The out-dir must also sit beside inscription.py (as out/ does), because the .puya.map
# records the source path relative to it. contracts/verify_teal_matches_source.py enforces both.
(cd contracts && puyapy inscription.py --out-dir out --target-avm-version 12)
algokit generate client contracts/out/TrelyanInscription.arc56.json --output contracts/trelyan_client.py
# run the suite (localnet) or deploy to TestNet:
python -m pytest contracts/test_inscription.py -v          # 20 passed
python contracts/deploy_testnet.py                          # needs DEPLOYER_MNEMONIC + a funded TestNet account
```

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
