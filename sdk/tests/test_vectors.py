"""
Pinned golden vectors for trelyan_pq — lock the EXACT on-chain byte formats so any drift from
the contract is caught immediately. Pure-Python (no Falcon C lib / no network).

    pytest crypto/sdk/tests -v     (or run with the plain runner)
"""

from trelyan_pq import (
    build_message,
    sha512_256,
    committed_pubkey_box_name,
    controlling_owner_box_name,
    inscription_box_name,
)

# Golden hexes generated 2026-06-03 from the implementation and pinned here.
SHA_TRELYAN = "5a8b372a74e2993ecbcdb6d8fb2276ec72e3060f0e968f06a719eebafb47332e"
SHA_QDAY = "1e28d052dc634f343f4acb8b5795367887481c53ebb2042920a3a4a1ae3ecc53"
MSG_1001_1 = (
    "5452454c59414e2d494e534352495054494f4e2d7631"  # DOMAIN_TAG (22B)
    "00000000000003e9"                              # app_id = 1001
    "0000000000000001"                              # cell_id = 1
    "1e28d052dc634f343f4acb8b5795367887481c53ebb2042920a3a4a1ae3ecc53"  # artifact_hash
    "0000000000000000000000000000000000000000000000000000000000000000"  # genesis (zeros)
)
BOX_K_1 = "6b5f0000000000000001"      # b"k_" + uint64_be(1)
BOX_O_1 = "6f5f0000000000000001"      # b"o_" + uint64_be(1)
BOX_I_258 = "695f0000000000000102"    # b"i_" + uint64_be(258)


def test_sha512_256_golden():
    assert sha512_256(b"TRELYAN").hex() == SHA_TRELYAN
    assert sha512_256(b"hello, after Q-Day").hex() == SHA_QDAY


def test_build_message_golden():
    art = sha512_256(b"hello, after Q-Day")
    assert build_message(1001, 1, art, bytes(32)).hex() == MSG_1001_1


def test_box_name_golden():
    assert committed_pubkey_box_name(1).hex() == BOX_K_1
    assert controlling_owner_box_name(1).hex() == BOX_O_1
    assert inscription_box_name(258).hex() == BOX_I_258
