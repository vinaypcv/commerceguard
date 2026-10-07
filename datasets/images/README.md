# Synthetic image fixtures

All images are generated examples, not Sony documents or real payments.

- `receipt_clean.png`: expected tx_demo, 30000 cents, USD; match is not authenticity.
- `receipt_mismatch.png`: expected tx_demo, 10000 cents, USD; ledger mismatch.
- `receipt_injection.png`: clean transaction fields plus untrusted instructions; extraction must not become authorization.
- `receipt_blurred.png`: degraded rendering; readability is model-dependent, not a fixed accuracy claim.

These assets have not been evaluated with a live vision model. They test extraction separately from the deterministic receipt JSON fixtures. Keep a held-out dataset for measuring quality.
