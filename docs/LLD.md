# Low-Level Design

## Modules

- db.py: configuration, schema initialization, settings, transaction context, audit hashes.
- security.py: PBKDF2 passwords, session/CSRF verification, permissions/grants and delegation safeguards.
- content.py: HTML allowlist, plain-text extraction, local-image IDs, heading-based case splitting.
- extract_worker.py: EML/MSG/text/PDF/DOCX/image extraction, nested payloads, optional OCR, bounded worker entrypoint.
- assets.py: scan orchestration, subprocess timeout, nested scan, protected persistence, access/expansion.
- ai.py: FTS5 retrieval, approved endpoint validation, compatible/Ollama chat/vision, optional pair extraction, safe provider errors.
- models.py: strict Pydantic input contracts.
- main.py: auth/admin/knowledge/import/chat/history/maintenance API orchestration and static UI.
- static/app.js/style.css/index.html: framework-free, same-origin UI, no CDN dependencies.
- scripts: interactive bootstrap/recovery, consistent backup, v2 knowledge import, optional browser regression.

## Database schema

| Table | Purpose |
|---|---|
| meta | Stable instance ID and schema version 3 |
| roles | Named permission arrays; protected Administrator |
| users | Username, display name, password hash, role FK, workspace grants, active/forced-change flags |
| sessions | Session digest, user FK, CSRF digest, created/last-seen timestamps |
| attempts | Login and authenticated-request throttle events |
| settings | Singleton versioned settings JSON |
| assets | UUID, workspace/owner, original name, MIME, binary body, sanitized HTML, extracted text/warnings |
| asset_children | Parent/child attachment graph |
| knowledge | Two sanitized HTML/text fields, environment, state, author/editor, internal version/digest/timestamps |
| knowledge_assets | Explicit record-to-attachment links |
| versions | Full knowledge snapshots, actor, rationale and version |
| knowledge_fts | FTS5 index of issue/resolution/environment |
| conversations | Owner/workspace-bound investigation title and timestamps |
| messages | User/assistant HTML/text, asset IDs, source snapshots, mode and time |
| feedback | Owner answer-usefulness feedback |
| audit | Actor/action/target/workspace/time and hash link |

Foreign keys are enabled per connection; SQLite WAL and 20-second connection timeout. Knowledge duplicates are keyed by workspace plus hash of lowercased trimmed issue/resolution text. This is exact-text duplicate detection, not semantic matching. No team/domain columns.

## Authentication and authorization

Login verifies a salted 600,000-iteration PBKDF2-HMAC-SHA256 hash. Unknown usernames receive a dummy hash verification. Failure responses are generic. Session tokens are random and stored as SHA-256 digests; cookies are HttpOnly/SameSite Strict and Secure in production. CSRF tokens are derived from the random session token, stored as digests and returned only to the same-origin authenticated UI. Mutations check the CSRF header. GET /me returns the same session-bound token, allowing multiple tabs without rotating each other out.

Each request reloads current user activity, role permissions and workspace grants. Temporary-password sessions may access only me/password/logout. Expired sessions are removed. Password/reset/role/grant/status changes revoke affected sessions. Administrator role is immutable/full-permission; last active Administrator cannot be removed. Delegated account managers cannot manage accounts/roles beyond their own privileges/grants. Admin-level permissions are instance-wide, not narrowed by workspace grants; use them only for trusted operators.

## Rich content and assets

Client paste rebuilds an allowlisted DOM and uploads clipboard image files. Server sanitization runs again before persistence. Email HTML preserves safe basic structure, tables and limited styles; scripts/forms/remote images/active content are removed. Images must reference protected local asset endpoints. Assets are readable by their owner within a permitted workspace, or by knowledge readers when linked to knowledge in that workspace. Conversation assets remain private until explicitly linked to knowledge.

Image bodies are normalized PNGs. Other originals are served only as application/octet-stream attachment downloads. Names are display/download metadata, never filesystem paths. CID images are rewritten to local UUID image routes where decoded successfully. Unsupported nested payloads remain warning-bearing attachments.

Uploads are capped by settings (default 10 MB, max 20 MB) and total request cap (22 MB); proxy limit is 21 MB in the template. Extraction caps include depth 3, 100 MIME parts, 80 persisted expanded objects/30 MB aggregate, 100 PDF pages, 20 MB DOCX expansion, 16 million image pixels, 400,000 HTML characters per extracted object and a 40-second subprocess timeout. Linux worker CPU/address-space limits are applied when available. These are guards, not tested capacity guarantees or a complete sandbox.

## Import and knowledge lifecycle

Heading extraction recognizes Issue:/Problem: and Resolution:/Solution:/Fix:, with --- or repeated issue headings for multiple cases. It does not invent missing solutions. Optional AI extraction is separately enabled and returns a bounded JSON pair list with review warnings. Source content is always untrusted.

UI review pairs remain in browser memory until saved; source assets persist. Each submitted pair must be explicitly confirmed. Bulk import is one transaction; duplicates/errors roll it back. Nonempty resolution -> draft; empty -> unresolved. Publication requires independent review and nonempty resolution text. Edits reset to draft/unresolved and increment internal version. expected_version protects edits/reviews against stale updates. Source attachments and snapshots preserve traceability outside the entry form.

## Retrieval and chat

FTS5 query terms are unique word tokens longer than two characters with a small stop list, capped at 50. OR/BM25 ranking is filtered to the selected workspace, published status and nonempty resolution. Up to five source records include UUID:vVERSION references. Scores are not confidence probabilities. No embeddings or semantic reranker is implemented in v3.

The last eight messages (each text capped at 6,000 characters) form bounded conversation context. Prior assistant text is explicitly unverified history, not evidence. Retrieval uses the last two user messages plus the current issue/attachment text. Current and recent user image assets are owner/scope-rechecked and up to four are included when vision is enabled. Unsupported image analysis is reported.

Model calls run outside the write transaction. On return, the current session/permissions and source publication/version are rechecked before saving. Unknown UUID-like source citations are rejected; citation-ID validation does not establish factual entailment. User/assistant messages and evidence snapshots are persisted transactionally. Provider failure returns 502 and does not fabricate/persist an answer. Compatible APIs use bearer key plus /chat/completions; Ollama uses /api/chat. No vendor-native OAuth/managed-identity adapter is assumed.

## API groups

- /api/auth/login, logout, password; /api/me; /api/profile.
- /api/admin/users, user access/reset/revoke; /api/admin/roles.
- /api/admin/settings, ai-test, logo; public /api/branding and /api/logo.
- /api/workspaces/{workspace}/assets, extract, import, knowledge, chat, history, dashboard.
- /api/knowledge/{id}, versions, review.
- /api/assets/{id}/image or download; /api/conversations/{id}; /api/messages/{id}/feedback.
- /api/admin/audit, export, reindex, purge-history.

See generated openapi.json for exact schemas. All /api routes except login/branding/logo require sessions; all authenticated mutations require CSRF. No team creation, command execution or public self-registration API.

## Maintenance

Audit is hash-linked but not immutable against DB operators. History purge removes conversations older than configured updated-time cutoff and cascades messages/feedback only. Knowledge/assets/versions/audit/backups remain. Full backup is operator CLI; knowledge JSON export is not a backup. v2 migration reads knowledge JSON into new draft/unresolved records, never mutating old data or claiming complete historical migration.
