"""Bind every example's SDK call sites to the SDK's REAL signatures.

Why this exists
---------------
`examples/interop_algo_pqc_kit.py` passed a Falcon *signature* into `inscribe()`'s third
positional parameter -- which is a *private key*. The client re-derives M and re-signs
internally (inscription.py:135-136), so the argument reached
`falcon.py:192  raise ValueError("privkey must be 2305 bytes, got ...")`.

The example could not run in EITHER branch, and nothing caught it, because no test in this
repo imports or otherwise touches `examples/`. Its own docstring conceded "NOT yet executed
end-to-end", which is exactly why it went unnoticed: the disclaimer was doing the work a test
should have been doing.

What this checks
----------------
Two things, statically:

1. **Arity/keyword validity.** Each call to a known SDK method is bound with
   `inspect.Signature.bind()`. A renamed or reordered parameter breaks the example loudly here
   instead of at someone's TestNet run.

2. **Provenance.** A value produced by `.sign()` must never land in a parameter named
   `privkey`, and a private key must never land in `committed_pubkey`. This is the actual
   TCE-25 defect, and it is the one an arity check alone cannot see: a signature and a private
   key are both `bytes`, both plausible in that position, and the call has the right number of
   arguments either way.

Deliberately AST-only: the examples import `algo_pqc_kit`, the generated `trelyan_client`, and
a Falcon C library, and they want a funded TestNet account. None of that is available in CI,
and none of it is needed to check that a call site names the right things. The tradeoff is
honest -- this proves the examples are *well-formed against the SDK*, not that they run.
"""

from __future__ import annotations

import ast
import inspect
import pathlib

import pytest

from trelyan_pq.falcon import FalconDet1024
from trelyan_pq.inscription import TrelyanInscriptionClient

EXAMPLES_DIR = pathlib.Path(__file__).resolve().parents[1] / "examples"

# Methods whose real signatures we bind example call sites against.
_SIGNATURES = {
    name: inspect.signature(getattr(TrelyanInscriptionClient, name))
    for name in ("inscribe", "inscribe_bytes", "register_cell", "mint_cell", "read_back_matches")
}

# Parameters that must receive secret key material, and parameters that must not.
_MUST_BE_PRIVKEY = {"privkey"}
_MUST_NOT_BE_SECRET = {"committed_pubkey", "artifact_hash", "payload_uri"}


def _example_files() -> list[pathlib.Path]:
    return sorted(EXAMPLES_DIR.glob("*.py"))


def _origins(tree: ast.AST) -> dict[str, str]:
    """Map local variable name -> what produced it ('signature' | 'privkey' | 'pubkey').

    Only the three producers that matter are tracked. Anything else stays unknown, and unknown
    is permitted -- this is a check for *provably wrong* wiring, not a type system.
    """
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Call):
            continue
        func = node.value.func
        called = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        target = node.targets[0]

        if called == "sign":
            # sig = signer.sign(priv, M)  /  sig = pq.sign(M)
            if isinstance(target, ast.Name):
                out[target.id] = "signature"
        elif called == "keygen":
            # pub, priv = signer.keygen()  -- order is (public, private), see FalconDet1024.keygen
            if isinstance(target, ast.Tuple) and len(target.elts) == 2:
                names = [e.id for e in target.elts if isinstance(e, ast.Name)]
                if len(names) == 2:
                    out[names[0]], out[names[1]] = "pubkey", "privkey"
    return out


def _sdk_calls(tree: ast.AST):
    """Yield (method_name, ast.Call) for calls to methods we have real signatures for."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in _SIGNATURES:
                yield node.func.attr, node


def _bind(method: str, call: ast.Call) -> dict[str, ast.expr]:
    """Bind a call site's arguments to the real signature; return {param_name: arg_node}.

    `self` is prepended because we read the signature off the unbound function.
    """
    sig = _SIGNATURES[method]
    args = [ast.Constant(value=None), *call.args]  # placeholder for self
    kwargs = {kw.arg: kw.value for kw in call.keywords if kw.arg is not None}
    bound = sig.bind(*args, **kwargs)
    params = dict(bound.arguments)
    params.pop("self", None)
    return params


@pytest.mark.parametrize("path", _example_files(), ids=lambda p: p.name)
def test_example_calls_bind_to_real_sdk_signatures(path: pathlib.Path) -> None:
    """Every SDK call in every example must be valid against the installed SDK."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for method, call in _sdk_calls(tree):
        try:
            _bind(method, call)
        except TypeError as exc:  # arity / unknown keyword / missing required arg
            pytest.fail(
                f"{path.name}:{call.lineno}: {method}(...) does not match the SDK signature "
                f"{_SIGNATURES[method]}: {exc}"
            )


@pytest.mark.parametrize("path", _example_files(), ids=lambda p: p.name)
def test_no_signature_is_passed_where_a_private_key_is_expected(path: pathlib.Path) -> None:
    """TCE-25: the defect that made the interop example unrunnable in both branches.

    A signature and a private key are both `bytes` and both fit the slot, so only provenance
    distinguishes them.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    origins = _origins(tree)

    for method, call in _sdk_calls(tree):
        try:
            bound = _bind(method, call)
        except TypeError:
            continue  # reported by the arity test above; don't double-fail

        for param, arg in bound.items():
            if not isinstance(arg, ast.Name):
                continue
            origin = origins.get(arg.id)
            if origin is None:
                continue

            if param in _MUST_BE_PRIVKEY and origin != "privkey":
                pytest.fail(
                    f"{path.name}:{call.lineno}: {method}(...) receives `{arg.id}` (a {origin}) "
                    f"as `{param}`, which the SDK uses as a PRIVATE KEY and signs with. "
                    f"This fails at falcon.py with 'privkey must be 2305 bytes'."
                )
            if param in _MUST_NOT_BE_SECRET and origin == "privkey":
                pytest.fail(
                    f"{path.name}:{call.lineno}: {method}(...) passes private key `{arg.id}` "
                    f"as `{param}` -- that value is submitted on-chain."
                )


def test_the_guard_can_actually_see_the_defect() -> None:
    """Guard-the-guard: prove the provenance check fires on the exact pre-fix source.

    Without this, the two tests above would pass just as happily if `_origins` silently
    returned {} -- the vacuous-check shape this whole register documents.
    """
    pre_fix = (
        "signer = FalconDet1024()\n"
        "pub, priv = signer.keygen()\n"
        "sig = signer.sign(priv, M)\n"
        "c.inscribe(cell, artifact_hash, sig, b'ipfs://demo')\n"
    )
    tree = ast.parse(pre_fix)
    origins = _origins(tree)
    assert origins == {"pub": "pubkey", "priv": "privkey", "sig": "signature"}

    (method, call), = list(_sdk_calls(tree))
    bound = _bind(method, call)
    assert isinstance(bound["privkey"], ast.Name)
    assert origins[bound["privkey"].id] == "signature", "the defect must be visible as a signature"


def test_sdk_still_treats_the_third_positional_as_a_private_key() -> None:
    """If `inscribe` ever grows a real presigned path, this test should be revisited, not deleted.

    The whole provenance rule rests on the SDK signing internally. Pin that fact.
    """
    params = list(inspect.signature(TrelyanInscriptionClient.inscribe).parameters)
    assert params[:4] == ["self", "cell_id", "artifact_hash", "privkey"], (
        "inscribe()'s parameter order changed -- re-check examples and _MUST_BE_PRIVKEY"
    )
    src = inspect.getsource(TrelyanInscriptionClient.inscribe)
    assert "self.signer.sign(" in src, (
        "inscribe() no longer signs internally; an inscribe_presigned() path may now exist "
        "(see interop_algo_pqc_kit.py STATUS item 2)"
    )
