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
> **The deployed approval program is byte-for-byte what this repository's committed approval TEAL assembles to** (the clear-state program is not compared).
> Run `python contracts/verify_deployment.py` and it prints `MATCH`: the chain serves 709 B (`6fa5cee1…`) and the
> committed TEAL (`contracts/out/TrelyanInscription.approval.teal`) assembles to the same 709 B and digest. A separate
> CI job (`teal-matches-source`) recompiles `inscription.py` with the pinned puya and checks the committed TEAL is what
> it compiles to; `verify_deployment.py --recompile` does both locally (needs puya). The deployed program itself cannot
> change, *by design*: control **I5 (non-upgradability)** makes `on_update` and `on_delete` reject unconditionally (`contracts/inscription.py:404-412`), enforced by the contract itself, not by deployment convention.
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
> **What this means for a reviewer:** reading this source is reviewing the approval program of app `770964251` through two checked links: the chain's approval program matches what the committed approval TEAL assembles to (`verify_deployment.py`, run by the TestNet follow-up; the clear-state program is not compared), and the committed TEAL is what this source compiles to (CI job `teal-matches-source`). Both passed on `1b349f7` on 2026-09-07 (runs 34123818653 and 34123725705).
> `sdk/examples/verify_trelyan.py` reports **18 passed, 0 failed**.

**Status (honest):** the contract suite (`contracts/test_inscription.py`, **28 tests**) runs on LocalNet in CI on pushes and
PRs (not on the weekly schedule) and last passed **28/28 on 2026-09-04** (run 33836856910, `f8ae52c`; `contracts/inscription.py`,
`contracts/out/` and `contracts/test_inscription.py` unchanged since); [`LOCALNET_VALIDATION_2026-06-01.md`](LOCALNET_VALIDATION_2026-06-01.md) is the dated 20/20 record of the earlier contract. **Deployed on TestNet,
and the deployed approval program IS what this source's committed approval TEAL assembles to** — the follow-up job assembles
`contracts/out/TrelyanInscription.approval.teal` and compares the result with the deployed bytecode; it has passed since the 2026-09-03 redeploy (latest: run 34123818653, 2026-09-07); it is kept
out of the required merge gates only because it needs live algod, and it is never silenced.
**Not yet externally audited; not on MainNet.** Treat as a reference, not production‑ready. MIT licensed.

## Verify it yourself

**[`REVIEWER.md`](REVIEWER.md)** is a 5-minute, read-only guide to checking these claims yourself — and it
names what you still have to trust (our package and scripts, the algod endpoint, and the pinned Falcon C
source, which the AVM verifier also runs). The short version:

```
pip install trelyan-pq && python3 sdk/examples/verify_trelyan.py        # live TestNet + pinned-bytecode assert
docker build -f Dockerfile.repro -t trelyan-repro . \
  && docker run --rm trelyan-repro sh scripts/verify_all.sh             # full hermetic rebuild, all axes
```

The hermetic build compiles the pinned Falcon source, asserts the source-tree digest, and reproduces the
committed signatures **byte-for-byte**, then verifies the live deployment — read-only, from a clean container.

**Validation:** SDK suite **144 passed, 6 skipped** with the pinned library built (Linux and macOS; Windows 145 passed,
5 skipped — CI run 33836856910, 2026-09-04; 4 of the 6 skips are the optional algo-pqc-kit interop differential, and
`pytest -rs` prints every reason); contract suite **28/28** on LocalNet; byte-identity KAT green on Linux / macOS / Windows (3-OS CI);
coverage-guided fuzzing of the encoder (atheris) and the C verifier (libFuzzer · ASan/UBSan) ran 13.8M +
2.07M inputs with zero crashes. Audit scope: [`AUDIT_READINESS.md`](AUDIT_READINESS.md). Supply-chain
provenance (SLSA + cosign) is wired for future tagged releases in `release.yml` ([`RELEASES.md`](RELEASES.md)); it
has not run yet: tags v0.2.0 / v0.2.1 predate it and carry no attestations, and PyPI `trelyan-pq` 0.1.0 was not built by it.

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
- `contracts/test_inscription.py` — the 28-test contract suite, run on LocalNet in CI.
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
# instead of the committed `// inscription.py` — 67 lines of the approval TEAL, one per such
# comment, and the ARC-56 JSON line that embeds that TEAL, none of them a real
# change. The out-dir must also sit beside inscription.py (as out/ does), because the .puya.map
# records the source path relative to it. contracts/verify_teal_matches_source.py enforces both.
(cd contracts && puyapy inscription.py --out-dir out --target-avm-version 12)
algokit generate client contracts/out/TrelyanInscription.arc56.json --output contracts/trelyan_client.py
# run the suite (localnet) or deploy to TestNet:
python -m pytest contracts/test_inscription.py -v          # 28 passed
python contracts/deploy_testnet.py                          # needs DEPLOYER_MNEMONIC + a funded TestNet account
```

## Scope of the claim
Post‑quantum **authorization at the inscription layer** — not total quantum resistance (Algorand's own
consensus‑crypto upgrades are separate). Falcon‑1024 is NIST‑selected and the basis of the forthcoming
**FIPS 206 (FN‑DSA)**, which is **not yet published**. This reference signs with Algorand's **deterministic**
Falcon‑1024 variant (det1024, header `0xBA`) pinned at `algorand/falcon@ce15e75b` — the variant the AVM
`falcon_verify` opcode accepts — and makes **no FIPS 206 / FN‑DSA conformance claim**: NIST's provisional plan
for FIPS 206 permits randomized signing only, so det1024 would not conform unless that changes, and any migration
depends on Algorand changing its opcode (see `THREAT_MODEL_AND_TRACEABILITY.md`, "Standards trajectory"). When
FIPS 206 is published we will document how it relates to this reference.

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
