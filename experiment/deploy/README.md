# EC2 deployment (app.bayutaxia.com)

One Ubuntu EC2 (34.244.186.19, eu-west-1) runs the whole stack with Docker
Compose from `~/axia`:

| Service | What |
|---|---|
| caddy | Listens on `127.0.0.1:80` only. `/api/*` goes to Django, everything else (including the app's own `/admin` page) to Next.js. Holds requests for up to 30 s while a service restarts. |
| web | Next.js production build (`web.Dockerfile`). |
| backend | Django + gunicorn. `backend-start.sh` migrates, collects static, seeds presets, imports the DLD sales once and creates the first admin. |
| celery | Background tasks (issuing, email). |
| db, redis | Postgres 16 and Redis, on Docker volumes. |

**Traffic:** Cloudflare Access (company SSO) → Cloudflare Tunnel
(`cloudflared` service on the host, ingress `http://localhost:80`) → Caddy.
No inbound ports are open besides SSH; HTTPS ends at Cloudflare.

**Sign-in:** Django checks Cloudflare's signed `Cf-Access-Jwt-Assertion`
token and signs in the user with that email (`CF_ACCESS_TEAM_DOMAIN`,
`CF_ACCESS_AUD`). People must exist in the backend with roles; anyone new
waits for an admin to approve them. Django's built-in admin isn't exposed.

**Layout on the server:** these files sit in `~/axia`, the code in
`~/axia/app/{backend,web}`, secrets in `~/axia/backend.env` and `~/axia/.env`
(see `backend.env.example`). The previous code is kept in `~/axia/app.prev`.

**Auto-deploy:** every commit to `main` goes live within about a minute
plus build time. The `axia-autodeploy.timer` systemd timer runs
`~/axia/autodeploy.sh` each minute. It fetches `main` with a read-only
GitHub deploy key (`~/.ssh/axia_deploy`, ssh host `github-axia`), and when
the commit is new it rebuilds backend, celery and web, then reloads Caddy.
If the build fails or the site isn't healthy within 5 minutes, it puts the
previous code back. Log: `journalctl -u axia-autodeploy`.

The script and both units live here; after changing the units, copy them
to `/etc/systemd/system/` and run `sudo systemctl daemon-reload`.

**Manual deploy** (a branch, or without GitHub): `./deploy.sh <path to
axia.pem>`, or `./deploy.sh <key> web` to rebuild only the web app. The next
commit to `main` replaces it.

Not UAE-hosted (CLAUDE.md §7): demo/staging data only.
