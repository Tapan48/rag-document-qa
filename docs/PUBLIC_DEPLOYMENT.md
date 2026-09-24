# Public HTTPS and approved registration

This extends [the private production stack](DEPLOYMENT.md) on the same server.
Use Docker Compose 2.24.4 or newer (`!override` support). The approval feature adds an administrator flag, access requests, and email
delivery tables through Alembic. Existing accounts, documents, and vectors
remain intact.
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

The public override defaults to `REGISTRATION_MODE=closed`. Set it to `approval`
only after completing the Gmail and administrator setup below. `open` allows
unrestricted signup and is not the intended public mode. Explicit
`REGISTRATION_MODE` takes precedence over the legacy `REGISTRATION_ENABLED`
setting. Development retains its existing open-registration default.

Caddy obtains and renews a trusted certificate automatically. TCP 80/443 must
be reachable for certificate challenges. HTTP redirects to HTTPS. Certificate
issuance can take a minute; container health alone does not prove it succeeded.
Named volumes `rag-prod_caddy_data` and `rag-prod_caddy_config` preserve the
certificate, ACME account, and configuration state across container recreation.
Their initial ownership comes from the image (UID/GID 10001). Keep these
volumes during updates; do not repeatedly delete them to troubleshoot TLS.

## 3. Configure Gmail and your administrator

1. Enable Google 2-Step Verification and generate a dedicated **RAG app**
   App Password at https://myaccount.google.com/apppasswords. Availability
   depends on Google account policy; use an App Password, not your main password.
2. Add `SMTP_USERNAME=tapangarasangi@gmail.com` and `SMTP_PASSWORD` privately to
   the server's `.env.production`. Do not put credentials in commands, commits,
   screenshots, or chat. The default transport is `smtp.gmail.com:587` using
   STARTTLS with certificate verification. Allow outbound TCP 587 if restricted.
3. Keep `ACCESS_NOTIFICATION_EMAIL=tapangarasangi@gmail.com`. The public
   override derives `PUBLIC_APP_URL=https://<PUBLIC_HOSTNAME>` for email links;
   incoming Host headers never choose the links' destination.
4. Grant your **existing** owner account administrator access:

```bash
dc exec api python -m app.cli grant-admin --email tapangarasangi@gmail.com
```

If the account does not exist, first create it with
`dc exec api python -m app.cli create-user --email tapangarasangi@gmail.com`.
Use the hidden password prompt without `-T`. Granting admin does not change
an existing password. Public requests cannot set administrator privileges.

After SMTP authentication succeeds, set `REGISTRATION_MODE=approval` in the
server env file and run `dc up -d --wait api worker frontend`. Approval-mode
production startup requires SMTP credentials and an HTTPS public origin.
Check `/api/auth/config` reports `registration_mode: approval`.

### Daily use

Visitors choose **Request access** and submit their email. You receive a
notification linking to `/admin/access-requests`. Sign in with your owner
account, then choose **Approve** or **Reject**. The workspace also contains an
**Access requests** link for administrators. Opening an email link alone never
approves a request.

Approval emails the visitor a registration link, valid for seven days, bound
to their email, and usable once. They choose their own password. **Resend
invitation** generates a new link and invalidates the previous one. Rejecting
an approved request revokes its link; it does not delete an existing account.
Existing users continue logging in normally. Rejected requests do not reopen
through public resubmission; an administrator can explicitly approve them.

The admin list displays pending, approved, rejected, and registered requests,
with the five latest email delivery records for each. Refresh to see delivery
updates. SMTP acceptance is recorded as `sent`; it does not guarantee inbox
placement, so check spam folders during verification.

### Delivery and recovery

The API commits request/delivery records before queuing an email task. Celery
sends mail with up to three attempts, 60 seconds apart. Tasks contain only a
delivery ID. Invitation tokens are derived with a purpose-specific HMAC using
the JWT secret and a random invitation version; only their hashes are stored
for validation. Raw tokens and SMTP errors are not logged. Tokens travel in a
URL fragment and API request bodies, not HTTP access-log query strings.

Email delivery is at least once: an SMTP disconnect after acceptance can cause
a duplicate email. It never creates another account or changes the invitation.
Worker/broker failure can leave pending records. The admin page offers **Retry
email** for failed deliveries and for pending/retrying records older than five
minutes. Old/revoked invitation jobs are cancelled without sending. Expired
invitations need **Resend invitation**. Rotating `JWT_SECRET` can prevent unsent
invitation jobs from reproducing their token; resend those invitations.

Public submissions produce a generic confirmation. Existing accounts and
approved/rejected requests do not trigger notifications. Redis admits at most
one owner notification per normalized email in 24 hours and ten new owner
notifications per fixed hour, across API processes. Delivery retries and explicit
administrator actions are not new public submissions. A Redis outage returns
503; the global cap returns 429. There is no IP-based limiter, CAPTCHA, email
verification before requesting access, or automatic rejection email in v1.

This controls account admission, not per-user OpenAI spending. Approved users
can still generate provider costs. To pause requests and invitation registration,
set `REGISTRATION_MODE=closed` and recreate API/worker; existing login continues.
The server-only `create-user` command remains available for operator recovery.

## 4. Verify from outside the VM

No SSH tunnel is needed:

```bash
curl -I http://tapan-rag.duckdns.org/
curl --fail https://tapan-rag.duckdns.org/api/health
curl --fail https://tapan-rag.duckdns.org/api/auth/config
```

Expect an HTTP→HTTPS redirect, `{"status":"ok"}`, and
`{"registration_enabled":false,"registration_mode":"approval"}` respectively. Do not use `curl -k`: a trusted
certificate is part of this check. In a browser, verify login, refresh on
`/workspace`, a text upload reaching `ready`, a streamed answer with citations,
and Stop during generation. Check an uninvited visit to `/register` links to Request access.
Registration without an approved invitation must return 403. Verify one real
request → owner email → approval → invitation email → registration flow, then
confirm the invitation cannot be reused.

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
bindings. Keep `REGISTRATION_ENABLED=false` in the env file when reverting to the base
configuration to prevent unrestricted signup. The approval-mode setting is
applied by the public override.
Close Oracle 80/443 ingress if public access is no longer needed.

If HTTPS fails, check DNS, Oracle ingress, host forwarding, and frontend logs
before changing certificates. If login works but ingestion fails, inspect
worker errors and provider credit/model access separately. Never post env
files, tokens, uploaded private documents, or unredacted logs publicly.

## Local verification

- 164 backend tests and 66 frontend tests passed; production build and type
  checking passed. Lint reports three existing Fast Refresh warnings.
- Both production images built on ARM64. An isolated public Compose stack
  passed health checks with a locally trusted test certificate.
- HTTP redirected to HTTPS; reviewer login, authenticated routes, SPA deep
  links, SSE completion, and registration rejection passed through Caddy.
- The private Caddy configuration still served the API with the new image.
- An isolated production stack delivered request and invitation emails through
  Celery and a STARTTLS SMTP receiver. Browser approval and invitation
  registration passed, and registration consumed the token.
- Staged changes were scanned for secrets before each commit. Environment
  files, SSH keys, uploaded data, and TLS private material stay outside Git.

Local checks use a temporary CA and mocked provider calls. They do not prove
public certificate issuance, Oracle ingress, or real provider access; verify
those on the live server using the steps above.

## Optional web-search configuration

The production Compose configuration passes `WEB_SEARCH_MODEL` (default `gpt-5.6-luna`), `WEB_SEARCH_MAX_TOOL_CALLS` (3), `WEB_SEARCH_TIMEOUT_SECONDS` (90), `WEB_SEARCH_MAX_OUTPUT_TOKENS` (3000), and `ANSWER_TIMEOUT_SECONDS` (60). The existing `OPENAI_API_KEY` is used; no new provider credentials or migrations are required. Set overrides in the ignored `.env.production` and recreate the API container to apply them. Rebuild API and frontend images when updating code.

Web mode starts off for each workspace session. Enabling it adds paid research calls before answer generation; invitation controls and per-request limits do not impose a total spending cap. Research is synchronous to the request and can be stopped. Results reflect cited pages at the research time, not guaranteed current stock or compatibility.
