# Live demo (Algorand TestNet)

The reference contract is **deployed and verified on Algorand TestNet**:

- **App ID `763809096`** — https://lora.algokit.io/testnet/application/763809096
- A real post-quantum inscription was written **only after** an on-chain Falcon-1024 verification
  passed and every authorization check succeeded — the same validated path covered by the 20/20
  localnet suite.

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
