"""Local stdio server. Process environment establishes the principal."""

import os

from mcp.server.fastmcp import FastMCP

from .models import Evidence, Refund
from .runtime import ReadRuntime
from .service import Gateway
from .store import Store


def build_server():
    owner = os.environ.get("COMMERCE_OWNER")
    if not owner:
        raise RuntimeError("COMMERCE_OWNER required; tools cannot select their own identity")
    store = Store(os.getenv("COMMERCE_DB", "data/commerce.db"))
    gateway = Gateway(store)
    runtime = ReadRuntime(store)
    server = FastMCP("CommerceGuard")

    @server.tool()
    def get_transaction(transaction_id: str) -> dict:
        """Read a synthetic transaction belonging to the process principal."""

        def read():
            with store.connect() as db:
                return store.ledger(db, transaction_id, owner)

        return runtime.read(read)

    @server.tool()
    def request_refund(request: Refund) -> dict:
        """Execute a policy-checked synthetic refund. Reuse the key on uncertain retries."""
        return gateway.refund(owner, request)

    @server.tool()
    def triage_receipt(evidence: Evidence) -> dict:
        """Compare extracted evidence. Never authorizes money or verifies authenticity."""
        return gateway.triage(owner, evidence)

    return server


if __name__ == "__main__":
    build_server().run(transport="stdio")
