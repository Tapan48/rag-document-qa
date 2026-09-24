# Deployment Plan

1. **Create an Oracle Cloud instance** — Ubuntu 24.04 ARM64, Always Free–eligible Ampere A1, 2 OCPUs, 12 GB RAM, and a 50 GB boot disk.

2. **Configure networking and SSH** — Use a public subnet, internet gateway, and public IP; save the SSH private key securely.

3. **Install server tools** — Connect through SSH and install Docker, Docker Compose, and Git; verify Docker works.

4. **Prepare production files** — Add production Dockerfiles, Compose configuration, Caddy, health checks, and persistent volumes. Keep secrets and SSH keys ignored by Git.

5. **Configure production secrets** — Clone the GitHub repository and create `.env.production` with database credentials, JWT secret, and the OpenAI API key.

6. **Start the application** — Start PostgreSQL and Redis, run migrations, then start the API, Celery worker, and frontend. Verify health and access through an SSH tunnel.

7. **Enable public HTTPS** — Point `tapan-rag.duckdns.org` to the server, allow ports 80/443, and configure Caddy for automatic HTTPS.

8. **Verify and maintain releases** — Test uploads, ingestion, answers, and citations. For updates: test → scan for secrets → commit → push → pull on Oracle → rebuild affected services → verify health.
