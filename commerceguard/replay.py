"""Historical snapshot replay, never writes a decision or changes a balance."""

import json

from .policy import POLICY


def replay(store, proposed_cap_cents):
    if type(proposed_cap_cents) is not int or proposed_cap_cents <= 0:
        raise ValueError("Proposed cap must be positive integer cents")
    if not store.verify_audit()["valid"]:
        raise ValueError("Audit integrity check failed")
    rows = []
    with store.connect() as db:
        for row in db.execute("SELECT seq,payload FROM audit ORDER BY seq"):
            event = json.loads(row["payload"])
            if "decision" not in event:
                continue
            facts = event["facts"]
            amount = event["request"]["amount_cents"]
            allowed = (
                0 < amount <= proposed_cap_cents
                and amount <= facts["paid_cents"] - facts["refunded_cents"]
                and event["daily_spend"] + amount <= POLICY["daily_cents"]
                and 0 <= facts["age_days"] <= POLICY["window_days"]
                and facts["consumed"] == 0
                and event["request"]["currency"] == facts["currency"] == POLICY["currency"]
            )
            rows.append(
                {
                    "seq": row["seq"],
                    "original_allowed": event["decision"]["allowed"],
                    "proposed_allowed": allowed,
                    "changed": allowed != event["decision"]["allowed"],
                }
            )
    return {
        "mode": "historical snapshots; not a sequential alternate-history simulation",
        "proposed_cap_cents": proposed_cap_cents,
        "changed": sum(row["changed"] for row in rows),
        "decisions": rows,
    }
