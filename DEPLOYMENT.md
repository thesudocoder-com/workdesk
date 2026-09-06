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

Before each upgrade, stop writes and make a database backup. Pull or install the release, run
`uv run alembic upgrade head`, then restart and check `/health`, login, and a static asset.
Schema downgrades are intentionally not automatic. To roll back, stop the service, restore the
pre-upgrade database backup, deploy the prior application release, and restart.

## Backup and restore

For a consistent online SQLite backup, run `sqlite3 /data/workdesk.db ".backup '/backup/workdesk-YYYYMMDD.db'"`
(use `/var/lib/workdesk/workdesk.db` for systemd). Copy the backup off-host and periodically
test it. To restore, stop WorkDesk, preserve the current database, copy the selected backup into
the configured path with the correct owner and permissions, run migrations, and restart.
