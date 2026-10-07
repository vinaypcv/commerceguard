# Executed verification

Prepared 2026-10-07T05:56:03.132369+00:00 on Linux, Python 3.12.14.

| Check | Observed result |
|---|---|
| Ruff lint and format | Passed |
| Pytest | 39 passed; one upstream Starlette/httpx deprecation warning |
| Property test | 150 generated policy examples compared with an independent arithmetic oracle |
| MCP | Real stdio subprocess initialization, tool discovery, account isolation, refund and replay passed |
| HTTP | Live Uvicorn server: commit, replay, account isolation and audit smoke passed |
| Synthetic transaction evaluation | 14/14 expected outcomes |
| Unsafe commits in that fixed suite | 0 for gateway; 4 for deliberately weak schema-only baseline |
| Race / crash | Concurrent same-key replay, concurrent daily cap, injected pre-commit rollback passed |
| Offline demo | Commit, identical replay, daily-cap denial, review-only receipt, valid audit |

Artifacts: `results/pytest.txt`, `results/http-smoke.txt`, `results/evaluation.json`, `results/demo.json`, and `results/source-sha256.json`.

The evaluation contains 14 hand-authored cases. Most cases fail early validation, so aggregate latency is not representative of successful refunds. Machine-local timing is included in JSON solely to make this run inspectable. No load, production traffic, or live model quality claim is made.

**Not executed here:** Windows VS Code commands; GitHub creation/push/CI; live Gemini requests; image OCR accuracy; Docker or cloud deployment; actual payment-provider integration. The CI workflow and optional model adapter are provided, not represented as live-service verification.

Constraints record tested direct/transport dependency versions. They are not a cryptographically locked complete environment. All data and policies are synthetic.
