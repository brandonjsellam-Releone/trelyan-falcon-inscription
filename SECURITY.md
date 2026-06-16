# Security Policy

TRELYAN — Falcon-1024 Inscription (open reference). This repository is a
**reference implementation**. It is validated on localnet (20/20) and deployed
to **Algorand TestNet**, but it is **not externally audited and is not intended
for MainNet value**. Treat it as a reference, not production-ready software.

## Reporting a vulnerability

Please report suspected security issues **privately** to:

- **Email:** fondation@trelyan.ch
- Subject line: `SECURITY — trelyan-falcon-inscription`

Include, where possible: a description, affected file/function, the invariant or
check (I1–I5 / C1–C5) you believe is violated, and a minimal reproduction
against `contracts/test_inscription.py` or a TestNet transaction.

We aim to acknowledge reports on a **best-effort basis** (the project is
currently solo-maintained — see `CONTRIBUTING.md`). Please allow reasonable time
for a fix before any public disclosure; we will credit reporters who wish it.

## In scope

- The reference contract logic (`contracts/inscription.py`) and its invariants.
- The off-chain deterministic Falcon-1024 signer (`contracts/falcon_det1024.py`)
  and the on-chain / off-chain message-construction match.
- The spec and threat model (`TRELYAN_PROTOCOL_SPEC_v0.2.md`,
  `THREAT_MODEL_AND_TRACEABILITY.md`).

## Out of scope

- The Algorand AVM, the `falcon_verify` opcode, and the consensus layer.
- Third-party dependencies (report upstream); we will track advisories.
- The economics or governance of any separate TRELYAN activity — not part of
  this codebase.

## Test vectors (committed test keys are intentional)

`sdk/tests/vectors/det1024_kat.json` is a **known-answer test (KAT)** fixture. By design it
contains a **committed test-only keypair — including a private key** — plus fixed messages and their
expected signatures, used to assert byte-identical signatures across compilers and operating systems
(the build-divergence / determinism control).

This follows standard cryptographic practice: NIST PQC KATs (`.rsp`), IETF RFC test vectors
(Ed25519/ECDSA), and Google Wycheproof all ship private keys inside their test files — because the
verifier must reproduce a *fixed* answer. **This key is a PUBLIC TEST VECTOR, not an operational
secret:** it is a throwaway bound to no Cell, never used on-chain, never produced via the
sign-once-destroy (`keygen_sign_seal`) path, and must never be used operationally. Secret scanners
will flag it by design; it is allow-listed by path in `.gitleaks.toml`, and a test
(`test_kat_private_key_does_not_leak_into_source`) fails the build if those key bytes ever appear in
source outside that one fixture. The repo rule "never commit secrets" targets operational credentials,
not published test vectors.

## Planned hardening

An **independent third-party security audit** is planned before any MainNet
deployment. If supported, we intend to pursue NLnet's audit path via Radically
Open Security. Until that audit completes, every public claim in this repo is
deliberately scoped to "reference / TestNet / unaudited."
