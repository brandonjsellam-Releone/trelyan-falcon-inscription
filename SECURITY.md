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

## Planned hardening

An **independent third-party security audit** is planned before any MainNet
deployment. If supported, we intend to pursue NLnet's audit path via Radically
Open Security. Until that audit completes, every public claim in this repo is
deliberately scoped to "reference / TestNet / unaudited."
