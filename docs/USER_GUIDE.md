# User Guide

## Sign in

Use your individual username/password. A temporary password must be changed before using the app. Forgot password directs you to an administrator; there is no recovery email service. Profile supports display-name and password changes. Password changes revoke all sessions.

## Workspaces

Choose Inhouse, Enable, RPA or MATE from the top workspace selector. LCM is the deployment name. Your granted workspaces and role determine available pages/actions. Changing workspace resets the active UI conversation, not saved history.

## Add Knowledge

Only two main fields: Issue / Email / Extracted Content and Resolution. Paste safe formatted email text, upload a whole email or attach files/images. Optional Environment/Server is collapsed. Review warnings. Save creates a draft, or unresolved if resolution is empty. Internal version/audit metadata is not an entry field.

If a document already contains both issue and solution: upload -> Review extracted issue-resolution pairs -> compare with source -> edit only if needed -> check each pairing -> Save reviewed cases as drafts. Multiple cases are separate records. You do not need to retype the solution. Missing or ambiguous solutions must not be invented. AI extraction is optional and requires approved provider configuration. Unsaved review edits remain in this tab; source uploads persist.

## Review

Knowledge Library shows draft/unresolved/published/archived records. Open a record to read content, download source attachments, edit, inspect internal versions or review if permitted. Author/latest editor cannot publish their own content, including Administrators. Another reviewer checks accuracy, applicability and sensitivity. Edits withdraw publication. Only published nonempty resolutions are retrieved as fixes.

## Solve Issue

Paste a whole email or describe the issue, attach files/images and send. Extraction warnings identify unreadable/unsupported content. Evidence-only mode returns historical evidence without calling AI. Approved AI mode can reason and continue follow-up questions with bounded conversation context. Images require OCR or enabled capable vision model. Validate applicability, risks and outcome; no commands are executed.

History resumes your private workspace investigations. Capture final resolution opens Add Knowledge with the issue; enter the engineer-validated outcome, not an untested AI suggestion. Old answers are snapshots and not proof of current source approval.

## Administrator

Users: create individual accounts, assign role/workspace grants, activate/disable, reset password and revoke sessions. Temporary passwords are shown once and require secure delivery. Roles & RBAC: create/edit/delete unassigned custom roles. Administrator is protected. Settings: approved provider/model/vision/extraction, security limits, branding PNG and instance name. Secrets and server network controls stay in environment configuration. Audit and maintenance: events, index rebuild, knowledge-only export, manual history purge. Full backup/restore is operator CLI.

Use the top theme control for light/dark mode. Only theme preference is stored in localStorage. Do not upload secrets or unapproved customer/personal data. Read SECURITY before operational use.
