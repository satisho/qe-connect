# QE Connect

QE Connect is a client-neutral QE Assessment survey platform, and the first part of a QE Community of Practice
platform. Install one copy per client organization and give it that organization's name and colour. The assessment team sets up the applications, respondents and question bank, sends each respondent a survey
link by email, follows progress on a tracker, and downloads each response as soon as it comes back.

Version 2.0.0. See [CHANGELOG.md](CHANGELOG.md). QE Connect 2.0 is the client-neutral version of QE Connect 1.0.1.

## Make it yours: organization branding

Each installation belongs to one client organization. Set it up once:

- **First run**: the setup screen asks for the organization name along with the first administrator.
- **Administration › Organization** (administrators): organization name, assessment team name (for example
  "Quality Engineering CoE") and accent colour (`#RRGGBB`, the client's brand colour). Leave the colour empty for the
  default teal.
- The invitation email can use `{organization}` and `{team_name}`; the default text already does.

The product name QE Connect stays on screen; the organization's name is shown beside it.

---

## Quick start (Windows laptop)

1. Install **Python 3.10 or newer** from <https://www.python.org/downloads/>. On the first installer screen, tick
   **Add python.exe to PATH**.
2. Unzip QE Connect into a folder you keep, for example `C:\QEConnect`.
3. Double-click **start.bat**. The first run sets up a private Python environment and installs QE Connect's
   components (about a minute, needs internet access to pypi.org). Your browser then opens
   <http://localhost:8000>.
4. Create the first administrator account.
5. Optional: **Administration › Load sample data** fills in example applications, questions and responses so you can
   look around. Loading it replaces everything, so do it before entering real data.

Keep the black window open while you use QE Connect; closing it stops the application. Run `start.bat` again any
time; it only reinstalls components when they change.

On macOS or Linux, run `./start.sh` instead.

Nothing else is needed: Node.js is only required if you change the web interface (see *Development*).

---

## How the survey runs

1. **Setup › Lines of business**: the LOB choices. They also come in automatically from the question bank's Lists
   sheet and from the applications import.
2. **Setup › Questions**: import the client's question bank workbook (for example `QA_Survey_Question_Bank.xlsx`)
   as it is. Every sheet that has *Q ID* and *Question* columns is read; columns are matched by header name, so order
   doesn't matter and a title row above the header is fine. Read columns: Q ID, Section, Pillar, Focus area,
   Question, Help text, Response type, Answer options (one per line in the cell), Required?, Priority (Core /
   Optional), Show-if logic, Source, EQA dimension.
   - Show-if rules are understood in the form `Show if B8 is not 'None' or 'Not known'` (also `is`, `includes`).
     A note that options *mirror the LOBs on the Lists tab* makes that question's choices follow the LOB list.
     Any other wording is flagged **Rule not recognised** and the question is always shown; use **Edit** to fix it.
   - **Preview survey** opens the survey exactly as respondents see it.
3. **Setup › Applications**: import from Excel (download the template from the import box) or add one at a time.
   Each application has one respondent email.
4. **Setup › Invitation email**: the message, with placeholders such as `{first_name}`, `{application}`,
   `{due_date}` and `{survey_link}`.
5. **Setup › Email delivery**: connect to Microsoft 365 or an SMTP relay and send a test email (see below).
6. **Tracker**: select applications and **Send survey**, choosing a respond-by date. Each respondent gets their own
   link. Status moves from *Sent* to *Opened*, *In progress* and *Completed*; the page refreshes itself.
   **Remind** sends the same link again. **Copy link** lets you share it another way. **Cancel** stops a link.
7. When a response is **Completed**, use **Download** (Excel) or **View**. **Export completed** gives one workbook
   with a *Summary* sheet (one row per application, one column per question) and an *Answers* sheet (one row per
   answer). **Reopen** lets a respondent change a submitted response with the same link.

Respondents don't sign in: the link is their key. Answers save as they go, so they can stop and come back. The
team's answers on file (name, LOB, application, delivery team) are filled in for them.

---

## Email delivery

Choose one route on **Setup › Email delivery**. Secrets never go into the portal or the database; they are set in
the `.env` file on the server and the page shows whether they are present.

**Microsoft 365 (Graph), recommended.** Ask the client's IT team for:
- an Entra ID app registration with the **Mail.Send** application permission and admin consent;
- an application access policy (or RBAC for Applications) limiting the app to the QE Connect mailbox only;
- a certificate (preferred) or client secret;
- a shared mailbox such as `qe-connect@example.com`;
- outbound HTTPS from the QE Connect server to `login.microsoftonline.com` and `graph.microsoft.com`.

Enter the tenant ID, client ID and mailbox on the page. Put the secret in `.env` as `QEC_MAIL_CLIENT_SECRET=...`,
or for a certificate set `QEC_MAIL_CERT_PATH` to the PEM private key file and enter the thumbprint on the page.
Restart QE Connect after changing `.env`.

**SMTP relay.** An Exchange receive connector, or an Exchange Online relay connector, that accepts mail from the
QE Connect server's IP address. Enter host, port and encryption. If the relay needs sign-in, enter the username on
the page and put the password in `.env` as `QEC_SMTP_PASSWORD`. Microsoft is retiring basic-auth SMTP in Exchange
Online, so prefer Graph or an IP-based connector.

**Not connected.** Emails are recorded under **Sent emails** but not sent. Useful for dry runs; you can still copy
survey links from the tracker.

Emails are queued and sent in the background at the **Most emails per minute** rate (Exchange Online allows about 30
a minute per mailbox). Failed emails are retried twice, then shown as **Failed** with the reason and a **Try again**
button.

**Survey link address** must be reachable from respondents' computers and phones, for example
`https://qe-connect.example.local`. If it is empty, `QEC_PUBLIC_URL` is used.

---

## Your data and backups

Everything is in the **data** folder next to `start.bat` (`data/qe-connect.db`). To back up, stop QE Connect and copy
the folder; or use **Administration › Download backup** while it runs. That backup holds applications, respondents,
questions, settings, survey links, responses and sent emails, encrypted with a password you choose (AES-256-GCM);
team accounts and server secrets are not included. Keep the password safe: the backup can't be opened without it.
**Restore from a backup** replaces everything except team accounts (1.0.0 JSON backups can also be restored).
The data folder itself is not encrypted by QE Connect; put it on an encrypted disk.

To use PostgreSQL instead of SQLite, set `QEC_DATABASE_URL` in `.env` (start.bat installs the driver). The schema is
created and upgraded automatically at start-up.

---

## Configuration

Copy `.env.example` to `.env` and change what you need. All settings are optional.

| Setting | Default | What it does |
|---|---|---|
| `QEC_HOST` | `127.0.0.1` | `0.0.0.0` lets other computers connect (open the port in the firewall) |
| `QEC_PORT` | `8000` | Port to listen on |
| `QEC_PUBLIC_URL` | `http://localhost:<port>` | Address people use; default base for survey links |
| `QEC_DATA_DIR` | `data` | Folder for the SQLite database |
| `QEC_DATABASE_URL` | (SQLite) | e.g. `postgresql+psycopg://user:pass@host:5432/qec` |
| `QEC_SESSION_HOURS` | `12` | Hours before team members sign in again |
| `QEC_SECURE_COOKIES` | `false` | Send the sign-in cookie only over HTTPS (automatic on HTTPS requests) |
| `QEC_TLS_CERT`, `QEC_TLS_KEY` | | PEM certificate and key: QE Connect serves HTTPS itself |
| `QEC_TRUSTED_PROXIES` | | Reverse proxy addresses (e.g. `127.0.0.1`) so client addresses and HTTPS are seen correctly |
| `QEC_ALLOWED_HOSTS` | | Extra host names to answer to (localhost and the `QEC_PUBLIC_URL` host are always allowed; `*` allows any) |
| `QEC_MAIL_CLIENT_SECRET` | | Microsoft 365 app client secret |
| `QEC_MAIL_CERT_PATH` | | PEM private key for certificate sign-in to Microsoft 365 |
| `QEC_SMTP_PASSWORD` | | Password for an SMTP relay that needs sign-in |
| `QEC_MAIL_WORKER` | `true` | `false` stops this server sending queued emails |
| `QEC_API_DOCS` | `false` | Interactive API docs at `/api/docs` |
| `QEC_LOG_LEVEL` | `info` | `debug`, `info`, `warning`, `error` |

Use forward slashes in paths, even on Windows.

---

## Hosting for the team

- **Just you**: the default. Only this computer can open <http://localhost:8000>.
- **Colleagues on the same network**: set `QEC_HOST=0.0.0.0`, `QEC_PUBLIC_URL=http://<computer-name>:8000` and
  `QEC_ALLOWED_HOSTS=<computer-name>,<computer-name>.<domain>`,
  allow port 8000 in Windows Firewall, and share that address. A laptop that sleeps takes the survey offline, so this
  suits a short pilot only.
- **Client network (recommended for the real survey)**: a small Windows or Linux server or VM; an internal DNS
  name such as `qe-connect.example.local`; an HTTPS certificate from the client's internal certificate authority
  (put both the short and full names in the certificate); a reverse proxy (IIS, nginx) on port 443 in front of
  QE Connect; QE Connect run as a service (NSSM on Windows, systemd on Linux); `QEC_TRUSTED_PROXIES` set to the proxy's
  address; `QEC_SECURE_COOKIES=true`; sign-in codes required for everyone; nightly
  backups of the data folder or database; an encrypted disk. Don't expose a laptop to the internet.
- **Docker with PostgreSQL**: copy `deploy/.env.docker.example` to `deploy/.env`, set the passwords, then run
  `docker compose -f deploy/docker-compose.yml up -d --build`. The container runs as a non-root user with a health
  check.

---

## Security

- Team sign-in uses local accounts. Passwords are hashed with scrypt; sessions are random tokens stored hashed, in
  HttpOnly, SameSite=Strict cookies; every change needs a custom request header (protects against cross-site
  requests); after 5 failed sign-ins for an account, or 20 from one address, in 15 minutes, sign-in is blocked for
  that account or address (counted from the security log).
- **Sign-in codes**: anyone can turn on an authenticator app (Microsoft Authenticator, Google Authenticator and
  others) from the account menu; **Administration › Sign-in security** can require it for everyone. Lost phone: an
  administrator uses **Team › Reset codes**, or on the server run
  `..\.venv\Scripts\python -m app --reset-mfa someone@example.com` from the `backend` folder.
- Sessions end after 30 minutes without activity (changeable) and after 12 hours at most.
- **Security log** (Admin › Security log): sign-ins including failures and blocks, sign-outs, sign-in codes, account,
  role and policy changes, downloads, exports and deletions; filter and download as CSV.
- **HTTPS**: set `QEC_TLS_CERT` and `QEC_TLS_KEY` for built-in HTTPS, or run behind a reverse proxy and set
  `QEC_TRUSTED_PROXIES`. HSTS is sent over HTTPS and the sign-in cookie is then Secure.
- Requests are limited in size before they are read; uploaded workbooks are size-checked and parsed with defusedxml.
- QE Connect only answers to known host names; survey links are masked in the server log.
- Backups are encrypted with a password you choose.
- Installs are checked against published package hashes (`backend/requirements.lock`).
- Roles: **admin** (everything, including email delivery, team and backups), **editor** (setup, sending,
  downloads), **viewer** (tracker and downloads).
- A strict Content Security Policy, no third-party scripts, fonts or trackers; the interface makes no outside calls.
- Survey links are long random tokens. A link only opens its own application's survey, and can be cancelled.
- Free-text answers are neutralised in downloads so spreadsheet formulas can't run.
- Uploads are limited to 10 MB of .xlsx, .csv or text.
- The only outbound connections are to the email route you configure.
- The activity log records sign-ins, changes, sends, downloads and survey submissions.

Forgotten administrator password: stop QE Connect, open a command prompt in the `backend` folder and run
`..\.venv\Scripts\python -m app --reset-password you@example.com`.

Upgrading from 1.0.x: stop QE Connect, back up the `data` folder, unzip 2.0 over the old folder (keep `data` and
`.env`), and run `start.bat`. The database is upgraded automatically; then set **Administration › Organization**.

---

## Troubleshooting

| Problem | What to do |
|---|---|
| start.bat says Python is missing | Install Python 3.10+ with **Add python.exe to PATH** ticked, then run start.bat again |
| Install fails | Check internet or proxy access to pypi.org; delete the `.venv` folder and try again |
| Port 8000 is in use | Set `QEC_PORT=8010` in `.env` |
| "QE Connect doesn't answer to this address" | Add the name people use (e.g. the computer name) to `QEC_ALLOWED_HOSTS` |
| Someone lost the phone with their authenticator app | **Team › Reset codes**, or `python -m app --reset-mfa <email>` on the server |
| Colleagues can't open it | `QEC_HOST=0.0.0.0`, firewall rule for the port, and use the computer name in `QEC_PUBLIC_URL` |
| Respondents' links don't open | Set **Survey link address** to an address their devices can reach |
| Test email fails | The checklist on the Email delivery page names the problem; for Graph, check the secret and the Mail.Send consent |
| "The database was created by a newer version" | You started an older QE Connect on newer data. Run the newer version, or restore a backup of the data folder |

---

## Development

```
cd backend
python -m venv ../.venv && ../.venv/bin/pip install -r requirements-dev.txt
# after changing requirements.txt, regenerate the hash-locked files:
uv pip compile requirements.txt --universal --python-version 3.10 --generate-hashes -o requirements.lock
uv pip compile requirements.txt requirements-postgres.txt --universal --python-version 3.10 --generate-hashes -o requirements-postgres.lock
../.venv/bin/python -m pytest              # backend tests (SQLite)
QEC_TEST_DATABASE_URL=postgresql+psycopg://... ../.venv/bin/python -m pytest   # same tests on PostgreSQL
../.venv/bin/python -m app                 # API and built UI on :8000

cd ../frontend
npm install
npm run dev                                # UI with hot reload on :5173, proxying /api to :8000
npm run build                              # rebuilds frontend/dist, which the backend serves
```

Layout: `backend/app` (FastAPI, SQLAlchemy 2.0, Alembic migrations run at start-up), `backend/tests` (pytest),
`frontend` (React, TypeScript, Vite, React Query; the built `dist` folder is shipped), `deploy` (Docker).
