import os
import secrets
import sqlite3
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .models import Evidence, Refund
from .runtime import CircuitOpen, ReadRuntime
from .service import Conflict, Gateway
from .store import Store


def create_app(store=None, token=None, owner=None):
    store = store or Store(os.getenv("COMMERCE_DB", "data/commerce.db"))
    token = token or os.getenv("COMMERCE_TOKEN")
    owner = owner or os.getenv("COMMERCE_OWNER")
    if not token or len(token) < 24 or not owner:
        raise RuntimeError("Set COMMERCE_TOKEN (24+ characters) and COMMERCE_OWNER")
    app = FastAPI(title="CommerceGuard", version="0.1.0")
    gateway = Gateway(store)
    runtime = ReadRuntime(store)
    bearer = HTTPBearer(auto_error=False)

    def identity(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
        if credentials is None or not secrets.compare_digest(credentials.credentials, token):
            raise HTTPException(401, "Invalid bearer credential")
        return owner

    @app.get("/health")
    def health():
        return {"status": "ok", "mode": "synthetic-local-ledger"}

    @app.get("/ready")
    def ready():
        with store.connect() as db:
            db.execute("SELECT 1 FROM ledger LIMIT 1")
        return {"ready": True}

    @app.get("/ledger/{transaction_id}")
    def ledger(transaction_id: str, principal: Annotated[str, Depends(identity)]):
        try:

            def read():
                with store.connect() as db:
                    return store.ledger(db, transaction_id, principal)

            return runtime.read(read)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except (CircuitOpen, TimeoutError, ConnectionError) as exc:
            raise HTTPException(503, "Dependency unavailable") from exc

    @app.post("/refunds")
    def refund(request: Refund, principal: Annotated[str, Depends(identity)]):
        try:
            return gateway.refund(principal, request)
        except Conflict as exc:
            raise HTTPException(409, str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except sqlite3.OperationalError as exc:
            raise HTTPException(503, "Ledger busy; retry with the SAME idempotency key") from exc

    @app.post("/evidence/triage")
    def triage(evidence: Evidence, principal: Annotated[str, Depends(identity)]):
        try:
            return gateway.triage(principal, evidence)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/audit/verify")
    def audit(principal: Annotated[str, Depends(identity)]):
        return store.verify_audit()

    @app.get("/reviews")
    def reviews(principal: Annotated[str, Depends(identity)]):
        with store.connect() as db:
            return [
                dict(row)
                for row in db.execute(
                    "SELECT id,route,status FROM reviews WHERE owner=? ORDER BY id DESC LIMIT 100",
                    (principal,),
                )
            ]

    return app
