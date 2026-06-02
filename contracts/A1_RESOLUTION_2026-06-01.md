# A1 Resolution — `falcon_verify` argument order & signature encoding

**Date:** 1 June 2026 · **Status of A1:** RESOLVED by official documentation; one belt-and-suspenders
TEAL/test confirmation deferred to compile time (sandbox VM unavailable this session).

A1 was the single CRITICAL open item in the reference contract: *is the `falcon_verify` call in
`inscription.py` using the correct argument order and signature encoding?* If wrong, check C4 (the
whole authorization model) silently fails. This memo records the resolution and its sources so the
Runtime Verification auditor does not have to re-derive it.

## The finding

Algorand exposes Falcon verification as a **native AVM opcode**, `falcon_verify`, with signature:

```
falcon_verify(data, signature, public_key) -> bool      # signature in COMPRESSED Falcon encoding
```

- **data** — the message that was signed
- **signature** — the Falcon-1024 signature, **compressed** encoding (variable length, ~1.0–1.5 KB)
- **public_key** — the Falcon-1024 public key (**1793 bytes**)

## Why the contract is correct

`inscription.py` (C4, line ~194):

```python
assert op.falcon_verify(m, falcon_sig.bytes, pubkey), "falcon signature invalid"
```

maps to **(data = m, signature = falcon_sig, public_key = pubkey)** — exactly the documented order.

Supporting constants/types in the contract are also consistent with the spec:
- `PUBKEY_LEN = 1793` and `assert pubkey.length == PUBKEY_LEN` → correct Falcon-1024 pubkey length.
- `falcon_sig: arc4.DynamicBytes` (no fixed-length assert) → correct, because the compressed
  signature is variable-length. (A fixed-length assert here would be a bug.)
- `m` is reconstructed on-chain by `_build_message` (domain tag ‖ app_id ‖ cell_id ‖ artifact_hash
  ‖ genesis_id_hash), so the verifier signs over exactly what the chain rebuilds (defeats
  cross-cell / cross-app replay).

## Sources
- Algorand Developer Portal — `op.falconVerify` function reference (algorand-typescript) and the
  `algopy` `op.falcon_verify` API reference.
- Algorand Developer Portal — AVM opcodes reference (`falcon_verify`).
- algorand.co — "Technical Brief: Quantum-resistant transactions on Algorand with Falcon
  signatures" (states the opcode takes `(data, signature, public_key)`, compressed encoding).

## Residual (must still be done at compile/test time — NOT blockers to the code being right)
1. **TEAL dump:** after `algokit project run build`, open the approval TEAL and confirm the
   `falcon_verify` operand order in the emitted opcode (mechanical sanity check).
2. **Live test vector:** generate a real Falcon-1024 keypair off-chain, sign the reconstructed
   message `M`, and assert `inscribe` accepts the valid signature and rejects a tampered one
   (`test_inscription.py`).
3. **Encoding match (now the likeliest failure mode):** confirm the off-chain signer (liboqs /
   `pqcrypto` / `falcon.py`) emits the **same compressed signature encoding** Algorand's
   `falcon_verify` expects. Algorand's Falcon library has a specific byte framing; a wrong framing
   makes a *valid* signature fail verification even though the contract logic is correct.

## What changed in the repo as a result
- `inscription.py`: AUDIT-NOTE A1 downgraded CRITICAL → RESOLVED-by-docs (kept visible, not
  deleted; residual recorded).
- `COMPILE_REVIEW_2026-06-01.md`: item 3 marked resolved with the same finding.
