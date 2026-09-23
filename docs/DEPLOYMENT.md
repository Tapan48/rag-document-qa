# Oracle deployment: private access through SSH

This setup targets Ubuntu 24.04 on an ARM64 Oracle A1 VM with 2 OCPUs,
12 GB RAM, and a 50 GB boot volume. Docker Engine, the Compose plugin, Git,
and SSH access must already work. It also builds on AMD64.

The production frontend is a compiled React bundle served by Caddy. Only
`127.0.0.1:8080` is published on the server. PostgreSQL, Redis, and FastAPI
are reachable only inside Docker. Use an SSH tunnel to access the site;
do not open Oracle ingress ports 8080, 8000, 5432, or 6379.

This is a single-server portfolio deployment, without high availability or
public HTTPS. OpenAI calls remain separately billed. The production files
do not resize the VM or change your Oracle subscription.

## 1. Get the code and configure secrets

After the production commits have been pushed by the repository owner,
run on the server:

```bash
git clone https://github.com/Tapan48/rag-document-qa.git
cd rag-document-qa
umask 077
cp .env.production.example .env.production
chmod 600 .env.production
openssl rand -hex 32
openssl rand -hex 32
```

Edit `.env.production` with your preferred editor. Use the two independently
generated values for `POSTGRES_PASSWORD` and `JWT_SECRET`, and set your real
`OPENAI_API_KEY`. Do not use the same value for both secrets. The entrypoint
requires each generated secret to be exactly 64 hexadecimal characters.
The database username and database name are both `rag`; the connection URL
is derived from the same password used to initialize PostgreSQL.

Model names and generation settings remain configurable. Embeddings stay
at 1536 dimensions to match the existing schema. No secrets are passed to
the frontend build or web server. Migration containers receive only database
credentials. `.env.production`, SSH keys, uploads, and backups are ignored
by Git and excluded from Docker builds. Never paste secrets into issue
reports, screenshots, or shell commands that will enter shell history.

Define this helper in the server shell, from the repository root:

```bash
dc() {
  sudo docker compose --env-file .env.production -f compose.prod.yml -p rag-prod "$@"
}
```

Run it again after opening a new SSH session. All commands below use this
helper. `--env-file` is essential: it supplies Compose interpolation values;
the development `.env` is not the production configuration.

## 2. First deployment

Run each command only after the previous one succeeds:

```bash
dc config --quiet
dc build api frontend
dc up -d --wait db redis
dc run --rm migrate
dc up -d --wait api worker frontend
dc ps
curl --fail http://127.0.0.1:8080/api/health
```

`config --quiet` validates without printing resolved credentials. Avoid plain
`docker compose config` when recording output. Missing required secrets fail
configuration; invalid database/JWT secrets fail the backend entrypoint.

The `migrate` service is a one-off tool, excluded from ordinary `up` by its
profile. **Do not start API/worker if migration fails.** Compose does not
automatically gate their startup on a previous manual migration. Startup
health checks wait for PostgreSQL and Redis; `/health` is API liveness,
not a complete dependency or OpenAI check.

The API runs one Uvicorn process with no reload; Celery uses two worker
processes. Application and frontend run as UID/GID `10001:10001`. A fresh
uploads volume inherits writable ownership from the backend image.

## 3. Connect from your computer

In a separate local terminal, replace the key path and IP:

```bash
ssh -N -o ExitOnForwardFailure=yes \
  -L 8080:127.0.0.1:8080 \
  -i /path/to/private.key ubuntu@YOUR_SERVER_IP
```

Keep this terminal open. Visit:

- Application: http://localhost:8080
- Swagger: http://localhost:8080/api/docs
- Health: http://localhost:8080/api/health

The network hop to the VM is encrypted by SSH. HTTP runs on the loopback
endpoints and Docker network. If local port 8080 is occupied, use
`-L 8081:127.0.0.1:8080` and browse `http://localhost:8081`.

Verify registration/login, a sample upload reaching `ready`, an answer with
citations, a stopped stream, and page refresh on `/workspace`. Perform one
complete real-provider smoke test here before calling the Oracle deployment
verified. Local mocked verification does not prove API credit or model access.

## 4. Updates and shutdown

Before updating, make the backup below and record `git rev-parse HEAD`.
Stop new traffic and allow ingestion to finish before stopping the worker.

```bash
dc stop frontend api worker
git pull --ff-only
dc config --quiet
dc build api frontend
dc up -d --wait db redis
dc run --rm migrate
dc up -d --force-recreate --wait api worker frontend
```

Stop on any failed command. Environment changes require recreation; a plain
restart does not reload `.env.production`. Never change `POSTGRES_PASSWORD`
on an initialized volume without also rotating the PostgreSQL role password:
the image's initialization variables only create credentials on first boot.

Normal shutdown preserves volumes:

```bash
dc down
```

**Do not use `down -v` on a deployment with data.** The project name `rag-prod`
keeps volume names stable: `rag-prod_pgdata`, `rag-prod_redisdata`, and
`rag-prod_uploads`. Service restart policies restart containers after a host
reboot, but they do not repair application failures or rerun migrations.

If an update fails, leave API/worker stopped while investigating. Returning
to an older code revision is safe only if its schema is compatible. Otherwise
restore a matching backup and code revision; do not blindly downgrade Alembic.

## 5. Backup and restore

Keep an off-server copy of backups and securely retain `.env.production`
separately. A volume on the same VM is persistence, not a disaster backup.

For a consistent backup, stop new requests, let queued ingestion finish,
then stop API/worker. Before proceeding, this query must return `0`:

```bash
dc stop frontend
dc exec -T db psql -U rag -d rag -tAc \
  "SELECT count(*) FROM documents WHERE status IN ('QUEUED', 'PROCESSING');"
```

If jobs remain, let the worker finish; investigate failed/stuck jobs before
continuing. Then:

```bash
dc stop api worker
umask 077
backup_dir="backups/$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "$backup_dir"
git rev-parse HEAD > "$backup_dir/revision.txt"
dc exec -T db pg_dump -U rag -d rag -Fc > "$backup_dir/database.dump"
dc run --rm --no-deps -T --entrypoint tar api \
  -C /data/uploads -czf - . > "$backup_dir/uploads.tar.gz"
dc up -d --wait api worker frontend
```

Check every command's exit status and the archive sizes before relying on
the backup. Restart services after resolving any backup failure.
These backups include password hashes and uploaded documents: keep them private.
Redis AOF survives routine recreation, but this disaster backup intentionally
requires an empty ingestion queue and restores database/files only.

For recovery, check out the revision saved with the backup and configure
the retained environment. Build the images and start only healthy DB/Redis.
Keep frontend/API/worker stopped. Use an empty uploads volume for a clean
recovery. Replace the backup directory below:

```bash
backup_dir="backups/YOUR_BACKUP_TIMESTAMP"
dc exec -T db pg_restore -U rag -d rag --clean --if-exists \
  --no-owner --exit-on-error < "$backup_dir/database.dump"
dc run --rm --no-deps -T --entrypoint tar api \
  -C /data/uploads -xzf - < "$backup_dir/uploads.tar.gz"
dc run --rm migrate
dc up -d --wait api worker frontend
```

The restore overwrites matching database objects: use it only for deliberate
recovery. Restore into a stopped deployment without leftover queued Redis
tasks; a fresh VM/Compose project is the simplest disaster-recovery target.
Repeat the login, document listing, and citation smoke checks after restoring.

## 6. Troubleshooting and limits

```bash
dc ps
dc logs --tail 100 api worker frontend
dc exec -T db psql -U rag -d rag -c '\dx vector'
dc exec -T worker celery -A app.celery_app inspect ping
```

- All images support ARM64. Do not force `linux/amd64` on the Oracle A1 VM.
- Docker logs rotate at 10 MB, retaining three files per service. Application
  documents and database storage still grow; monitor disk usage.
- An old uploads volume may need its ownership repaired to `10001:10001`.
  Back it up first; do not solve permissions with world-writable modes.
- Graceful shutdown allows 75 seconds for API and 120 seconds for the worker.
  Forced termination can leave ingestion stuck: Redis persistence does not
  add job-recovery guarantees to the existing Celery implementation. Delete
  and re-upload a stuck document after investigating the failure.
- The current JWT/sessionStorage design and lack of public abuse controls
  remain portfolio limitations. A public launch needs a separate HTTPS,
  access-control, and usage-limit review. Do not simply change the loopback
  binding to a public address.
- Image major-version tags can change on rebuild. Record tested image IDs
  with releases and retest before deploying rebuilt images.

## Verification record

Verified locally on ARM64 Docker Desktop with isolated database/Redis volumes
and a mock OpenAI HTTP service (no real provider requests):

- Both production images built; app/frontend run as UID 10001.
- Fresh migrations, all five service health checks, and loopback-only binding.
- 137 backend tests passed, including eight production entrypoint tests.
- 49 frontend tests, type checking, and production build passed. Lint passed
  with three existing Fast Refresh warnings in UI components.
- Proxy health, Swagger prefix, SPA refresh, registration/login, upload,
  Celery ingestion, stored vectors, and cited answers passed.
- Incremental SSE, upstream cancellation on disconnect, provider-error events,
  cross-user isolation, and oversized/unsupported upload rejection passed.
- Data, vectors, uploaded files, and Redis values survived container recreation.
- PostgreSQL dump/restore preserved vector rows; the uploads archive restored
  into a separate volume using the non-root application user.
- Production login rendered in a browser without JavaScript errors.
- Blank production configuration was rejected. Image-layer inspection found
  no environment files, SSH keys, local assignment PDF, or baked credential
  variables in either application image.

Oracle application deployment and a real-provider smoke test are still pending.
The existing development stack was kept running during verification.
