# Deployment Plan

1. **Create an Oracle Cloud instance** — Ubuntu 24.04 ARM64, Always Free–eligible Ampere A1, 2 OCPUs, 12 GB RAM, and a 50 GB boot disk.

2. **Configure networking and SSH** — Use a public subnet, internet gateway, and public IP; save the SSH private key securely.

3. **Install server tools** — Connect through SSH and install Docker, Docker Compose, and Git; verify Docker works.

4. **Prepare production files** — Add production Dockerfiles, Compose configuration, Caddy, health checks, and persistent volumes. Keep secrets and SSH keys ignored by Git.

5. **Configure production secrets** — Clone the GitHub repository and create `.env.production` with database credentials, JWT secret, and the OpenAI API key.

6. **Start the application** — Start PostgreSQL and Redis, run migrations, then start the API, Celery worker, and frontend. Verify health and access through an SSH tunnel.

7. **Enable public HTTPS** — Point `tapan-rag.duckdns.org` to the server, allow ports 80/443, and configure Caddy for automatic HTTPS.

8. **Verify and maintain releases** — Test uploads, ingestion, answers, and citations. For updates: test → scan for secrets → commit → push → pull on Oracle → rebuild affected services → verify health.


## Shared Caddy entry point for ticket booking (2026-10-08)

Public 80/443 remain mapped to the RAG frontend's internal 8080/8443. Caddy keeps
the original RAG API/static/SSE routes and adds `event-ticket-booking.duckdns.org`,
forwarded with verified TLS to `ticket-origin:8443`. Both domains redirect HTTP to
HTTPS. RAG backend services and their private network are unchanged.

Before starting the public stack, provision the shared proxy network once:

```sh
docker network create --driver bridge --internal ticket-edge
docker network inspect ticket-edge --format '{{.Driver}} {{.Internal}}'
```

The expected properties are `bridge true`. Only `rag-prod-frontend-1` and
`ticket-booking-proxy-1` join it. The ticket repository's
`deploy/ensure-edge-network.sh` creates/validates it during ticket releases.
The ticket deployment must provide the `ticket-origin` alias and port 8443.

`compose.public.yml` mounts `frontend/Caddyfile.public` read-only, so deploy that
tracked file with the Compose update. The mount persists across container recreation;
updates to the baked image alone do not replace the mounted routing configuration.
Certificate data/config volumes stay intact. Back up both tracked files before updates.
Validate Compose with the production env file and validate Caddy with PUBLIC_HOSTNAME
set. Recreate only frontend using the existing production/public Compose files:
`up -d --no-deps --no-build --wait frontend`. The admin API remains disabled.
Do not restart API, worker, DB or Redis for routing changes.

Verify both domains' TLS, HTTP redirects, RAG health/API and ticket login/CSRF.
To roll back, restore the saved Compose/Caddyfile pair and recreate only frontend;
RAG resumes its prior routing and ticket booking remains accessible at its legacy
HTTPS port 8443. Never remove database or certificate volumes.
