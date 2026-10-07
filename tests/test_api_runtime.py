import pytest
from fastapi.testclient import TestClient

from commerceguard.api import create_app
from commerceguard.runtime import CircuitOpen, ReadRuntime, adapt_read_parameters
from commerceguard.store import Store


@pytest.fixture
def client(tmp_path):
    store = Store(tmp_path / "api.db")
    store.seed()
    return TestClient(create_app(store, "test-token-with-24-characters", "alice"))


HEADERS = {"Authorization": "Bearer test-token-with-24-characters"}
PAYLOAD = {"transaction_id": "tx_demo", "amount_cents": 100, "idempotency_key": "api-test-1"}


def test_api_end_to_end(client):
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 200
    assert client.post("/refunds", json=PAYLOAD).status_code == 401
    first = client.post("/refunds", json=PAYLOAD, headers=HEADERS)
    assert first.json()["status"] == "COMMITTED"
    assert client.post("/refunds", json=PAYLOAD, headers=HEADERS).json() == first.json()
    assert client.post("/refunds", json={**PAYLOAD, "amount_cents": 101}, headers=HEADERS).status_code == 409
    assert client.get("/ledger/tx_demo", headers=HEADERS).json()["refunded_cents"] == 100
    assert client.get("/audit/verify", headers=HEADERS).json()["valid"]


def test_api_spoof_and_bad_json(client):
    assert client.get("/ledger/tx_other", headers=HEADERS).status_code == 404
    assert client.post("/refunds", json={**PAYLOAD, "owner": "bob"}, headers=HEADERS).status_code == 422
    assert (
        client.post(
            "/refunds", content="{", headers={**HEADERS, "Content-Type": "application/json"}
        ).status_code
        == 422
    )
    assert client.post("/refunds", json={**PAYLOAD, "amount_cents": True}, headers=HEADERS).status_code == 422


def test_api_evidence(client):
    result = client.post(
        "/evidence/triage",
        json={
            "transaction_id": "tx_demo",
            "extraction": {
                "transaction_id": "tx_demo",
                "amount_cents": 30000,
                "currency": "USD",
                "readable": True,
            },
        },
        headers=HEADERS,
    )
    assert result.json()["route"] == "MATCHED_FOR_REVIEW"
    assert client.get("/reviews", headers=HEADERS).json()[0]["id"] == result.json()["review_id"]
    assert client.get("/ledger/tx_demo", headers=HEADERS).json()["refunded_cents"] == 0


def test_runtime_retries_only_transient_reads(tmp_path):
    store = Store(tmp_path / "runtime.db")
    runtime = ReadRuntime(store)
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise TimeoutError()
        return {"account_id": "alice"}

    assert runtime.read(flaky) == {"account_id": "alice"}
    with store.connect() as db:
        states = [row[0] for row in db.execute("SELECT state FROM traces ORDER BY seq")]
    assert states == ["CONTINUE", "REFLECT", "REPLAN", "CONTINUE", "VERIFY"]


def test_circuit_recovery_and_permanent_error(tmp_path):
    now = [0]
    runtime = ReadRuntime(Store(tmp_path / "runtime.db"), threshold=1, cooldown=10, clock=lambda: now[0])

    def fail():
        raise TimeoutError()

    with pytest.raises(TimeoutError):
        runtime.read(fail)
    with pytest.raises(CircuitOpen):
        runtime.read(lambda: "must not run")
    now[0] = 11
    assert runtime.read(lambda: "recovered") == "recovered"
    calls = []

    def permanent():
        calls.append(1)
        raise LookupError("unknown identity")

    with pytest.raises(LookupError):
        runtime.read(permanent)
    assert len(calls) == 1


def test_schema_adapter_preserves_identity():
    assert adapt_read_parameters({"user_id": "alice"}) == {"account_id": "alice"}
    with pytest.raises(ValueError):
        adapt_read_parameters({"user_id": "alice", "account_id": "bob"})
