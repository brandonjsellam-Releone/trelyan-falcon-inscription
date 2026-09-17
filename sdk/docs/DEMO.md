# Live demo (Algorand TestNet)

The reference contract is **deployed on Algorand TestNet**; its approval and clear-state programs are what the committed TEAL assembles to, and its state schemas and extra-program-pages equal the committed artifacts (`contracts/verify_deployment.py`; the app's global-state contents (including the admin address), box contents and creator are not compared), and the inscription below was accepted by the AVM's `falcon_verify` (the same `algorand/falcon@ce15e75b` code this repo pins, so not an independent verification):

- **App ID `770964251`** — https://lora.algokit.io/testnet/application/770964251
- A real post-quantum inscription was written **only after** an on-chain Falcon-1024 verification
  passed and every authorization check succeeded — the same contract whose 28-test suite CI runs on LocalNet
  (last run on `main` 28/28, 2026-09-04).

## Reproduce it with the SDK

```bash
pip install "trelyan-pq[algorand]"
export FALCON_DET1024_LIB=/path/to/libfalcondet1024.so          # build steps: tutorials/01
export DEPLOYER_MNEMONIC="<25-word funded TestNet account>"     # faucet: https://bank.testnet.algorand.network/

# generate the typed client from the contract ARC-56 (see ../../contracts), then:
PYTHONPATH="src:../contracts:." python examples/quickstart.py
```

Expected output: a fresh app is deployed, a cell ASA is minted, the committed key is registered,
the artifact is inscribed after an on-chain Falcon verification, and the record reads back — with
the new app and asset IDs printed.

## In CI

The `testnet-e2e` job in `.github/workflows/ci.yml` runs this on demand (`workflow_dispatch`)
once a `DEPLOYER_MNEMONIC` repository secret is set — so each run leaves a public, reproducible
record of a live post-quantum inscription with its app/asset IDs in the run log.
