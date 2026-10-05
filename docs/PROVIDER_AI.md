# Provider AI and academic portals

## Operator configuration
AI is disabled until explicitly configured. API keys stay in backend environment; the browser only sees provider/model/budget metadata. No paid live calls were made during development. Do not paste API keys into GitHub, chat, CSV, or portal forms.

Copy .env.example to .env locally. Start backend with `uv run uvicorn campus_assistant.api.main:app --env-file .env --host 127.0.0.1 --port 8000`.

Ollama: set AI_PROVIDER=ollama, AI_MODEL to an installed local model that supports structured JSON, OLLAMA_URL=http://127.0.0.1:11434. Start Ollama and download your chosen model separately. Local rates may be zero because there is no per-token provider invoice; hardware/energy/operation costs must still enter the ROI scenario. Remote Ollama requires HTTPS. Browser/model cannot supply a provider URL.

OpenAI: set AI_PROVIDER=openai, AI_MODEL to a model available in your API project supporting Chat Completions JSON schema, OPENAI_API_KEY to your own backend key, and both token rates AI_INPUT_IDR_PER_MILLION / AI_OUTPUT_IDR_PER_MILLION to positive IDR estimates matching the model price and exchange rate. No default paid model or price is assumed. Budget estimates are only as accurate as these rates; check invoices separately.

AI_MAX_OUTPUT_TOKENS defaults 800 (64–2000 accepted), single-call absolute timeout 45 seconds, no automatic retries, max 300 runs/class/UTC month. AI_MAX_RUN_IDR defaults 5000; AI_MONTHLY_CLASS_IDR defaults 100000. AGENT_DISABLED=1 blocks generation and approval while deterministic outcomes remain available. Restart backend after environment changes.

## Lecturer workflow
Data Akademik → fill scores → Provider AI → choose student → create AI draft → inspect run log → Intervensi → review → approve/reject. Complete data and at least one CPMK gap are required. The provider receives only CPMK codes, gap magnitudes and assessment IDs; no name, student ID, class name or student free text. Do not encode PII into assessment IDs.

The output is validated locally against schema and exact evidence/CPMK sets. Model numbers never replace Outcome Engine scores. Valid JSON and correct references do not prove pedagogical quality: lecturer review is mandatory. There is no tool execution, code execution or outbound student messaging.

## Budget and reliability
Database ledger reserves a conservative input/schema/framing token bound plus max output before external calls. Class row lock serializes PostgreSQL reservations. Run status and idempotency key persist; a repeated request never causes a second provider call for that key. Reported usage settles validated calls; failed/uncertain calls conservatively retain reservation because timeouts can still be billed. Stale snapshot/kill-switch after a call prevents draft publication. Crashed running runs keep their reservation and require operator reconciliation; automatic recovery is not implemented.

Per-class estimates are not a provider-enforced hard spend limit, especially with misconfigured rates. Provider account billing caps should be configured independently. Token usage and latency are logged; do not infer ROI from successful generation alone. Evaluate arm C against B with review and correction time included.

## Portal accounts
Lecturer: Data Akademik → Akun portal → choose student/prodi → username + initial password (12+ characters). Student accounts bind to exactly one Student record; prodi accounts bind to the current class. Existing usernames/accounts are not overwritten. Account reset and multi-class membership administration are not yet provided.

Same login page redirects student/prodi users to /portal. Student can read only their own outcomes, approved/completed plans, and submit a one-time completion note on an approved plan. Student submission does not change grades or mark a plan completed; lecturer remains responsible for review. Prodi sees class-scoped CPL aggregates and data completeness; cohorts under 5 suppress distributions. No individual IDs/names, drafts, or score editing endpoints are exposed to prodi. These aggregates are not a formal privacy guarantee or full curriculum CPL computation.

Synthetic demonstration only:

```powershell
$env:PORTAL_DEMO_PASSWORD = Read-Host 'Password demo portal minimal 12 karakter'
uv run python -m campus_assistant.api.seed_portals
```

Run normal seed first. Creates usernames mahasiswa (STD-003) and prodi (RPL-01) only when absent. Does not overwrite prior credentials. Use separate credentials for real accounts.

## References used for adapters
https://docs.ollama.com/api/chat
https://docs.ollama.com/capabilities/structured-outputs
https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create

## Verification — 2026-10-05
GitHub Actions run 37278680745 passed backend, frontend and PostgreSQL 18 jobs. PostgreSQL verification includes Alembic upgrade → downgrade → upgrade and the concurrent budget reservation test. Local SQLite suite: 32 passed, PostgreSQL-only test skipped locally.

Eight real Chromium browser tests passed: four desktop and four mobile covering academic input, CSV export, provider readiness, intervention approval, pilot measurement, student self-access and program aggregates. Screenshots were visually inspected; mobile navigation wraps and horizontal tables scroll within their container. Browser suites use synthetic SQLite data, not PostgreSQL; PostgreSQL is verified separately through API integration tests. Each browser project restarts the isolated API to keep login throttling intact without cross-suite interference.

Run locally after frontend build: `uv run python scripts/browser_verify.py`. Playwright Chromium must be installed (`cd frontend && npx playwright install chromium`). Optional CHROMIUM_EXECUTABLE selects a compatible installed Chromium. Live Ollama/OpenAI behavior and educational ROI remain unverified; adapters were exercised with mocked HTTP responses.
