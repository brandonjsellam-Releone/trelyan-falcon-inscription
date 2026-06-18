# Falcon signature encoding for `falcon_verify` — what the off-chain signer MUST produce

**Date:** 1 June 2026 · **Why this exists:** after A1 (argument order) was resolved, the single
likeliest remaining way to get a *false negative* — a correct contract that rejects a valid-looking
signature — is **signature-encoding mismatch**. This memo pins the exact encoding Algorand's
`falcon_verify` opcode expects, sourced from Algorand's own Falcon headers. Get this wrong and the
audit test fails for the wrong reason.

## The headline (the trap)
Algorand's `falcon_verify` verifies **Deterministic Falcon-1024 (`falcon_det1024`) in COMPRESSED
format** — NOT the randomized/"salted" Falcon that generic libraries (liboqs, `pqcrypto`, most NIST
KAT tooling) emit. Algorand's own header says it outright: the deterministic signature *"is
incompatible with randomized ('salted') Falcon signatures: it excludes the salt (nonce), adds a
salt version byte, and changes the header byte."*

**Consequence:** the test scaffold's original suggestion (`pip install pqcrypto`) would produce
signatures that **fail** `falcon_verify` even though `inscription.py` is correct. Use
`algorand/falcon`'s `falcon_det1024_sign_compressed`.

## Exact constants (Falcon-1024, logn = 10), computed from `algorand/falcon` headers
| Quantity | Value | Source |
|---|---|---|
| Public key size | **1793 B** | `FALCON_PUBKEY_SIZE(10) = (7<<8)+1` — matches contract `PUBKEY_LEN` |
| Private key size | **2305 B** | `FALCON_PRIVKEY_SIZE(10) = ((10-5)<<8)+(1<<10)+1` |
| Standard compressed max | 1462 B | `FALCON_SIG_COMPRESSED_MAXSIZE(10)` |
| **Det compressed max** | **1423 B** | `= 1462 − 40 (drop nonce) + 1 (salt-version byte)` |
| Det compressed typical | ~1222 B | std compressed avg 1261 − 40 + 1 |
| Det **compressed header byte** | **`0xBA`** | `0x3A \| 0x80` (high bit = deterministic) |
| Det **CT header byte** | `0xDA` | `0x5A \| 0x80` (CT format — NOT what the opcode here wants) |
| Current salt version | `0` | `FALCON_DET1024_CURRENT_SALT_VERSION` |

`falcon_verify` infers the format from the header byte. A valid signature for THIS contract begins
with **byte `0xBA`**, followed by the 1-byte salt version (`0x00`), then the compressed-encoded
`s2` polynomial. If the first byte is `0x3A` you handed it a randomized sig — wrong variant.

## What the off-chain signer must do (and what the contract already does)
- Off-chain: `falcon_det1024_keygen` → (privkey 2305 B, pubkey 1793 B); then
  `falcon_det1024_sign_compressed(privkey, M)` where **M is the raw message the contract rebuilds**
  (`DOMAIN_TAG ‖ app_id ‖ cell_id ‖ artifact_hash ‖ genesis_id_hash`). Do **not** pre-hash M —
  the signer hashes internally with the fixed deterministic salt.
- On-chain: `op.falcon_verify(M, sig, pubkey)` — already correct (A1). The opcode re-derives the
  hash-to-point with the same fixed salt and checks the lattice short-vector.
- The committed key check `sha512_256(pubkey) == committed_key_hash` (C5) is independent of the sig
  encoding and already correct.

A runnable signer (`falcon_det1024.py`) and a round-trip self-test ship alongside this memo; wire
them into `test_inscription.py` (its `falcon_keypair`/`falcon_sign` stubs).

## Two small follow-ups this surfaced (optional, low-risk)
1. **Website sig-size figure (resolved).** Public copy now states **~1,222 B** (≤1423 B) for the
   deterministic compressed signature — typically ~1,222–1,233 B (KAT goldens 1232–1233). The 1,280 B
   figure is the distinct *padded* form, not the compressed size; ~1,262 B is the compressed average.
2. **Optional contract hardening.** Before the (opcode-heavy) verify, you may add
   `assert falcon_sig.length <= UInt64(1423), "sig too large"` as a cheap upper bound — rejects an
   oversized blob before paying for `falcon_verify`. Not required for correctness; nice for budget
   safety. (Leave the lower bound off — compressed sigs are genuinely variable.)

## Sources
- `algorand/falcon` — `deterministic.h` (det1024 API, header bytes `0x3A|0x80` / `0x5A|0x80`,
  salt-version byte, "incompatible with randomized Falcon").
- `algorand/falcon` — `falcon.h` (size macros `FALCON_PUBKEY_SIZE`/`FALCON_PRIVKEY_SIZE`/
  `FALCON_SIG_COMPRESSED_MAXSIZE`, SHAKE256 context layout, format header-byte inference).
- Algorand Developer Portal — `falcon_verify` opcode ("signature format is the compressed Falcon
  encoding").
