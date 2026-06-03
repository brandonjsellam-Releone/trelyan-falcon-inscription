"""
trelyan_pq.message — on-chain message construction + box/encoding helpers for TRELYAN
post-quantum inscriptions on Algorand.

Dependency-light (Python stdlib only). These primitives encode the two integration traps
the reference implementation solves, as reusable helpers:

  1. **Byte-exact signed message.** The message M you sign off-chain must be byte-identical
     to what the contract rebuilds on-chain: domain-separated and binding app_id + cell_id +
     artifact hash + network genesis hash. `build_message()` produces exactly that. Sign M
     directly with the deterministic Falcon-1024 signer — do NOT pre-hash it.

  2. **The 2048-byte ApplicationArgs cap.** A Falcon-1024 public key (1793 B) plus a
     compressed signature (<=1423 B) is ~3 KB, over the AVM's per-call arg limit. The pattern:
     commit the public key into a box at registration, then pass only the signature at
     inscribe. The box-name helpers here mirror the contract's BoxMap layout exactly.

All values match the reference contract (inscription.py) and spec v0.2 (§4, §1.1, §1.3).
"""

from __future__ import annotations

import hashlib
from typing import List

__all__ = [
    "DOMAIN_TAG",
    "PUBKEY_LEN",
    "SIG_COMPRESSED_MAXSIZE",
    "DET_COMPRESSED_HEADER",
    "TOTAL_CELLS",
    "INS_VERSION",
    "MAX_APP_ARGS_TOTAL_BYTES",
    "MESSAGE_LEN",
    "sha512_256",
    "artifact_hash",
    "cell_key",
    "committed_pubkey_box_name",
    "controlling_owner_box_name",
    "inscription_box_name",
    "box_refs",
    "build_message",
]

# --- protocol constants (must match inscription.py / spec v0.2) -------------------------------
DOMAIN_TAG = b"TRELYAN-INSCRIPTION-v1"      # 22 bytes; spec §4 domain separation tag
PUBKEY_LEN = 1793                           # Falcon-1024 public key length (spec §1.1)
SIG_COMPRESSED_MAXSIZE = 1423               # deterministic compressed signature, max bytes
DET_COMPRESSED_HEADER = 0xBA                # 0x3A | 0x80 — deterministic-compressed Falcon-1024
TOTAL_CELLS = 1024                          # reference cap (an implementation parameter)
INS_VERSION = 1                             # InscriptionRecord.version
MAX_APP_ARGS_TOTAL_BYTES = 2048             # AVM cap that forces the pubkey-box-commit pattern

# M = DOMAIN_TAG(22) + app_id(8) + cell_id(8) + artifact_hash(32) + genesis_hash(32)
MESSAGE_LEN = len(DOMAIN_TAG) + 8 + 8 + 32 + 32  # == 102

# Contract BoxMap key prefixes (inscription.py): committed_pubkey=k_, controlling_owner=o_,
# inscriptions=i_  — each keyed by uint64_be(cell_id).
_KEY_PREFIX_PUBKEY = b"k_"
_KEY_PREFIX_OWNER = b"o_"
_KEY_PREFIX_INSCRIPTION = b"i_"


def sha512_256(data: bytes) -> bytes:
    """SHA-512/256 artifact-commitment hash (spec §1.3). Returns 32 bytes."""
    h = hashlib.new("sha512_256")
    h.update(data)
    return h.digest()


# readable alias at call sites: artifact_hash(file_bytes)
artifact_hash = sha512_256


def cell_key(cell_id: int) -> bytes:
    """8-byte big-endian encoding of a cell_id — the BoxMap key body."""
    if not isinstance(cell_id, int) or cell_id < 0 or cell_id > 0xFFFFFFFFFFFFFFFF:
        raise ValueError("cell_id must be a uint64 (0 .. 2**64-1)")
    return cell_id.to_bytes(8, "big")


def committed_pubkey_box_name(cell_id: int) -> bytes:
    """Box holding the immutable committed Falcon public key for `cell_id` (prefix k_)."""
    return _KEY_PREFIX_PUBKEY + cell_key(cell_id)


def controlling_owner_box_name(cell_id: int) -> bytes:
    """Box holding the controlling-owner address for `cell_id` (prefix o_)."""
    return _KEY_PREFIX_OWNER + cell_key(cell_id)


def inscription_box_name(cell_id: int) -> bytes:
    """Box holding the write-once InscriptionRecord for `cell_id` (prefix i_)."""
    return _KEY_PREFIX_INSCRIPTION + cell_key(cell_id)


def box_refs(cell_id: int) -> List[bytes]:
    """The three box references an `inscribe` app call reads/writes for a cell (k_, o_, i_)."""
    return [
        committed_pubkey_box_name(cell_id),
        controlling_owner_box_name(cell_id),
        inscription_box_name(cell_id),
    ]


def build_message(app_id: int, cell_id: int, artifact_hash: bytes, genesis_hash: bytes) -> bytes:
    """
    Reconstruct the exact message the contract verifies on-chain (spec §4):

        M = DOMAIN_TAG
            || uint64_be(app_id)
            || uint64_be(cell_id)
            || artifact_hash  (32 bytes, sha512_256 of the artifact)
            || genesis_hash   (32 bytes, the network Global.genesis_hash)

    Sign M directly with the deterministic Falcon-1024 signer — do NOT pre-hash it (the opcode
    hashes internally). `genesis_hash` pins the signature to one network (replay protection).

    Returns a 102-byte message.
    """
    if len(artifact_hash) != 32:
        raise ValueError("artifact_hash must be 32 bytes (a sha512_256 digest)")
    if len(genesis_hash) != 32:
        raise ValueError("genesis_hash must be 32 bytes (the network genesis hash)")
    msg = (
        DOMAIN_TAG
        + int(app_id).to_bytes(8, "big")
        + cell_key(cell_id)
        + bytes(artifact_hash)
        + bytes(genesis_hash)
    )
    assert len(msg) == MESSAGE_LEN, "internal: message length drift"
    return msg
