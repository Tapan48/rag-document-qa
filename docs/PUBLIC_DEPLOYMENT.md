# Public HTTPS and invite-only access

This extends [the private production stack](DEPLOYMENT.md) on the same server.
Use Docker Compose 2.24.4 or newer (`!override` support). There are no new
database migrations. Existing accounts, documents, and vectors remain intact.
The application and worker retain their existing non-root execution settings.

## 1. DNS and network

Point your hostname's DNS A record to the VM's public IPv4 address. For this
deployment: `tapan-rag.duckdns.org` → `141.148.210.67`. Remove any stale AAAA
record unless IPv6 is actually configured. If the public IP changes, update DNS.

In Oracle Console, open **Networking → Virtual cloud networks → your VCN →
Subnets → public subnet → Security lists → the attached security list**.
Add stateful ingress rules from `0.0.0.0/0`, TCP, all source ports, destination
ports **80** and **443**. Keep the existing SSH rule. The public subnet needs
its existing default route to an internet gateway.

Docker publishes only TCP 80/443 on the host. Caddy listens on unprivileged
8080/8443 inside its container; no extra Linux capability is required. Keep
8000, 8080, 8081, 8443, 5432, 6379, and 2019 closed externally. UDP 443 is not
published, so HTTP/3 is not required for this deployment.

Check the host firewall's INPUT, FORWARD, and DOCKER-USER rules as well as
Oracle ingress. Docker bridge traffic traverses forwarding rules; an INPUT
allow rule alone does not guarantee access. Preserve SSH and existing Docker
rules. Do not enable UFW or flush iptables blindly on a remote server.

## 2. Configure and deploy

On the VM, inside the existing repository, pull the tested commit. Add this
non-secret setting to the existing `.env.production` without replacing secrets:

```dotenv
PUBLIC_HOSTNAME=tapan-rag.duckdns.org
```

Use this helper in every server shell, including when following the base
guide's update, backup, and restore commands:

```bash
dc() {
  sudo docker compose --env-file .env.production \
    -f compose.prod.yml -f compose.public.yml -p rag-prod "$@"
}
dc config --quiet
dc build api frontend
```

For an existing installation, wait for active uploads/questions to finish.
Take the database and uploads backup described in the base guide, then:

```bash
dc stop frontend api worker
dc up -d --wait db redis
dc run --rm migrate
dc up -d --wait api worker frontend
dc ps
```

On a new installation, first follow the base guide's secret setup, then use
the commands above. Stop if migrations fail. Never use `down -v` or switch
the project name: those actions can remove or detach persistent data.

The public override **forces `REGISTRATION_ENABLED=false`** for API and worker,
even if the env file says true. The private/development default remains true.
Registration is blocked by the API, including direct HTTP requests; hiding
the frontend link is only a usability feature. `/register` displays an
invitation message. Login works for existing users and CLI-created reviewers.

Caddy obtains and renews a trusted certificate automatically. TCP 80/443 must
be reachable for certificate challenges. HTTP redirects to HTTPS. Certificate
issuance can take a minute; container health alone does not prove it succeeded.
Named volumes `rag-prod_caddy_data` and `rag-prod_caddy_config` preserve the
certificate, ACME account, and configuration state across container recreation.
Their initial ownership comes from the image (UID/GID 10001). Keep these
volumes during updates; do not repeatedly delete them to troubleshoot TLS.

## 3. Create reviewer accounts

From an interactive SSH terminal in the repository:

```bash
dc exec api python -m app.cli create-user --email reviewer@example.com
```

Replace the example email. Type and confirm a unique password when prompted;
input is hidden. Do **not** use `-T`, pass passwords on the command line, or put
them in environment files. The CLI refuses an echoing input fallback, validates
email/password, hashes the password, and rejects duplicate email addresses.
It does not reset existing passwords or send invitations. Share credentials
privately with the intended reviewer. They sign in at the public URL.

There is no account administration UI or password-reset flow in this version.
Inviting someone grants access to uploads and provider-backed questions in
their own account. Invite-only access limits who can use these operations;
it is not a rate limiter, per-user quota, or OpenAI spending cap.

## 4. Verify from outside the VM

No SSH tunnel is needed:

```bash
curl -I http://tapan-rag.duckdns.org/
curl --fail https://tapan-rag.duckdns.org/api/health
curl --fail https://tapan-rag.duckdns.org/api/auth/config
```

Expect an HTTP→HTTPS redirect, `{"status":"ok"}`, and
`{"registration_enabled":false}` respectively. Do not use `curl -k`: a trusted
certificate is part of this check. In a browser, verify login, refresh on
`/workspace`, a text upload reaching `ready`, a streamed answer with citations,
and Stop during generation. Check `/register` shows the invite-only message.
A valid direct registration request must return 403.

Confirm all services are healthy and inspect relevant logs if a check fails:

```bash
dc logs --tail=100 frontend
dc logs --tail=100 api worker
```

To verify TLS persistence, note the served certificate serial, recreate only
the frontend, and confirm the same certificate is still served:

```bash
openssl s_client -connect tapan-rag.duckdns.org:443 \
  -servername tapan-rag.duckdns.org </dev/null 2>/dev/null | openssl x509 -noout -serial
dc up -d --wait --force-recreate frontend
```

Rerun the certificate command and health request. Normal certificate renewal
will eventually change the serial; recreation alone should not require issuance.

## 5. Recovery and private access

Use the base guide's database/uploads backup and recovery procedure with the
public `dc` helper. Also preserve or securely back up both Caddy volumes; their
contents contain private TLS/account keys and must never enter Git or images.

To return to SSH-only access, use the base `compose.prod.yml` helper and
`dc up -d --wait --force-recreate frontend`. This removes the public port
bindings. Keep `REGISTRATION_ENABLED=false` in the env file if you want
invite-only registration to persist when using the base configuration.
Close Oracle 80/443 ingress if public access is no longer needed.

If HTTPS fails, check DNS, Oracle ingress, host forwarding, and frontend logs
before changing certificates. If login works but ingestion fails, inspect
worker errors and provider credit/model access separately. Never post env
files, tokens, uploaded private documents, or unredacted logs publicly.

## Local verification

- 145 backend tests and 56 frontend tests passed; production build and type
  checking passed. Lint reports three existing Fast Refresh warnings.
- Both production images built on ARM64. An isolated public Compose stack
  passed health checks with a locally trusted test certificate.
- HTTP redirected to HTTPS; reviewer login, authenticated routes, SPA deep
  links, SSE completion, and registration rejection passed through Caddy.
- The private Caddy configuration still served the API with the new image.
- Staged changes were scanned for secrets before each commit. Environment
  files, SSH keys, uploaded data, and TLS private material stay outside Git.

Local checks use a temporary CA and mocked provider calls. They do not prove
public certificate issuance, Oracle ingress, or real provider access; verify
those on the live server using the steps above.
