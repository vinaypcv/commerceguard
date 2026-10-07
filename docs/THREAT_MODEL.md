# Threat model and boundaries

| Threat | v0.1.0 behavior | Remaining boundary |
|---|---|---|
| Model invents premium status or account age | Proposal schema rejects eligibility fields; reads ledger | Ledger ingest/admin accuracy trusted |
| Model asks for another user's refund | Server principal scopes transaction lookup | Single-principal API configuration; production OIDC/RBAC pending |
| JSON coercion, booleans as numbers, negative cents | Strict Pydantic validation, extra fields forbidden | Body-size/rate limiting not implemented |
| Duplicate/replayed request | Persistent owner+key result; changed payload conflict | Stable key selection still required; business caps limit new-key duplicates |
| Parallel requests race a balance/daily cap | SQLite BEGIN IMMEDIATE covers check and mutation | Single-database bottleneck; not a distributed transaction |
| Crash before commit | Transaction rollback across all monetary records and audit | External provider outbox/reconciliation not implemented |
| Response lost after commit | Same-key retry returns committed result | Caller must retain/reuse the operation key |
| Prompt injection in an image | Output schema and ledger comparison; no image-driven payment action | Prompt instructions alone do not solve injection or authenticity |
| Tampered audit event | Hash chain consistency check fails | Full rewrite or tail deletion by DB admin can evade; external anchoring needed |
| Missing identity | Missing principal config fails startup; missing/foreign ledger record fails | Local OS user controls stdio environment |
| Dependency timeout | At most two read attempts, process-local breaker, trace to disk | Caller must enforce its own I/O timeout; no arbitrary-call interruption |
| Schema migration | Explicit narrow field adapter preserves identity | Adapter is a tested migration utility, not auto-discovery wired to a live source |
| Unreadable receipt | Re-upload route; no adverse financial decision | No authentic fraud detection; human review needed |
| Solver unknown | Denied, no funds changed | Encoded rules may still omit real-world requirements |

Only synthetic information belongs in this demonstration. API auth failures and schema failures are returned by the framework but not written to the monetary audit chain; comprehensive security telemetry is future work. Review queue items are pending records, not an implemented multi-role case-management system. SQLite file permissions, backups, and local operating-system access remain the operator's responsibility.
