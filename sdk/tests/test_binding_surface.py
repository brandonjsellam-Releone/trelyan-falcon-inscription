"""
Guard: the C binding surface stays inside the audited subset of algorand/falcon.

WHY THIS TEST EXISTS
────────────────────────────────────────────────────────────────────────────────────────────────
The pinned build (`algorand/falcon` @ ce15e75b, which IS tag v0.1.0 — the release go-algorand
vendors) contains a confirmed out-of-bounds read in `falcon_det1024_convert_compressed_to_ct`:
it computes `sig_compressed_len - 2`, which wraps to SIZE_MAX on a short input, after which
`comp_decode`'s `v >= max_in_len` guard can never fire. Proven by varying only out-of-buffer
memory: the pinned build returns -2 / **0 (success!)** / 0 / -2 depending on adjacent bytes,
while upstream HEAD returns a constant -4. A `len == 0` input is out-of-bounds by construction.

TRELYAN's documented position is ACCEPT-AND-DOCUMENT, and it rests on exactly one fact:

    the SDK never binds that function, so the defect is not reachable from this package.

The pin itself is deliberately NOT bumped — ce15e75b is the network's release, and moving to the
untagged fix commit would make TRELYAN stricter than the deployed on-chain verifier for no
reachable benefit. See PINNED_BUILD.md and FALCON_PIN_BUMP_EVIDENCE_2026-08-11.md.

That makes the acceptance only as durable as the binding surface. One `lib.falcon_det1024_
convert_compressed_to_ct` added later — reasonably, by someone implementing CT-format support —
silently converts a documented non-issue into a live out-of-bounds read, and nothing would say
so. This test is the mechanism that says so.

WHY THIS IS NOT THE TAUTOLOGY IT RESEMBLES
────────────────────────────────────────────────────────────────────────────────────────────────
This repo has been bitten by checks that compare a value to a constant derived from that same
value (see verify_trelyan.py's approval-program pin, and contracts/verify_deployment.py which
replaced it). This test is deliberately NOT that shape. The two sides come from independent
sources: one is DERIVED from the source code by parsing it, the other is the DECLARED security
policy below. An allowlist compared against parsed fact can fail. A constant compared against
itself cannot. If you ever change _ALLOWED to make this test pass, you have inverted it — the
correct response to a failure is to justify the new binding or remove it.

No shared library is loaded here: the check is static, so it runs in the no-native-lib CI job.
"""

import ast
import pathlib

import pytest

_SDK_SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "trelyan_pq"
_FALCON_PY = _SDK_SRC / "falcon.py"

# The audited binding surface. Every symbol TRELYAN is permitted to call in the pinned build.
_ALLOWED = frozenset({
    "shake256_init_prng_from_system",
    "falcon_det1024_keygen",
    "falcon_det1024_sign_compressed",
    "falcon_det1024_verify_compressed",
})

# Symbols quarantined for a stated reason, mapped to that reason. A failure naming one of these
# is not a style violation - it invalidates a documented risk acceptance.
_QUARANTINED = {
    "falcon_det1024_convert_compressed_to_ct":
        "confirmed size_t underflow -> unbounded read in the pinned build (ce15e75b). Binding it "
        "makes the accepted 'unreachable' risk reachable and requires re-assessing the pin.",
    "falcon_det1024_verify_ct":
        "consumes CT-format signatures, which are produced by convert_compressed_to_ct. Binding "
        "it implies bringing the vulnerable conversion path into the package.",
}


def _bind_function() -> ast.FunctionDef:
    tree = ast.parse(_FALCON_PY.read_text(encoding="utf-8"), filename=str(_FALCON_PY))
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_bind":
            return node
    pytest.fail(
        f"_bind() not found in {_FALCON_PY}. If binding moved elsewhere this guard is no longer "
        "watching anything - point it at the new chokepoint rather than deleting it."
    )


def _bound_symbols() -> set[str]:
    """Symbol names accessed on the CDLL handle inside _bind(), read from the AST."""
    fn = _bind_function()
    handle = fn.args.args[0].arg  # the CDLL parameter, by whatever name it carries
    found: set[str] = set()
    for node in ast.walk(fn):
        # lib.<symbol>.argtypes = ... parses as Attribute(Attribute(Name(lib), symbol), argtypes)
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == handle:
            found.add(node.attr)
    return found


def test_binding_surface_is_exactly_the_audited_set():
    bound = _bound_symbols()

    unexpected = bound - _ALLOWED
    assert not unexpected, (
        "New C symbol(s) bound that are outside the audited surface: "
        f"{sorted(unexpected)}.\n"
        + "".join(
            f"  - {s}: {_QUARANTINED[s]}\n" for s in sorted(unexpected) if s in _QUARANTINED
        )
        + "If a new binding is genuinely required, add it to _ALLOWED in the SAME commit that "
        "documents why it is safe against the pinned build - not afterwards to turn the test green."
    )

    missing = _ALLOWED - bound
    assert not missing, (
        f"Expected binding(s) no longer present: {sorted(missing)}. The signer's surface shrank; "
        "update _ALLOWED deliberately so the guard keeps describing reality."
    )


@pytest.mark.parametrize("symbol", sorted(_QUARANTINED))
def test_quarantined_symbol_appears_nowhere_in_the_package(symbol):
    """Catch what the AST check cannot: getattr(lib, "..."), string-built names, other modules.

    The AST test only inspects _bind(). A dynamic lookup anywhere else would slip past it, so
    this sweeps every shipped source file textually.
    """
    offenders = []
    for path in sorted(_SDK_SRC.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if symbol in line and not line.lstrip().startswith("#"):
                offenders.append(f"{path.relative_to(_SDK_SRC.parent.parent)}:{lineno}: {line.strip()}")

    assert not offenders, (
        f"Quarantined symbol {symbol!r} referenced in shipped code:\n"
        + "\n".join(f"  {o}" for o in offenders)
        + f"\n\nReason it is quarantined: {_QUARANTINED[symbol]}"
    )


def test_guard_can_actually_fail():
    """A guard that cannot fail is the defect this repo keeps finding. Prove this one can.

    Rather than trusting that the assertions above would fire, run the extraction against a
    synthetic module that binds a quarantined symbol and confirm it is detected.
    """
    synthetic = ast.parse(
        "def _bind(lib):\n"
        "    lib.falcon_det1024_keygen.restype = None\n"
        "    lib.falcon_det1024_convert_compressed_to_ct.restype = None\n"
        "    return lib\n"
    )
    fn = next(n for n in ast.walk(synthetic) if isinstance(n, ast.FunctionDef))
    handle = fn.args.args[0].arg
    found = {
        n.attr
        for n in ast.walk(fn)
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == handle
    }
    assert "falcon_det1024_convert_compressed_to_ct" in found - _ALLOWED, (
        "The extraction failed to notice a quarantined binding in a module that plainly has one, "
        "so the guard above would pass vacuously."
    )
