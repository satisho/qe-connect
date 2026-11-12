# Changelog

## 2.0.0 (2026-11-11) — QE Connect

QE Connect 2.0 is **client-neutral**: install one copy per client organization and give it that organization's name
and colour. Every 1.0.1 feature
and security control is kept; nothing about the survey, tracker, email delivery, backups or sign-in has been removed.

- **Organization branding** (Administration › Organization, admins only): organization name, assessment team name and
  an accent colour. They appear in the portal header, the sign-in page, the respondent's survey and the invitation
  email's survey button. The first-run setup screen asks for the organization name.
- **New email placeholders** `{organization}` and `{team_name}`. The default invitation email uses them, so it reads
  correctly for any client. Without a name set, emails say "your organization".
- **Client-neutral content**: the sample data, question examples, answer options, import templates, hints, email
  delivery guidance and documentation no longer mention a specific client. Sample addresses use `example.com`.
- **New look**: new QE Connect mark and a neutral deep-teal theme (light and dark), replaced by the organization's colour
  when one is set.
- **Upgrading from 1.0.x**: unzip 2.0 over the old folder (keep `data` and `.env`); the database is upgraded
  automatically and 1.0.x backups still restore. Existing settings are kept; set Administration › Organization.
- Settings keep the `QEC_` prefix, so existing `.env` files work unchanged.
- Tests for branding, its permissions and validation, backups, and a check that no client-specific text ships.

## 1.0.1 (2026-10-27) — QE Connect security release

Fixes every finding from the 1.0.0 security review pack that can be fixed in the application. No new survey features.

- **Sign-in codes (MFA)**: authenticator-app codes (TOTP) for team accounts, optional per person or required for
  everyone (Administration › Sign-in security); a used code can't be reused; administrators can reset a lost phone;
  `python -m app --reset-mfa <email>` recovers from the server. (SEC-05)
- **Security log**: sign-ins (successful, failed and blocked), sign-outs, inactivity sign-outs, sign-in code events,
  password, account, role and policy changes, downloads, exports and deletions, with an admin page, filters and CSV
  download. (SEC-06)
- **HTTPS**: built-in HTTPS with `QEC_TLS_CERT` / `QEC_TLS_KEY`; HSTS on HTTPS; Secure cookies automatically over HTTPS;
  `QEC_TRUSTED_PROXIES` for a reverse proxy; Permissions-Policy header. (SEC-07)
- **Email queue**: line breaks are removed from names and email headers, and an unexpected error on one email marks it
  Failed instead of stopping the queue. (SEC-01)
- **Uploads**: workbooks are size-checked before parsing (unpacked size, parts, sheets) and parsed with defusedxml. (SEC-02)
- **Request limits**: 1 MB for normal requests, 11 MB for imports, 51 MB for backups, enforced before any parsing. (SEC-03)
- **Logs**: survey links are masked in the access log. (SEC-04)
- **Inactivity timeout**: 30 minutes by default, set on the Administration page. (SEC-08)
- **Sign-in throttle** is counted from the security log, per account and per client address, so it survives restarts. (SEC-09)
- Respondent reference numbers are generated separately from the survey link. (SEC-10)
- Installs are hash-checked from `requirements.lock`; start scripts and Docker use it. (SEC-11)
- certifi updated to 2026.10.19: earlier versions trust a compromised certificate authority root (GHSA-6q48-6c7w-9gw2,
  found by the 1.0.1 dependency scan). It is used when signing in to Microsoft 365 for email.
- QE Connect only answers to known host names (`QEC_ALLOWED_HOSTS`). (SEC-12)
- GitHub Actions checks (tests on SQLite and PostgreSQL, dependency scans) and Dependabot. (SEC-13)
- Backups are encrypted with a password you choose (AES-256-GCM); 1.0.0 JSON backups can still be restored. (SEC-14)
- Database migration 0002 adds the new columns and the security log; existing data is kept and each survey gets its own
  reference. Downgrade is supported.

## 1.0.0 (2026-10-27) — QE Connect

First release of QE Connect, phase 1 of the QE Community of Practice platform: the QE Assessment survey.

- **Assessment portal** for the QE Assessment team, with local accounts and three roles (admin, editor, viewer).
- **Setup**: lines of business; applications with their respondent; the question bank. Each can be imported from
  Excel (.xlsx) or CSV, or pasted from Excel. The question bank workbook is read as-is: every sheet with Q ID and
  Question columns, multi-line answer options, Required, Priority (Core / Optional) and Show-if logic, plus the LOB
  column of a Lists sheet. Unreadable show-if rules are flagged and can be fixed in the portal.
- **Invitation email** template with placeholders and a live preview.
- **Email delivery** through Microsoft 365 (Graph, client secret or certificate) or an SMTP relay (Exchange receive
  connector or Exchange Online relay), with a test email, a send queue paced to a per-minute limit, retries, and a
  "not connected" mode that records emails without sending them.
- **Tracker**: send invitations and reminders, copy or cancel a survey link, follow status (Not sent, Sent, Opened,
  In progress, Completed) and progress, view a response, reopen it, and download it as Excel or CSV, one at a time
  or all completed responses together.
- **Respondent survey** from the emailed link: core or full survey, answers the team already knows filled in, show-if
  rules, "Other (please specify)", autosave, review and submit; works on phones.
- Activity log, workspace backup and restore (JSON), one-click sample data, first-run setup, password recovery from
  the command line.
- Runs on a Windows laptop with Python 3.10+ (start.bat), or in Docker with PostgreSQL.
