# MN Parks — hobby hosting and deploy

**Today:** 2026-10-19. Prices below are from vendor pages that day, USD, excluding tax. Custom-domain and Blueprint YAML details are from [Render custom domains](https://render.com/docs/custom-domains) and the [Blueprint YAML reference](https://render.com/docs/blueprint-spec) that day.

**Default host: [Render](https://render.com/pricing).** Production URL: **https://parks.mattmcf.com**. Monthly floor **$0** on a Hobby workspace with Free web + Free Postgres. Durable hobby (always-on web + a database that does not expire) is **$13/month**. Hobby includes **2 custom domains**; `parks.mattmcf.com` uses one. TLS is included.

The repo is **public** (`mattmcf/mn-parks`) and that is fine. It is already wired for Render. Matthew has **not** created a Render account yet. The agent cannot create that account or change DNS. Do not create a paid Heroku or Render app from this agent.

**Matthew does this first:** step 1 — create a Render Hobby account with GitHub login.

---

## Checklist (Matthew + agent)

1. **Create a Render Hobby account** (GitHub login). Open [render.com](https://render.com), sign up with GitHub, stay on **Hobby** ($0). No credit card for Free compute; add a card only if you later upgrade or blow past included bandwidth.
2. **Connect GitHub / grant `mattmcf/mn-parks`.** If Render asks, authorize the GitHub App and grant access to this repo (public is enough; no visibility change).
3. **Blueprints → New Blueprint → `main` → Approve.** Dashboard → **Blueprints** → **New Blueprint Instance** → repo **`mn-parks`**, branch **`main`**. Render reads `render.yaml`. **Approve**. That creates:
   - Web service `mn-parks` (Free, Ohio) with custom domain **`parks.mattmcf.com`** declared in the Blueprint (`domains:`)
   - Postgres `mn-parks-db` (Free, Ohio, private network)
   - `DATABASE_URL` from the database
   - `SECRET_KEY_BASE` (generated; never in git)
   - `APPLICATION_HOST=parks.mattmcf.com` (Rails host allow-list)
4. **Wait for the first deploy; note the `*.onrender.com` URL.** Build is bundle + `npm ci` + Vite + `db:migrate` + `db:seed`. Copy the service hostname from the dashboard (example shape `mn-parks.onrender.com` — **use the real one Render prints**, not a guess). That URL works before DNS.
5. **DNS at wherever `mattmcf.com` is registered.** As of 2026-10-19, nameservers are **`ns33.domaincontrol.com` / `ns34.domaincontrol.com`** (GoDaddy DNS). Add **one** record — do **not** use an A record or a guessed IP:

   | Field | Value |
   | --- | --- |
   | Type | **CNAME** |
   | Name / Host | **`parks`** |
   | Points to / Target | **the exact `*.onrender.com` hostname from step 4** (dashboard → web service → URL, without `https://`) |
   | TTL | default, or 600s / 1 min if you want faster verify |

   Remove any **AAAA** on `parks` if one exists (Render is IPv4). Leave the apex `mattmcf.com` alone.
6. **Render custom domain `parks.mattmcf.com` + TLS.** The Blueprint already associates the domain on Approve. After the CNAME exists, Render usually verifies and issues a Let’s Encrypt / Google Trust Services cert automatically; HTTP redirects to HTTPS. If Settings → Custom Domains still says DNS update needed, click **Verify**. If the domain is missing (rare), **+ Add Custom Domain** → `parks.mattmcf.com`. Hobby limit is 2 domains; this uses 1. Keep the `onrender.com` subdomain **enabled** until `parks.mattmcf.com` loads.
7. **Who clicks vs what the agent already did** — see [Agent vs Matthew](#agent-vs-matthew) below. Short version: Matthew does account, GitHub grant, Approve, DNS, Verify if needed. The agent already committed Blueprint + Rails host allow-list and pushed; it does **not** create a Render account or edit DNS.
8. **Verify:** open **https://parks.mattmcf.com** (map) and **https://parks.mattmcf.com/api/parks** (JSON). Also hit the step-4 `onrender.com` URL if DNS has not propagated yet. First hit after 15 minutes idle can show Render’s loading page for about a minute (Free web spin-down).

No `RAILS_MASTER_KEY` paste. Production boots from `SECRET_KEY_BASE`. `config/master.key` stays gitignored. Pushing to `main` after Approve redeploys by itself.

Optional later (not required to go live):

- Dashboard → Postgres → upgrade off Free **before day 30** if you want the inventory to survive (Free DBs expire after 30 days, then 14 days to upgrade or they are deleted).
- Web service → upgrade to Starter (`0.5c-512mb`, $7) to stop 15-minute spin-down.
- Environment → add `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_OAUTH_REDIRECT_URL=https://parks.mattmcf.com/api/auth/google_oauth2/callback` if you want Google sign-in.

---

## Agent vs Matthew

| | Agent | Matthew |
| --- | --- | --- |
| `render.yaml` Blueprint (web + Postgres + secrets + `domains: [parks.mattmcf.com]`) | Done, in git | — |
| Rails production host allow-list / CORS for `parks.mattmcf.com` | Done, in git | — |
| This checklist and repo `docs/deploy.md` | Done, in git | — |
| Create Render account / Hobby workspace | **Cannot** (no access, no billing) | **Step 1** |
| Grant GitHub App access to `mattmcf/mn-parks` | Cannot | **Step 2** |
| New Blueprint → `main` → Approve | Cannot | **Step 3** |
| Change DNS / registrar | **Cannot** | **Step 5** |
| Click Verify / wait for TLS | Cannot | **Step 6** if it does not auto-complete |
| Repo visibility | Leave as-is (**public**) | Leave as-is |
| Open https://parks.mattmcf.com | After Matthew finishes 1–6 | **Step 8** |

---

## Recommendation

| Criterion | Why Render wins |
| --- | --- |
| Cheap / free hobby | Hobby workspace is **$0/month**. Free web (512 MB) + Free Postgres (1 GB) is **$0**. |
| Agent owns deploy | `render.yaml` Blueprint: GitHub push deploys. `DATABASE_URL` and `SECRET_KEY_BASE` are injected; nothing secret is in git. |
| Rails + Postgres | Native Ruby runtime, official [Rails 8 guide](https://render.com/docs/deploy-rails-8). Node/npm is on the same image, so the Vite build runs in the same service. |
| SPA + API | Production build of `web/` is copied into `public/`. Rails (Puma) serves the map and `/api` on one origin. No reverse proxy required. |
| Few clicks | New Blueprint → this repo → Approve, then one CNAME. |
| Custom domain | Blueprint `domains` lists `parks.mattmcf.com`. You still add the CNAME; Render does not edit your DNS. |

**GitHub Pages cannot run this app.** Pages (and Actions that publish to Pages) serve static HTML/CSS/JS only. There is no Rails process, no `/api`, no Devise sessions, and no Postgres. The map would have nothing to talk to. Do not use Pages as the production host.

---

## What the agent already did

In the GitHub repo:

- **`render.yaml`** — Blueprint: Free Ruby web service + Free Postgres, Ohio, health check `/up`, **`domains: [parks.mattmcf.com]`** ([Blueprint spec](https://render.com/docs/blueprint-spec) `domains` field, 2026-10-19). `renderSubdomainPolicy` left at default **enabled** so `*.onrender.com` still works.
- **`bin/render-build.sh`** — `bundle install`, Vite production build, copy SPA into `public/`, `db:migrate`, `db:seed` (seed is idempotent; it reloads shipped park JSON).
- **`bin/install-spa`** / **`rake spa:build`** — copies `web/dist/index.html` → `public/index.html` and hashed assets → `public/spa-assets/` (does not collide with Rails `/assets`).
- **`web/vite.config.ts`** — `build.assetsDir: "spa-assets"`.
- **`SpaController`** + root route — Rails serves the map if a request reaches the app instead of the static middleware.
- **`SECRET_KEY_BASE`** from the environment (`generateValue` on Render). **`DATABASE_URL`** from Render Postgres. **`APPLICATION_HOST=parks.mattmcf.com`**. **`RAILS_ENV=production`**. **`RAILS_MASTER_KEY` not required** (`config.require_master_key = false`). No secrets committed.
- Production SSL / `/up` health skip, host allow-list includes **`parks.mattmcf.com`** plus `RENDER_EXTERNAL_HOSTNAME`, CORS includes `https://parks.mattmcf.com`.
- **`Procfile`** — Heroku-shaped `web:` process if you ever switch.
- **`Dockerfile`** — same SPA+Rails image for Coolify / Fly; Render does **not** use it (native Ruby runtime).

Local preview of the production SPA (still talks to local Rails if you run it):

```bash
npm --prefix web ci && npm --prefix web run build && ./bin/install-spa
```

---

## Hobby comparison (2026-10-19)

Floor = cheapest way to run **this** stack (Rails process + Postgres + SPA). “Durable” = always-on web + a database that is not deleted on a timer.

| Host | Floor | Durable hobby | Agent can own | Notes |
| --- | --- | --- | --- | --- |
| **Render (pick)** | **$0** Hobby + Free web + Free Postgres | **$13** ($7 Starter web + $6 Starter Postgres) | **Yes** — Blueprint in-repo | Free web sleeps after **15 min**; ~1 min cold start. **750** Free instance-hours/month. Free Postgres: **1 GB**, **no backups**, **expires 30 days** after create. Bandwidth 5 GB on Hobby. Custom domains: **2 included** on Hobby. [Pricing](https://render.com/pricing) · [Free limits](https://render.com/docs/free) · [Custom domains](https://render.com/docs/custom-domains) |
| Heroku Eco + Essential-0 | **$10** ($5 Eco dyno plan + $5 Essential-0 Postgres) | Same $10 (Eco still sleeps **30 min**) | Partial — `Procfile` is in-repo; you still create the app and add billing | Eco: **1000** dyno-hours / $5, personal apps only. Essential-0: 1 GB, 20 connections. [Dynos](https://www.heroku.com/pricing/) · [Eco hours](https://devcenter.heroku.com/articles/eco-dyno-hours) (updated 2026-04-18) · [Postgres](https://devcenter.heroku.com/articles/heroku-postgres-plans) (updated 2026-10-15) |
| Railway Hobby | **$5** subscription (includes $5 usage) | Often **~$5–15** once Rails + Postgres RAM is metered | Partial — GitHub deploy, usage still surprises | Free plan is **$1/month** usage after trial and is too small for this app. RAM **$10/GB-month**, CPU **$20/vCPU-month**. [Plans](https://docs.railway.com/pricing/plans) |
| Fly.io | Trial only (2 machine-hours or 7 days), then pay | Smallest Machine **~$2.19**/30d **plus** Managed Postgres **$38** (Basic) | `fly.toml` possible; new accounts have **no free tier** | Self-managed Postgres on a volume is cheaper than MPG but more ops than Render. [Pricing](https://fly.io/pricing/) · [Machines](https://docs.fly.io/about/pricing) |
| Coolify on a VPS | **~$7** (Hetzner CX23 2 vCPU / 4 GB, ~€5.99–$7) | Same; you own the box | Low — you create the VPS, SSH, backups | Coolify itself is free software. Fits Rails+Postgres. Not few-clicks. |
| GitHub Pages + Actions | **$0** | n/a | n/a | **Cannot run Rails or Postgres.** Static hosting only. |

**Not chosen:** Heroku is a clean Rails default but **starts at $10** and still sleeps. Railway’s $5 floor is real but usage-metered Postgres is easy to overrun. Fly’s managed DB is not hobby-priced. Coolify is the cheapest *always-on* box if Matthew already wants a VPS; it is not the few-click path.

---

## How production is shaped

```
Browser  →  https://parks.mattmcf.com
              (CNAME parks → <service>.onrender.com)
              ├─ /              Vite index.html (public/index.html)
              ├─ /spa-assets/*  hashed JS/CSS
              └─ /api/*         Rails JSON + Devise cookie session
                      └─ DATABASE_URL → Render Postgres (internal)

Fallback  →  https://<service>.onrender.com   (until you disable it)
```

Development is unchanged: Vite **4174**, Rails **3451**, `/api` proxied.

Env vars (Render sets the first five):

| Variable | Source | In git? |
| --- | --- | --- |
| `RAILS_ENV` | `production` in `render.yaml` | value only, not a secret |
| `DATABASE_URL` | Render Postgres `connectionString` | **no** |
| `SECRET_KEY_BASE` | Render `generateValue` | **no** |
| `APPLICATION_HOST` | `parks.mattmcf.com` in `render.yaml` | hostname only |
| `RAILS_LOG_TO_STDOUT` / `RAILS_SERVE_STATIC_FILES` | `render.yaml` | values only |
| `RAILS_MASTER_KEY` | not used | `config/master.key` gitignored |
| `GOOGLE_*` | optional, Dashboard later | **no** |

Free-plan migrations run **in the build** (`bin/render-build.sh`). Paid plans can move `db:migrate` to a pre-deploy command later.

---

## After the first deploy

- **Cold start:** first hit after 15 minutes idle shows Render’s loading page for about a minute.
- **Park data:** `db:seed` loads `db/data/*.json`. Runtime still does **not** call DNR/NPS/etc. Re-ingest stays `bin/rake parks:refresh` locally, commit JSON, push.
- **Free Postgres clock:** upgrade or dump before day 30 if this should stay up. Starter Postgres is **$6/month** (`0.1c-256mb`).
- **Repo visibility:** public website; GitHub repo **`mattmcf/mn-parks` stays public**. That is fine. This doc does not change visibility.
- **Do not** point GitHub Pages at this repo as the live site.

---

## Switching hosts later

The same production contract (one process, `DATABASE_URL`, `SECRET_KEY_BASE`, SPA in `public/`) works elsewhere:

- **Heroku:** `Procfile` is present. You still create the app, Eco dynos, and Essential-0 Postgres in Matthew’s account ($10/month).
- **Coolify / Fly:** `Dockerfile` builds the SPA then Rails. Set the same env vars. Fly managed Postgres is not the cheap option.

Stay on Render until those tradeoffs matter.
