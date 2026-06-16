"""
trelyan_pq._seal_worker — short-lived ISOLATED signing worker for sign-once-destroy.

Run as a subprocess (``python -m trelyan_pq._seal_worker``). It reads ONE seal request as JSON on
stdin, generates a FRESH Deterministic Falcon-1024 keypair (ephemeral — the key is NEVER provisioned,
stored, read from disk/env, or derived from a seed; there is no long-term private key, only this
one-shot keygen), signs the inscription message once, wipes the private key, and writes back ONLY the
public key + signature as JSON on stdout — then the process exits.

Why a separate process (the containment win over in-process mlock):
  The private key's ENTIRE lifetime — keygen, the FFI / Falcon-internal temporaries, the stack, and
  the final buffer — lives inside THIS process's address space, which the OS unmaps and reclaims on
  exit. No long-lived parent (the SDK / caller) ever holds key material; the parent receives only the
  public key and signature. The in-process path (keygen_sign_seal) can only pin/wipe the final
  buffer, leaving FFI temporaries exposed; this worker removes that whole class.

Honest residual: while this worker is briefly alive the key is in its memory (mlock-pinned and wiped
before exit). A privileged attacker (ptrace, core dump, DMA) during that window, or OS pages not
scrubbed until reuse, are still out of scope — this is process isolation, not a hardware enclave.
"""

from __future__ import annotations

import ctypes
import json
import sys

from .falcon import default_signer, PRIVKEY_SIZE, _unlock_pages
from .message import build_message, DET_COMPRESSED_HEADER


def _harden_process() -> dict:
    """Best-effort: shrink the worker's exposure BEFORE any key exists. POSIX-focused; no-ops where
    unavailable (e.g. Windows). Returns exactly what was applied, so a missing protection is visible
    (auditable), never a silent 'success'. (Council asks: mlockall, no-core-dump, no-ptrace.)"""
    applied = {"mlockall": False, "no_core_dump": False, "no_ptrace": False, "platform": sys.platform}
    if sys.platform == "win32":
        return applied  # mlockall/prctl/RLIMIT_CORE have no Windows equivalent here; VirtualLock remains
    try:
        import resource
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))           # no core dump can capture the key
        applied["no_core_dump"] = True
    except Exception:
        pass
    try:
        libc = ctypes.CDLL(None, use_errno=True)
    except Exception:
        libc = None
    if libc is not None:
        try:
            MCL_CURRENT, MCL_FUTURE = 1, 2
            if libc.mlockall(MCL_CURRENT | MCL_FUTURE) == 0:       # pin ALL pages incl. FFI temporaries
                applied["mlockall"] = True
        except Exception:
            pass
        if sys.platform.startswith("linux"):
            try:
                PR_SET_DUMPABLE = 4
                if libc.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) == 0:   # block ptrace / /proc/<pid>/mem
                    applied["no_ptrace"] = True
            except Exception:
                pass
    return applied


def main() -> int:
    protections = _harden_process()
    try:
        req = json.loads(sys.stdin.read())
        app_id = int(req["app_id"])
        cell_id = int(req["cell_id"])
        artifact_hash = bytes.fromhex(req["artifact_hash"])
        genesis_hash = bytes.fromhex(req["genesis_hash"])
        require_locked = bool(req.get("require_locked", False))
    except Exception as e:  # noqa: BLE001 — report any malformed request, never crash silently
        sys.stdout.write(json.dumps({"ok": False, "error": f"bad request: {e!r}"}))
        return 2

    # fail-closed: if the caller demands swap-proof memory, refuse to keygen unless mlockall pinned
    # ALL pages (POSIX). Windows has no mlockall, so require_locked there is honestly unsatisfiable.
    # [DeepSeek/OpenAI seats: treat lock failure as a hard error, not a silent degradation.]
    if require_locked and not protections.get("mlockall"):
        sys.stdout.write(json.dumps({
            "ok": False,
            "error": ("require_locked=True but mlockall could not pin memory (RLIMIT_MEMLOCK limit, or "
                      "an unsupported platform such as Windows); refusing to generate a key on "
                      "swappable memory — seal on a POSIX host with a sufficient memlock limit"),
            "protections": protections,
        }))
        return 6

    signer = default_signer()  # loads FALCON_DET1024_LIB (inherited from the parent env)
    try:
        pubkey, privkey_buf = signer._keygen_into_buffer()  # mlock'd inside _keygen_into_buffer
    except Exception as e:  # noqa: BLE001
        sys.stdout.write(json.dumps({"ok": False, "error": f"keygen failed: {e!r}"}))
        return 3

    sig = b""
    try:
        m = build_message(app_id, cell_id, artifact_hash, genesis_hash)
        try:
            sig = signer.sign(privkey_buf, m)
        except AssertionError as e:  # sign() raises if header != 0xBA — a bad-build signal
            sys.stdout.write(json.dumps({"ok": False, "error": f"bad signature header: {e}"}))
            return 4
        if (not sig or sig[0] != DET_COMPRESSED_HEADER
                or not signer.verify_inscription(sig, pubkey, app_id, cell_id, artifact_hash, genesis_hash)):
            sys.stdout.write(json.dumps({"ok": False, "error": "self-verify failed (do not broadcast)"}))
            return 5
    finally:
        # wipe + release the private key on EVERY path, before this process exits
        ctypes.memset(ctypes.addressof(privkey_buf), 0, PRIVKEY_SIZE)
        _unlock_pages(privkey_buf)

    sys.stdout.write(json.dumps({
        "ok": True, "pubkey": pubkey.hex(), "signature": sig.hex(), "protections": protections,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
