"""
Pure-Python tests for trelyan_pq.message — no Falcon C library or Algorand stack needed.

These lock the byte-exact wire formats (message + box names) that MUST match the on-chain
contract. Run:  pytest crypto/sdk/tests -v
"""

import hashlib

from trelyan_pq import (
    DOMAIN_TAG,
    MESSAGE_LEN,
    build_message,
    sha512_256,
    cell_key,
    box_refs,
    committed_pubkey_box_name,
    controlling_owner_box_name,
    inscription_box_name,
)


def test_sha512_256_is_32_bytes_and_correct():
    d = sha512_256(b"hello, after Q-Day")
    assert len(d) == 32
    assert d == hashlib.new("sha512_256", b"hello, after Q-Day").digest()


def test_cell_key_is_8_byte_big_endian():
    assert cell_key(1) == b"\x00\x00\x00\x00\x00\x00\x00\x01"
    assert cell_key(258) == (258).to_bytes(8, "big")


def test_cell_key_rejects_out_of_range():
    for bad in (-1, 2 ** 64):
        try:
            cell_key(bad)
        except ValueError:
            pass
        else:
            raise AssertionError(f"cell_key accepted out-of-range value {bad}")


def test_box_names_match_contract_prefixes():
    assert committed_pubkey_box_name(7) == b"k_" + cell_key(7)
    assert controlling_owner_box_name(7) == b"o_" + cell_key(7)
    assert inscription_box_name(7) == b"i_" + cell_key(7)
    assert box_refs(7) == [b"k_" + cell_key(7), b"o_" + cell_key(7), b"i_" + cell_key(7)]


def test_build_message_layout():
    art = sha512_256(b"artifact")
    genesis = bytes(range(32))
    m = build_message(app_id=1001, cell_id=1, artifact_hash=art, genesis_hash=genesis)
    assert len(m) == MESSAGE_LEN == 102
    # DOMAIN_TAG || app_id(8) || cell_id(8) || artifact_hash(32) || genesis(32)
    assert m[:22] == DOMAIN_TAG
    assert m[22:30] == (1001).to_bytes(8, "big")
    assert m[30:38] == (1).to_bytes(8, "big")
    assert m[38:70] == art
    assert m[70:102] == genesis


def test_build_message_validates_lengths():
    good = bytes(32)
    for bad_art in (bytes(31), bytes(33)):
        try:
            build_message(1, 1, bad_art, good)
        except ValueError:
            pass
        else:
            raise AssertionError("build_message accepted a non-32-byte artifact_hash")
    try:
        build_message(1, 1, good, bytes(16))
    except ValueError:
        pass
    else:
        raise AssertionError("build_message accepted a non-32-byte genesis_hash")


def test_build_message_is_deterministic():
    art, g = sha512_256(b"x"), bytes(32)
    assert build_message(5, 9, art, g) == build_message(5, 9, art, g)
    assert build_message(5, 9, art, g) != build_message(6, 9, art, g)  # app_id binds
    assert build_message(5, 9, art, g) != build_message(5, 10, art, g)  # cell_id binds
