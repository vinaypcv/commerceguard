"""Run against an already-running local API, using this terminal's COMMERCE_TOKEN."""

import os
import uuid

import httpx

with httpx.Client(
    base_url="http://127.0.0.1:8000",
    trust_env=False,
    timeout=10,
    headers={"Authorization": "Bearer " + os.environ["COMMERCE_TOKEN"]},
) as client:
    assert client.get("/health").status_code == 200
    body = {"transaction_id": "tx_demo", "amount_cents": 1, "idempotency_key": "smoke-" + uuid.uuid4().hex}
    first = client.post("/refunds", json=body)
    first.raise_for_status()
    assert first.json()["status"] == "COMMITTED", first.text
    assert client.post("/refunds", json=body).json() == first.json()
    assert client.get("/ledger/tx_other").status_code == 404
    assert client.get("/audit/verify").json()["valid"]
print("HTTP smoke passed: commit, replay, account isolation, audit")
