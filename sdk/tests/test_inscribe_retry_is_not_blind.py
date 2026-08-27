"""inscribe() must not blind-retry a WRITE-ONCE on-chain call.

Found 2026-08-16 (register TCE-75). The submit path used a bare `except Exception:` and
immediately re-submitted with different fee parameters.

`inscribe` is write-once (invariant I1; the contract asserts `cid not in inscriptions`), so it is
NOT idempotent. Anything that raises AFTER submission - a confirmation timeout, a dropped
connection - leaves a successful inscription on chain while the client believes it failed. The
retry then submits again, the contract correctly rejects it as already inscribed, and the caller
is handed a FAILURE for an operation that SUCCEEDED. For a write-once record that is exactly the
wrong way round.

Secondarily, the two strategies differ ONLY in fee handling, so a rejected signature or a wrong
controlling owner fails identically both times - the retry wastes a round trip and surfaces the
SECOND exception, discarding the first and usually more informative one.

These tests use fakes throughout: no node, no Falcon library, no algokit_utils, no network. That
is deliberate. The original gap survived because every test that could have caught it needed
something the matrix legs did not have.
"""

from __future__ import annotations

import pytest

from trelyan_pq import inscription


class _Sender:
    """Stands in for `client.app.send`, recording every inscribe attempt."""

    def __init__(self, first_raises: bool, already_inscribed: bool) -> None:
        self.calls = 0
        self._first_raises = first_raises
        self._already = already_inscribed

    def inscribe(self, **kw: object) -> object:
        self.calls += 1
        if self.calls == 1 and self._first_raises:
            raise RuntimeError("confirmation timed out (the txn may or may not have landed)")
        return object()

    def read_inscription(self) -> object:
        if self._already:
            return object()
        # Contract AUDIT-NOTE A3: a missing box READ raises; it never returns a zero record.
        raise RuntimeError("box not found")


class _AlgoAmount:
    @staticmethod
    def from_micro_algo(n: int) -> int:
        return n


class _Au:
    """Only the three names inscribe() touches."""

    AlgoAmount = _AlgoAmount
    CommonAppCallParams = staticmethod(lambda **kw: kw)
    SendParams = staticmethod(lambda **kw: kw)


def _client(monkeypatch, *, first_raises: bool, already_inscribed: bool):
    c = inscription.TrelyanInscriptionClient.__new__(inscription.TrelyanInscriptionClient)
    sender = _Sender(first_raises, already_inscribed)

    class _App:
        send = sender
        app_id = 1        # TrelyanInscriptionClient.app_id proxies to this

    c.app = _App()
    c.deployer = type("D", (), {"address": "A" * 58})()
    c.signer = type("S", (), {"sign": staticmethod(lambda pk, m: b"\x0b" * 64)})()

    monkeypatch.setattr(inscription, "_algokit", lambda: _Au)
    monkeypatch.setattr(inscription, "build_message", lambda *a, **k: b"\x00" * 102)
    monkeypatch.setattr(c, "network_genesis_hash", lambda: b"\x00" * 32, raising=False)
    monkeypatch.setattr(c, "get_inscription", lambda cell_id: sender.read_inscription(),
                        raising=False)
    return c, sender


def test_no_retry_when_the_first_attempt_actually_landed(monkeypatch):
    """The dangerous case: the call raised, but the inscription EXISTS on chain."""
    c, sender = _client(monkeypatch, first_raises=True, already_inscribed=True)
    c.inscribe(cell_id=7, artifact_hash=b"\x01" * 32, privkey=b"\x02" * 32)
    assert sender.calls == 1, (
        "inscribe was re-submitted for a cell that is ALREADY inscribed. The contract rejects it "
        "as write-once, so the caller receives a failure for an operation that succeeded."
    )


def test_the_fee_fallback_still_runs_when_nothing_landed(monkeypatch):
    """The fallback exists for inner-transaction fee coverage and must stay reachable."""
    c, sender = _client(monkeypatch, first_raises=True, already_inscribed=False)
    c.inscribe(cell_id=7, artifact_hash=b"\x01" * 32, privkey=b"\x02" * 32)
    assert sender.calls == 2, "the fee fallback must still run when the cell is NOT inscribed"


def test_the_happy_path_submits_exactly_once(monkeypatch):
    c, sender = _client(monkeypatch, first_raises=False, already_inscribed=False)
    c.inscribe(cell_id=7, artifact_hash=b"\x01" * 32, privkey=b"\x02" * 32)
    assert sender.calls == 1


def test_a_short_artifact_hash_never_reaches_the_chain(monkeypatch):
    c, sender = _client(monkeypatch, first_raises=False, already_inscribed=False)
    with pytest.raises(ValueError):
        c.inscribe(cell_id=7, artifact_hash=b"\x01" * 31, privkey=b"\x02" * 32)
    assert sender.calls == 0, "a malformed hash must be rejected before any submission"
