# Design decisions

## Start with a local ledger

The attached brief contains conceptual demonstrations, not a complete transactional commerce system. CommerceGuard implements one local database end to end so check/commit/audit boundaries can be exercised without hardware, Docker, or payment credentials. Wallet top-ups and subscription changes are intentionally outside v0.1.0; each needs different state transitions and policies.

## Use integer cents

Amounts are USD minor units, never binary floating point and never int-cast truncation. Currency is explicit. A multi-currency extension must use currency-specific scale metadata and trusted exchange-rate inputs; changing the currency literal alone is insufficient.

## Identity is an input from the application, not the agent

The API bearer credential maps to one configured owner. MCP stdio tools inherit a process principal. The proposal cannot select an owner. Database queries bind that principal and use parameterized SQL. The Python service layer is trusted application code, not a standalone authentication boundary.

## Verification and execution must share a consistency boundary

A standalone Z3 check followed later by a balance update leaves a race. `BEGIN IMMEDIATE` acquires a SQLite write transaction before reading state, so all writers using this service serialize. Ledger update, daily spend, decision cache, and audit append commit together. Rejected policy decisions are cached too: reusing a denied key remains denied, even on a different day; use a new key for a deliberately new operation.

A single UTC date is captured for each refund transaction. Refund timing and age use that date. Replaying the same key on a later day returns the original result. The seed function creates rows only if absent; it never silently resets historical balances.

## Keep probabilistic extraction away from authorization

Gemini proposes structured data, with a 20-second client timeout. Output is validated again locally. Receipt comparison produces pending review, mismatch review, or re-upload; it does not assert authenticity or issue funds. This avoids interpreting a plausible screenshot as authoritative purchase evidence.

## Recovery must preserve identity and semantics

Only transient read failures are retried, at most twice, with identical parameters. Unknown identity is a permanent error. The schema adapter recognizes one explicit migration and rejects ambiguous payloads. The circuit breaker is thread-safe within one runtime process, not distributed across workers.

## Explain denials without silently changing requests

Responses contain violated rule names, an unsat core, and an advisory maximum amount computed from the same facts. The maximum is not a promise that a later request will succeed; state may change. No modified refund is submitted automatically.

## Record bounded evidence

Audit events include timestamp, input, fact snapshot, policy hash, and result. Hash linking supports consistency checks. The read-only replay utility compares a proposed cap against historical snapshots; it uses the other current v1 rules and is not a general policy-version migration engine. Changing those rules requires updating replay semantics and evaluation fixtures together.

## Source layout

- `commerceguard/models.py`: strict untrusted-data contracts.
- `commerceguard/policy.py`: symbolic constraints and explanations.
- `commerceguard/store.py`: ledger, audit, review queue, traces.
- `commerceguard/service.py`: atomic gateway and triage.
- `commerceguard/api.py`: authenticated HTTP entrypoints.
- `commerceguard/mcp_server.py`: real local MCP transport.
- `commerceguard/runtime.py`: bounded read recovery and schema adapter.
- `commerceguard/gemini.py`: optional structured proposal / image extraction.
- `commerceguard/replay.py`: read-only historical analysis.
- `commerceguard/evaluation.py`: synthetic case evaluation.
- `datasets/`: explicit expected outcomes.
- `tests/`: regression, arithmetic oracle, concurrency, API, MCP, model contract tests.
