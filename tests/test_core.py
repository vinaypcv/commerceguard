import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from commerceguard.models import Evidence, Receipt, Refund
from commerceguard.policy import evaluate
from commerceguard.service import Conflict, Gateway
from commerceguard.store import Store


@pytest.fixture
def store(tmp_path):
    store = Store(tmp_path / "test.db")
    store.seed()
    return store


def request(amount=12000, key="test-0001"):
    return Refund(transaction_id="tx_demo", amount_cents=amount, idempotency_key=key)


def test_replay_survives_restart(store):
    first = Gateway(store).refund("alice", request())
    assert Gateway(Store(store.path)).refund("alice", request()) == first
    with store.connect() as db:
        assert store.ledger(db, "tx_demo", "alice")["refunded_cents"] == 12000
        assert db.execute("SELECT COUNT(*) FROM refunds").fetchone()[0] == 1
    assert store.verify_audit()["events"] == 1


def test_conflicting_key(store):
    gateway = Gateway(store)
    gateway.refund("alice", request())
    with pytest.raises(Conflict):
        gateway.refund("alice", request(100))


def test_rollback_and_retry(store):
    with pytest.raises(RuntimeError):
        Gateway(store).refund("alice", request(), fail_before_commit=True)
    with store.connect() as db:
        assert store.ledger(db, "tx_demo", "alice")["refunded_cents"] == 0
        assert db.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 0
    assert store.verify_audit()["events"] == 0
    assert Gateway(store).refund("alice", request())["status"] == "COMMITTED"


def test_concurrent_daily_cap(store):
    def work(i):
        return Gateway(store).refund("alice", request(12000, f"parallel-{i}"))["status"]

    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(work, range(6)))
    assert results.count("COMMITTED") == 1
    assert results.count("DENIED") == 5
    assert store.verify_audit()["valid"]


def test_concurrent_same_key(store):
    with ThreadPoolExecutor(max_workers=6) as executor:
        results = list(executor.map(lambda _: Gateway(store).refund("alice", request()), range(6)))
    assert all(result == results[0] for result in results)
    assert store.verify_audit()["events"] == 1


def test_tamper_detected(store):
    Gateway(store).refund("alice", request())
    with store.connect() as db:
        db.execute("UPDATE audit SET payload='{}' WHERE seq=1")
    assert not store.verify_audit()["valid"]


CASES = json.loads((Path(__file__).parents[1] / "datasets/transactions.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["id"])
def test_dataset(store, case):
    payload = {
        "transaction_id": case.get("transaction_id", "tx_demo"),
        "amount_cents": case["amount"],
        "idempotency_key": "case-" + case["id"],
        **case.get("extra", {}),
    }
    try:
        actual = Gateway(store).refund("alice", Refund.model_validate(payload))["status"]
    except ValidationError:
        actual = "INVALID"
    except LookupError:
        actual = "UNAVAILABLE"
    assert actual == case["expected"]


RECEIPTS = json.loads((Path(__file__).parents[1] / "datasets/receipts.json").read_text())


@pytest.mark.parametrize("case", RECEIPTS, ids=lambda case: case["id"])
def test_receipts_cannot_move_money(store, case):
    extraction = Receipt.model_validate({k: v for k, v in case.items() if k not in {"id", "expected"}})
    result = Gateway(store).triage("alice", Evidence(transaction_id="tx_demo", extraction=extraction))
    assert result["route"] == case["expected"]
    assert result["financial_action"] is False
    with store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM refunds").fetchone()[0] == 0


@given(
    amount=st.integers(1, 1000000),
    remaining=st.integers(0, 50000),
    spent=st.integers(0, 25000),
    age=st.integers(-1, 30),
    consumed=st.integers(0, 1),
)
@settings(max_examples=150, deadline=None)
def test_solver_matches_independent_arithmetic_oracle(amount, remaining, spent, age, consumed):
    facts = {
        "paid_cents": remaining,
        "refunded_cents": 0,
        "age_days": age,
        "consumed": consumed,
        "currency": "USD",
    }
    expected = amount <= min(15000, remaining, 20000 - spent) and 0 <= age <= 14 and consumed == 0
    assert evaluate(request(amount), facts, spent)["allowed"] == expected


def test_counterfactual_does_not_silently_reduce_request(store):
    result = Gateway(store).refund("alice", request(16000))
    assert result["status"] == "DENIED"
    assert result["counterfactual_max_cents"] == 15000
    assert "action_cap" in result["unsat_core"]


def test_policy_replay_read_only(store):
    from commerceguard.replay import replay

    Gateway(store).refund("alice", request(12000))
    before = store.verify_audit()
    report = replay(store, 10000)
    assert report["changed"] == 1
    assert not report["decisions"][0]["proposed_allowed"]
    assert store.verify_audit() == before
    with store.connect() as db:
        assert store.ledger(db, "tx_demo", "alice")["refunded_cents"] == 12000


def test_unknown_solver_fails_closed(monkeypatch):
    import z3

    monkeypatch.setattr(z3.Solver, "check", lambda self: z3.unknown)
    facts = {"paid_cents": 30000, "refunded_cents": 0, "age_days": 0, "consumed": 0, "currency": "USD"}
    result = evaluate(request(), facts, 0)
    assert not result["allowed"]
    assert result["solver"] == "unknown"
    assert result["counterfactual_max_cents"] == 0
