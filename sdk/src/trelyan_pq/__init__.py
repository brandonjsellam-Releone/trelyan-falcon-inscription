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

# Derived from the INSTALLED package metadata, never hand-written.
#
# This was `"0.1.0"` while pyproject.toml declared `0.2.2`, so anyone who pip-installed 0.2.2 got a
# package that reported itself as 0.1.0 — and `Dockerfile.verify`, the "hermetic checker" an auditor
# is pointed at, pinned `trelyan-pq==0.1.0` on the strength of it. Three numbers, two of them wrong,
# and nothing compared them.
#
# Reading the metadata makes the drift impossible rather than merely fixed: there is now one source
# of truth, and `pyproject.toml` is it. The fallback covers a source checkout that was never
# installed (running straight out of `src/`), where no distribution metadata exists to read.
from importlib.metadata import PackageNotFoundError, version as _pkg_version

try:
    __version__ = _pkg_version("trelyan-pq")
except PackageNotFoundError:  # running from an uninstalled source tree
    __version__ = "0.0.0+source"

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
