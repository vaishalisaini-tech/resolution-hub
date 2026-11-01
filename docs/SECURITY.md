# Security Review and Release Gates

## Implemented controls

- PBKDF2-HMAC-SHA256 passwords, 600,000 iterations, per-password random salt; 15-128 characters. No plaintext password persistence or shipped default accounts.
- Random session tokens stored as digests; HttpOnly/SameSite=Strict cookies; production Secure requirement; idle/absolute expiry.
- Session-bound CSRF token for mutations, origin checks and cross-site request rejection. Password/reset/access/role changes revoke sessions.
- Login throttling in SQLite (10 failures per IP or username in 15 minutes), authenticated chat/upload throttles and request size limits.
- Backend permission checks and workspace grants, private owner-bound conversations, attachment access checks, delegation bounds, protected Administrator and last-active-admin safeguard.
- Independent publication review against original author/latest content editor; edits reset to draft; unresolved entries excluded from fixes; optimistic versions and transactional imports.
- Server-side HTML allowlist, active/remote content removal, same-origin protected inline images, CSP, no raw HTML downloads, image re-encoding.
- Scanner fail-closed path, nested attachment scan, bounded extraction subprocess, archive/count/depth/pixel/text/time limits and explicit warnings.
- Server-owned AI host allowlist and external opt-in; no browser-exposed provider keys; safe upstream errors; no command execution; source version recheck before saving answers.
- Hash-linked audit events, consistent backup utility, manual history purge and read-only old-data migration source.

These are implementation controls, not a claim of organizational compliance, penetration-test success or complete attack resistance.

## Residual risks and limits

- No SSO/MFA, breach-password screening, automated recovery email, managed identity, centralized session service or immutable external audit sink.
- HTML sanitization is custom and needs adversarial review. Exact email rendering is deliberately sacrificed for safety. File parsers are subprocess-bounded, not a full OS/network sandbox.
- Scanner must be installed with maintained signatures. Antivirus is not proof that a file is safe. Signature age enforcement/updates are operational responsibilities.
- Regex credential rejection is not DLP; many secrets/customer identifiers may be missed. Uploaded emails can contain third-party/personal data requiring approval.
- AI can hallucinate, misapply evidence or follow malicious embedded instructions. Prompt guidance and citation-ID checks do not prove support or prevent all injection. AI extraction is always reviewable, never automatically published.
- Saved history contains evidence snapshots already disclosed to its owner. Source archive/access changes do not retroactively erase those snapshots. Define cleanup/revocation policy.
- SQLite/one worker is single-node, not HA. Attachment BLOBs grow the DB. Synchronous extraction/model calls can consume resources. No ingestion queue or load-tested capacity guarantee.
- Maintenance/admin permissions are instance-wide. Only trusted operators should receive them. A server/DB operator can access all instance data and reset accounts.
- No built-in at-rest encryption, complete lifecycle deletion, legal hold, automatic backup scheduling or general schema migration engine.
- Request-body buffering and parsing remain bounded but can consume memory; proxy connection/body/rate limits are still required.
- Host allowlisting does not replace egress firewalling/DNS protection. Local AI endpoints are trusted operator configuration.
- Direct package pins are not a fully hashed transitive lock, SBOM or vulnerability scan. Container base image is not digest-pinned.

## Before production

Approve hosting/data/model use and licensing; configure HTTPS/secure cookies/explicit origins; use least privilege; require maintained malware scanning; isolate parser execution; add approved DLP/secrets/encryption/egress controls; scan dependencies/images; evaluate real mail/MSG/vision/OCR and prompt-injection cases; test load, restore and rollback; define lifecycle for knowledge, attachments, history, audit, exports and backups; assign operations/incident ownership. Consider corporate SSO/MFA rather than local passwords for enterprise rollout.

References informing controls:
- [OWASP Password Storage](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html)
- [OWASP Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html)
- [OWASP File Upload](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)

No production deployment, organizational approval, live AI validation or penetration test was performed in this delivery.
