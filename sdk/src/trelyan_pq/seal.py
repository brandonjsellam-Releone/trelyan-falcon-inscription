"""
trelyan_pq.seal — sign-once-destroy for TRELYAN inscriptions.   # T1 sign-once-destroy

Generate a Deterministic Falcon-1024 keypair, sign the ONE domain-separated inscription message M,
and wipe the private key from memory in a single operation. The private key is NEVER returned or
persisted: keygen_sign_seal() hands back only the public key, the signature, and the cell_id.

Honest scope (read this before citing it as a guarantee):
  - The API does not return or persist the private key. Its in-memory buffer (a MUTABLE ctypes
    buffer, never an immutable `bytes`) is wiped in place with ctypes.memset on a BEST-EFFORT basis
    before the call returns.
  - This is NOT secure erasure. The key buffer's pages ARE pinned in RAM on a best-effort basis
    (mlock / VirtualLock) to narrow the swap-to-disk window, but CPython / the OS may still leave
    copies the wipe cannot reach: freed-page reuse, FFI / Falcon-internal temporaries, core dumps,
    registers, hibernation images, or any privileged / debugger / DMA read. There is no secure
    allocator. These residuals remain a documented AUDIT ITEM (THREAT_MODEL key-loss class, §4.3),
    not a closed property.
  - This mechanism is DEFENSE-IN-DEPTH, not the security boundary. The single-controlling-key
    property is enforced ON-CHAIN: register_cell commits exactly one Falcon public key per cell, and
    inscribe verifies only against that committed key (contracts/inscription.py). A second locally
    generated keypair yields a DIFFERENT public key the contract will not accept.

What is true and useful: because the API retains no key, a divergent or non-reproducible local
build cannot be used to emit a SECOND signature for a sealed cell through this API — that failure
mode collapses into the already-disclosed key-loss class. keygen_sign_seal self-verifies the
signature (header 0xBA + verify_inscription) before returning, so a bad local build is caught
BEFORE anything is broadcast.

Falcon here = signatures / integrity / anti-forgery, NOT encryption.
"""

from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

from . import falcon as _falcon
from .message import DET_COMPRESSED_HEADER, build_message
from .falcon import FalconDet1024, PRIVKEY_SIZE, default_signer

__all__ = [
    "SealResult",
    "SealStore",
    "JsonFileSealStore",
    "InMemorySealStore",
    "CellAlreadySealed",
    "SealVerificationError",
    "keygen_sign_seal",
    "keygen_sign_seal_isolated",
]


class CellAlreadySealed(Exception):
    """The cell_id has already been sealed (the one-signature-per-cell tripwire fired)."""


class SealVerificationError(Exception):
    """The freshly produced signature failed its self-check (header 0xBA + verify_inscription):
    the local build would have broadcast bytes the on-chain falcon_verify opcode rejects. The cell
    is NOT consumed in this case — fix the build and retry (a fresh keypair is fine pre-register)."""


@dataclass(frozen=True)
class SealResult:
    """The public outputs of a seal. There is deliberately NO private-key field (T1)."""
    pubkey: bytes        # Falcon-1024 public key, 1793 B (public — safe to return)
    signature: bytes     # deterministic compressed signature, header 0xBA, <= 1423 B
    cell_id: int


@runtime_checkable
class SealStore(Protocol):
    """Durable tripwire recording sealed cell_ids. Single-writer assumed (see JsonFileSealStore)."""
    def is_sealed(self, cell_id: int) -> bool: ...
    def record(self, cell_id: int) -> None: ...


class InMemorySealStore:
    """Non-durable SealStore for tests / ephemeral single-process use (e.g. CI). NOT persisted, so
    it provides no cross-run tripwire — use JsonFileSealStore when the guarantee must survive a
    process restart."""

    def __init__(self) -> None:
        self._sealed: set = set()

    def is_sealed(self, cell_id: int) -> bool:
        return int(cell_id) in self._sealed

    def record(self, cell_id: int) -> None:
        self._sealed.add(int(cell_id))


class JsonFileSealStore:
    """SealStore backed by a JSON file holding a sorted list of sealed cell_ids.

    Writes are ATOMIC and DURABLE (write temp + fsync + os.replace), so a crash never leaves a torn
    file. SINGLE-WRITER assumption: there is no cross-process lock, so concurrent writers could both
    pass is_sealed() and race. For the intended use (one operator sealing one cell at a time) that
    is sufficient; a multi-writer deployment must front this with a transactional store enforcing a
    UNIQUE(cell_id) constraint — flagged as an audit follow-up, not closed here.

    cell_ids are small integers (1..1024), not personal data; nothing secret is written to disk."""

    def __init__(self, path) -> None:
        self.path = os.fspath(path)

    def _load(self) -> set:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return set(int(x) for x in json.load(f))
        except FileNotFoundError:
            return set()

    def is_sealed(self, cell_id: int) -> bool:
        return int(cell_id) in self._load()

    def record(self, cell_id: int) -> None:
        sealed = self._load()
        sealed.add(int(cell_id))
        payload = json.dumps(sorted(sealed)).encode("utf-8")
        directory = os.path.dirname(os.path.abspath(self.path)) or "."
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".seal_", suffix=".json.tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())          # durability: the bytes hit disk
            os.replace(tmp, self.path)        # atomicity: same-dir rename, never a torn file
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise


def keygen_sign_seal(
    app_id: int,
    cell_id: int,
    artifact_hash: bytes,
    genesis_hash: bytes,
    *,
    store: SealStore,
    signer: Optional[FalconDet1024] = None,
) -> SealResult:
    """Generate a Deterministic Falcon-1024 keypair, sign the inscription message M for
    (app_id, cell_id, artifact_hash, genesis_hash), wipe the private key, and return only the
    public key + signature + cell_id.   # T1 sign-once-destroy

    The private key is never returned or persisted; see the module docstring for the honest scope
    of "wiped" (best-effort, not secure erasure — a documented audit item).

    Ordering (fail-closed): the cell is checked against `store` BEFORE any keygen; the private-key
    buffer is wiped in a `finally` ALWAYS; and the seal is recorded durably AFTER self-verification
    and BEFORE the signature is returned, so a kill between sign and return can never leave a
    returned signature with a still-re-sealable cell.

    Raises:
        CellAlreadySealed: if `store` already records cell_id.
        SealVerificationError: if the produced signature fails self-verification (bad local build).
            The cell is NOT consumed in this case.
    """
    if signer is None:
        signer = default_signer()

    # tripwire (checked before any keygen): refuse a second seal of the same cell
    if store.is_sealed(cell_id):
        raise CellAlreadySealed(f"cell_id {cell_id} already sealed")

    # keygen into a MUTABLE buffer; the private key is never materialized as immutable bytes
    pubkey, privkey_buf = signer._keygen_into_buffer()
    try:
        m = build_message(app_id, cell_id, artifact_hash, genesis_hash)
        # privkey_buf is a ctypes buffer of length PRIVKEY_SIZE — len-compatible and ctypes-passable
        # to sign(); deliberately NOT copied into a `bytes` so it stays wipeable.
        try:
            sig = signer.sign(privkey_buf, m)
        except AssertionError as e:
            # sign() raises AssertionError if the header byte isn't 0xBA — a bad-build signal
            raise SealVerificationError(str(e)) from e

        # self-verify BEFORE returning: catch a divergent local build before anything is broadcast
        if not sig or sig[0] != DET_COMPRESSED_HEADER:
            raise SealVerificationError(
                f"signature header {(sig[0] if sig else -1):#04x} != {DET_COMPRESSED_HEADER:#04x}; "
                f"the local build would be rejected on-chain"
            )
        if not signer.verify_inscription(sig, pubkey, app_id, cell_id, artifact_hash, genesis_hash):
            raise SealVerificationError(
                "self-verification failed; the local build produced a signature the on-chain "
                "falcon_verify opcode would reject (do not broadcast)"
            )
    finally:
        # best-effort wipe of the private-key buffer, ALWAYS (success or exception). The pubkey/sig
        # are public; only the private key is sensitive. (Not secure erasure — see module docstring.)
        ctypes.memset(ctypes.addressof(privkey_buf), 0, PRIVKEY_SIZE)
        _falcon._unlock_pages(privkey_buf)   # release the mlock/VirtualLock page-pin after wiping

    # record the seal durably AFTER self-verify and BEFORE returning the signature (fail-closed)
    store.record(cell_id)
    return SealResult(pubkey=pubkey, signature=sig, cell_id=int(cell_id))


def keygen_sign_seal_isolated(
    app_id: int,
    cell_id: int,
    artifact_hash: bytes,
    genesis_hash: bytes,
    *,
    store: SealStore,
    require_locked: bool = False,
    python_exe: Optional[str] = None,
    timeout: float = 120.0,
) -> SealResult:
    """Hardened variant of keygen_sign_seal: keygen + sign run in a SHORT-LIVED SUBPROCESS that exits
    immediately, so no long-lived process ever holds the private key — including the FFI / Falcon-
    internal temporaries that the in-process wipe/mlock cannot reach. This process receives only the
    public key + signature; the key's whole lifetime is confined to the worker, whose address space
    the OS reclaims on exit. (Containment hardening; see _seal_worker for the honest residual.)

    Same contract as keygen_sign_seal: CellAlreadySealed if `store` has cell_id; the seal is recorded
    AFTER an independent re-verification and BEFORE returning (fail-closed); SealVerificationError on a
    bad local build (cell not consumed).
    """
    if store.is_sealed(cell_id):
        raise CellAlreadySealed(f"cell_id {cell_id} already sealed")

    request = json.dumps({
        "app_id": int(app_id),
        "cell_id": int(cell_id),
        "artifact_hash": bytes(artifact_hash).hex(),
        "genesis_hash": bytes(genesis_hash).hex(),
        # fail-closed: if True the worker refuses to keygen unless mlockall pinned all pages (POSIX).
        # Recommended True for sealing real cells on a POSIX host; unsatisfiable on Windows.
        "require_locked": bool(require_locked),
    }).encode("utf-8")

    # sanitized environment for the worker: drop code-injection vectors (LD_PRELOAD / *_LIBRARY_PATH /
    # PYTHON*) while keeping FALCON_DET1024_LIB. close_fds defaults True; the interpreter path is absolute.
    env = dict(os.environ)
    for _k in ("LD_PRELOAD", "LD_LIBRARY_PATH", "DYLD_INSERT_LIBRARIES", "DYLD_LIBRARY_PATH",
               "PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"):
        env.pop(_k, None)
    proc = subprocess.run(
        [python_exe or sys.executable, "-m", "trelyan_pq._seal_worker"],
        input=request, capture_output=True, timeout=timeout, env=env,
    )
    try:
        out = json.loads(proc.stdout.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        out = {}
    if proc.returncode != 0 or not out.get("ok"):
        detail = out.get("error") or (proc.stderr.decode("utf-8", "replace")[:200] or "no output")
        raise SealVerificationError(f"isolated signer failed (rc={proc.returncode}): {detail}")

    pubkey = bytes.fromhex(out["pubkey"])
    sig = bytes.fromhex(out["signature"])
    # this process independently re-verifies (pubkey, sig) — using only public values — before
    # recording, catching any transport corruption. The private key never crosses the boundary.
    if not sig or sig[0] != DET_COMPRESSED_HEADER:
        raise SealVerificationError(f"isolated signer returned a bad header {(sig[0] if sig else -1):#04x}")
    if not default_signer().verify_inscription(sig, pubkey, app_id, cell_id, artifact_hash, genesis_hash):
        raise SealVerificationError("isolated signer's signature failed parent re-verification")

    store.record(cell_id)
    return SealResult(pubkey=pubkey, signature=sig, cell_id=int(cell_id))
