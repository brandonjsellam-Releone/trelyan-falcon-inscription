# Contributing

Contributions are welcome. This is an **open reference** for post-quantum
inscriptions on Algorand, published so any developer can study, reproduce, fork,
and improve the pattern.

## Project status (honest)

- **Reference implementation.** Validated 20/20 on localnet, deployed + verified
  on Algorand TestNet. **Not externally audited; not on MainNet.**
- **Currently solo-maintained** by Brandon J. Sellam. The project is actively
  **seeking a co-maintainer** (cryptography / Algorand smart-contract review).
  If that's you, open an issue or email **fondation@trelyan.ch**.

## Build & test

The pinned toolchain and full reproduction steps are in the README ("Reproduce")
and `THREAT_MODEL_AND_TRACEABILITY.md` §4. In short: PuyaPy 5.8.1 +
algorand-python on Python 3.13, algokit localnet (Docker), AVM target v12.

```
python contracts/falcon_det1024.py                         # signer self-test
puyapy contracts/inscription.py --out-dir contracts/out --target-avm-version 12
python -m pytest contracts/test_inscription.py -v          # 20 passed
```

## How to propose changes

1. **Open an issue first** for anything that changes protocol behavior, an
   invariant (I1–I5), or a check (C1–C5) — so the design discussion is public.
2. For fixes, send a PR. **Any behavior change must add or update a test** and
   keep the invariant -> test -> code traceability matrix in
   `THREAT_MODEL_AND_TRACEABILITY.md` accurate.
3. Keep claims precise and non-overstated (this is security/crypto tooling).

## Decision-making

Design decisions are recorded in the spec, threat model, and the review memos in
`contracts/` (`COMPILE_REVIEW`, `RED_TEAM_REVIEW`, `A1_RESOLUTION`). As the
project grows a co-maintainer and a foundation steward, governance will move to a
documented multi-maintainer model.

## Licensing

Inbound = outbound: contributions are accepted under the project's **MIT**
license (see `LICENSE`).

## AI-assistance transparency

Parts of the specification and documentation in this repository were drafted with
AI assistance and then human-reviewed and tested. We disclose this in the spirit
of NLnet's generative-AI policy; the cryptographic design choices and the
test-verified behavior are the human-reviewed source of truth.
