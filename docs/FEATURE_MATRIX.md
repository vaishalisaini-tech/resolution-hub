# Implemented Scope and Boundaries

| Approved feature | Implementation / boundary |
|---|---|
| Four direct workspaces | Inhouse, Enable, RPA, MATE; separate instance model retained |
| Username/password login | Real backend login, hashes, cookies, CSRF, forced change and admin reset |
| RBAC editable in Admin | Custom role create/edit/delete, backend permission/grant checks; Administrator protected |
| Two main knowledge fields | Rich Issue and Resolution; optional Environment/Server; removed form fields absent |
| Complete file already has both | Heading-based extraction and optional approved AI extraction; editable source comparison and bulk draft import |
| Multiple cases | Review queue, confirm each pair, save separately in one transaction |
| Missing solution | Unresolved record, excluded from published fixes; no invented resolution |
| Whole email | EML/MSG body/headers/supported attachments; MSG implementation needs representative fixture validation |
| Rich paste and inline images | Sanitized basic HTML, uploaded clipboard images, CID rewrite; not pixel-perfect Outlook |
| PDF/DOCX | Text extraction, tables/images as supported, explicit layout warnings; scanned PDF OCR deferred |
| Image understanding | Normalized image storage; optional Tesseract OCR and model vision input; live quality not verified |
| Continuing chat | Persistent owner/workspace-bound history, bounded user/assistant context and recent images |
| Knowledge evidence | Local FTS5/BM25, published resolutions only, versioned references; no embeddings in v3 |
| Admin options | Users/roles/grants, settings, provider test, logo, security policy, audit, reindex/export/history purge |
| Workspace definitions | Deployment config; runtime user grants editable, no runtime team creation |
| Light/dark and logo | Actual themed UI, theme-only localStorage, local PNG upload/reset |
| Backup | Consistent CLI backup; not browser-scheduled backup or full lifecycle automation |
| Production hardening | Implemented controls plus explicit rollout gates; not production-certified/HA |
| SSO/MFA/recovery email | Not implemented; administrator-assisted recovery and local passwords |
| Complete v2 migration | Not implemented; knowledge-only JSON import, old history/audit retained separately |
| Live approved internal Playground | No undocumented auth contract assumed; adapter needed if incompatible |

No real operational data, credentials, logo or AI model is bundled. Test examples are synthetic fixtures only.
