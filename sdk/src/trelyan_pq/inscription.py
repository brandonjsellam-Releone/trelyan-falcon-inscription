"""
trelyan_pq.inscription — high-level client for TRELYAN post-quantum inscriptions on Algorand.

Turns the validated end-to-end flow into a few method calls:

    deploy -> fund -> mint cell ASA -> register (commit Falcon key) ->
    inscribe (sign M off-chain, submit only the signature) -> read back

and encapsulates the opcode-budget / box-reference / fee handling the `falcon_verify`
inscribe path needs (the two-strategy submit proven on localnet 20/20 and on TestNet).

Requires the `algorand` extra:

    pip install "trelyan-pq[algorand]"

and the generated typed app client class (TrelyanInscriptionFactory) produced from the
contract's ARC-56 (`algokit generate client ...`). It is build-specific, so you pass it in.

Example:

    from trelyan_client import TrelyanInscriptionFactory          # generated from the ARC-56
    from trelyan_pq.inscription import TrelyanInscriptionClient

    c = TrelyanInscriptionClient.deploy_testnet(MNEMONIC, TrelyanInscriptionFactory)
    c.fund_app()
    pk, sk = c.signer.keygen()
    cell = c.mint_cell()
    c.register_cell(cell, c.deployer.address, pk)
    c.inscribe_bytes(cell, b"my artifact", sk, b"ipfs://...")
    assert c.read_back_matches(cell, b"my artifact")
"""

from __future__ import annotations

import base64
from typing import Any, Optional

from .falcon import FalconDet1024
from .message import build_message, sha512_256, box_refs


def _algokit():
    try:
        import algokit_utils as au  # type: ignore
        return au
    except ImportError as e:  # pragma: no cover
        raise ImportError(
            'trelyan_pq.inscription needs the Algorand stack. '
            'Install it with:  pip install "trelyan-pq[algorand]"'
        ) from e


class TrelyanInscriptionClient:
    """High-level orchestration over a generated typed app client + a Falcon-1024 signer."""

    def __init__(self, algorand: Any, app_client: Any, deployer: Any,
                 signer: Optional[FalconDet1024] = None) -> None:
        self.algorand = algorand
        self.app = app_client            # generated typed client: .app_id, .app_address, .send.*
        self.deployer = deployer
        self.signer = signer or FalconDet1024()

    # ---- construction -----------------------------------------------------------------------
    @classmethod
    def deploy_testnet(cls, deployer_mnemonic: str, factory_cls: Any,
                       signer: Optional[FalconDet1024] = None) -> "TrelyanInscriptionClient":
        """Connect to TestNet, create the app, and return a ready client."""
        au = _algokit()
        algorand = au.AlgorandClient.testnet()
        deployer = algorand.account.from_mnemonic(mnemonic=deployer_mnemonic)
        factory = algorand.client.get_typed_app_factory(factory_cls, default_sender=deployer.address)
        app_client, _ = factory.send.create.create()
        return cls(algorand, app_client, deployer, signer)

    @classmethod
    def from_app_client(cls, algorand: Any, app_client: Any, deployer: Any,
                        signer: Optional[FalconDet1024] = None) -> "TrelyanInscriptionClient":
        """Wrap an app client you built yourself (e.g. attached to an existing app_id)."""
        return cls(algorand, app_client, deployer, signer)

    @property
    def app_id(self) -> int:
        return self.app.app_id

    @property
    def app_address(self) -> str:
        return self.app.app_address

    # ---- chain helpers ----------------------------------------------------------------------
    def network_genesis_hash(self) -> bytes:
        """The 32-byte network genesis hash (binds signatures to this network)."""
        gh = self.algorand.client.algod.suggested_params().gh
        if isinstance(gh, (bytes, bytearray)) and len(gh) == 32:
            return bytes(gh)
        return base64.b64decode(gh)

    def fund_app(self, micro_algo: int = 1_500_000) -> None:
        """Fund the app account for box min-balance (committed-key box ~0.72 ALGO + overhead)."""
        au = _algokit()
        self.algorand.send.payment(
            au.PaymentParams(sender=self.deployer.address, receiver=self.app_address,
                             amount=au.AlgoAmount.from_micro_algo(micro_algo))
        )

    def mint_cell(self, unit_name: str = "CELL", asset_name: str = "TRELYAN cell") -> int:
        """Create a clean pure-NFT cell ASA (total=1, decimals=0, no clawback/freeze/manager)."""
        au = _algokit()
        res = self.algorand.send.asset_create(
            au.AssetCreateParams(sender=self.deployer.address, total=1, decimals=0,
                                 default_frozen=False, unit_name=unit_name, asset_name=asset_name)
        )
        return res.asset_id

    # ---- protocol calls ---------------------------------------------------------------------
    def register_cell(self, cell_id: int, controlling_owner: str, committed_pubkey: bytes) -> None:
        """Commit the FULL Falcon public key + controlling owner for a cell (admin-only, once)."""
        au = _algokit()
        self.app.send.register_cell(
            args=(cell_id, controlling_owner, committed_pubkey),
            params=au.CommonAppCallParams(sender=self.deployer.address),
        )

    def inscribe(self, cell_id: int, artifact_hash: bytes, privkey: bytes,
                 payload_uri: bytes = b"", *, static_fee_micro: int = 20_000,
                 max_fee_micro: int = 50_000) -> None:
        """Sign M off-chain and submit ONLY the signature; the contract verifies on-chain.

        `artifact_hash` must be a 32-byte sha512_256 digest (use inscribe_bytes() to hash for you).
        Uses the proven two-strategy submit: a fat static fee + manual box/asset references first,
        then auto resource population + inner-fee coverage as a fallback.
        """
        if len(artifact_hash) != 32:
            raise ValueError("artifact_hash must be 32 bytes (use inscribe_bytes() to hash raw data)")
        au = _algokit()
        m = build_message(self.app_id, cell_id, artifact_hash, self.network_genesis_hash())
        sig = self.signer.sign(privkey, m)
        args = (cell_id, artifact_hash, sig, payload_uri)
        try:
            self.app.send.inscribe(
                args=args,
                params=au.CommonAppCallParams(
                    sender=self.deployer.address,
                    static_fee=au.AlgoAmount.from_micro_algo(static_fee_micro),
                    box_references=box_refs(cell_id), asset_references=[cell_id],
                    validity_window=1000),
                send_params=au.SendParams(populate_app_call_resources=False),
            )
        except Exception:
            self.app.send.inscribe(
                args=args,
                params=au.CommonAppCallParams(
                    sender=self.deployer.address,
                    max_fee=au.AlgoAmount.from_micro_algo(max_fee_micro),
                    validity_window=1000),
                send_params=au.SendParams(cover_app_call_inner_transaction_fees=True),
            )

    def inscribe_bytes(self, cell_id: int, artifact: bytes, privkey: bytes,
                       payload_uri: bytes = b"", **kw: Any) -> bytes:
        """Convenience: hash `artifact` with sha512_256, then inscribe. Returns the artifact hash."""
        h = sha512_256(artifact)
        self.inscribe(cell_id, h, privkey, payload_uri, **kw)
        return h

    def update_owner(self, cell_id: int, new_owner: str) -> None:
        """Move the controlling owner of a (pre-inscription) cell."""
        au = _algokit()
        self.app.send.update_owner(
            args=(cell_id, new_owner),
            params=au.CommonAppCallParams(sender=self.deployer.address),
        )

    # ---- reads ------------------------------------------------------------------------------
    def get_inscription(self, cell_id: int) -> Any:
        """Read the on-chain InscriptionRecord (readonly)."""
        au = _algokit()
        return self.app.send.get_inscription(
            args=(cell_id,),
            params=au.CommonAppCallParams(sender=self.deployer.address, validity_window=1000),
        ).abi_return

    def read_back_matches(self, cell_id: int, artifact: bytes, *, prehashed: bool = False) -> bool:
        """True iff the on-chain record's artifact_hash matches `artifact` (hashed unless prehashed)."""
        expected = artifact if prehashed else sha512_256(artifact)
        rec = self.get_inscription(cell_id)
        return bytes(rec.artifact_hash) == expected
