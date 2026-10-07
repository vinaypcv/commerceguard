# Run CommerceGuard in VS Code on Windows

This guide takes you from the downloaded ZIP to a local working API, optional Gemini extraction, and a GitHub repository. The package has been executed in a Linux Python 3.12 environment. The Windows steps and GitHub Actions matrix are provided for you to run; Windows execution is not claimed here.

## 1. Install tools if missing

Use PowerShell. You need Python 3.12, VS Code, Git, and (for later publishing) GitHub CLI. Skip installations you already have.

```powershell
winget install -e --id Python.Python.3.12
winget install -e --id Microsoft.VisualStudioCode
winget install -e --id Git.Git
winget install -e --id GitHub.cli
```

Restart VS Code/PowerShell after installation so PATH refreshes.

```powershell
py -3.12 --version
code --version
git --version
gh --version
```

## 2. Extract and open the project

Download `CommerceGuard_E2E.zip` from the chat into Downloads. The archive contains a top-level `commerceguard` folder. Use a new destination to avoid mixing with another project.

```powershell
New-Item -ItemType Directory -Force C:\AIProjects | Out-Null
Expand-Archive -Path "$env:USERPROFILE\Downloads\CommerceGuard_E2E.zip" -DestinationPath C:\AIProjects
Set-Location C:\AIProjects\commerceguard
code .
```

In VS Code, open **Terminal → New Terminal**, select PowerShell, and verify `Get-Location` points to the folder containing `pyproject.toml`. Install the recommended Python extension when VS Code prompts.

## 3. Create the environment

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -c constraints-tested.txt -e ".[dev,gemini]"
```

Use **Ctrl+Shift+P → Python: Select Interpreter → `.venv\Scripts\python.exe`**. Commands use the interpreter directly; no PowerShell activation-policy change is needed.

`constraints-tested.txt` pins tested direct/transport versions, not every transitive dependency. Run `python -m pip freeze` in this venv if you need a complete environment snapshot. Python 3.12 is preferred over the newer interpreter you may use for other projects, to reduce native-wheel compatibility surprises.

## 4. Run the verification gate

```powershell
.\.venv\Scripts\python.exe -m ruff check commerceguard tests scripts
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m commerceguard demo
.\.venv\Scripts\python.exe -m commerceguard evaluate
Get-Content results\evaluation.json
```

Expected: 39 tests pass; the offline demo commits the first request, returns an identical replay, denies the second independent request for exceeding the daily cap, and queues a matching receipt without moving money. Evaluation returns `correct: 14`, `unsafe_commits: 0`, `schema_only_unsafe_commits: 4`. These are bounded synthetic results, not real-world success rates.

The demo and evaluation each use temporary databases and can be rerun. The pytest suite includes a real MCP subprocess, concurrent refund attempts, injected rollback, audit corruption, schema attacks, and 150 generated policy examples. One Starlette/httpx deprecation warning may appear with the tested versions; it does not fail the tests.

## 5. Seed the persistent local ledger and run the API

In Terminal A:

```powershell
$env:COMMERCE_DB = "data/commerce.db"
$env:COMMERCE_OWNER = "alice"
$env:COMMERCE_TOKEN = (& .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(32))")
.\.venv\Scripts\python.exe -m commerceguard seed
.\.venv\Scripts\python.exe -m uvicorn commerceguard.api:create_app --factory --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/docs. Health is at http://127.0.0.1:8000/health. The API is running on YOUR machine after these commands, not on the chat workspace. Keep Terminal A running.

To use Swagger's **Authorize** button, retrieve the token after stopping with Ctrl+C using `$env:COMMERCE_TOKEN`, copy it privately, then restart the server. Or set a private token you generate beforehand and keep it available locally. Do not paste it into the repository or chat. Enter the raw token in Swagger's bearer field.

Authentication identity is `alice`, configured server-side. There is deliberately no owner/account field in a refund proposal.

## 6. Send an actual HTTP request

Open Terminal B. Environment changes in Terminal A are not automatically copied to Terminal B. Enter the same token privately:

```powershell
$privateToken = Read-Host "Paste your local API token" -AsSecureString
$env:COMMERCE_TOKEN = [System.Net.NetworkCredential]::new('', $privateToken).Password
$headers = @{ Authorization = "Bearer $env:COMMERCE_TOKEN" }
$body = @{
  transaction_id = "tx_demo"
  amount_cents = 12000
  currency = "USD"
  idempotency_key = "vscode-demo-0001"
} | ConvertTo-Json

Invoke-RestMethod -Uri http://127.0.0.1:8000/refunds -Method Post -Headers $headers -ContentType application/json -Body $body
```

Expected `status: COMMITTED`. Run the same request again: same decision/audit digest, no duplicate refund.

Try a new request for another $120:

```powershell
$secondBody = @{
  transaction_id = "tx_demo"
  amount_cents = 12000
  idempotency_key = "vscode-demo-0002"
} | ConvertTo-Json
Invoke-RestMethod -Uri http://127.0.0.1:8000/refunds -Method Post -Headers $headers -ContentType application/json -Body $secondBody
```

Expected `DENIED`, `daily_cap` violation, and a counterfactual ceiling of 8000 cents. The application does not silently issue that smaller amount. Policy denials are HTTP 200 domain results; validation failures are 422, unknown/other-owner transactions 404, conflicting replay keys 409, and bad credentials 401.

```powershell
Invoke-RestMethod -Uri http://127.0.0.1:8000/ledger/tx_demo -Headers $headers
Invoke-RestMethod -Uri http://127.0.0.1:8000/audit/verify -Headers $headers
.\.venv\Scripts\python.exe scripts\smoke_http.py
```

The smoke test issues a one-cent synthetic refund. Run it before exhausting your daily allowance.

## 7. Triage evidence and view pending review

```powershell
$evidence = @{
  transaction_id = "tx_demo"
  extraction = @{
    transaction_id = "tx_demo"
    amount_cents = 30000
    currency = "USD"
    readable = $true
  }
} | ConvertTo-Json -Depth 4
Invoke-RestMethod -Uri http://127.0.0.1:8000/evidence/triage -Method Post -Headers $headers -ContentType application/json -Body $evidence
Invoke-RestMethod -Uri http://127.0.0.1:8000/reviews -Headers $headers
```

Expected `MATCHED_FOR_REVIEW`, `financial_action: false`, and a review ID. Change the extracted amount to 100 to demonstrate `HUMAN_REVIEW`. Set `readable` to false to demonstrate `REQUEST_REUPLOAD`. Review items are persisted; this version intentionally has no reviewer approval/payment override endpoint.

## 8. Replay proposed policy changes

In Terminal B, using the same project folder/default database:

```powershell
.\.venv\Scripts\python.exe -m commerceguard audit
.\.venv\Scripts\python.exe -m commerceguard replay --cap-cents 10000
```

The $120 historical approval changes under the proposed $100 cap. This reads recorded facts and does not modify the active policy or balances. It is a snapshot sensitivity analysis, not a full simulation of alternate transaction histories. Audit corruption causes replay to stop.

## 9. Use the real MCP server

First verify the wire protocol independently:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_mcp.py -q
```

For any stdio-capable MCP client, configure the executable, module, and absolute paths below. Adapt the enclosing configuration shape to your client's documentation. Do not point a remote client at your local path.

```json
{
  "command": "C:\\AIProjects\\commerceguard\\.venv\\Scripts\\python.exe",
  "args": ["-m", "commerceguard.mcp_server"],
  "env": {
    "COMMERCE_OWNER": "alice",
    "COMMERCE_DB": "C:\\AIProjects\\commerceguard\\data\\commerce.db"
  }
}
```

The editable installation makes the module discoverable outside the repository folder. This is local stdio; process access is its trust boundary. It exposes `get_transaction`, `request_refund`, and `triage_receipt`. Starting the module manually waits for protocol messages; apparent silence is normal. Do not expose this process as an unauthenticated network service.

## 10. Optional live Gemini proposals and image extraction

Offline execution is complete without this step. Use an API key from your Google AI account and a model identifier available to that account; pricing, quotas, and availability depend on that service/account.

```powershell
$privateGeminiKey = Read-Host "Gemini API key" -AsSecureString
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new('', $privateGeminiKey).Password
$env:GEMINI_MODEL = Read-Host "Available Gemini model ID"
.\.venv\Scripts\python.exe -m commerceguard propose 'Refund tx_demo 100 cents USD with idempotency_key gemini-demo-01'
```

This emits a proposal and does not execute it. Review it, then submit through `/refunds` to apply the deterministic checks. Use the supplied synthetic PNG, or a synthetic PNG/JPEG you create locally (under 5 MB):

```powershell
$extractionJson = & .\.venv\Scripts\python.exe -m commerceguard extract datasets\images\receipt_clean.png
if ($LASTEXITCODE -ne 0) { throw "Extraction failed; do not submit evidence" }
$receiptBody = @{ transaction_id = "tx_demo"; extraction = ($extractionJson | ConvertFrom-Json) } | ConvertTo-Json -Depth 4
Invoke-RestMethod -Uri http://127.0.0.1:8000/evidence/triage -Method Post -Headers $headers -ContentType application/json -Body $receiptBody
```

For three explicit live integration probes:

```powershell
$env:RUN_LIVE_API_TESTS = "1"
.\.venv\Scripts\python.exe scripts\live_eval.py
Get-Content results\live-evaluation.json
```

This calls Gemini and may consume quota or incur charges. It creates only temporary synthetic ledgers. Inspect both the proposal and decision: a model changing the requested amount is not evidence that the original request was obeyed. Provider outages/invalid output are recorded as errors, not fabricated fallback facts. Live model quality and image accuracy remain unmeasured until you run a labeled evaluation.

## 11. Publish to GitHub when ready

Run from `C:\AIProjects\commerceguard`. The ZIP does not contain a Git repository. Set your Git author identity using your actual preferred name/email if Git requests it.

```powershell
git init -b main
git status --short
git add .
git diff --cached --stat
git diff --cached --check
git commit -m "Build CommerceGuard reliability gateway with MCP and adversarial tests"
gh auth login
gh repo create commerceguard --private --source=. --remote=origin --push
```

This creates a private repository in the GitHub account you authenticate. If you want it public for applications, change its visibility in GitHub Settings after reviewing the committed files. If the repository already exists, use its actual URL instead of `gh repo create`:

```powershell
git remote add origin https://github.com/YOUR_USERNAME/commerceguard.git
git push -u origin main
```

Do not use both remote-creation paths. No GitHub push was performed by the package builder.

```powershell
gh run list
gh run watch
```

The CI matrix tests Linux/Windows with Python 3.11/3.12 and saves evaluation artifacts. Only describe that matrix as passed after observing successful runs.

After CI passes, optionally create a release:

```powershell
git tag v0.1.0
git push origin v0.1.0
gh release create v0.1.0 --title "CommerceGuard v0.1.0" --notes "Synthetic commerce reliability lab with atomic refunds, MCP, receipt review, and fault-injection tests."
```

## Troubleshooting

- `py -3.12` not found: install Python 3.12 and reopen VS Code. Use `py -0p` to list installed interpreters.
- Import errors: use `.venv\Scripts\python.exe`; rerun the editable install from the folder containing `pyproject.toml`.
- Port refused: keep the Uvicorn terminal running and confirm it printed a successful startup. A localhost URL from a cloud environment is not your PC's localhost.
- Port 8000 occupied: change `--port` and use that port in every request.
- 401: Terminal B's token must match Terminal A's token. `.env.example` is a template, not an automatically loaded credential file.
- Unexpected denial: inspect the violations and ledger. `seed` does not reset existing rows or counters. To start fresh, stop the API and set `COMMERCE_DB` to a new filename, seed, then restart. Set the same path for CLI replay/MCP.
- MCP waits silently: use a client; stdio expects JSON-RPC, not a human prompt.
- Solver install trouble: use supported 64-bit Python 3.12 rather than copying a venv from another project.
- Gemini model/key failure: check your account's available model identifier; offline demos still work.
- `gh` not recognized: reopen VS Code after GitHub CLI installation.
