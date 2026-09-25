# Deployment

## Docker Compose

```bash
cd docker
docker-compose up -d
```

`docker/docker-compose.yml` defines four services: `postgres`, `backend`,
`n8n`, `frontend`. Its `build.context`, `env_file`, and bind-mount paths
(`../backend`, `../frontend`, `../n8n/workflows`) are relative to the compose
file's own directory (`docker/`) — this matches the `cd docker` step above.
**These paths were pointing at `./backend`/`./frontend`/`./n8n` (i.e.
`docker/backend` etc., which don't exist) until this pass** — that bug meant
`docker-compose up` would have failed immediately on a missing build context.
If you ever move the compose file, every one of these paths needs re-deriving
relative to its new location, not copied as-is.

Inter-container communication uses Docker service names, not `localhost`:
the backend's `DATABASE_URL`/`SYNC_DATABASE_URL` point at `postgres:5432`,
not `localhost:5432`. The one exception is the **frontend's**
`NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1` — that's intentional, since
`NEXT_PUBLIC_*` variables are consumed by the *browser*, not by another
container, and the browser reaches the backend through its published port on
the host, not through the Docker network.

### Environment variables the backend service needs

Secrets (`TELEGRAM_BOT_TOKEN`, `WHATSAPP_ACCESS_TOKEN`, `META_ACCESS_TOKEN`,
API keys, etc.) are **not** set in `docker-compose.yml` — they flow in via
`env_file: ../backend/.env`, which is gitignored. Never add a real secret to
the compose file itself; it gets committed.

Non-secret provider switches are set directly in the compose file's
`environment:` block with safe defaults, overridable via shell env vars:

- `AI_TEXT_PROVIDER` (default `local`)
- `PUBLIC_MEDIA_BASE_URL` (default empty → falls back to `STATIC_BASE_URL`).
  **This must be set to a publicly reachable URL before Instagram/Facebook/
  WhatsApp posting can work live** — a Docker-internal address like
  `http://backend:8000` is not reachable from those platforms' servers. See
  [social-media-integration.md](social-media-integration.md).

### Database migrations in Docker

The backend container's `DATABASE_URL`/`SYNC_DATABASE_URL` point at
PostgreSQL. Run migrations against it explicitly — they are not applied
automatically on container start:

```bash
docker compose exec backend alembic upgrade head
```

All migrations under `backend/alembic/versions/` use plain
`op.add_column`/`sa.Boolean`/`sa.DateTime` — no SQLite-only batch mode — so
they apply the same way to PostgreSQL as to the SQLite dev database.

### What has and hasn't been verified

`docker` is not installed in this development environment, so `docker compose
config` and a live `alembic upgrade head` against a running Postgres
container could not actually be executed as part of this pass. The compose
file's paths were instead audited by hand and confirmed (via a script
resolving them exactly as Compose would) to now point at real files. Treat
the "Environment variables" and "Database migrations" sections above as
correct-by-inspection, not run-verified, until someone runs them against a
real Docker daemon.

## Manual (non-Docker) deployment

Run the backend and frontend as ordinary long-lived processes behind
whatever process manager/reverse proxy you use elsewhere — there is nothing
Docker-specific baked into either. The backend needs `DATABASE_URL` pointed
at a real PostgreSQL instance and `alembic upgrade head` run once against it
before first start. The frontend needs `NEXT_PUBLIC_API_URL` pointed at
wherever the backend is actually reachable from the browser.
