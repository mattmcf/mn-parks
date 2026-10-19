# MN Parks — hobby hosting and deploy

**Today:** 2026-10-19. Prices below are from vendor pages that day, USD, excluding tax.

**Default host: [Render](https://render.com/pricing).** Monthly floor **$0** on a Hobby workspace with Free web + Free Postgres. Durable hobby (always-on web + a database that does not expire) is **$13/month**.

The repo is already wired for that path. Matthew’s remaining work is **one account action** — create a Render account, connect GitHub, Approve the Blueprint. Do not create a paid Heroku or Render app from this agent; that needs Matthew’s billing.

---

## Recommendation

| Criterion | Why Render wins |
| --- | --- |
| Cheap / free hobby | Hobby workspace is **$0/month**. Free web (512 MB) + Free Postgres (1 GB) is **$0**. |
| Agent owns deploy | `render.yaml` Blueprint: GitHub push deploys. `DATABASE_URL` and `SECRET_KEY_BASE` are injected; nothing secret is in git. |
| Rails + Postgres | Native Ruby runtime, official [Rails 8 guide](https://render.com/docs/deploy-rails-8). Node/npm is on the same image, so the Vite build runs in the same service. |
| SPA + API | Production build of `web/` is copied into `public/`. Rails (Puma) serves the map and `/api` on one origin. No reverse proxy required. |
| Few clicks | New Blueprint → this repo → Approve. |

**GitHub Pages cannot run this app.** Pages (and Actions that publish to Pages) serve static HTML/CSS/JS only. There is no Rails process, no `/api`, no Devise sessions, and no Postgres. The map would have nothing to talk to. Do not use Pages as the production host.

---

## What Matthew must click (once)

1. Open [render.com](https://render.com) and **sign up** with GitHub. Stay on the **Hobby** workspace ($0). You do **not** need a credit card for Free compute; add one only if you later upgrade or blow past included bandwidth.
2. If Render asks, **authorize GitHub** and grant access to `mattmcf/mn-parks`.
3. Dashboard → **Blueprints** → **New Blueprint Instance**.
4. Pick the **`mn-parks`** repo, branch **`main`**. Render reads `render.yaml`.
5. **Approve**. Render creates:
   - Web service `mn-parks` (Free, Ohio)
   - Postgres `mn-parks-db` (Free, Ohio, private network)
   - `DATABASE_URL` from the database
   - `SECRET_KEY_BASE` (generated; never in git)
6. Wait for the first deploy (bundle + `npm ci` + Vite build + `db:migrate` + `db:seed`). Open the `.onrender.com` URL it prints. That URL is the public map.

No `RAILS_MASTER_KEY` paste. Production boots from `SECRET_KEY_BASE`. `config/master.key` stays gitignored.

Optional later (not required to go live):

- Dashboard → Postgres → upgrade off Free **before day 30** if you want the inventory to survive (Free DBs expire after 30 days, then 14 days to upgrade or they are deleted).
- Web service → upgrade to Starter (`0.5c-512mb`, $7) to stop 15-minute spin-down.
- Environment → add `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_OAUTH_REDIRECT_URL=https://<your-host>/api/auth/google_oauth2/callback` if you want Google sign-in.
- Custom domain.

That is the entire human path. Pushing to `main` after this redeploys by itself.

---

## What the agent already did

In the GitHub repo:

- **`render.yaml`** — Blueprint: Free Ruby web service + Free Postgres, Ohio, health check `/up`.
- **`bin/render-build.sh`** — `bundle install`, Vite production build, copy SPA into `public/`, `db:migrate`, `db:seed` (seed is idempotent; it reloads shipped park JSON).
- **`bin/install-spa`** / **`rake spa:build`** — copies `web/dist/index.html` → `public/index.html` and hashed assets → `public/spa-assets/` (does not collide with Rails `/assets`).
- **`web/vite.config.ts`** — `build.assetsDir: "spa-assets"`.
- **`SpaController`** + root route — Rails serves the map if a request reaches the app instead of the static middleware.
- **`SECRET_KEY_BASE`** from the environment (`generateValue` on Render). **`DATABASE_URL`** from Render Postgres. **`RAILS_ENV=production`**. **`RAILS_MASTER_KEY` not required** (`config.require_master_key = false`). No secrets committed.
- **`Procfile`** — Heroku-shaped `web:` process if you ever switch.
- **`Dockerfile`** — same SPA+Rails image for Coolify / Fly; Render does **not** use it (native Ruby runtime).
- Production SSL / `/up` health skip, Render hostname allow-list, CORS includes `RENDER_EXTERNAL_URL`.

Local preview of the production SPA (still talks to local Rails if you run it):

```bash
npm --prefix web ci && npm --prefix web run build && ./bin/install-spa
```

---

## Hobby comparison (2026-10-19)

Floor = cheapest way to run **this** stack (Rails process + Postgres + SPA). “Durable” = always-on web + a database that is not deleted on a timer.

| Host | Floor | Durable hobby | Agent can own | Notes |
| --- | --- | --- | --- | --- |
| **Render (pick)** | **$0** Hobby + Free web + Free Postgres | **$13** ($7 Starter web + $6 Starter Postgres) | **Yes** — Blueprint in-repo | Free web sleeps after **15 min**; ~1 min cold start. **750** Free instance-hours/month. Free Postgres: **1 GB**, **no backups**, **expires 30 days** after create. Bandwidth 5 GB on Hobby. [Pricing](https://render.com/pricing) · [Free limits](https://render.com/docs/free) |
| Heroku Eco + Essential-0 | **$10** ($5 Eco dyno plan + $5 Essential-0 Postgres) | Same $10 (Eco still sleeps **30 min**) | Partial — `Procfile` is in-repo; you still create the app and add billing | Eco: **1000** dyno-hours / $5, personal apps only. Essential-0: 1 GB, 20 connections. [Dynos](https://www.heroku.com/pricing/) · [Eco hours](https://devcenter.heroku.com/articles/eco-dyno-hours) (updated 2026-04-18) · [Postgres](https://devcenter.heroku.com/articles/heroku-postgres-plans) (updated 2026-10-15) |
| Railway Hobby | **$5** subscription (includes $5 usage) | Often **~$5–15** once Rails + Postgres RAM is metered | Partial — GitHub deploy, usage still surprises | Free plan is **$1/month** usage after trial and is too small for this app. RAM **$10/GB-month**, CPU **$20/vCPU-month**. [Plans](https://docs.railway.com/pricing/plans) |
| Fly.io | Trial only (2 machine-hours or 7 days), then pay | Smallest Machine **~$2.19**/30d **plus** Managed Postgres **$38** (Basic) | `fly.toml` possible; new accounts have **no free tier** | Self-managed Postgres on a volume is cheaper than MPG but more ops than Render. [Pricing](https://fly.io/pricing/) · [Machines](https://docs.fly.io/about/pricing) |
| Coolify on a VPS | **~$7** (Hetzner CX23 2 vCPU / 4 GB, ~€5.99–$7) | Same; you own the box | Low — you create the VPS, SSH, backups | Coolify itself is free software. Fits Rails+Postgres. Not few-clicks. |
| GitHub Pages + Actions | **$0** | n/a | n/a | **Cannot run Rails or Postgres.** Static hosting only. |

**Not chosen:** Heroku is a clean Rails default but **starts at $10** and still sleeps. Railway’s $5 floor is real but usage-metered Postgres is easy to overrun. Fly’s managed DB is not hobby-priced. Coolify is the cheapest *always-on* box if Matthew already wants a VPS; it is not the few-click path.

---

## How production is shaped

```
Browser  →  https://mn-parks.onrender.com
              ├─ /              Vite index.html (public/index.html)
              ├─ /spa-assets/*  hashed JS/CSS
              └─ /api/*         Rails JSON + Devise cookie session
                      └─ DATABASE_URL → Render Postgres (internal)
```

Development is unchanged: Vite **4174**, Rails **3451**, `/api` proxied.

Env vars (Render sets the first four):

| Variable | Source | In git? |
| --- | --- | --- |
| `RAILS_ENV` | `production` in `render.yaml` | value only, not a secret |
| `DATABASE_URL` | Render Postgres `connectionString` | **no** |
| `SECRET_KEY_BASE` | Render `generateValue` | **no** |
| `RAILS_LOG_TO_STDOUT` / `RAILS_SERVE_STATIC_FILES` | `render.yaml` | values only |
| `RAILS_MASTER_KEY` | not used | `config/master.key` gitignored |
| `GOOGLE_*` | optional, Dashboard later | **no** |

Free-plan migrations run **in the build** (`bin/render-build.sh`). Paid plans can move `db:migrate` to a pre-deploy command later.

---

## After the first deploy

- **Cold start:** first hit after 15 minutes idle shows Render’s loading page for about a minute.
- **Park data:** `db:seed` loads `db/data/*.json`. Runtime still does **not** call DNR/NPS/etc. Re-ingest stays `bin/rake parks:refresh` locally, commit JSON, push.
- **Free Postgres clock:** upgrade or dump before day 30 if this should stay up. Starter Postgres is **$6/month** (`0.1c-256mb`).
- **Repo visibility:** product intent is a **private** GitHub repo and a **public** website. As of this writing GitHub reports `mattmcf/mn-parks` as **public**. Flip it in GitHub → Settings → Danger zone → Change visibility if you still want private. Render can deploy a private repo once the GitHub App has access. This doc does not change visibility.
- **Do not** point GitHub Pages at this repo as the live site.

---

## Switching hosts later

The same production contract (one process, `DATABASE_URL`, `SECRET_KEY_BASE`, SPA in `public/`) works elsewhere:

- **Heroku:** `Procfile` is present. You still create the app, Eco dynos, and Essential-0 Postgres in Matthew’s account ($10/month).
- **Coolify / Fly:** `Dockerfile` builds the SPA then Rails. Set the same env vars. Fly managed Postgres is not the cheap option.

Stay on Render until those tradeoffs matter.
