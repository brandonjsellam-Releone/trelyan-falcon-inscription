# Trap 1 — the opcode wants *deterministic*, compressed Falcon (header `0xBA`)

Algorand's native `falcon_verify` opcode does **not** accept generic Falcon-1024 from liboqs or
pqcrypto. It requires **deterministic, COMPRESSED** Falcon, whose first byte is **`0xBA`**.

**Why `0xBA`?** The standard compressed-1024 signature header is `0x3A`. Algorand requires the
high bit set to select *deterministic* mode:

```
0x3A | 0x80  =  0xBA
```

A randomized signature (header `0x3A`) is **rejected on-chain** — and you only discover it *after*
spending the (expensive) `falcon_verify` opcode budget. This single detail costs the next team a
day or more.

`trelyan_pq.falcon` emits exactly the accepted bytes:

```python
from trelyan_pq import FalconDet1024
falcon = FalconDet1024()
pk, sk = falcon.keygen()
sig = falcon.sign(sk, message)     # message = the RAW M (see Trap 2 / quickstart); do NOT pre-hash
assert sig[0] == 0xBA
```

Sizes you can rely on (asserted in the SDK): public key **1793 B**, deterministic compressed
signature **≤ 1423 B**, salt-version byte `0`.

The signer is a thin `ctypes` binding over the `algorand/falcon` C library — the same code path
Algorand uses for State Proofs — so the bytes are interoperable by construction. Build it once
(see the [quickstart](01-quickstart.md)).
