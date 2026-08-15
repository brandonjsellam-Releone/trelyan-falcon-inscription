"""Regression test: `verify()` must reject a mis-sized public key BEFORE the FFI call.

Found 2026-08-15 by an adversarial review and reproduced with a guard page.

`falcon_det1024_verify_compressed` takes **no pubkey length parameter**. `deterministic.c` calls
`falcon_verify(..., pubkey, FALCON_DET1024_PUBKEY_SIZE, ...)`, so it reads exactly 1793 bytes from
that pointer regardless of what the caller allocated. `sig` and `message` are length-delimited and
therefore bounded; `pubkey` alone was not.

`FalconDet1024.verify()` passed `pubkey` straight through as a bare `c_char_p` with no check, so a
shorter buffer was an out-of-bounds read of up to 1729 bytes. Demonstrated against a two-page
allocation with only the first page committed and the payload placed flush against the boundary:

    full 1793-byte pubkey  -> returns cleanly (reads exactly 1793, stops at the edge)
    1792-byte pubkey       -> ACCESS VIOLATION at the first byte past the buffer
    64-byte pubkey         -> ACCESS VIOLATION

The one-byte-short case is the one that matters: it is the realistic truncation, and it faults.
Reaching it needs no valid signature — junk bytes with the right two header values get there.

**The asymmetry is what makes it an oversight rather than a decision.** `sign()` has always
checked `len(privkey) != PRIVKEY_SIZE`. `verify()` checked nothing.

WHY NOTHING CAUGHT IT, WHICH IS THE PART WORTH KEEPING:

* `tests/fuzz/fuzz_falcon_verify.cc` (the C/ASan harness, 13.8M executions) **documents this exact
  invariant** and honours it — it always hands the function a fixed 1793-byte buffer, and its
  comment calls a smaller one "a caller-side over-read — a harness bug, not a finding". Correct,
  and it means that harness can never surface the defect by construction.
* `tests/fuzz/fuzz_encoding_atheris.py` **did** feed short pubkeys, and asserted verify() "must
  return False, not raise" — an assertion the code could not satisfy, because it crashed instead.
  That harness is referenced by no workflow, so it has never run.
* No test in this suite varied pubkey length. `test_signature_kat.py` and `test_signature_fuzz.py`
  vary the signature only, always with a full-size key.

So the invariant was written down in one file, violated in another, and the harness that would
have caught it was never wired up. These tests need no C library, so they run everywhere.
"""

from __future__ import annotations

import inspect

import pytest

from trelyan_pq.falcon import PRIVKEY_SIZE, PUBKEY_SIZE, FalconDet1024


@pytest.mark.parametrize(
    "length",
    [0, 1, 64, PUBKEY_SIZE - 1, PUBKEY_SIZE + 1, PUBKEY_SIZE * 2],
    ids=lambda n: f"{n}B",
)
def test_verify_rejects_any_pubkey_that_is_not_exactly_pubkey_size(length: int) -> None:
    """`PUBKEY_SIZE - 1` is the case that faulted; the others bracket it."""
    signer = FalconDet1024()
    with pytest.raises(ValueError, match=r"pubkey must be 1793 bytes"):
        signer.verify(b"\xba\x00" + b"\x00" * 100, b"\x0a" * length, b"message")


def test_the_guard_runs_before_the_ffi_call_not_after() -> None:
    """Ordering is the whole point: a check after the call happens after the over-read.

    Asserted on the parsed body rather than on the source text, because the docstring mentions
    the C function by name and a substring check would pass on that alone — a proxy assertion,
    which is the defect class this repository's register is about.
    """
    import ast
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(FalconDet1024.verify))).body[0]
    body = tree.body
    if isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]  # drop the docstring

    assert isinstance(body[0], ast.If), (
        "the length guard must be the FIRST statement in verify(); anything before it runs on an "
        "unvalidated pubkey"
    )
    raise_line = next(n.lineno for n in ast.walk(tree) if isinstance(n, ast.Raise))
    call_line = next(
        n.lineno
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and getattr(n.func, "attr", "") == "falcon_det1024_verify_compressed"
    )
    assert raise_line < call_line, "the guard must raise before the FFI call, not after"


def test_sign_and_verify_now_treat_a_mis_sized_key_the_same_way() -> None:
    """The asymmetry was the tell. Pin that it is gone, so a future edit cannot reintroduce it."""
    signer = FalconDet1024()
    with pytest.raises(ValueError, match=rf"privkey must be {PRIVKEY_SIZE} bytes"):
        signer.sign(b"\x00" * 64, b"m")
    with pytest.raises(ValueError, match=rf"pubkey must be {PUBKEY_SIZE} bytes"):
        signer.verify(b"\xba\x00", b"\x00" * 64, b"m")


def test_the_contracts_side_copy_carries_the_same_guard() -> None:
    """`contracts/falcon_det1024.py` is the copy `deploy_testnet.py` signs real inscriptions with.

    It had the identical defect. A fix applied to only one of the two would leave the TestNet path
    exposed — which is exactly how TCE-03's `cwd` hijack survived its first fix.
    """
    import pathlib

    src = (
        pathlib.Path(__file__).resolve().parents[2] / "contracts" / "falcon_det1024.py"
    ).read_text(encoding="utf-8")
    fn = src[src.index("def verify_compressed(") :]
    fn = fn[: fn.index("\ndef ", 1)] if "\ndef " in fn[1:] else fn
    assert "pubkey must be" in fn, (
        "contracts/falcon_det1024.py::verify_compressed has no pubkey length guard; it reads "
        "1793 bytes unconditionally just like the SDK copy did"
    )
    assert fn.index("raise ValueError") < fn.index("falcon_det1024_verify_compressed(sig"), (
        "the contracts-side guard must also raise before its FFI call"
    )
