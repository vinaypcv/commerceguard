import argparse
import json
import os
import tempfile
from pathlib import Path

from .models import Evidence, Receipt, Refund
from .service import Gateway
from .store import Store


def main():
    parser = argparse.ArgumentParser(description="CommerceGuard synthetic commerce lab")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("seed")
    sub.add_parser("demo")
    sub.add_parser("audit")
    replay_parser = sub.add_parser("replay")
    replay_parser.add_argument("--cap-cents", type=int, required=True)
    ev = sub.add_parser("evaluate")
    ev.add_argument("--out", default="results/evaluation.json")
    proposal = sub.add_parser("propose")
    proposal.add_argument("text")
    extract = sub.add_parser("extract")
    extract.add_argument("image")
    args = parser.parse_args()
    if args.command == "evaluate":
        from .evaluation import run

        result = run()
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(result, indent=2), encoding="utf-8")
    elif args.command in {"propose", "extract"}:
        from . import gemini

        result = (
            gemini.propose(args.text) if args.command == "propose" else gemini.extract(args.image)
        ).model_dump()
    elif args.command == "demo":
        with tempfile.TemporaryDirectory() as folder:
            store = Store(Path(folder) / "demo.db")
            store.seed()
            gateway = Gateway(store)
            request = Refund(transaction_id="tx_demo", amount_cents=12000, idempotency_key="demo-0001")
            approved = gateway.refund("alice", request)
            replay = gateway.refund("alice", request)
            denied = gateway.refund("alice", request.model_copy(update={"idempotency_key": "demo-0002"}))
            triage = gateway.triage(
                "alice",
                Evidence(
                    transaction_id="tx_demo",
                    extraction=Receipt(
                        transaction_id="tx_demo", amount_cents=30000, currency="USD", readable=True
                    ),
                ),
            )
            result = {
                "first": approved,
                "replay_identical": approved == replay,
                "second": denied,
                "receipt": triage,
                "audit": store.verify_audit(),
            }
    else:
        store = Store(os.getenv("COMMERCE_DB", "data/commerce.db"))
        if args.command == "seed":
            store.seed()
            result = {"seeded": True, "database": store.path, "owner": "alice", "transaction": "tx_demo"}
        elif args.command == "replay":
            from .replay import replay

            result = replay(store, args.cap_cents)
        else:
            result = store.verify_audit()
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
