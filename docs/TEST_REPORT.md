# Verification Report: v3.0.0

## Executed successfully

- **56 pytest tests passed** in the available Python 3.12 Linux environment.
- Python compilation and deployable JavaScript syntax checks passed.
- Headless Chromium browser workflow passed: real password login, four direct workspaces, text-file upload, complete-document import with prefilled resolution, source-pair confirmation, independent publication review, evidence retrieval, continuing chat, history resume, workspace isolation, user creation, custom role creation, administrator pages, profile/guide, light/dark themes and 375px responsive dashboard. No browser page errors observed.
- Interactive bootstrap, refusal to recreate an existing Administrator and consistent SQLite backup/read-back passed on temporary databases.
- v2 knowledge JSON import tested with synthetic data.
- EML with HTML body, CID inline image and text attachment tested through the real extraction subprocess. DOCX and text extraction tested. Unsupported/invalid files and unavailable scanner rejection tested.
- Compatible chat, vision payload, AI extraction and quota error handling tested with mocked provider responses, not live models.

All accounts, passwords, records, emails and model responses in tests are synthetic fixtures. No production data or credentials are bundled. Screenshots under screenshots/ are actual browser captures of the implemented UI with temporary synthetic test data.

## Coverage

Authentication/cookies, bad credentials, CSRF/origin checks, login throttle, logout, password change, session expiry, forced first-password change, workspace/record/asset scope, reader write denial, draft/unresolved states, independent review including admin self-approval rejection, duplicate detection, stale versions, edit withdrawal, secret-pattern rejection, HTML sanitization, upload/extraction, confirmed multi-pair import, transaction rollback, private multi-turn history, feedback, user/reset/role/session controls, last-admin protection, settings concurrency, provider allowlist, scanner fail-closed path, PNG branding, maintenance, safe AI failure and production startup guards.

## Not verified

Live Gemini/OpenAI/Ollama/internal Playground calls, live vision or OCR quality, representative real MSG extraction, representative PDF layouts/scanned PDFs, actual ClamAV malware/signature detection, Docker image build/Compose/nginx/TLS deployment, clean registry installation, transitive dependency vulnerability/licensing review, hostile-file corpus, load/HA, penetration testing, production restore/rollback or organizational approval.

MSG/PDF/OCR/scanner paths are implemented with warnings/guards but need environment-specific acceptance testing. No resolution-accuracy, throughput, latency or capacity claim is made.

One upstream Starlette TestClient/HTTPX deprecation warning was emitted; tests passed. Validate the approved dependency graph before deployment. Direct dependency pins are not a fully hashed transitive lock.

## Reproduce

```bash
pip install -r requirements-dev.txt
python -m pytest -q
python -m compileall -q app scripts tests
node --check app/static/app.js
python -m playwright install chromium
python scripts/browser_smoke.py
```

The browser runner uses a temporary server/database and synthetic records. A matching Chromium installation is required; optionally set CHROMIUM_EXECUTABLE to an existing approved browser binary. Passing tests establishes exercised behavior, not production certification.
