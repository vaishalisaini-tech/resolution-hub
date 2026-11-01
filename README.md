# Resolution Hub v3

Email-first troubleshooting and team knowledge base for one LCM deployment with **Inhouse, Enable, RPA and MATE** workspaces. Other teams customize `config/instance.json` and deploy independent copies with their own database. This is the implemented application, not an in-memory preview.

A FastAPI backend (SQLite + FTS5) serves a single-page vanilla-JS frontend. Knowledge is captured as **Issue / Email / Extracted Content** and **Resolution** pairs, and an advisory AI assistant helps investigate issues using only your published resolutions as evidence.

---

## Highlights

- **Professional UI** — refreshed design with a navy → light-blue gradient accent (Ericsson-style), neutral black/grey dark mode, and a clean light mode. Light/dark toggle; theme preference is the only item stored in the browser.
- **ChatGPT / Gemini-style follow-up assistant** — on the Solve page, after the first resolution the right-hand panel becomes a conversational assistant for follow-up questions within the same investigation (message bubbles, typing indicator, suggestion chips, evidence inline). All answers are advisory and never auto-saved.
- **Email-based password reset** — "Forgot password?" sends a one-time, time-limited reset link to the user's registered email. Requests are throttled and return a constant response (no account/email enumeration). Falls back to logging the link when SMTP is not configured.
- **Authentication & RBAC** — username/password login, hashed passwords, cookie sessions, CSRF checks, forced temporary-password change, admin reset/revocation; database-backed custom roles, backend permission and workspace grants; protected Administrator role and last-admin safeguard.
- **Knowledge capture & import** — two main fields plus optional Environment/Server; whole-email/file upload, sanitized rich-text paste, protected attachments and inline email images; complete-document import that extracts multiple issue–resolution pairs for review and bulk save.
- **Evidence-grounded answers** — local FTS5/BM25 lexical retrieval over published resolutions only. No embeddings API is called in this release.
- **Admin console** — users, roles/RBAC, workspaces, AI provider, branding/logo, security policy, imports, audit log, search rebuild, knowledge export and history retention.

---

## Requirements

- **Python 3.12** (this package is tested on 3.12; it is not a 3.8 build)
- SQLite (bundled with Python)

Core dependencies (see `requirements.txt`): FastAPI, Uvicorn, Pydantic, httpx, python-multipart, python-dotenv, BeautifulSoup4, pypdf, python-docx, extract-msg, Pillow.

---

## Quick start (local, port 8001)

> Use a **new directory and a new database**. Do not overwrite v2 or copy its database into v3.

```bash
cd resolution-hub-v3
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python scripts/bootstrap.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1
```

`bootstrap.py` creates `.env` from `.env.example` if absent, asks you to choose the first Administrator username/password, and creates the database. No default password, API key, real knowledge or sample account is shipped. Stop any old process on port 8001 first, then open http://127.0.0.1:8001.

Create Engineer and Reviewer accounts in **Users**. Temporary passwords are shown once and must be changed on first sign-in; deliver them securely.

---

## Email-based password reset (SMTP)

Password recovery is available by email when the server is configured with SMTP and users have a registered email address (set in **Admin → Users**). Configure these in your server environment (see `.env.example`):

| Variable | Purpose |
|---|---|
| `APP_BASE_URL` | Base URL used to build the reset link (e.g. `https://hub.example.com`) |
| `RESET_TOKEN_MINUTES` | Reset-link lifetime in minutes (default `30`) |
| `SMTP_HOST` / `SMTP_PORT` | Mail server host and port |
| `SMTP_USERNAME` / `SMTP_PASSWORD` | SMTP auth credentials (optional) |
| `SMTP_STARTTLS` | `true` to use STARTTLS (default) |
| `SMTP_SSL` | `true` for implicit TLS (SMTPS) |
| `MAIL_FROM` | From address for reset emails |

If `SMTP_HOST`/`MAIL_FROM` are not set, the reset link is written to the server log instead of emailed — useful for local development. Tokens are hashed at rest, single-use, and revoke all of the user's sessions on completion.

---

## AI settings

On the **first initialization only**, `.env` seeds chat/provider settings into the database. After that, edit them in **Admin → AI Provider**; changing `.env` alone does not replace saved database settings. Secrets, network allowlists, secure cookies, origins, OCR and scanner mode remain server environment settings and require a restart.

Default mode is **evidence-only** and does not call any model. Chat/vision/AI extraction require an approved compatible or Ollama endpoint and actual model access. This release uses local FTS5 lexical retrieval and does **not** call an embeddings API. Public external AI must not be used for organizational data without the applicable approval.

---

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

Optional browser regression (needs a separately installed Playwright Chromium):

```bash
python -m playwright install chromium
python scripts/browser_smoke.py
```

The browser runner creates a temporary database and synthetic accounts/content — test fixtures, not shipped credentials.

---

## Documentation

- [Deployment guide](docs/DEPLOYMENT.md) — local, AI, Docker, TLS, scanning, OCR, backup/restore
- [Migration guide](docs/MIGRATION.md) — v2 knowledge export to v3 drafts; no in-place upgrade
- [Security and release gates](docs/SECURITY.md) — controls and residual risks
- [Feature coverage](docs/FEATURE_MATRIX.md) — implemented scope and limitations
- [HLD](docs/HLD.md) / [LLD](docs/LLD.md) — architecture, schema, authorization and workflows
- [Verification report](docs/TEST_REPORT.md) — executed tests vs unverified production behavior
- [User guide](docs/USER_GUIDE.md) — daily workflow and admin controls
- [API schema](docs/openapi.json) — generated OpenAPI

---

## Production status

Hardened **single-node release candidate** — not a production-certified or organization-approved system. SQLite is not an HA/multi-replica design. Before operational rollout: approve hosting/data/model use, configure HTTPS/secure cookies/allowed origins, require maintained malware scanning, isolate parsers, scan dependencies/images, test live models and representative mail formats, verify backup/restore, and complete a security/load review. See [docs/SECURITY.md](docs/SECURITY.md).

---

## License

Released under the MIT License. See [LICENSE](LICENSE).
