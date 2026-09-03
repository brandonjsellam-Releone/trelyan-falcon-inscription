# Blockers

Open items that keep a check red on purpose. Do not close one by skipping the
check or by copying a hash off the chain and calling it agreement.

---

## CLOSED 2026-09-03 — was: awaiting TestNet redeploy of app 763809096

**Status: CLOSED.** Resolved the only way it could be, by deploying a NEW
application from the committed artifact — not by skipping the check, and not by
copying a hash off the chain and calling it agreement.

    contracts/verify_deployment.py --app-id 770964251  ->  MATCH  (exit 0)
      expected (committed TEAL) : 709 B  sha512_256 6fa5cee1...b981c4b
      deployed app 770964251    : 709 B  sha512_256 6fa5cee1...b981c4b

    sdk/examples/verify_trelyan.py  ->  18 passed, 0 failed   (was 17 / 1)

New app **770964251**, cell ASA **770964264**, deployed 2026-09-03. Signature
header 0xba (det1024 deterministic marker). App **763809096** remains on chain,
unmodified, as the historical record — it was never patched, because I1/I5
forbid it.

The measured drift is preserved verbatim below. It is quoted by
`sdk/tests/test_testnet_drift_banner.py`, which is kept as a regression guard:
if drift ever recurs, the banner must still name the app and both sizes rather
than degrade into a silent skip.

**How long it stayed open, deliberately:** three months. The check ran and
failed publicly that entire time rather than being folded into the green gates.

---

### Historical record — the drift as measured while this was OPEN

**Status at the time:** OPEN. Local merge gates were green. The live chain did
not match the committed contract. That mismatch was the finding.

**Why CI is split.** `Required merge gates (local)` (trelyan-pq CI) and
`Required merge gates (rust)` (rust-ci) stay blocking. Live TestNet bytecode
match is [TestNet follow-up](.github/workflows/testnet-followup.yml): it still
runs, still fails, and must not be a required merge check until this blocker
closes. Folding those jobs back into the required workflow to “make main
green” would hide the drift.

**Do not** spend money, use production secrets, or deploy to MainNet. TestNet
only. App `763809096` **cannot be updated in place** — `on_update` / `on_delete`
reject every UpdateApplication / DeleteApplication (invariants I1/I5).
Redeploy means **create a new TestNet app** from the committed artifacts, then
retarget the constants below.

### Measured drift

Recorded on GitHub Actions run
[33099650683](https://github.com/brandonjsellam-Releone/trelyan-falcon-inscription/actions/runs/33099650683)
(2026-08-27, commit `14515d4`). Re-measure before you redeploy —
`python contracts/verify_deployment.py` prints live numbers.

| Side | Size | `sha512_256` (Algorand program hash) |
|---|---|---|
| Committed TEAL, assembled via TestNet algod | **709 B** | `6fa5cee145762e4a0c2ba93738a0e6f51e93b02c71f23e4e663ac6d73b981c4b` |
| Live TestNet app **763809096** | **660 B** | `d24d9071209f526a2075542d9408295d78f83ca5ed4c8cc233000130dcc97d44` |

The 660 B fingerprint is also pinned in `sdk/examples/verify_trelyan.py` as
`PINNED_ON_CHAIN_SHA512_256`. That pin only proves the June 2026 app was not
*replaced*; it does **not** prove the app implements `contracts/inscription.py`
as committed. Source correspondence is the 709 B row.

Local source → TEAL (`teal-matches-source`) already agrees. The chain predates
that source (contract changed `2ec798e` / 2026-06-16; app created 2026-06-02).

Explorer (historical only):
https://lora.algokit.io/testnet/application/763809096

### BLOCKED — repository secret this agent cannot use

An unattended agent **cannot** list Actions secrets (HTTP 403) and **cannot**
dispatch `trelyan-pq CI` / `testnet-e2e` (HTTP 403). No `DEPLOYER_MNEMONIC` is
present in the agent environment. Issue
[#5](https://github.com/brandonjsellam-Releone/trelyan-falcon-inscription/issues/5)
is still open asking for that secret. Do not invent a mnemonic. Do not scrape
files for one.

**Required repository secret** (Settings → Secrets and variables → Actions):

| Secret | Required? | Why |
|---|---|---|
| `DEPLOYER_MNEMONIC` | **YES** | 25-word funded TestNet account. Signs `create()` / fund / register / inscribe. |
| `ALGOD_URL` | no | `AlgorandClient.testnet()` uses the public TestNet algod. |
| `ALGOD_TOKEN` | no | same |
| `ALGOD_SERVER` | no | same |
| `ALGOD_PORT` | no | same |
| `ALGOD_*` | no | same |
| any MainNet mnemonic / token | **must not be set** | This job is TestNet only. |

Once `DEPLOYER_MNEMONIC` is set, run the keyed job — do not spend, do not
MainNet:

1. Actions → **TestNet redeploy** (`.github/workflows/testnet-redeploy.yml`) →
   **Run workflow** → type `TESTNET`.
2. Or Actions → **trelyan-pq CI** → **Run workflow** (`testnet-e2e`).

Both fail closed with the table above if the secret is missing. Neither prints
the mnemonic. Success is a **new** TestNet app id whose assembled bytecode
**MATCH**es at **709 B**. Then continue at step 5 below.

### One-shot redeploy checklist (Brandon, or the keyed job above)

No signing keys in an unattended agent. Use a funded **TestNet** account and
`DEPLOYER_MNEMONIC` in the environment or the repo secret of the same name.
Faucet: https://bank.testnet.algorand.network/ — a few ALGO is enough.

1. **Confirm local gates are still green** (no need to redeploy a dirty tree):

   ```
   python contracts/verify_teal_matches_source.py
   python contracts/verify_client_matches_arc56.py
   ```

2. **Build the pinned Falcon library** (same flags as CI / `PINNED_BUILD.md`):

   ```
   cc -O3 -fPIC -DFALCON_UNALIGNED=0 -fno-strict-aliasing -shared \
     -o libfalcondet1024.so \
     third_party/falcon-det1024/src/codec.c \
     third_party/falcon-det1024/src/common.c \
     third_party/falcon-det1024/src/falcon.c \
     third_party/falcon-det1024/src/fft.c \
     third_party/falcon-det1024/src/fpr.c \
     third_party/falcon-det1024/src/keygen.c \
     third_party/falcon-det1024/src/rng.c \
     third_party/falcon-det1024/src/shake.c \
     third_party/falcon-det1024/src/sign.c \
     third_party/falcon-det1024/src/vrfy.c \
     third_party/falcon-det1024/src/deterministic.c
   export FALCON_DET1024_LIB="$PWD/libfalcondet1024.so"
   ```

3. **Generate the typed client** if you just recompiled (already committed today):

   ```
   (cd contracts && puyapy inscription.py --out-dir out --target-avm-version 12)
   algokit generate client contracts/out/TrelyanInscription.arc56.json \
     --output contracts/trelyan_client.py
   ```

4. **Deploy a new TestNet app** from that client (creates a **new** app id):

   ```
   pip install -r contracts/requirements.txt
   export DEPLOYER_MNEMONIC="…"   # never commit; TestNet only
   python contracts/deploy_testnet.py
   ```

   Or, if the repo secret is set, run a keyed job (same secret name):

   - Actions → **TestNet redeploy** → type `TESTNET`. This path runs
     `contracts/deploy_testnet.py` and then
     `verify_deployment.py --app-id <NEW>` (must MATCH / 709 B).
   - Actions → **trelyan-pq CI** → **Run workflow** (`testnet-e2e`). That path
     uses `sdk/examples/quickstart.py` and also prints a new app id.

5. **Record the new ids and the new program hash** from the script / explorer.
   Then:

   ```
   python contracts/verify_deployment.py --app-id <NEW_APP_ID>
   ```

   Success is `MATCH` and **709 B** (or whatever the committed TEAL assembles
   to on that day) on both sides. Exit 1 is still drift. Exit 2 is “could not
   check” — do not treat that as a match.

6. **Retarget the repo** (same PR or a follow-up). At least:

   | What | Where |
   |---|---|
   | Default app id | `contracts/verify_deployment.py` (`DEFAULT_APP_ID`) |
   | Reviewer script | `sdk/examples/verify_trelyan.py` (`APP_ID`, `PINNED_ON_CHAIN_SHA512_256`) |
   | Status / explorer links | `README.md`, `REVIEWER.md`, `sdk/docs/DEMO.md`, `ROADMAP.md`, `AUDIT_READINESS.md` |
   | This blocker | close the section below once the follow-up is green |

   Leave app `763809096` in git history as the June 2026 inscription. Do not
   pretend it implements the current source.

7. **Confirm the follow-up is green.**
   `TestNet follow-up` / `Committed TEAL vs deployed app` and
   `Live TestNet verification` must both exit 0. Then this item is closed.
   After that, branch protection **may** require those checks; until then it
   must not.

### After this closes

- Point `Required merge gates (local)` + `Required merge gates (rust)` remain
  the merge blockers.
- Optionally require the TestNet follow-up as well — only once it is honestly
  green.
- Do not MainNet.
