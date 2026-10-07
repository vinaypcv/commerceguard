import hashlib
import json

from .models import Refund
from .policy import evaluate
from .store import canonical, utc_day


class Conflict(Exception):
    pass


class Gateway:
    def __init__(self, store):
        self.store = store

    def refund(self, owner: str, request: Refund, *, fail_before_commit=False):
        fingerprint = hashlib.sha256(canonical(request.model_dump()).encode()).hexdigest()
        with self.store.connect() as db:
            # Serialize check + ledger mutation + idempotency record + audit in one transaction.
            db.execute("BEGIN IMMEDIATE")
            cached = db.execute(
                "SELECT * FROM decisions WHERE owner=? AND idem=?", (owner, request.idempotency_key)
            ).fetchone()
            if cached:
                if cached["fingerprint"] != fingerprint:
                    raise Conflict("Idempotency key reused with different payload")
                return json.loads(cached["result"])
            day = utc_day()
            facts = self.store.ledger(db, request.transaction_id, owner, today=day)
            spent = db.execute(
                "SELECT COALESCE(SUM(amount_cents),0) FROM refunds WHERE owner=? AND day=?",
                (owner, day),
            ).fetchone()[0]
            decision = evaluate(request, facts, spent)
            result = {
                **decision,
                "status": "COMMITTED" if decision["allowed"] else "DENIED",
                "transaction_id": request.transaction_id,
                "amount_cents": request.amount_cents,
            }
            if decision["allowed"]:
                db.execute(
                    "UPDATE ledger SET refunded_cents=refunded_cents+? WHERE transaction_id=?",
                    (request.amount_cents, request.transaction_id),
                )
                db.execute(
                    "INSERT INTO refunds VALUES (?, ?, ?, ?)",
                    (owner, day, request.amount_cents, request.transaction_id),
                )
            result["audit_digest"] = self.store.append_audit(
                db,
                {
                    "owner": owner,
                    "request": request.model_dump(),
                    "facts": facts,
                    "daily_spend": spent,
                    "decision": result.copy(),
                },
            )
            db.execute(
                "INSERT INTO decisions VALUES (?, ?, ?, ?)",
                (owner, request.idempotency_key, fingerprint, canonical(result)),
            )
            if fail_before_commit:
                raise RuntimeError("Injected crash before commit")
            return result

    def triage(self, owner, evidence):
        with self.store.connect() as db:
            facts = self.store.ledger(db, evidence.transaction_id, owner)
        e = evidence.extraction
        if not e.readable:
            route = "REQUEST_REUPLOAD"
        elif (e.transaction_id, e.amount_cents, e.currency) != (
            facts["transaction_id"],
            facts["paid_cents"],
            facts["currency"],
        ):
            route = "HUMAN_REVIEW"
        else:
            route = "MATCHED_FOR_REVIEW"
        # A match is not authenticity, and NEVER creates a refund.
        result = {"route": route, "financial_action": False, "authenticity_verified": False}
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            cursor = db.execute(
                "INSERT INTO reviews(owner,route,evidence) VALUES (?,?,?)",
                (owner, route, canonical(evidence.model_dump())),
            )
            result["review_id"] = cursor.lastrowid
            self.store.append_audit(db, {"owner": owner, "evidence": evidence.model_dump(), "triage": result})
        return result
