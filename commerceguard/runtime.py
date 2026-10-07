"""Bounded read recovery. No guessed identities, no mutation retries here."""

import time
import uuid
from threading import Lock


class CircuitOpen(Exception):
    pass


class ReadRuntime:
    def __init__(self, store, threshold=3, cooldown=10, clock=time.monotonic):
        self.store = store
        self.threshold = threshold
        self.cooldown = cooldown
        self.clock = clock
        self.failures = 0
        self.opened = None
        self.lock = Lock()

    def trace(self, run_id, state, detail):
        with self.store.connect() as db:
            db.execute("INSERT INTO traces(run_id,state,detail) VALUES (?,?,?)", (run_id, state, detail))

    def read(self, operation):
        run_id = str(uuid.uuid4())
        # Serialized half-open probe for this local runtime instance.
        with self.lock:
            if self.opened is not None and self.clock() - self.opened < self.cooldown:
                self.trace(run_id, "ESCALATE", "circuit_open")
                raise CircuitOpen("Read dependency temporarily unavailable")
            for attempt in range(2):
                self.trace(run_id, "CONTINUE", f"attempt={attempt + 1}")
                try:
                    result = operation()
                except (TimeoutError, ConnectionError):
                    self.trace(run_id, "REFLECT", "transient_read_failure")
                    if attempt == 0:
                        self.trace(run_id, "REPLAN", "retry_same_identity_same_parameters")
                        continue
                    self.failures += 1
                    if self.failures >= self.threshold:
                        self.opened = self.clock()
                    self.trace(run_id, "ESCALATE", "retry_budget_exhausted")
                    raise
                except Exception:
                    self.trace(run_id, "ESCALATE", "non_retryable_failure")
                    raise
                self.failures = 0
                self.opened = None
                self.trace(run_id, "VERIFY", "read_completed")
                return result


def adapt_read_parameters(payload):
    """Explicit v1->v2 contract migration; never fuzzy exception-string repair."""
    if set(payload) == {"user_id"}:
        return {"account_id": payload["user_id"]}
    if set(payload) == {"account_id"}:
        return dict(payload)
    raise ValueError("Unsupported or conflicting schema")
