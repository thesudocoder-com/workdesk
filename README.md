# WorkDesk

WorkDesk is a private, server-rendered operations desk for one small business. It connects
client organizations and contacts to engagements, delivery projects, fixed-fee agreements,
instalments, recurring services, invoices, payment allocations, expenses, a derived calendar,
reports, and team access using Litestar, SQLAlchemy, Jinja, and a pinned local HTMX transport.

## Local first run

```bash
uv sync
export WORKDESK_SETUP_TOKEN='choose-a-local-setup-token'
uv run alembic upgrade head
uv run litestar --app Application.Main:app run --reload --port 8010
```

Open `http://127.0.0.1:8010`. A new database is empty and redirects to `/Setup`. Enter the
environment setup token, workspace name, and first Developer credentials. There are no demo
users, demo credentials, or automatic records.

Developers can add teammates with temporary passwords. A teammate must replace that password
at first login. Password resets, deactivation, and security-sensitive role changes invalidate
existing signed sessions. WorkDesk always protects the final active Developer and prevents
self-deactivation.

## Workflow

Use **New project** for the guided Client → Engagement → Project flow. Existing client and
engagement detail pages can enter the same wizard with safe preselection. Tasks require open
projects; milestones and invoices require active engagements; payments require an outstanding
invoice. All referenced records are revalidated on the server.

Workspace identity, address, timezone, currency, invoice prefix, payment terms, tax details,
and footer are editable under Settings. Secrets, database location, public URL, and cookie
security remain environment configuration.

Invoices can be printed from the browser or downloaded as private, on-demand PDF files. The
PDF is generated from the current invoice and workspace settings and is not stored on disk.

The normalized finance model is additive. Existing milestones, invoice fields, payment links,
IDs, and routes remain available as compatibility surfaces. New writes also create invoice
lines and payment allocations. Recurring billing dates create forecast occurrences; they do
not become receivables until invoiced.

Client workspaces group each engagement with its delivery projects, fixed-fee position, and
recurring services. Project pages surface the linked engagement and provide a direct recurring
service action. Recurring service pages support editing safe commercial fields, pausing,
resuming, cancelling, and reviewing the forecast schedule without rewriting historical dates.
The Calendar provides responsive month and agenda views with client, engagement, and project
filters. The Dashboard clock shows the current local time for the workspace timezone rather
than exposing its raw IANA identifier.

## Database and tests

```bash
uv run alembic upgrade head
uv run workdesk finance-migrate          # dry-run; never writes
uv run workdesk finance-migrate --apply  # explicit, safe to rerun
uv run pytest
```

Alembic owns schema creation and upgrades. SQLite enables foreign keys, WAL, and a busy timeout.
Use one application worker. Invoice numbers use a persisted monotonic counter rather than row
count, so deletions do not recycle identifiers.

See [DEPLOYMENT.md](DEPLOYMENT.md) for Docker Compose and systemd installation, TLS, upgrades,
backup, restore, and rollback.
