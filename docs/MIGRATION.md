# Safe Upgrade from v2

**No in-place database upgrade.** v3 has new users, sessions, roles, attachments, two-field knowledge and conversations. Startup rejects an old v2 DB. Do not copy the v2 `.env` wholesale: USERS_JSON/tokens and embedding settings are obsolete.

1. Keep the old directory and consistent database/config backup.
2. In v2, export knowledge separately for each workspace through its Administrator export control. Preserve original exports securely.
3. Extract v3 to a new directory, create its environment/new DB and bootstrap an Administrator.
4. From the v3 root, import each v2 knowledge JSON export:

```bash
python scripts/import_v2.py /secure/path/inhouse-knowledge.json --owner YOUR_V3_ADMIN_USERNAME
```

5. Inspect imported records, correct pairings, complete missing resolutions and obtain independent review before publishing.
6. Validate staging before cutover. Keep v2 read-only for historical investigations/audit if required by approved retention.

The importer requires schema_version=2 and matching instance_id. It maps stable workspace IDs, converts source title/content to sanitized text and uses explicit Issue:/Resolution: headings when available. Unstructured old notes remain unresolved rather than guessing a fix. It creates new UUIDs/drafts, records old-to-new mappings in audit and prints them. Import is transactional; duplicates/errors roll it back. It does not mutate the source JSON/database.

Not migrated: v2 tokens/users, sessions, generated answers, feedback, old versions/audit chain, old embedding vectors or old metadata fields. Retain the old backup for those. The new import owner is recorded as author; original authorship remains in the old export/backup, not falsely attributed. This is knowledge transfer, not a complete historical migration. Review a staging import first.

AI settings are seeded from `.env` only on first v3 initialization. Afterward use Admin > AI Provider. Server secrets/allowlists still come from environment. Never send real LCM data to an unapproved public provider during migration testing.
