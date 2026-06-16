"""
TRELYAN inscription contract -- localnet test suite.

Closes A1 (falcon_verify accepts a real det1024 sig on-chain), A8 (off-chain compressed encoding
verifies on-chain), A4 (same-group double-inscribe + flash-custody rejected), A9 (committed pubkey in
a box, sign-only inscribe), and A2 (message binds the NATIVE Global.genesis_hash).

Coverage expanded per the full AI-council review of the tested contract: non-upgradability /
non-deletability (I5), the cell cap is left to RV static check, update_owner guard failure paths,
get_inscription raise-on-missing, cross-cell signature replay, re-registration, and the
clawback/freeze/manager hardening on Cell ASAs.

Inscribe self-budgets falcon_verify via ensure_budget(GroupCredit); we pay a fat static_fee (surplus
funds the OpUps at runtime), hand over the box + asset references explicitly, and disable the
resource-resolution probe (a probe would replay the program with no fee surplus and die at
falcon_verify). No simulate runs for inscribe.

PREREQS: Falcon lib built + FALCON_DET1024_LIB set; `algokit localnet start` running; typed client
RE-generated after recompile; `pip install algokit-utils pytest`.
"""

import base64
import hashlib
import pytest

import falcon_det1024
from trelyan_client import TrelyanInscriptionFactory  # generated

from algokit_utils import (
    AlgorandClient,
    AlgoAmount,
    AppDeleteParams,
    AppUpdateParams,
    AssetCreateParams,
    AssetOptInParams,
    AssetTransferParams,
    CommonAppCallParams,
    PaymentParams,
    SendParams,
)

DOMAIN_TAG = b"TRELYAN-INSCRIPTION-v1"
STATIC_FEE = AlgoAmount.from_micro_algo(20_000)  # exact inscribe fee; surplus over min funds the GroupCredit OpUps

# the real network genesis hash, set by the `algorand` fixture; the contract now binds the NATIVE
# Global.genesis_hash, so the off-chain message build MUST use the same 32 bytes.
_GENESIS = {"hash": None}


def genesis() -> bytes:
    assert _GENESIS["hash"] is not None, "the `algorand` fixture must initialize the genesis hash first"
    return _GENESIS["hash"]


def send_opts() -> SendParams:
    # Skip the resource-resolution probe for inscribe: we pass box + asset references explicitly and a
    # fat static_fee, so GroupCredit funds the OpUps at real-send runtime. A probe would replay the
    # program with no fee surplus and die at/around falcon_verify. No simulate runs.
    return SendParams(populate_app_call_resources=False)


def box_refs(cell_id: int):
    # the three boxes inscribe reads/writes for this cell. BoxMap name = key_prefix + itob(cell_id):
    #   committed_pubkey -> b"k_", controlling_owner -> b"o_", inscriptions -> b"i_".
    k = cell_id.to_bytes(8, "big")
    return [b"k_" + k, b"o_" + k, b"i_" + k]


def build_message(app_id: int, cell_id: int, artifact_hash: bytes, genesis_id_hash: bytes) -> bytes:
    assert len(artifact_hash) == 32 and len(genesis_id_hash) == 32
    return (
        DOMAIN_TAG
        + app_id.to_bytes(8, "big")
        + cell_id.to_bytes(8, "big")
        + artifact_hash
        + genesis_id_hash
    )


def sha512_256(data: bytes) -> bytes:
    h = hashlib.new("sha512_256")
    h.update(data)
    return h.digest()


def falcon_keypair():
    return falcon_det1024.keygen()                       # (pubkey[1793], privkey[2305])


def falcon_sign(secret_key: bytes, message: bytes) -> bytes:
    return falcon_det1024.sign_compressed(secret_key, message)   # det1024 compressed, header 0xBA


# ---------------------------------------------------------------- fixtures
@pytest.fixture(scope="session")
def algorand() -> AlgorandClient:
    client = AlgorandClient.default_localnet()
    gh = client.client.algod.suggested_params().gh         # base64 str or raw bytes, depending on sdk
    _GENESIS["hash"] = bytes(gh) if isinstance(gh, (bytes, bytearray)) and len(gh) == 32 else base64.b64decode(gh)
    return client


@pytest.fixture(scope="session")
def accounts(algorand):
    dispenser = algorand.account.localnet_dispenser()
    admin = algorand.account.random()
    mallory = algorand.account.random()
    for acct in (admin, mallory):
        algorand.account.ensure_funded(acct.address, dispenser, AlgoAmount.from_algo(100))
    return admin, mallory


@pytest.fixture(scope="module")
def deployed(algorand, accounts):
    admin, _ = accounts
    factory = algorand.client.get_typed_app_factory(TrelyanInscriptionFactory, default_sender=admin.address)
    client, _ = factory.send.create.create()               # A2: no genesis arg anymore
    # fund the app account: each committed_pubkey box (1793 B) costs ~0.72 ALGO min-balance, plus small
    # owner/inscription boxes; ~15 cells get registered across the suite -> fund generously.
    algorand.send.payment(
        PaymentParams(sender=admin.address, receiver=client.app_address, amount=AlgoAmount.from_algo(40))
    )
    return client, client.app_id, admin


# ---------------------------------------------------------------- helpers
_mint_counter = 0


def _next_note(tag: str) -> bytes:
    global _mint_counter
    _mint_counter += 1
    return (tag + "-" + str(_mint_counter)).encode()


def mint_cell(algorand, admin, holder) -> int:
    """Create a pure-NFT Cell ASA (total=1, decimals=0, creator=admin, NO clawback/freeze/manager) and
    place it with `holder`. A unique note keeps each asset_create txid distinct across tests."""
    res = algorand.send.asset_create(
        AssetCreateParams(sender=admin.address, total=1, decimals=0, default_frozen=False,
                          unit_name="CELL", asset_name="TRELYAN Cell", note=_next_note("trelyan-mint"))
    )
    asset_id = res.asset_id
    if holder.address != admin.address:
        algorand.send.asset_opt_in(AssetOptInParams(sender=holder.address, asset_id=asset_id))
        algorand.send.asset_transfer(
            AssetTransferParams(sender=admin.address, asset_id=asset_id, amount=1, receiver=holder.address)
        )
    return asset_id


def register(client, admin, cell, pubkey):
    """register_cell commits the FULL Falcon public key (1793 B), not a hash (A9)."""
    client.send.register_cell(args=(cell, admin.address, pubkey),
                              params=CommonAppCallParams(sender=admin.address))


def do_inscribe(client, sender, *, cell, artifact_hash, sig, payload_uri=b""):
    """Single inscribe. Pubkey is read from committed_pubkey[cell] (A9), not passed. static_fee +
    box/asset references + populate off => GroupCredit funds the OpUps, no simulate runs."""
    return client.send.inscribe(
        args=(cell, artifact_hash, sig, payload_uri),
        params=CommonAppCallParams(sender=sender.address, static_fee=STATIC_FEE,
                                   box_references=box_refs(cell), asset_references=[cell]),
        send_params=send_opts(),
    )


# ---------------------------------------------------------------- A1 / A8 / A9: the signature path
def test_inscribe_accepts_valid(algorand, deployed):
    client, app_id, admin = deployed
    pk, sk = falcon_keypair()
    cell = mint_cell(algorand, admin, admin)
    artifact_hash = sha512_256(b"hello, after Q-Day")
    register(client, admin, cell, pk)
    m = build_message(app_id, cell, artifact_hash, genesis())
    do_inscribe(client, admin, cell=cell, artifact_hash=artifact_hash, sig=falcon_sign(sk, m))
    rec = client.send.get_inscription(args=(cell,)).abi_return
    assert bytes(rec.artifact_hash) == artifact_hash


def test_inscribe_rejects_tampered_sig(algorand, deployed):
    client, app_id, admin = deployed
    pk, sk = falcon_keypair()
    cell = mint_cell(algorand, admin, admin)
    artifact_hash = sha512_256(b"x")
    register(client, admin, cell, pk)
    m = build_message(app_id, cell, artifact_hash, genesis())
    bad = bytearray(falcon_sign(sk, m)); bad[10] ^= 0xFF
    with pytest.raises(Exception):           # C4: falcon_verify fails on the tampered signature
        do_inscribe(client, admin, cell=cell, artifact_hash=artifact_hash, sig=bytes(bad))


def test_inscribe_rejects_wrong_key(algorand, deployed):
    """A9 moved this from the old C5 hash-check to C4: the contract verifies against the COMMITTED key
    (pk_good), so a signature by a different key (sk_evil) fails falcon_verify."""
    client, app_id, admin = deployed
    pk_good, _ = falcon_keypair()
    _, sk_evil = falcon_keypair()
    cell = mint_cell(algorand, admin, admin)
    artifact_hash = sha512_256(b"y")
    register(client, admin, cell, pk_good)
    m = build_message(app_id, cell, artifact_hash, genesis())
    with pytest.raises(Exception):
        do_inscribe(client, admin, cell=cell, artifact_hash=artifact_hash, sig=falcon_sign(sk_evil, m))


def test_double_inscribe_rejected_separate_txns(algorand, deployed):
    client, app_id, admin = deployed
    pk, sk = falcon_keypair()
    cell = mint_cell(algorand, admin, admin)
    artifact_hash = sha512_256(b"z")
    register(client, admin, cell, pk)
    sig = falcon_sign(sk, build_message(app_id, cell, artifact_hash, genesis()))
    do_inscribe(client, admin, cell=cell, artifact_hash=artifact_hash, sig=sig)
    with pytest.raises(Exception):           # C2 write-once
        do_inscribe(client, admin, cell=cell, artifact_hash=artifact_hash, sig=sig)


# ---------------------------------------------------------------- A4: same-group write-once
def test_double_inscribe_SAME_GROUP_rejected(algorand, deployed):
    """A4(b): two inscribe calls for the SAME cell in ONE atomic group -- the 2nd must fail write-once,
    failing the whole group (the AVM applies box writes between sequential grouped app calls)."""
    client, app_id, admin = deployed
    pk, sk = falcon_keypair()
    cell = mint_cell(algorand, admin, admin)
    artifact_hash = sha512_256(b"same-group")
    register(client, admin, cell, pk)
    sig = falcon_sign(sk, build_message(app_id, cell, artifact_hash, genesis()))
    p = CommonAppCallParams(sender=admin.address, static_fee=STATIC_FEE,
                            box_references=box_refs(cell), asset_references=[cell])
    grp = (client.new_group()
           .inscribe(args=(cell, artifact_hash, sig, b""), params=p)
           .inscribe(args=(cell, artifact_hash, sig, b""), params=p))
    with pytest.raises(Exception):
        grp.send(send_params=send_opts())
    with pytest.raises(Exception):           # whole group reverted -> still un-inscribed
        client.send.get_inscription(args=(cell,))


def test_flash_custody_rejected(algorand, deployed, accounts):
    """A4(a)/C1: a holder who is NOT the recorded controlling owner cannot inscribe, even while
    genuinely holding the Cell ASA. C1 gates on the mint-time controlling_owner, not bare balance."""
    client, app_id, admin = deployed
    _, mallory = accounts
    pk, sk = falcon_keypair()
    cell = mint_cell(algorand, admin, admin)
    artifact_hash = sha512_256(b"flash")
    register(client, admin, cell, pk)
    algorand.send.asset_opt_in(AssetOptInParams(sender=mallory.address, asset_id=cell))
    algorand.send.asset_transfer(
        AssetTransferParams(sender=admin.address, asset_id=cell, amount=1, receiver=mallory.address)
    )
    m = build_message(app_id, cell, artifact_hash, genesis())
    with pytest.raises(Exception):           # controlling_owner[cell] is still admin -> C1 rejects mallory
        do_inscribe(client, mallory, cell=cell, artifact_hash=artifact_hash, sig=falcon_sign(sk, m))


# ---------------------------------------------------------------- A2: cross-cell replay
def test_cross_cell_replay_rejected(algorand, deployed):
    """M binds cell_id, so a signature authorizing cell_a is invalid for cell_b -- even with the same
    committed key. Proves the message-integrity binding (I2/C3) the happy-path tests don't exercise."""
    client, app_id, admin = deployed
    pk, sk = falcon_keypair()
    cell_a = mint_cell(algorand, admin, admin)
    cell_b = mint_cell(algorand, admin, admin)
    register(client, admin, cell_a, pk)
    register(client, admin, cell_b, pk)            # same key committed to a different cell
    artifact_hash = sha512_256(b"replay")
    sig_a = falcon_sign(sk, build_message(app_id, cell_a, artifact_hash, genesis()))
    with pytest.raises(Exception):                 # sig over cell_a's M fails falcon_verify for cell_b
        do_inscribe(client, admin, cell=cell_b, artifact_hash=artifact_hash, sig=sig_a)


# ---------------------------------------------------------------- I5: non-upgradable / non-deletable
def test_rejects_update(algorand, deployed):
    """I5: UpdateApplication must be rejected by on_update (assert False) -- the approval program can
    never be replaced. The dummy program is irrelevant; the existing on_update handler runs first."""
    client, app_id, admin = deployed
    with pytest.raises(Exception):
        algorand.send.app_update(AppUpdateParams(
            sender=admin.address, app_id=app_id,
            approval_program="#pragma version 12\nint 1",
            clear_state_program="#pragma version 12\nint 1"))


def test_rejects_delete(algorand, deployed):
    """I1/I5: DeleteApplication must be rejected by on_delete (assert False) -- inscriptions permanent."""
    client, app_id, admin = deployed
    with pytest.raises(Exception):
        algorand.send.app_delete(AppDeleteParams(sender=admin.address, app_id=app_id))


# ---------------------------------------------------------------- register guards
def test_register_only_admin(algorand, deployed, accounts):
    client, app_id, admin = deployed
    _, mallory = accounts
    pk, _ = falcon_keypair()
    cell = mint_cell(algorand, admin, admin)
    with pytest.raises(Exception):                    # non-admin sender rejected
        client.send.register_cell(args=(cell, mallory.address, pk),
                                  params=CommonAppCallParams(sender=mallory.address))


def test_register_rejects_non_nft(algorand, deployed):
    client, app_id, admin = deployed
    pk, _ = falcon_keypair()
    res = algorand.send.asset_create(
        AssetCreateParams(sender=admin.address, total=1000, decimals=2, unit_name="NOT", asset_name="not nft",
                          note=_next_note("trelyan-nonnft"))
    )
    with pytest.raises(Exception):                    # fails the pure-NFT check (total!=1)
        register(client, admin, res.asset_id, pk)


def test_register_rejects_clawback_cell(algorand, deployed):
    """Council/Grok hardening: a Cell ASA with a clawback (or freeze/manager) set is rejected at
    register, so the C1 holding check can never be gamed by clawback/freeze timing."""
    client, app_id, admin = deployed
    pk, _ = falcon_keypair()
    res = algorand.send.asset_create(
        AssetCreateParams(sender=admin.address, total=1, decimals=0, unit_name="CLAW",
                          asset_name="clawbackable", clawback=admin.address, note=_next_note("trelyan-claw"))
    )
    with pytest.raises(Exception):                    # cell has a clawback -> rejected
        register(client, admin, res.asset_id, pk)


def test_register_rejects_bad_pubkey_length(algorand, deployed):
    """A9 hardening: committed key length validated at register (the only entry point)."""
    client, app_id, admin = deployed
    cell = mint_cell(algorand, admin, admin)
    with pytest.raises(Exception):
        register(client, admin, cell, b"\x00" * 1792)             # one byte short of PUBKEY_LEN (1793)


def test_register_rejects_bad_pubkey_header(algorand, deployed):
    """T4/Q13: register_cell rejects a CORRECT-length (1793 B) key whose HEADER byte != 0x0A
    (Deterministic Falcon-1024 logn=10 public keys begin with 0x0A). This is distinct from the
    length check above — the key is the right size but the wrong shape. A real det1024 key (header
    0x0A from keygen) still registers."""
    client, app_id, admin = deployed
    cell = mint_cell(algorand, admin, admin)
    with pytest.raises(Exception):                                # right length, wrong header (0x00 != 0x0A)
        register(client, admin, cell, b"\x00" * 1793)
    pk, _ = falcon_keypair()                                      # real key, header 0x0A -> accepted
    cell_ok = mint_cell(algorand, admin, admin)
    register(client, admin, cell_ok, pk)


def test_reregister_rejected(algorand, deployed):
    client, app_id, admin = deployed
    pk, _ = falcon_keypair()
    cell = mint_cell(algorand, admin, admin)
    register(client, admin, cell, pk)
    with pytest.raises(Exception):                    # register-once per cell
        register(client, admin, cell, pk)


# ---------------------------------------------------------------- inscribe input guards
def test_payload_uri_too_long_rejected(algorand, deployed):
    client, app_id, admin = deployed
    pk, sk = falcon_keypair()
    cell = mint_cell(algorand, admin, admin)
    artifact_hash = sha512_256(b"uri")
    register(client, admin, cell, pk)
    m = build_message(app_id, cell, artifact_hash, genesis())
    with pytest.raises(Exception):           # cheap URI length check (pre-falcon_verify)
        do_inscribe(client, admin, cell=cell, artifact_hash=artifact_hash,
                    sig=falcon_sign(sk, m), payload_uri=b"x" * 129)          # > URI_MAXLEN (128)


def test_sig_too_large_rejected(algorand, deployed):
    client, app_id, admin = deployed
    pk, _ = falcon_keypair()
    cell = mint_cell(algorand, admin, admin)
    artifact_hash = sha512_256(b"big")
    register(client, admin, cell, pk)
    with pytest.raises(Exception):           # cheap sig length check (pre-falcon_verify)
        do_inscribe(client, admin, cell=cell, artifact_hash=artifact_hash,
                    sig=b"\xba" + b"\x00" * 1500)                            # > 1423


# ---------------------------------------------------------------- update_owner state machine
def test_update_owner_only_owner(algorand, deployed, accounts):
    client, app_id, admin = deployed
    _, mallory = accounts
    pk, _ = falcon_keypair()
    cell = mint_cell(algorand, admin, admin)
    register(client, admin, cell, pk)
    with pytest.raises(Exception):           # only the current controlling_owner may reassign
        client.send.update_owner(args=(cell, mallory.address), params=CommonAppCallParams(sender=mallory.address))


def test_update_owner_after_inscribed_rejected(algorand, deployed, accounts):
    client, app_id, admin = deployed
    _, mallory = accounts
    pk, sk = falcon_keypair()
    cell = mint_cell(algorand, admin, admin)
    artifact_hash = sha512_256(b"frozen-owner")
    register(client, admin, cell, pk)
    do_inscribe(client, admin, cell=cell, artifact_hash=artifact_hash,
                sig=falcon_sign(sk, build_message(app_id, cell, artifact_hash, genesis())))
    with pytest.raises(Exception):           # owner frozen once inscribed
        client.send.update_owner(args=(cell, mallory.address), params=CommonAppCallParams(sender=admin.address))


def test_update_owner_then_inscribe(algorand, deployed, accounts):
    """update_owner is the AUTHORIZED handoff: after the owner reassigns to mallory and the ASA moves,
    mallory CAN inscribe -- proving C1 gates on the recorded owner, and the legit path works."""
    client, app_id, admin = deployed
    _, mallory = accounts
    pk, sk = falcon_keypair()
    cell = mint_cell(algorand, admin, admin)
    artifact_hash = sha512_256(b"handoff")
    register(client, admin, cell, pk)
    client.send.update_owner(args=(cell, mallory.address), params=CommonAppCallParams(sender=admin.address))
    algorand.send.asset_opt_in(AssetOptInParams(sender=mallory.address, asset_id=cell))
    algorand.send.asset_transfer(
        AssetTransferParams(sender=admin.address, asset_id=cell, amount=1, receiver=mallory.address)
    )
    m = build_message(app_id, cell, artifact_hash, genesis())
    do_inscribe(client, mallory, cell=cell, artifact_hash=artifact_hash, sig=falcon_sign(sk, m))
    rec = client.send.get_inscription(args=(cell,)).abi_return
    assert bytes(rec.artifact_hash) == artifact_hash


# ---------------------------------------------------------------- read path (I3)
def test_get_inscription_missing_raises(algorand, deployed):
    """A3/I3: get_inscription on a registered-but-not-inscribed cell RAISES (missing box read), so
    callers treat a failed read as 'not inscribed' rather than reading a zero record."""
    client, app_id, admin = deployed
    pk, _ = falcon_keypair()
    cell = mint_cell(algorand, admin, admin)
    register(client, admin, cell, pk)                 # registered, NOT inscribed
    with pytest.raises(Exception):
        client.send.get_inscription(args=(cell,))


# ---------------------------------------------------------------- T5/Q2: encoding rejection matrix
def test_signature_encoding_rejection_matrix(algorand, deployed):
    """T5/Q2: the malformed-signature rejection matrix AT THE OPCODE BOUNDARY, spelled out. One
    registered cell; every malformed encoding is rejected (so the cell stays un-inscribed across all
    of them), then the valid sigma accepts. Mirrors test_signature_kat.test_sdk_encoding_rejection_
    matrix off-chain. A fuzzing harness over these is a noted follow-up (out of scope)."""
    client, app_id, admin = deployed
    pk, sk = falcon_keypair()
    cell = mint_cell(algorand, admin, admin)
    artifact_hash = sha512_256(b"encoding-matrix")
    register(client, admin, cell, pk)
    m = build_message(app_id, cell, artifact_hash, genesis())
    good = falcon_sign(sk, m)
    assert good[0] == 0xBA and good[1] == 0x00                      # det1024 compressed header + salt-version

    wrong_header = bytes([0x3A]) + good[1:]                         # not 0xBA (randomized-Falcon header)
    truncated = good[:-64]                                          # short of a complete sigma
    over_long = good + b"\x00" * (1424 - len(good))                 # > SIG_COMPRESSED_MAXLEN (1423)
    bad_salt = bytes([good[0], good[1] ^ 0xFF]) + good[2:]          # tampered salt-version byte
    wrong_m = falcon_sign(sk, build_message(app_id, cell, sha512_256(b"different"), genesis()))  # valid sig, wrong M

    # DIFFERENTIAL ORACLE: the off-chain verifier and the on-chain falcon_verify opcode must AGREE
    # on every case — the SDK can't accept what the chain rejects, or vice-versa.
    assert falcon_det1024.verify_compressed(good, pk, m)           # off-chain accept (matches on-chain)
    for bad in (wrong_header, truncated, over_long, bad_salt, wrong_m):
        assert not falcon_det1024.verify_compressed(bad, pk, m)    # off-chain rejects (no crash)...
        with pytest.raises(Exception):                             # ...and on-chain rejects too
            do_inscribe(client, admin, cell=cell, artifact_hash=artifact_hash, sig=bad)

    do_inscribe(client, admin, cell=cell, artifact_hash=artifact_hash, sig=good)   # positive accept
    rec = client.send.get_inscription(args=(cell,)).abi_return
    assert bytes(rec.artifact_hash) == artifact_hash
