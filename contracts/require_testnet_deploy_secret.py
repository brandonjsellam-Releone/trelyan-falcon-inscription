#!/usr/bin/env python3
"""Fail closed unless the TestNet deploy secret is present and usable.

Prints only secret NAMES. Never prints values, never writes them to a file,
never interpolates them into a log line. algosdk raises ValueError with the
word list when a mnemonic is invalid — that exception must never reach a log.

Required repository secret (Settings -> Secrets and variables -> Actions):

    DEPLOYER_MNEMONIC    25-word funded Algorand TestNet account

Not required (the sanctioned path uses the public TestNet algod):

    ALGOD_URL, ALGOD_TOKEN, ALGOD_SERVER, ALGOD_PORT, ALGOD_*

Never set for this job:

    any MainNet mnemonic or token

Exit 0 = required secret is present (and, with --parse, is a valid mnemonic).
Exit 1 = BLOCKED; stdout lists the exact missing or invalid names.
Exit 2 = could not complete the parse check (algosdk not installed).
"""

from __future__ import annotations

import argparse
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
INVALID_MNEMONIC = (
    "BLOCKED: DEPLOYER_MNEMONIC is set but is not a valid Algorand mnemonic."
)
VALUE_NOT_PRINTED = "Replace the repository secret. The value is not printed."


def missing_required() -> list[str]:
    return [name for name in REQUIRED if not os.environ.get(name, "").strip()]


def _word_count(mn: str) -> int:
    return len(mn.split())


def print_missing() -> int:
    print("BLOCKED: TestNet redeploy cannot run. Missing repository secret(s):")
    for name in missing_required():
        print(f"  - {name}")
    print()
    print("Set them under Settings -> Secrets and variables -> Actions.")
    print("Use a dedicated, low-balance TestNet account only.")
    print("Faucet: https://bank.testnet.algorand.network/")
    print("Do not add MainNet keys. Do not add paid infra.")
    print("Not required:")
    for name in NOT_REQUIRED:
        print(f"  - {name}")
    return 1


def parse_mnemonic_ok(mn: str) -> bool:
    """True iff algosdk accepts mn. Never raises with mn in the exception."""
    try:
        from algosdk.mnemonic import to_private_key
    except ImportError as exc:
        raise RuntimeError("algosdk not installed") from exc
    try:
        to_private_key(mn)
        return True
    except Exception:
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--parse",
        action="store_true",
        help="also require a valid Algorand mnemonic (needs algosdk; never prints the value)",
    )
    args = parser.parse_args(argv)

    missing = missing_required()
    if missing:
        return print_missing()

    mn = os.environ.get("DEPLOYER_MNEMONIC", "")
    n = _word_count(mn)
    if n != 25:
        print(f"BLOCKED: DEPLOYER_MNEMONIC must be 25 words (got {n}).")
        print(VALUE_NOT_PRINTED)
        return 1

    if args.parse:
        try:
            ok = parse_mnemonic_ok(mn)
        except RuntimeError:
            print("COULD NOT CHECK: algosdk is not installed; cannot parse DEPLOYER_MNEMONIC.")
            print(VALUE_NOT_PRINTED)
            return 2
        if not ok:
            print(INVALID_MNEMONIC)
            print(VALUE_NOT_PRINTED)
            print("Faucet: https://bank.testnet.algorand.network/")
            return 1
        print("required TestNet deploy secret parses as an Algorand mnemonic (value not printed)")
        return 0

    print("required TestNet deploy secret(s) are present (values not printed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
