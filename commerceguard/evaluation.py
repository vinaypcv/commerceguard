"""Small synthetic regression set, not a fraud or production generalization benchmark."""

import hashlib
import json
import platform
import statistics
import tempfile
import time
from pathlib import Path

from pydantic import ValidationError

from .models import Refund
from .policy import POLICY_HASH
from .service import Gateway
from .store import Store


def run():
    path = Path(__file__).resolve().parents[1] / "datasets" / "transactions.json"
    cases = json.loads(path.read_text())
    rows = []
    for case in cases:
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "eval.db")
            store.seed()
            payload = {
                "transaction_id": case.get("transaction_id", "tx_demo"),
                "amount_cents": case["amount"],
                "idempotency_key": "eval-" + case["id"],
                **case.get("extra", {}),
            }
            start = time.perf_counter()
            try:
                result = Gateway(store).refund("alice", Refund.model_validate(payload))["status"]
            except ValidationError:
                result = "INVALID"
            except LookupError:
                result = "UNAVAILABLE"
            elapsed = (time.perf_counter() - start) * 1000
            # Clearly labeled deliberately weak baseline: schema validation only.
            try:
                Refund.model_validate(payload)
                baseline = "COMMITTED"
            except ValidationError:
                baseline = "INVALID"
            rows.append(
                {
                    "id": case["id"],
                    "expected": case["expected"],
                    "actual": result,
                    "schema_only_baseline": baseline,
                    "elapsed_ms": round(elapsed, 3),
                }
            )
    times = sorted(row["elapsed_ms"] for row in rows)
    unsafe = [row for row in rows if row["expected"] != "COMMITTED"]
    return {
        "scope": "14 hand-authored synthetic cases; not live LLM evaluation",
        "python": platform.python_version(),
        "policy_hash": POLICY_HASH,
        "dataset_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "cases": len(rows),
        "correct": sum(row["actual"] == row["expected"] for row in rows),
        "unsafe_commits": sum(row["actual"] == "COMMITTED" for row in unsafe),
        "schema_only_unsafe_commits": sum(row["schema_only_baseline"] == "COMMITTED" for row in unsafe),
        "median_ms": statistics.median(times),
        "p95_ms": times[int(0.95 * (len(times) - 1))],
        "latency_scope": "includes validation, solver, SQLite transaction; excludes database initialization",
        "rows": rows,
    }
