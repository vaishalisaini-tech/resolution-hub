# v3.0.0

Implemented the approved email-first UI and workflows as a standalone application. This is a new schema/release, not a patch applied to the user's local v2 files. Local custom v2 changes were not available and are not automatically merged.

- Token-paste login replaced with username/password sessions and administration.
- Custom RBAC roles and workspace grants stored in DB and enforced on API requests.
- Knowledge capture simplified to Issue and Resolution; Environment renamed Environment/Server and made optional. Type/category/review-date/version form fields removed; internal versioning retained.
- EML/MSG/file extraction, protected attachment persistence, sanitized rich paste and inline-image mapping added.
- Complete-document case pairing, source comparison, confirmation and bulk draft import added. Missing resolutions stay unresolved.
- Persistent continuing conversations, follow-up context, optional vision/OCR, source evidence and feedback added.
- Top navigation, screenshot-inspired light/dark styling, user/profile/guide/admin pages and offline PNG branding implemented.
- Production guardrails, scanner fail-closed path, extraction resource limits, cookie/CSRF/origin controls, throttles and safe provider errors added.
- v2 knowledge-only import, backup/recovery utilities, Docker/TLS templates, HLD/LLD and verification docs included.

## Deliberate boundaries

v3 uses local FTS5 lexical retrieval; it does not call embeddings APIs or reuse v2 vectors. Saved Admin provider settings supersede .env seeds after first initialization. Production remains single-node SQLite and requires deployment/security validation. No SSO/MFA, automated recovery email, full historical migration, scanned-PDF OCR pipeline, HA or undocumented internal Playground adapter is claimed.
