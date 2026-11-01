# Deployment Guide

## 1. Local staging on your laptop

Extract into a NEW `resolution-hub-v3` directory. Keep `resolution-hub-v2`, its `.env`, database and backups unchanged. From the new project root:

```bash
python3.12 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python scripts/bootstrap.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1
```

Bootstrap creates `.env` only if absent and asks for an Administrator password (15-128 characters). No default password exists. Do not expose the development HTTP listener remotely. Use approved package mirrors/offline wheels where required. The pinned direct versions match the test environment; a clean registry install, full transitive lock and dependency vulnerability scan were not performed here.

## 2. Initial account setup

Sign in, open Users, create an Engineer and a Reviewer with the needed workspace grants. Copy the one-time temporary password into an approved secure delivery channel. Each user changes it on first sign-in; all sessions are revoked after password change/reset. Never share Administrator credentials.

Create custom roles in Admin > Roles & RBAC, then assign them in Users. Permissions are backend-enforced. Administrator is a protected full-permission role; the last active Administrator cannot be disabled/demoted. Role/access changes revoke affected sessions. Administrative permissions such as settings.manage/audit.read/maintenance.manage are instance-wide; grant them only to trusted instance operators.

## 3. Configure approved AI

Default provider `evidence` makes no model call. Local FTS5 retrieval is always used; embeddings are not required or called.

First initialization seeds provider/model/base URL from `.env`. Thereafter **Admin > AI Provider is authoritative** for those saved settings. Secret and network settings remain environment-owned:

```dotenv
OPENAI_API_KEY=YOUR_APPROVED_SECRET
ALLOW_EXTERNAL_AI=false
AI_ALLOWED_HOSTS=
```

For a remote approved compatible service, set ALLOW_EXTERNAL_AI=true and AI_ALLOWED_HOSTS to its exact hostname (comma-separated if needed), restart, then configure provider=openai, its documented base URL and model in Admin. HTTPS is required for remote hosts. `openai` denotes the compatible request format, not vendor endorsement. The adapter appends `/chat/completions`. Do not use a browser Playground URL as an API endpoint. No internal Playground authentication contract is assumed or implemented.

For local Ollama, configure provider=ollama and the model in Admin; OLLAMA_URL remains a server setting. In a container, loopback refers to that container, not the host. Use an approved reachable service URL and network design. The special local hostname `ollama` is accepted for a service on a private container network; this package does not provision that service/models.

The adapter supports bearer-key compatible APIs and Ollama chat, not every vendor-specific authentication method. Managed identity/OAuth adapters require separate implementation. HTTPX ignores inherited proxy environment variables; adapt deliberately for an approved proxy. Host allowlisting is not a substitute for network egress controls or DNS protections.

Use Admin > Test saved connection with synthetic text. Provider quota/model/endpoint errors return safe diagnostics rather than fabricated answers. AI extraction and image input are opt-in checkboxes. Model support and data permission must be validated before enabling them. Live provider, image quality and extraction quality were not tested in this delivery.

## 4. Mail/files and OCR

EML: MIME body, subject/from/to/date, supported nested attachments and CID inline images. MSG: extract-msg parser, body and supported attachments. Rich HTML is sanitized; remote images/scripts/forms are removed. Original pixel-perfect Outlook rendering is not guaranteed. Text PDFs and DOCX extraction have layout warnings. Encrypted files are rejected; scanned PDFs require separate OCR preprocessing. Unsupported nested attachments are retained with warnings and not silently treated as understood.

PNG/JPEG/WebP are decoded and re-encoded to PNG, bounded to 16 million pixels and resized to at most 2400x2400. For OCR, install approved Tesseract/language packs and set OCR_ENABLED=true. The worker invokes `tesseract image.png stdout`. If unavailable, the image remains with a warning. Vision input is separate and requires an approved capable model. At most four current/recent images are sent per chat request, with warnings for omissions. Images are never claimed to have been analysed in evidence-only mode.

Extraction runs in a bounded subprocess with timeout, Linux CPU/address-space limits and archive/depth/count caps. This is not a complete OS/network sandbox. Add container/OS isolation and hostile-file testing before untrusted uploads. Extraction is synchronous; no background worker or scheduled ingestion is provided.

## 5. Production settings

Before setting APP_ENV=production, configure:

```dotenv
APP_ENV=production
COOKIE_SECURE=true
ALLOWED_ORIGINS=https://YOUR_APPROVED_HOSTNAME
UPLOAD_SCAN=required
CLAMSCAN_PATH=/usr/bin/clamscan
```

Use your actual approved hostname. Do not copy this placeholder unchanged. Production startup rejects insecure cookies, missing HTTPS origins and disabled required scanning. Uploads fail closed if scanner/signatures are unavailable or scanning fails. Keep signatures updated through an approved operational process. The application does not download/update them automatically. It scans outer files and decoded nested attachments before persistence.

Protect the server data directory (database, attachments in DB, logo) and `.env` with least-privilege filesystem permissions. Apply encrypted storage/backups and network controls through your hosting platform. No built-in at-rest encryption, SSO/MFA or corporate security certification is supplied.

## 6. Docker

Templates are supplied but were not built/run here. The image installs ClamAV/Tesseract; use approved mirrors and scan/pin the image/dependencies before deployment. From the project root, create `.env` from the example and customize it, then:

```bash
docker compose -p lcm-resolution-v3 build
docker compose -p lcm-resolution-v3 run --rm hub python scripts/bootstrap.py
docker compose -p lcm-resolution-v3 up -d
docker compose -p lcm-resolution-v3 logs --tail=100 hub
```

Bootstrap is interactive and uses the persistent named data volume. In Docker the existing env_file supplies settings; no secret is baked into the image. The app runs as UID 10001, with read-only root, dropped capabilities, bounded tmpfs, one worker and a loopback-bound host port 8001. Do not use `down -v` on a populated deployment. Do not share the SQLite volume across replicas or network filesystems.

For production, provision a current ClamAV signature directory on the host, set CLAMAV_DB_DIR to its absolute path, configure the HTTPS settings in `.env`, then use both Compose files consistently:

```bash
docker compose -p lcm-resolution-v3 -f compose.yaml -f compose.production.yaml config --quiet
docker compose -p lcm-resolution-v3 -f compose.yaml -f compose.production.yaml up -d --build
```

The overlay mounts signatures read-only and forces secure-cookie/scan settings. Signature provisioning, TLS and network policy remain operator prerequisites. Missing signatures cause uploads to fail, not bypass scanning.

## 7. TLS proxy

`deploy/nginx.conf` is a same-host template. Replace hostname/certificate paths, validate through operations and terminate approved TLS. It includes body/login-rate limits and longer provider timeout. The app also caps request bodies, per-user uploads and chat calls. Only trust forwarded client headers from your actual proxy; do not trust arbitrary remote X-Forwarded-For. Configure Uvicorn's trusted proxy IPs for your deployment. Shared proxy IPs can otherwise cause login throttling across users.

Do not expose raw app/model ports to untrusted networks. Health checks verify app/database only, not AI/scanner readiness. No central monitoring/alerting stack is provisioned.

## 8. Backup/restore

From the project root:

```bash
python scripts/backup.py /secure/backups/hub-v3-backup.db
```

This uses SQLite's consistent backup API and integrity check, including stored attachments. Destination must not exist. Back up logo.png, instance config and protected environment/secrets references separately. Restrict/encrypt all backups.

For Compose, run the backup command inside the hub container to a new file in `/srv/hub/data`, copy it out with `docker compose cp`, then remove the temporary in-volume backup after verifying the external copy. Use the same project/overlay arguments as the deployment. A knowledge JSON export is not a full backup.

Restore in staging first: stop the app, preserve the current DB/WAL/SHM set, restore the backup to the configured DB path, remove stale sidecars from the restore location, set correct ownership, restore matching config/logo, restart and verify integrity, login, grants, knowledge, attachments and history. Never overwrite a running database. Production restore/rollback was not executed here.

## 9. Separate team instances

Copy source, edit config/instance.json (instance ID/name and workspace IDs/names), create a new `.env`, generate a new Administrator, use a separate database/volume/server/hostname and complete that team's approvals. Never copy LCM credentials or data. IDs are stable data keys; startup rejects removing populated workspace IDs or changing the instance bound to a DB. Runtime user grants are managed in Users; workspace definitions remain deployment configuration.

## 10. Rollout gates

Review SECURITY, test real sanitized mail/MSG/PDF samples, live approved AI/vision/OCR, malware scanning, restore/rollback, access revocation, concurrent use and capacity. This release is single-node SQLite, not HA. Do not label it production-approved merely because tests pass.
