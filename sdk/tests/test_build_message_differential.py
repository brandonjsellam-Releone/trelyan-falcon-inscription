"""The two remaining build_message implementations must agree, and must match the chain.

WHY THIS FILE EXISTS
────────────────────────────────────────────────────────────────────────────────────────────────
There were FOUR copies of the signed-message construction and no test compared any two:

    sdk/src/trelyan_pq/message.py       the SDK's, published to PyPI
    contracts/falcon_det1024.py         the contracts-side signer
    contracts/deploy_testnet.py         a local copy — DELETED
    contracts/test_inscription.py       a local copy — DELETED

The two deleted copies were not harmless duplication. `deploy_testnet.py`'s omitted the length
checks entirely, so a 31- or 33-byte artifact hash produced a 101- or 103-byte M and was signed
without complaint — in the script that signs REAL TestNet inscriptions. The ABI's
`StaticArray[Byte, 32]` blocks that reaching the chain, which is why this is low and not high,
but "another layer catches it" is a mitigation, not a reason for the layer below to be wrong.

Two implementations remain, deliberately: `contracts/` has to work without the SDK installed.
Two is a decision; four was an accident. What makes two safe is that something compares them.

M is the preimage of every Falcon signature this project produces. If these two ever disagree
by a byte, signatures minted by one path stop verifying on the other, and the failure surfaces
as "invalid signature" — the least informative error possible for the actual cause.

AUDIT_READINESS.md §2.3 cited three tests as covering this. None of them compared two
implementations; each exercised one.
"""

import base64
import hashlib
import pathlib
import sys

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT / "contracts"))

from trelyan_pq import build_message as sdk_build_message  # noqa: E402

try:
    from falcon_det1024 import build_message as contracts_build_message  # noqa: E402
except Exception as exc:  # pragma: no cover - reported, never silently skipped
    pytest.fail(
        "contracts/falcon_det1024.py could not be imported, so the two implementations cannot "
        f"be compared and this file would pass vacuously: {type(exc).__name__}: {exc}"
    )

# The exact message accepted on-chain for TestNet app 763809096, cell 763809098 — read from the
# live inscription record (artifact_hash at rec[9:41]) and the TestNet genesis hash. This is the
# anchor: it is not what either implementation says M should be, it is what the chain took.
_LIVE_APP_ID = 763809096
_LIVE_CELL_ID = 763809098
_LIVE_ARTIFACT = bytes.fromhex("5680fc4ddf9d331b585198239ab41bdc768e3192efc477793a9daa1445dd4574")
_TESTNET_GENESIS = base64.b64decode("SGO1GKSzyE7IEPItTxCByw9x8FmnrCDexi9/cOUJOiI=")
_LIVE_M_HEX = (
    "5452454c59414e2d494e534352495054494f4e2d7631"  # DOMAIN_TAG
    "000000002d86cd48"                              # app_id
    "000000002d86cd4a"                              # cell_id
    "5680fc4ddf9d331b585198239ab41bdc768e3192efc477793a9daa1445dd4574"  # artifact_hash
    "4863b518a4b3c84ec810f22d4f1081cb0f71f059a7ac20dec62f7f70e5093a22"  # genesis_hash
)


def _cases():
    """Inputs chosen to separate the implementations if they differ at all."""
    h = lambda s: hashlib.new("sha512_256", s).digest()  # noqa: E731
    return [
        pytest.param(_LIVE_APP_ID, _LIVE_CELL_ID, _LIVE_ARTIFACT, _TESTNET_GENESIS, id="live-testnet"),
        pytest.param(0, 0, bytes(32), bytes(32), id="all-zero"),
        pytest.param(1, 1, b"\xff" * 32, b"\xff" * 32, id="all-ff"),
        # 2**64-1 exercises the full 8-byte big-endian width on both fields.
        pytest.param(2**64 - 1, 2**64 - 1, h(b"max"), h(b"genesis"), id="uint64-max"),
        pytest.param(1001, 1, h(b"hello, after Q-Day"), bytes(32), id="doc-example"),
        pytest.param(763809096, 258, h(b"boundary"), h(b"g"), id="two-byte-cell-id"),
    ]


@pytest.mark.parametrize(("app_id", "cell_id", "artifact", "genesis"), _cases())
def test_both_implementations_agree(app_id, cell_id, artifact, genesis):
    a = sdk_build_message(app_id, cell_id, artifact, genesis)
    b = contracts_build_message(app_id, cell_id, artifact, genesis)
    assert a == b, (
        "the SDK and contracts-side build_message disagree:\n"
        f"  sdk       {a.hex()}\n  contracts {b.hex()}\n"
        "M is the preimage of every Falcon signature here, so a byte of divergence means "
        "signatures minted by one path stop verifying on the other."
    )
    assert len(a) == 102


def test_both_match_the_message_the_chain_accepted():
    """The anchor. Not what either implementation claims, but what TestNet actually took."""
    for name, fn in (("sdk", sdk_build_message), ("contracts", contracts_build_message)):
        m = fn(_LIVE_APP_ID, _LIVE_CELL_ID, _LIVE_ARTIFACT, _TESTNET_GENESIS)
        assert m.hex() == _LIVE_M_HEX, (
            f"{name} build_message no longer reproduces the live TestNet message for cell "
            f"{_LIVE_CELL_ID}:\n  got      {m.hex()}\n  expected {_LIVE_M_HEX}"
        )


@pytest.mark.parametrize("bad_len", [0, 31, 33, 64])
def test_both_reject_a_wrong_length_artifact_hash(bad_len):
    """The divergence that actually existed: the deleted copies had no length check.

    `deploy_testnet.py`'s version concatenated whatever it was given, so a 31-byte hash yielded a
    101-byte M and got signed. Both survivors must refuse, and refuse for the same inputs.
    """
    bad = b"\xab" * bad_len
    for name, fn in (("sdk", sdk_build_message), ("contracts", contracts_build_message)):
        with pytest.raises(Exception):
            fn(_LIVE_APP_ID, _LIVE_CELL_ID, bad, _TESTNET_GENESIS)


@pytest.mark.parametrize("bad_len", [0, 31, 33])
def test_both_reject_a_wrong_length_genesis_hash(bad_len):
    bad = b"\xcd" * bad_len
    for name, fn in (("sdk", sdk_build_message), ("contracts", contracts_build_message)):
        with pytest.raises(Exception):
            fn(_LIVE_APP_ID, _LIVE_CELL_ID, _LIVE_ARTIFACT, bad)


def test_the_comparison_is_not_vacuous():
    """Both names must resolve to genuinely different function objects.

    If an import shortcut ever made these the same object, every assertion above would compare a
    function to itself and pass no matter what either does.
    """
    assert sdk_build_message is not contracts_build_message, (
        "both names resolve to the same function; this file would be comparing it to itself"
    )
