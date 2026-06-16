# TRELYAN Inscription Contract — reference implementation
# Language: Algorand Python (Algopy / puyapy)
# Spec: crypto/TRELYAN_PROTOCOL_SPEC_v0.2.md  (implements C1-C5, I1-I5)
# Status: DRAFT for Runtime Verification audit. NOT audited. NOT for mainnet.
#
# This reference prioritizes auditability and spec-traceability over gas-golfing.
# Every check is commented with its spec tag. An auditor should be able to read this
# top-to-bottom against the spec's §5 and §6 without ambiguity.
#
# Council-review fixes baked in:
#   [Hermes#3] app_id bound into the signed message M
#   [Hermes#2] ownership check hardened beyond a bare balance>0
#   [Hermes#4] committed key read from immutable mint storage, set atomically at mint
#   [Hermes#1] non-upgradable: update/delete permanently disabled (I5)
#   [Hermes#5] Falcon verify isolated; budget pooled via ensure_budget (OpUp / GroupCredit)
#   [Gemini]   collision-resistance framing for the hash (doc, not code)
#   [watsonx]  lifecycle (key loss / abandoned cells) handled at policy layer, noted here
#   [A9 / full council 2026-06-01] committed key stored IN FULL in box state and read by inscribe,
#              so the 1793 B key never rides in the 2048 B ApplicationArgs budget (see A9 below)
#
# ============================ OPEN AUDIT NOTES ============================
# These are UNRESOLVED items from the Council code review (Hermes second pass).
# They MUST be confirmed against the LIVE Algorand AVM reference + resolved with the
# RV auditor before mainnet. They are intentionally left visible, not silently "fixed",
# because fixing them against UNVERIFIED opcode semantics could introduce new errors.
#
#   [AUDIT-NOTE A1 — RESOLVED by official docs 2026-06-01; confirmed on localnet 2026-06-01]
#       Argument order CONFIRMED against Algorand's own references: the native opcode is
#       falcon_verify(data, signature, public_key) -> bool, with the signature in COMPRESSED
#       Falcon encoding. Sources: dev.algorand.co op.falconVerify reference + algopy
#       op.falcon_verify; algorand.co "Quantum-resistant transactions with Falcon signatures"
#       technical brief. This code's call `op.falcon_verify(m, falcon_sig.bytes, pubkey)`
#       MATCHES that order. PUBKEY_LEN=1793 is the correct Falcon-1024 public-key length; the
#       compressed signature is variable-length, hence falcon_sig is DynamicBytes (no fixed-len
#       assert — correct). The emitted TEAL operand order was eyeballed post-PuyaPy build, and a
#       live accept/reject vector runs in test_inscription.py. See A1_RESOLUTION_2026-06-01.md.
#
#   [AUDIT-NOTE A2 — RESOLVED 2026-06-01 (full-council must-fix, Mistral lead)]
#       Network binding source. _build_message now binds the NATIVE `Global.genesis_hash` (32-byte
#       network genesis, min AVM v10) directly. create() no longer takes or stores a genesis_id_hash,
#       so there is NO deploy-time setter that could silently scope signatures to the wrong network
#       (a wrong stored value was the prior footgun). The off-chain signer + localnet suite use the
#       real network genesis hash and verify green against it. Closed.
#
#   [AUDIT-NOTE A3 — RESOLVED by docs 2026-06-01]
#       BoxMap miss semantics. CONFIRMED (Algorand Python storage docs): a missing-key read
#       `box[cid]` RAISES and fails the program — it does NOT return a zero/default value.
#       (Safe alternatives exist: `.get(default=...)`, `.maybe()`, the `in` operator.) Every read
#       in this contract is already guarded by `assert cid in self.<map>`, and even an unguarded
#       subscript of an unset box would fail rather than silently read zero — so no path can act on
#       a zero-value box read. Optional defense-in-depth: switch hot reads to `.maybe()` for an
#       explicit (value, exists) tuple; not required for correctness.
#
#   [AUDIT-NOTE A4 — DIRECTION CONFIRMED 2026-06-01; localnet group-test PASSING 2026-06-01]
#       Group-composition / same-group race. AVM executes grouped application calls SEQUENTIALLY,
#       and box resources + read/write budgets are SHARED across the atomic group. On that model:
#       (b) two inscribe calls for the same cell in one group cannot both pass write-once — txn#2
#       observes `cid in self.inscriptions` set by txn#1 and `assert cid not in self.inscriptions`
#       fails; (a) update_owner is a SEPARATE authorized call, so a transient ASA holder cannot
#       self-grant within a group. The localnet suite now exercises BOTH a grouped double-inscribe
#       (test_double_inscribe_SAME_GROUP_rejected) and a flash-custody attempt
#       (test_flash_custody_rejected), both rejected as expected. STILL want the RV auditor to
#       formally confirm the intra-group state-visibility assumption for this exact pattern.
#
#   [AUDIT-NOTE A9 — RESOLVED 2026-06-01 by localnet + full AI council; the design decision]
#       AVM hard limit: a single app call's ApplicationArgs total <= 2048 bytes. The original ABI
#       passed BOTH the Falcon-1024 public key (1793 B) and the compressed signature (<=1423 B) as
#       inscribe args (~3079 B) -> node-rejected ("tx.ApplicationArgs total length is too long").
#       FIX (AI council, 4-of-6 incl. the cryptography and architecture seats): store the FULL
#       committed public key in box state at register_cell and have inscribe READ it, passing only
#       the signature. The key is now bound to the cell BY CONSTRUCTION; the prior C5 "reveal pubkey
#       and check sha512_256(pubkey)==committed_hash" is removed — it was a storage optimization, not
#       a security property (Falcon public keys are public, so revealing at mint vs at inscribe is
#       immaterial, and using the committed key directly is a STRONGER binding: no key argument can
#       be substituted). Council residuals folded in: (a) the exact pubkey length is validated at
#       register_cell — the ONLY point a key enters state — so a malformed key can never be committed
#       [OpenAI/Grok/Gemini]; (b) the sig arg is sized for the det1024 MAXIMUM (SIG_COMPRESSED_MAXLEN
#       =1423, above the ~1330 generic-Falcon max) [Gemini]; (c) the pubkey is NOT duplicated into the
#       inscription record — it lives once in committed_pubkey[cid] and an I3 re-verifier reads both
#       boxes, ~halving per-cell box rent [watsonx].
#       OPEN residuals for RV: (i) cross-chain/instance replay — M binds app_id + genesis_hash;
#       confirm sufficiency (a re-deployed app reusing app_id on a fork with identical genesis is the
#       only residual) [Grok]; (ii) key loss is irrecoverable by design (immutable commitment, no
#       rotation) — intentional per I4/I5 but a documented, accepted lifecycle fact [Grok/watsonx];
#       (iii) committed-key box min-balance ~0.72 ALGO/cell (~737 ALGO across all 1024 cells) — an
#       accepted Foundation cost [watsonx]; (iv) the controlling public key is visible on-chain from
#       mint — a public key, not PII, but noted in the threat model [Mistral].
# =========================================================================

from typing import Literal
from algopy import (
    ARC4Contract,
    Account,
    Asset,
    Bytes,
    BoxMap,
    Global,
    OpUpFeeSource,
    Txn,
    UInt64,
    arc4,
    ensure_budget,
    op,
    subroutine,
)

# ---- protocol constants (spec §4) ----
DOMAIN_TAG = b"TRELYAN-INSCRIPTION-v1"   # 22 bytes
INS_VERSION = 1                          # stored into an arc4.UInt8 field — keep <= 255 (L2)
PUBKEY_LEN = 1793                        # Falcon-1024 public key (spec §1.1)
SIG_COMPRESSED_MAXLEN = 1423             # det1024 compressed sig max (FALCON_ENCODING_2026-06-01.md)
HASH_LEN = 32                            # sha512_256 output
URI_MAXLEN = 128                         # payload_uri cap (spec §3) — keeps the box within budget (M3)
TOTAL_CELLS = 1024


class InscriptionRecord(arc4.Struct):
    """Write-once inscription record stored in box INS(cell_id). Spec §3.
    The Falcon public key is NOT duplicated here — it lives permanently in committed_pubkey[cell_id]
    (written once at register_cell); an I3 re-verifier reads BOTH boxes by cell_id. [A9/watsonx]"""
    version: arc4.UInt8
    cell_id: arc4.UInt64
    artifact_hash: arc4.StaticArray[arc4.Byte, Literal[32]]
    inscribed_round: arc4.UInt64
    inscriber: arc4.Address
    payload_uri: arc4.DynamicBytes


class TrelyanInscription(ARC4Contract):
    """
    TRELYAN post-quantum inscription application.

    Storage:
      - committed_pubkey   : BoxMap[cell_id -> 1793B] immutable, written ONLY at register_cell (the
                                                       Cell mint record). The FULL Falcon-1024 public
                                                       key, NOT a hash: inscribe reads it from here so
                                                       the key never travels as a call arg (A9). I4/C5.
      - inscriptions       : BoxMap[cell_id -> InscriptionRecord]  write-once. Spec I1/C2.
      - controlling_owner  : BoxMap[cell_id -> 32B]    address allowed to inscribe. Spec C1.
      - (network pin)      : the native Global.genesis_hash is read in _build_message — no stored
                             genesis value, no deploy-time arg, so the chain can never be mis-pinned (A2).
      - admin              : the Foundation/Stiftung address permitted to register cells
                             ONLY (mint). It has NO power over inscriptions. Spec governance.
    """

    def __init__(self) -> None:
        # committed Falcon-1024 public key per cell — stored IN FULL (1793 B), immutable after
        # register_cell. Stored as the full key (not a hash) so inscribe can READ it from state
        # instead of taking it as a call arg: the AVM caps total ApplicationArgs at 2048 B and
        # pubkey(1793) + sig(<=1423) would overflow it. See AUDIT-NOTE A9.
        self.committed_pubkey = BoxMap(UInt64, Bytes, key_prefix=b"k_")
        # the actual inscriptions (write-once)
        self.inscriptions = BoxMap(UInt64, InscriptionRecord, key_prefix=b"i_")
        # controlling owner recorded at register (hardened ownership, [Hermes#2])
        self.controlling_owner = BoxMap(UInt64, Bytes, key_prefix=b"o_")
        # governance (network is pinned via native Global.genesis_hash in _build_message — A2)
        self.admin = Account()
        self.cells_registered = UInt64(0)

    # -------------------------------------------------------------------------
    # Lifecycle: create / mint registration
    # -------------------------------------------------------------------------

    @arc4.abimethod(create="require")
    def create(self) -> None:
        """Deploy. Sets the admin (mint authority). The network is pinned via the NATIVE
        Global.genesis_hash read in _build_message (A2 resolved) — there is no deploy-time genesis
        argument, so a wrong value can never silently scope signatures to the wrong network."""
        self.admin = Txn.sender

    @arc4.abimethod
    def register_cell(
        self,
        cell: Asset,
        controlling_owner: arc4.Address,
        committed_pubkey: arc4.DynamicBytes,
    ) -> None:
        """
        Mint record for a Cell. Sets the immutable committed Falcon-1024 public key and the
        controlling owner ATOMICALLY (spec C5/I4/[Hermes#4]).

        Only the admin (Foundation) may register; only ONCE per cell; only up to 1,024 cells.
        The registration is BOUND to a real Cell ASA — a pure NFT created by the admin — so a
        commitment cannot be registered under an arbitrary or nonexistent integer id. This closes
        the I4/M1 gap found in pre-audit review: `cid` derives from a real `Asset` (cell.id),
        exactly as inscribe() does, so the two can never key off different id spaces.

        The FULL public key is stored (not a hash): inscribe READS it from state, so the 1,793-byte
        key never has to travel as a call argument — the AVM caps total ApplicationArgs at 2,048 B,
        which pubkey + signature would overflow (AUDIT-NOTE A9). The exact key length is enforced
        HERE, at the only point a key ever enters state, so a malformed key can never be committed
        [council: validate-at-register]. After this call committed_pubkey[cell.id] is immutable
        (no method rewrites it) — the controlling key is bound to the cell by construction.
        """
        cid = cell.id
        # admin-only mint authority
        assert Txn.sender == self.admin, "only admin may register cells"
        # bind to a REAL Cell ASA: pure NFT (total 1 / decimals 0) created by the admin (I4/M1)
        assert cell.total == UInt64(1) and cell.decimals == UInt64(0), "cell must be a pure NFT"
        assert cell.creator == self.admin, "cell ASA not created by admin"
        # Cells must be immutable, owner-controlled NFTs: no clawback (can't be seized or balance-gamed
        # to fake the C1 holding check), no freeze (can't be frozen to block inscription), no manager
        # (so clawback/freeze can never be re-added later). [council/Grok: closes the AssetHoldingGet
        # clawback / freeze / close-out timing vector at the source.]
        assert cell.clawback == Global.zero_address, "cell must have no clawback"
        assert cell.freeze == Global.zero_address, "cell must have no freeze"
        assert cell.manager == Global.zero_address, "cell manager must be cleared (immutable config)"
        # validate the committed key length at the ONLY point a key enters state (C5/I4/A9).
        # A malformed (wrong-length) key would brick the cell — reject it at the source.
        assert committed_pubkey.native.length == PUBKEY_LEN, "bad committed pubkey length"  # .native = raw bytes (no ARC4 len prefix)
        # [T4/Q13] header-byte well-formedness: a Deterministic Falcon-1024 (logn=10) public key
        # begins with 0x0A (FALCON_ENCODING_2026-06-01.md; confirmed against the algorand/falcon
        # keygen). Checked at the ONLY point a key enters state, so a wrong-curve/malformed key can
        # never be committed. ABI-compatible: added assert only, no signature/selector change.
        assert op.getbyte(committed_pubkey.native, UInt64(0)) == UInt64(0x0A), "bad committed pubkey header (logn=10)"
        # 1,024 cell hard cap (spec §2)
        assert self.cells_registered < TOTAL_CELLS, "all 1024 cells registered"
        # register-once: committed key and owner must not already exist
        assert cid not in self.committed_pubkey, "cell already registered"
        assert cid not in self.controlling_owner, "cell already registered (owner)"

        # write immutable commitments atomically
        self.committed_pubkey[cid] = committed_pubkey.native   # store the raw 1793 B key, NOT the ARC4-prefixed encoding
        self.controlling_owner[cid] = controlling_owner.bytes
        self.cells_registered += UInt64(1)

    # -------------------------------------------------------------------------
    # Core: inscribe  (spec §5, checks C1-C5)
    # -------------------------------------------------------------------------

    @arc4.abimethod
    def inscribe(
        self,
        cell: Asset,
        artifact_hash: arc4.StaticArray[arc4.Byte, Literal[32]],
        falcon_sig: arc4.DynamicBytes,
        payload_uri: arc4.DynamicBytes,
    ) -> None:
        """
        Inscribe `cell` with `artifact_hash`, authorized by a Falcon-1024 signature over the
        domain-separated message M.

        The controlling public key is NOT a parameter — it was committed in full at register_cell
        and is READ from state here (AUDIT-NOTE A9). That (1) keeps the 1,793 B key out of the
        2,048 B ApplicationArgs budget — only the signature (<=1423 B) rides in the args — and
        (2) binds the key to the cell by construction: a caller cannot substitute a key.

        Budget note [Hermes#5]: falcon_verify is opcode-heavy (~1700). ensure_budget pools the extra
        budget via OpUp inner txns funded from the group's fee surplus (GroupCredit) — the caller
        attaches surplus fee, so inscribe is self-budgeting (no hand-assembled OpUp group needed).
        """
        cid = cell.id
        art = artifact_hash.bytes

        # --- structural preconditions ---
        assert cid in self.committed_pubkey, "cell not registered"             # must be minted
        assert falcon_sig.native.length <= SIG_COMPRESSED_MAXLEN, "falcon sig too large"  # .native (no ARC4 prefix); det1024 compressed <=1423B: cheap pre-verify DoS bound
        assert art.length == HASH_LEN, "bad artifact hash length"
        assert payload_uri.native.length <= URI_MAXLEN, "payload_uri too long"  # .native (no ARC4 prefix); spec §3 <=128B: bounds the write-once box size (M3)

        # --- C1: ownership, HARDENED [Hermes#2] ---
        # Sender must (a) currently hold exactly the Cell, AND (b) be the controlling owner recorded
        # at mint. (b) defeats transient/flash-custody: a temporary ASA holder is not the recorded
        # controlling owner. An owner transfer must go through update_owner (below), which requires
        # the prior owner's authorization — not a bare balance flip.
        balance, exists = op.AssetHoldingGet.asset_balance(Txn.sender, cell)
        assert exists and balance == UInt64(1), "sender does not hold the cell"
        assert cid in self.controlling_owner, "no controlling owner set"
        assert self.controlling_owner[cid] == Txn.sender.bytes, "sender not controlling owner"

        # --- C2: single-use / write-once (I1) ---
        assert cid not in self.inscriptions, "cell already inscribed"

        # --- C5: the controlling key is the one committed at mint, read from the IMMUTABLE mint
        # record [Hermes#4]. There is no pubkey argument to validate against a hash anymore (A9): the
        # contract uses the committed key DIRECTLY, so key-substitution is impossible by construction
        # — strictly stronger than the prior reveal-and-hash-check. ---
        pubkey = self.committed_pubkey[cid]

        # --- C3: reconstruct M on-chain, including app_id [Hermes#3] (I2) ---
        m = self._build_message(cid, art)

        # --- ensure opcode budget for falcon_verify (~1700) via OpUp inner txns [Hermes#5 / FALCON_BUDGET].
        # Placed AFTER the cheap structural + ownership checks so an unauthorized attempt rejects
        # cheaply (fail-fast preserved). GroupCredit: the caller supplies surplus fee to fund the OpUps. ---
        ensure_budget(UInt64(2100), fee_source=OpUpFeeSource.GroupCredit)
        # --- C4: Falcon-1024 signature check against the COMMITTED key (the expensive opcode, run last) ---
        assert op.falcon_verify(m, falcon_sig.native, pubkey), "falcon signature invalid"  # .native: raw compressed sig, no ARC4 len prefix

        # --- effect: write the write-once record. The committed pubkey is NOT duplicated here — it
        # already lives permanently in committed_pubkey[cid]; an I3 re-verifier reads both boxes. ---
        rec = InscriptionRecord(
            version=arc4.UInt8(INS_VERSION),
            cell_id=arc4.UInt64(cid),
            artifact_hash=artifact_hash.copy(),
            inscribed_round=arc4.UInt64(Global.round),
            inscriber=arc4.Address(Txn.sender),
            payload_uri=payload_uri.copy(),
        )
        self.inscriptions[cid] = rec.copy()

    @subroutine
    def _build_message(self, cell_id: UInt64, artifact_hash: Bytes) -> Bytes:
        """M = DOMAIN_TAG ‖ app_id ‖ cell_id ‖ artifact_hash ‖ genesis_id_hash. Spec §4."""
        return (
            DOMAIN_TAG
            + op.itob(Global.current_application_id.id)   # [Hermes#3] bind to THIS app
            + op.itob(cell_id)
            + artifact_hash
            + Global.genesis_hash          # A2: native network genesis (not a deploy-time arg)
        )

    # -------------------------------------------------------------------------
    # Owner transfer (controlled — defeats transient-custody inscription)
    # -------------------------------------------------------------------------

    @arc4.abimethod
    def update_owner(self, cell: Asset, new_owner: arc4.Address) -> None:
        """
        Reassign the controlling owner. Only the CURRENT controlling owner may do this, and
        only if the cell is NOT yet inscribed. This is the authorized way ownership moves for
        inscription purposes — distinct from raw ASA transfer, so flash-custody of the ASA
        does not confer inscription rights. [Hermes#2]
        """
        cid = cell.id
        assert cid in self.controlling_owner, "cell not registered"
        assert self.controlling_owner[cid] == Txn.sender.bytes, "only controlling owner"
        assert cid not in self.inscriptions, "already inscribed; owner frozen"
        self.controlling_owner[cid] = new_owner.bytes

    # -------------------------------------------------------------------------
    # Read-only verification helper (spec I3 — public re-verifiability)
    # -------------------------------------------------------------------------

    @arc4.abimethod(readonly=True)
    def get_inscription(self, cell_id: arc4.UInt64) -> InscriptionRecord:
        """Return the inscription record so anyone can re-verify off-chain. Spec I3.
        NOTE: subscripts the box directly; for a not-yet-inscribed cell this RAISES (per A3 a
        missing box read fails — it never returns a zero record). Callers treat a failed read as
        'not inscribed'. The controlling public key for re-verification is read separately from
        committed_pubkey[cell_id] (A9). This is the only unguarded box read in the contract."""
        return self.inscriptions[cell_id.native]

    # -------------------------------------------------------------------------
    # I5: NON-UPGRADABILITY  [Hermes#1] — the single most important control
    # -------------------------------------------------------------------------

    @arc4.baremethod(allow_actions=["UpdateApplication"])
    def on_update(self) -> None:
        """Reject ALL updates. The approval program can never be replaced. Spec I5/G2."""
        assert False, "contract is non-upgradable (I5)"  # noqa: B011

    @arc4.baremethod(allow_actions=["DeleteApplication"])
    def on_delete(self) -> None:
        """Reject deletion. Inscriptions are permanent. Spec I1/I5."""
        assert False, "contract is non-deletable (I1/I5)"  # noqa: B011
