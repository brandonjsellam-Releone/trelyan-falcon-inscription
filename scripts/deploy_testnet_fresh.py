#!/usr/bin/env python3
"""Deploy from a FRESH throwaway TestNet account whose seed never leaves this process.

Sibling of `deploy_testnet_secure.py`. That one prompts for an existing mnemonic; this one
generates a new account instead, for when the old deployer's mnemonic has been lost.

Why generate in-process rather than `python -c "...print(mnemonic)"` then paste:

  * printing the mnemonic puts it in terminal scrollback, and from there into screenshots,
    screen-shares and shell logs;
  * pasting it into a prompt puts it on the clipboard, which other processes can read;
  * writing it to a file to "keep it safe" is the durable copy we are trying to avoid.

Here the seed exists only as a local in one Python process, is handed to the audited deploy path
as a child-process environment variable, and is gone when the process exits. Only the ADDRESS is
ever displayed — that is public and is what the faucet needs.

The cost of that: if this process dies before the deploy finishes, the account is unrecoverable
and any ALGO in it is stranded. On TestNet that is free to redo — generate again, re-faucet. Do
NOT use this script for an account you intend to keep, and never on MainNet.

Like its sibling it refuses to do anything when FALCON_DET1024_LIB is missing, so a run that would
deploy, fund and then die at keygen never gets started.

  cd /c/dev/trelyan-falcon-inscription
  python scripts/deploy_testnet_fresh.py

Deliberately thin: generate, show the address, wait for funds to actually arrive, exec the real
script. Any logic beyond that belongs in contracts/deploy_testnet.py, which is the audited path.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time
import urllib.request

REPO = pathlib.Path(__file__).resolve().parent.parent
DEPLOY = REPO / "contracts" / "deploy_testnet.py"
ALGOD = "https://testnet-api.algonode.cloud"
FAUCET = "https://bank.testnet.algorand.network/"
# The redeploy locks ~0.951 ALGO (app base + global schema + the 1793 B pubkey box and the 105 B
# record box) plus fees. Ask for a little over that so a marginal faucet grant does not half-deploy.
NEEDED_MICROALGO = 2_000_000
POLL_SECONDS = 5
POLL_LIMIT = 120  # 10 minutes


def find_falcon_lib() -> str | None:
    """An already-set FALCON_DET1024_LIB wins; otherwise look where the BUILD note puts it."""
    already = os.environ.get("FALCON_DET1024_LIB")
    if already:
        return already
    for name in ("falcondet1024.dll", "libfalcondet1024.so", "libfalcondet1024.dylib"):
        candidate = REPO / "build" / "falcon" / name
        if candidate.is_file():
            return str(candidate)
    return None


def balance(address: str) -> int:
    """Live spendable-ish balance in microALGO. 0 for an account the chain has never seen."""
    try:
        with urllib.request.urlopen(f"{ALGOD}/v2/accounts/{address}", timeout=20) as r:
            import json

            return int(json.load(r).get("amount", 0))
    except Exception:
        return 0


def main() -> int:
    if not DEPLOY.is_file():
        print(f"not found: {DEPLOY}", file=sys.stderr)
        return 2

    lib = find_falcon_lib()
    if not lib:
        print(
            "FALCON_DET1024_LIB is not set and no library was found under build/falcon/.\n"
            "Build it first (see scripts/deploy_testnet_secure.py's BUILD note) and run the KAT.\n"
            "Refusing to generate an account for a run that would fail at keygen anyway.",
            file=sys.stderr,
        )
        return 2

    try:
        from algosdk import account, mnemonic
    except ImportError:
        print("py-algorand-sdk is not installed: pip install py-algorand-sdk", file=sys.stderr)
        return 2

    print(f"falcon library: {lib}")

    private_key, address = account.generate_account()
    seed = mnemonic.from_private_key(private_key)
    del private_key

    print("\n" + "=" * 78)
    print("FRESH TESTNET ACCOUNT — the mnemonic is held in memory only and is never shown,")
    print("written, or copied. It dies with this process. TestNet only; do not reuse.")
    print("=" * 78)
    print(f"\n  ADDRESS:  {address}\n")
    print(f"  1. Fund it at {FAUCET}")
    print(f"  2. This waits until it sees at least {NEEDED_MICROALGO / 1e6:.2f} ALGO arrive.")
    print("     Ctrl+C to abort — nothing has been deployed and the account is simply discarded.\n")

    for _ in range(POLL_LIMIT):
        micro = balance(address)
        if micro >= NEEDED_MICROALGO:
            print(f"\nfunded: {micro / 1e6:.6f} ALGO. proceeding.\n")
            break
        print(f"  waiting for funds... {micro / 1e6:.6f} ALGO", end="\r", flush=True)
        time.sleep(POLL_SECONDS)
    else:
        print(
            f"\ntimed out waiting for {NEEDED_MICROALGO / 1e6:.2f} ALGO. Nothing was deployed; "
            "the generated account is discarded. Re-run to try again.",
            file=sys.stderr,
        )
        return 2

    env = dict(os.environ)
    env["DEPLOYER_MNEMONIC"] = seed
    env["FALCON_DET1024_LIB"] = lib
    del seed

    print(f"running {DEPLOY.relative_to(REPO)} ...\n")
    return subprocess.call([sys.executable, str(DEPLOY)], cwd=str(REPO), env=env)


if __name__ == "__main__":
    raise SystemExit(main())
