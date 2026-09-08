# WorkDesk deployment and recovery

WorkDesk is a single-workspace service. Run exactly one application worker when using SQLite.
Terminate TLS at a reverse proxy and expose port 8010 only on the loopback interface.

## Docker Compose installation

1. Copy `.env.production.example` to `.env.production`, generate distinct random setup and
   session secrets, set the public HTTPS URL, and restrict the file to its owner.
2. Run `docker compose up -d --build`. The container upgrades the persistent database before
   starting the one-worker server and is monitored through `/health`.
3. Open the public URL. The empty installation redirects to `/Setup`; enter the setup token
   once to create the business workspace and first Developer.

Database files live in the named `workdesk-data` volume. No image contains a database or user.

## systemd installation

Create an unprivileged `workdesk` service account, install the application at `/opt/workdesk`,
and create `/var/lib/workdesk` owned by that account. Put production variables in
`/etc/workdesk.env`, owned by root with mode `0600`, including:

```ini
WORKDESK_ENV=production
WORKDESK_DATABASE_URL=sqlite:////var/lib/workdesk/workdesk.db
WORKDESK_SESSION_SECRET=...
WORKDESK_SETUP_TOKEN=...
WORKDESK_PUBLIC_URL=https://workdesk.example.com
WORKDESK_SESSION_SECURE=true
WORKDESK_FINANCE_V2_ENABLED=false
```

Run migrations as the service account with `uv run alembic upgrade head`, then install:

```ini
[Unit]
Description=WorkDesk
After=network.target

[Service]
User=workdesk
Group=workdesk
WorkingDirectory=/opt/workdesk
EnvironmentFile=/etc/workdesk.env
ExecStartPre=/usr/local/bin/uv run alembic upgrade head
ExecStart=/usr/local/bin/uv run uvicorn Application.Main:app --host 127.0.0.1 --port 8010 --workers 1
Restart=on-failure
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/var/lib/workdesk

[Install]
WantedBy=multi-user.target
```

Place nginx, Caddy, or another TLS reverse proxy in front of the loopback listener.

## Upgrade and rollback

Never make an arbitrary `git pull` responsible for a production data conversion. Select a
tested release tag, stop writes, and verify a restorable database backup first. The financial
upgrade is deliberately split into an additive schema migration and an explicit, idempotent
data migration:

```bash
git fetch --tags
git checkout <tested-release-tag>
uv sync --frozen
uv run pytest
uv run alembic upgrade head
uv run workdesk finance-migrate
uv run workdesk finance-migrate --apply
uv run workdesk finance-migrate --apply
```

The first finance command is a dry-run and prints counts without writing. The first `--apply`
creates normalized contacts, agreements, instalments, recurring services, invoice lines, and
payment allocations from unambiguous legacy data. The second `--apply` must report zero for
every category. Ambiguous contact names and missing recurrence dates are recorded in
`migration_reviews`; the migrator does not guess them.

Restart and check `/health`, login, old client/project/invoice URLs, the Finance totals, and
the Calendar agenda. Reconcile contracted, scheduled, invoiced, collected, and outstanding
amounts before setting `WORKDESK_FINANCE_V2_ENABLED=true` for all users.

The schema migration does not rename or remove legacy columns and its downgrade is
intentionally non-destructive. The prior application can run against the additive schema. If
an application rollback is insufficient, stop the service, preserve the failed database for
diagnosis, restore the verified pre-upgrade backup, deploy the prior release, and restart.

### Staging rehearsal checklist

- Restore an anonymized production backup on a VM matching production.
- Deploy the exact candidate commit and install only the lockfile.
- Run schema migration, finance dry-run, apply, and the zero-change second apply.
- Compare row counts and financial totals before and after migration.
- Verify legacy routes plus client, engagement, finance, invoice, and calendar screens.
- Exercise 360, 390, 430, and 768 px viewports.
- Confirm logs, scheduled jobs, backup restore, and the rollback release.

## Backup and restore

For a consistent online SQLite backup, run `sqlite3 /data/workdesk.db ".backup '/backup/workdesk-YYYYMMDD.db'"`
(use `/var/lib/workdesk/workdesk.db` for systemd). Copy the backup off-host and periodically
test it. To restore, stop WorkDesk, preserve the current database, copy the selected backup into
the configured path with the correct owner and permissions, run migrations, and restart.
