# Resolution Hub v3.0.1 targeted workflow/provider update

This is an updater for the previously supplied v3.0.0 source, NOT a complete replacement project. Your local customized project was not accessible. Exact source anchors are checked before changes; mismatches stop the update. No .env, password, key, user, role or workspace configuration is changed.

## Error diagnosis first

The supplied screenshot reports upstream_status=503, wrapped by the app as HTTP 502. Google documents temporary unavailability/overload and bounded exponential backoff for transient errors. This is not proof of exhausted credits or invalid credentials. The local POST /api/admin/ai-test 401 is a separate app-session authorization failure; its exact cause is not established by access logs. An earlier 200 test alone is not proof of live inference because evidence-only mode also returns 200.

From your project root, using its existing virtual environment, after extracting this folder:

```bash
python workflow-update/diagnose_ai.py --project .
```

This reads the saved database settings and sends one synthetic inference request without a temperature override. It prints status, error code/status/message and request ID when supplied; it does not print the API key. Do not share secrets or business content. A successful minimal test does not prove the old failing request's cause: transient availability can change between calls.

If 503 persists, use bounded retries or explicitly select another supported model available to your project in Admin > AI Provider. No silent model/provider switch is implemented. Do not reset the database or rotate a key solely because of 503. Quota/auth errors need their own remedies.

## Apply

1. Stop Uvicorn with Ctrl+C. Do not patch while any app worker/service is running.
2. From the v3 project root:

```bash
python workflow-update/apply_update.py --project .
```

This is a dry run. It checks source, Python syntax, optional Node syntax and existing v3 DB. It reports how many existing resolved drafts would become searchable.

3. Apply:

```bash
python workflow-update/apply_update.py --project . --apply
```

The updater first backs up the three source files and consistent SQLite DB under upgrade-backups/<run>/, checks the backup, then updates source and migrates existing resolved drafts with new versions/audit events. Archived and unresolved records are unchanged. New saves with a resolution become searchable immediately; empty resolutions remain unresolved. Existing published entries remain unchanged.

To intentionally leave old resolved drafts unpublished while changing new saves, add --keep-existing-drafts. Default behavior removes the old approval queue by making those resolved drafts searchable. The dry run does not alter data.

4. Restart:

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --workers 1
```

5. Hard-refresh the browser (Ctrl+Shift+R), sign in if necessary, and test Admin > AI Provider > Test saved connection.

## Workflow changes

- No second-person approval for new or edited knowledge or imported confirmed pairs.
- Save with a resolution -> internally published/searchable immediately. Save without one -> unresolved, excluded from fixes.
- Legacy publish/withdraw buttons removed. Archive remains permission-controlled; legacy knowledge.review permission is retained for archive administration, not required for normal saving.
- Each assistant answer gets Edit answer & save as knowledge for users with knowledge.create permission.
- The action prefills original issue + prior user follow-ups and attachments, and the selected answer as editable resolution. It does not save automatically. User corrects/verifies and explicitly clicks Save knowledge.
- A correction creates a new knowledge record by default, not a silent overwrite of source evidence. Existing records can still be edited through Library with existing edit permissions and optimistic versions.
- RBAC, workspace isolation, sanitization, attachment controls, audit and versions remain. This does not weaken login or server-side AI allowlists.
- Source-pair confirmation during extraction remains: it checks that the issue and solution belong together; it is not another person's approval.

## Provider changes

- At most three attempts for transient 502/503/504 or selected network/timeouts, exponential delay plus jitter, bounded Retry-After handling.
- No automatic retries for quota 429, authentication/permission 401/403, validation 400 or missing model 404. These require diagnosis rather than blind retries.
- Gemini compatible requests omit temperature; Google currently documents removal of sampling overrides for newer models. This is compatibility hardening, not a claim that temperature caused the observed 503.
- Safe diagnostics include upstream status, code/status and attempt count. No fabricated fallback answer or silent model switch.
- Each HTTP operation uses a 25-second inactivity timeout (5-second connect); long-running models may need deliberate timeout/proxy tuning. Retries may incur provider usage if a request was processed but its response was lost.

## Validation

15 targeted tests passed using synthetic source/database fixtures and mocked provider responses. Coverage: source transformations and JavaScript syntax, fail-closed mismatch, immediate-save state, resolved-draft migration/versions/audit, CLI backup/read-back, correction prefill with follow-up/attachment context, transient retry/success/bounds, no auth/quota retry, Gemini sampling omission, empty-response rejection and long Retry-After behavior.

The complete v3 archive could not be reopened as runnable source in this session, so full-app/browser regression was NOT rerun. No live provider call or modification to your machine was performed. The updater's dry run validates exact anchors on your real files before applying. Existing v3 tests/docs that require independent publication are superseded by this workflow policy and need updating; do not interpret their old approval assertions as the new desired behavior.

## Acceptance checks

1. Add a synthetic issue/resolution as Engineer; save; it should be searchable without another account's approval.
2. Edit it with allowed permissions; the new resolution remains searchable and version increases.
3. Import a file with issue+resolution, confirm extraction pairing, save; no separate approval.
4. Save an issue without a resolution; it remains unresolved and is not returned as a fix.
5. Generate an answer, choose Edit answer & save as knowledge, correct it, save; verify a new searchable record and no silent source overwrite.
6. Reader without knowledge.create cannot use the correction-save action; backend permissions remain enforced.
7. Verify other-workspace records are not returned.
8. Test saved AI connection; if upstream 503 remains, the service is still unavailable despite retry handling.

## Rollback

Stop the app. Preserve the current DB/WAL/SHM and updated source first. Restore the three source files from the printed backup folder and restore its database.db to the configured database path using your stopped-app restore procedure. Do not leave stale WAL/SHM sidecars next to a restored DB. Restart with matching source/database. A rollback discards changes made after that backup; preserve them before restoring. Protect upgrade-backups because it contains user/password hashes, sessions, knowledge and attachments. No backup is uploaded externally.

## References

- https://ai.google.dev/gemini-api/docs/troubleshooting
- https://ai.google.dev/gemini-api/docs/openai
- https://ai.google.dev/gemini-api/docs/models

Use only approved data/provider routes. This patch does not authorize sending organizational or customer information to a public model.
