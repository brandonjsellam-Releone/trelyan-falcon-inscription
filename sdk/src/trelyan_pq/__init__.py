"""
trelyan_pq — post-quantum (Falcon-1024) inscription tooling for Algorand.

An open, MIT-licensed SDK that turns the TRELYAN reference implementation into importable
infrastructure for building post-quantum-authenticated records on Algorand using the network's
native `falcon_verify` opcode.

Two layers:

* **Core (stdlib-only):** `trelyan_pq.message` (byte-exact on-chain message construction + the
  box-commit / arg-cap helpers) and `trelyan_pq.falcon` (the deterministic Falcon-1024 signer
  in the exact 0xBA-header encoding the opcode accepts). No heavy dependencies.

* **On-chain client (`[algorand]` extra):** `trelyan_pq.inscription.TrelyanInscriptionClient`
  wraps the full deploy/register/inscribe/verify flow over algokit-utils.

Status: alpha. Validated on localnet (20/20) and Algorand TestNet; NOT externally audited and
NOT for MainNet value. See the reference repo for the spec, threat model, and validation record.
"""

from __future__ import annotations

from .message import (
    DOMAIN_TAG,
    PUBKEY_LEN,
    SIG_COMPRESSED_MAXSIZE,
    DET_COMPRESSED_HEADER,
    TOTAL_CELLS,
    INS_VERSION,
    MAX_APP_ARGS_TOTAL_BYTES,
    MESSAGE_LEN,
    sha512_256,
    artifact_hash,
    cell_key,
    committed_pubkey_box_name,
    controlling_owner_box_name,
    inscription_box_name,
    box_refs,
    build_message,
)
from .falcon import (
    FalconDet1024,
    PUBKEY_SIZE,
    PRIVKEY_SIZE,
    CURRENT_SALT_VERSION,
    keygen,
    sign,
    verify,
    sign_inscription,
    verify_inscription,
    default_signer,
)
from .seal import (
    SealResult,
    SealStore,
    JsonFileSealStore,
    InMemorySealStore,
    CellAlreadySealed,
    SealVerificationError,
    keygen_sign_seal,
    keygen_sign_seal_isolated,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # message / encoding
    "DOMAIN_TAG", "PUBKEY_LEN", "SIG_COMPRESSED_MAXSIZE", "DET_COMPRESSED_HEADER",
    "TOTAL_CELLS", "INS_VERSION", "MAX_APP_ARGS_TOTAL_BYTES", "MESSAGE_LEN",
    "sha512_256", "artifact_hash", "cell_key", "box_refs",
    "committed_pubkey_box_name", "controlling_owner_box_name", "inscription_box_name",
    "build_message",
    # falcon signer
    "FalconDet1024", "PUBKEY_SIZE", "PRIVKEY_SIZE", "CURRENT_SALT_VERSION",
    "keygen", "sign", "verify", "sign_inscription", "verify_inscription", "default_signer",
    # sign-once-destroy (T1) + isolated-signer containment
    "SealResult", "SealStore", "JsonFileSealStore", "InMemorySealStore",
    "CellAlreadySealed", "SealVerificationError", "keygen_sign_seal", "keygen_sign_seal_isolated",
]

# Optional on-chain client (only importable with the [algorand] extra installed).
try:  # pragma: no cover
    from .inscription import TrelyanInscriptionClient
    __all__.append("TrelyanInscriptionClient")
except Exception:  # ImportError if algokit-utils isn't installed
    TrelyanInscriptionClient = None  # type: ignore
