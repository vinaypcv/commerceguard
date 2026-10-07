import hashlib
import json

import z3

POLICY = {
    "version": "synthetic-v1",
    "per_action_cents": 15000,
    "daily_cents": 20000,
    "window_days": 14,
    "currency": "USD",
}
POLICY_HASH = hashlib.sha256(json.dumps(POLICY, sort_keys=True).encode()).hexdigest()


def evaluate(request, ledger, daily_spend, *, timeout_ms=100):
    # Facts come from the ledger. A separate Z3 context per call supports concurrency.
    ctx = z3.Context()
    solver = z3.Solver(ctx=ctx)
    solver.set(timeout=timeout_ms)
    amount = z3.Int("amount_cents", ctx)
    solver.add(amount == request.amount_cents)
    remaining = ledger["paid_cents"] - ledger["refunded_cents"]
    rules = {
        "positive_amount": amount > 0,
        "action_cap": amount <= POLICY["per_action_cents"],
        "remaining_balance": amount <= remaining,
        "daily_cap": amount + daily_spend <= POLICY["daily_cents"],
        "refund_window": z3.BoolVal(0 <= ledger["age_days"] <= POLICY["window_days"], ctx),
        "unconsumed": z3.BoolVal(ledger["consumed"] == 0, ctx),
        "currency_match": z3.BoolVal(request.currency == ledger["currency"] == POLICY["currency"], ctx),
    }
    violations = []
    for name, rule in rules.items():
        solver.assert_and_track(rule, z3.Bool(name, ctx))
        concrete = z3.simplify(z3.substitute(rule, (amount, z3.IntVal(request.amount_cents, ctx))))
        if z3.is_false(concrete):
            violations.append(name)
    result = solver.check()
    eligible = not set(violations) & {"refund_window", "unconsumed", "currency_match"}
    ceiling = max(0, min(POLICY["per_action_cents"], remaining, POLICY["daily_cents"] - daily_spend))
    return {
        "allowed": result == z3.sat,
        "solver": str(result),
        "violations": violations,
        "unsat_core": [str(x) for x in solver.unsat_core()] if result == z3.unsat else [],
        "counterfactual_max_cents": ceiling if eligible and result != z3.unknown else 0,
        "policy_hash": POLICY_HASH,
        "policy_version": POLICY["version"],
    }
