# Independent Verification Guide

**Verify TRELYAN's core claims yourself in ~5 minutes — no trust in us required.**

This is the fast path for a reviewer or auditor. Everything below is read-only and reproducible from
public inputs. Deeper analysis lives in `TRELYAN_PROTOCOL_SPEC_v0.2.md` and
`THREAT_MODEL_AND_TRACEABILITY.md`; a more detailed reviewer packet is available on request.

> **Scope.** Reference implementation on Algorand **TestNet**, **unaudited**, not for value. Falcon here
> provides a **signature** (integrity/authenticity), **not** encryption — no confidentiality is claimed.
> The deployed scheme is **round-3 deterministic Falcon-1024** (`falcon_det1024`), **not** FN-DSA /
> draft FIPS 206 (which remains unpublished as of mid-2026).

---

## Frozen verification target

| Item | Value |
|---|---|
| TestNet application | `763809096` (asset `763809098`) |
| Approval-program fingerprint | `sha512_256 = d24d9071209f526a2075542d9408295d78f83ca5ed4c8cc233000130dcc97d44` (660 B; `verify_trelyan.py` asserts this — Update is blocked, so it is fixed) |
| Pinned Falcon source | `algorand/falcon` commit `ce15e75bceb372867daf6b8e81918ab6978686eb` |
| Source-tree digest | `sha512_256 = c6adf487…` (27 files); `deterministic.c = 601390dc…` |
| FP backend (pinned) | `FALCON_FPEMU=1`, `FALCON_FPNATIVE=0` (integer-only emulated fixed point) |
| Pinned toolchain | python **3.13** · `trelyan-pq` **0.1.0** (PyPI) · PuyaPy **5.8.1** · algokit-utils **v4** · AVM target **v12** |
| On-chain verifier | AVM native `falcon_verify` opcode (`0x85`, **AVM v12** / consensus v41 / go-algorand v4.3.0), published cost `costly(1700)` |

---

## The 5-minute verification

### 1. On-chain + offline constants (no build needed)
```
pip install trelyan-pq
python3 sdk/examples/verify_trelyan.py
```
*Hermetic alternative* (pins python 3.13 + `trelyan-pq` 0.1.0, read-only): `docker build -f Dockerfile.verify -t trelyan-verify . && docker run --rm trelyan-verify`. For the **full** offline rebuild — compile the pinned Falcon lib + byte-identity KAT + digest gate, all in one container, then the on-chain check: `docker build -f Dockerfile.repro -t trelyan-repro . && docker run --rm trelyan-repro sh scripts/verify_all.sh` runs Axes A–D and prints one PASS/FAIL (both containers verified green on 2026-06-17: `verify` 15/15, `repro` 4/4).
Read-only. Confirms: the package constants (domain tag, 102-byte message, `0xBA` det-header, sig ≤1423 /
pubkey 1793); offline golden vectors (`sha512_256`, `build_message`, box names `k_`/`o_`/`i_`); the **live**
TestNet app `763809096` (prints its bytecode `sha512_256` fingerprint — diff it against your compile of
`contracts/inscription.py`); the registered 1793-byte Falcon public keys in box storage; and a byte-exact
local reconstruction of the domain-separated message `M` a live inscription must have signed. On 2026-06-17 this returned **15/15 PASS** against the live app — 1 registered cell (`763809098`) and 1 on-chain inscription — and asserted the pinned bytecode fingerprint above.

### 2. Signer byte-identity KAT (offline — proves determinism)
Build the pinned Falcon library, then:
```
FALCON_DET1024_LIB=/path/to/libfalcon_det1024.so \
  python3 -m pytest sdk/tests/test_signature_kat.py -v
```
Re-signs the committed vectors (`sdk/tests/vectors/det1024_kat.json`, goldens begin `ba00`) and asserts the
output is **byte-identical** to the goldens — including a one-byte-flip negative control.

### 3. Pinned-build digest (proves you built the exact source we pin)
```
python3 sdk/ci/verify_pinned_digest.py <path-to-falcon-source-tree>
```
Recomputes the 27-file tree digest, `deterministic.c` digest, and the FP-emulation pin → `PINNED BUILD VERIFIED`.

### Cross-platform reproducibility (already demonstrated)
The CI `signature-kat` job runs the byte-identity KAT on **Linux (gcc), macOS (clang), and Windows (MSVC)**;
the last run (commit `e49470a`) reproduced the committed goldens **byte-for-byte on all three OSes**, with the
alignment/UBSan sanitizer gate green on the Linux leg. The only residual is cross-**endianness**, argued by
construction (all CI runners are little-endian x86-64) rather than machine-exercised.

---

## Claims → evidence map

| Claim | Where to check |
|---|---|
| Signature is over a fixed 102-byte domain-separated `M` (tag‖app_id‖cell_id‖artifact_hash‖genesis_hash), signed **raw** | `sdk/src/trelyan_pq/message.py` (build), `contracts/inscription.py` `_build_message` (on-chain rebuild) |
| On-chain `M` is rebuilt from chain state (`Global.current_application_id`, `Global.genesis_hash`), never from caller args | `contracts/inscription.py:302-311` |
| Verification is the AVM `falcon_verify` opcode (outside our TCB), not a hand-rolled in-contract check | `contracts/inscription.py:288`; `SECURITY.md` |
| Public key is committed write-once per cell in box storage; `inscribe` takes no pubkey argument (no key substitution) | `contracts/inscription.py` register/inscribe paths |
| Write-once: a cell cannot be re-inscribed; Update/Delete OnCompletions blocked | invariants I1–I5, `THREAT_MODEL_AND_TRACEABILITY.md` |
| Deterministic signing is RFC-6979/Ed25519-style (`SHAKE256(logn‖privkey‖data)`), **not** a zeroed nonce | `contracts/falcon_det1024.py`; spec §1 |
| det-compressed signature: typically ~1222–1233 B (KAT goldens), ≤1423 B; compressed average ≈1262 B; padded fixed 1280 B; pubkey 1793 B | `TRELYAN_PROTOCOL_SPEC_v0.2.md` §param; `verify.html` |
| 20/20 localnet suite (register→inscribe→read-back + attack-rejection vectors) | `contracts/test_inscription.py`, `LOCALNET_VALIDATION_2026-06-01.md` |

---

## What this does **not** establish (honest boundaries)

- **Not audited.** No third-party security audit has been performed; this is a reference, not production.
- **Verifier correctness is assumed.** Soundness reduces to the `falcon_verify` opcode plus Algorand
  consensus — both outside this repository's trusted computing base.
- **Falcon's security is the literature's.** EUF-CMA in the (Q)ROM via a **non-tight** reduction resting on
  NTRU key-recovery (average-case; no clean worst-case-to-average-case guarantee) + NTRU-SIS. We decline
  worst-case-hardness and SUF-CMA claims.
- **Off-chain key hygiene is best-effort**, not secure erasure, and not a defense against a local attacker
  present during the single signing event.
- **Cross-endianness** byte-identity is argued by construction, not machine-tested.

We would rather you find a claim here too strong than discover it later. Issues and corrections welcome.
