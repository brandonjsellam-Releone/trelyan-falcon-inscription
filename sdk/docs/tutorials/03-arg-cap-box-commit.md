# Trap 2 — the 2048-byte ApplicationArgs cap, and the box-commit fix

A single Algorand app call caps total **ApplicationArgs at 2048 bytes**. But a Falcon-1024 public
key (**1793 B**) *plus* a compressed signature (**≤1423 B**) is ~3 KB — it does not fit in one
call.

**The fix:** commit the public key into a **box** at registration, then at inscribe time pass
**only the signature**. The key is bound to the cell by construction, and each call's args stay
under the limit.

`trelyan_pq.message` gives you the exact box names the contract uses. Each BoxMap key is a
prefix + `uint64_be(cell_id)`:

```python
from trelyan_pq import box_refs, committed_pubkey_box_name, inscription_box_name

committed_pubkey_box_name(1)      # b'k_\x00\x00\x00\x00\x00\x00\x00\x01'  (immutable, set at register)
box_refs(1)                       # the 3 boxes an inscribe call reads/writes:
#   k_<cell>  committed_pubkey      (1793 B, write-once at register)
#   o_<cell>  controlling_owner     (32 B)
#   i_<cell>  inscription record    (write-once)
```

Flow:

1. `register_cell(cell, owner, pubkey)` writes the `k_` box **once** (immutable). 1793-byte key
   never travels in args again.
2. `inscribe(cell, artifact_hash, sig, uri)` passes only the ~1.4 KB signature; the contract reads
   the committed key from its box and runs `falcon_verify`.

The high-level client supplies these box references (and the opcode-budget fee) for you — see
[end-to-end](04-end-to-end-inscribe-verify.md).
