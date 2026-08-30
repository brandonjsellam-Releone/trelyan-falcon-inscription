#!/usr/bin/env python3
"""Fail closed unless the TestNet deploy secret is present.

Prints only secret NAMES. Never prints values, never writes them to a file,
never interpolates them into a log line.

Required repository secret (Settings → Secrets and variables → Actions):

    DEPLOYER_MNEMONIC    25-word funded Algorand TestNet account

Not required (the sanctioned path uses the public TestNet algod):

    ALGOD_URL, ALGOD_TOKEN, ALGOD_SERVER, ALGOD_PORT, ALGOD_*

Never set for this job:

    any MainNet mnemonic or token

Exit 0 = required secret(s) present (values not printed).
Exit 1 = BLOCKED; stdout lists the exact missing names.
"""

from __future__ import annotations

import os
import sys

REQUIRED = ("DEPLOYER_MNEMONIC",)
NOT_REQUIRED = (
    "ALGOD_URL",
    "ALGOD_TOKEN",
    "ALGOD_SERVER",
    "ALGOD_PORT",
    "ALGOD_*",
)


def missing_required() -> list[str]:
    return [name for name in REQUIRED if not os.environ.get(name, "").strip()]


def main() -> int:
    missing = missing_required()
    if missing:
        print("BLOCKED: TestNet redeploy cannot run. Missing repository secret(s):")
        for name in missing:
            print(f"  - {name}")
        print()
        print("Set them under Settings → Secrets and variables → Actions.")
        print("Use a dedicated, low-balance TestNet account only.")
        print("Faucet: https://bank.testnet.algorand.network/")
        print("Do not add MainNet keys. Do not add paid infra.")
        print("Not required:")
        for name in NOT_REQUIRED:
            print(f"  - {name}")
        return 1
    print("required TestNet deploy secret(s) are present (values not printed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
