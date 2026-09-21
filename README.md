# MN Parks

Map-first website of **parks inside Minnesota**. Browse type-colored markers on a statewide map, filter by type and amenities, open details, jump to a random park, and — once you sign in — save favorites and mark parks visited.

This is a monorepo:

- Rails 8 JSON API + Postgres + Devise (`/`)
- Vite + React + TypeScript + Tailwind + shadcn/ui + MapLibre GL JS (`web/`)

The map is a React SPA. Rails does not render it.

## Run locally

You need Ruby 3.2+, Postgres, and Node 22+.

Open the **SPA** at **http://127.0.0.1:4174** — that is the map. The Rails JSON API is **http://127.0.0.1:3451** and is not the UI.

### Postgres (Mac vs Linux/cloud)

`config/database.yml` defaults to TCP **`localhost`** and **omits `username`**, so libpq uses your OS user (e.g. `matt` on a Mac). Cloud/Linux can still use a Unix socket by exporting `PGHOST` / `PGUSER`.

| | Mac (Homebrew / Postgres.app) | Linux / cloud |
| --- | --- | --- |
| Host | `localhost` (default, or `PGHOST=localhost`) | `PGHOST=/var/run/postgresql` |
| User | unset — Postgres uses the OS user | `PGUSER=ubuntu` (or that cluster’s role) |
| Databases | `mn_parks_development` / `mn_parks_test` | same |

```bash
# Mac
export PGHOST=localhost
# leave PGUSER unset

bundle install
bin/rails db:prepare            # create + migrate + seed shipped parks

cd web && npm install && cd ..
```

Linux/cloud over a Unix socket:

```bash
export PGHOST=/var/run/postgresql
export PGUSER=ubuntu
bin/rails db:prepare
```

Copy `.env.example` for optional Google sign-in (leave those vars blank to hide Google; email/password always works). `.env.example` also documents `PGHOST=localhost` for Mac. Rails does not auto-load `.env`; export the vars or use direnv.

Start both processes with **`bin/dev`** (Foreman reads `Procfile.dev`; uncommon ports on purpose):

```bash
bin/dev
```

Then open the **map** at **http://127.0.0.1:4174**. The Rails JSON API is **http://127.0.0.1:3451** (Vite proxies `/api` to it). The map, list, details, filters, and Random work logged out. Favorite and Visited prompt for sign-in.

`bin/dev` installs the `foreman` gem if it is missing, then runs:

- `api` — Rails on **3451**
- `web` — Vite SPA on **4174**

### Ports

| Service | Port |
| --- | --- |
| Vite SPA (open this) | **4174** |
| Rails JSON API | **3451** |

### Optional Google OAuth

Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`. Callback URL:

`http://127.0.0.1:3451/api/auth/google_oauth2/callback`

Without those env vars, Google is omitted. The map still works.

## Data: shipped inventory

v1 is **state + national + wilderness + regional + county**. City parks are a second pass.

The source of truth is committed static assets:

- **`db/data/parks.json`** — park inventory (including `source_url`)
- **`db/data/dark_sky.json`** — DarkSky International certified places, matched onto parks
- **`db/data/park_reviews.json`** — camping inventory / camping score

`db:seed`, `parks:ingest`, and the JSON API all read those files (API via Postgres after seed). The map loads `/api/parks`. **`rails server` and Vite never call DNR, NPS, Met Council, USFS, Wilderness Connect, DarkSky, The Dyrt, or any review site.** Details **Official source** is `source_url` from that inventory.

| Type | Count (current asset) | Source |
| --- | --- | --- |
| **State** | 74 | MN DNR Parks & Trails reference points (Geospatial Commons `bdry_dnr_lrs_prk`) — state parks and state recreation areas. Waysides omitted. |
| **National** | 5 | NPS Parks API (`stateCode=MN`): Voyageurs, Grand Portage, Pipestone, Mississippi NRRA, Saint Croix NSR. North Country NST omitted (trail, not a park unit). |
| **Wilderness** | 3 | National Wilderness Preservation System polygons (Wilderness Connect GIS). Minnesota units: Boundary Waters Canoe Area Wilderness (Superior NF), Agassiz Wilderness, Tamarac Wilderness. Centroids from the official polygons. |
| **Regional** | 70 | Metropolitan Council regional parks / park reserves (`LPH/Parks_CD`). Twin Cities system. |
| **County** | 146 | MetroGIS Collaborative Parks (county-owned units in the seven-county metro) **plus** curated Greater Minnesota county parks with real coordinates. |

**Official `source_url`:** refresh resolves a **park-specific** page when one exists and can be confirmed — DNR `park.html?id=spk#####` / `sra#####` from the GIS unit code, NPS unit URL from the Parks API, USFS/FWS or Wilderness Connect unit page for wilderness, MetroGIS `PARK_URL` when it names that park. A system hub (DNR parks index, Met Council Parks.aspx, a county homepage) is kept only when no unit page is found. URLs are not invented: IDs and links come from GIS/APIs, and guessed manager pages are kept only after an HTTP check that does not land on a hub.

Coordinates are real. Highlights and amenities are **sparse on purpose**: official GIS rarely includes a full amenity inventory. Empty states say “Not listed in our sources yet.” Do not invent amenities to fill chips.

**Not county-complete across all 87 counties.** Many counties do not publish park GIS. Greater MN points are a real-world seed, not a staff directory of every picnic ground.

### Iterate on park-finding

Edit sources or filters in `scripts/build_parks_json.py` (types, skip lists, Greater MN rows, amenity mapping, URL resolution). Then:

```bash
# Fetches official park GIS/APIs, NWPS wilderness, DarkSky places, and campground inventories;
# rewrites db/data/parks.json, dark_sky.json, park_reviews.json; loads Postgres
bin/rake parks:refresh
```

That is the only path that hits DNR / NPS / Met Council / Wilderness Connect / DarkSky. Commit the updated JSON artifacts with the code change. Optional `NPS_API_KEY` (otherwise the NPS `DEMO_KEY`). Optional `RIDB_API_KEY` for Recreation.gov RIDB (skipped if blank). Python packages for the park GIS rebuild: `pip install -r scripts/requirements.txt` (the rake task installs them if missing). Dark Sky and reviews builders need only Python 3 stdlib. Rebuild from already-downloaded GIS with `PARKS_SKIP_FETCH=1` or `python3 scripts/build_parks_json.py --skip-fetch`.

Offline load of already-shipped files (used by `db:prepare` / `db:seed` as well):

```bash
bin/rake parks:ingest
```

Rebuild just Dark Sky or camping intel (still offline at boot — these only run when you invoke rake):

```bash
bin/rake parks:refresh_dark_sky
bin/rake parks:refresh_reviews
```

### Dark Sky certified parks

Official list: DarkSky International WordPress REST API (`/wp-json/wp/v2/darksky_place`), not an HTML scrape. Minnesota places are those whose **address** is in Minnesota (`, MN`). Quetico (Ontario) is dropped even though the write-up mentions Minnesota.

Current asset: **2** certified Minnesota places, **2** matched to existing parks.

| Place | Category | Match |
| --- | --- | --- |
| Voyageurs National Park | International Dark Sky Park (2020) | `Voyageurs National Park` |
| Boundary Waters Canoe Area Wilderness | International Dark Sky Sanctuary (2020) | `Boundary Waters Canoe Area Wilderness` (own record; not guessed onto nearby state parks) |

Filter chip: **Dark Sky**. Details show the certification and a link to the DarkSky listing. Parks that are not certified stay `false` / empty.

### Camping score (human reviews fallback)

Visitor-review sites are **not** ingested:

| Candidate | Why not |
| --- | --- |
| The Dyrt | Terms forbid scrapers/robots without written permission; no public developer API |
| Campendium | No documented reuse API |
| Google Places | Places ToS forbids storing/caching ratings |
| Recreation.gov RIDB | Reuse is encouraged, but the live API needs `RIDB_API_KEY` and does not publish user ratings. The 571 MB bulk export is not pulled on refresh. |

**Chosen source:** MN DNR Parks & Trails camping units (Geospatial Commons `struc_parks_and_trails_campsites`) plus the NPS Campgrounds API for federal units. Official GIS / public-domain government data.

**Camping score** is a **0–5 official inventory score**, not a visitor-review average. Parks without a matching DNR camping-unit record have **no score** (not invented). Formula (also stored on `park_reviews.json`):

`size = min(1, log10(1 + unit_count) / log10(201))`  
`score = min(5, 2.0*size + 1.2*electric + 0.8*shower + 0.5*ADA + 0.5*waterfront)` rounded to 1 decimal, where electric / shower-listed / ADA / waterfront are shares of DNR camping units.

NPS campgrounds add campsite counts, an official description snippet, and a reservation URL **without** a made-up star rating. Missing reviews never block the map.

Current asset: **66** parks with a camping score, **68** with some camping intel. Details show the score when present, plus campsite count and snippet.

## What’s in vs deferred

**In this slice**

- MapLibre map that opens fitted to Minnesota; pan is allowed out into the Dakotas, Iowa, Wisconsin, and the Great Lakes. Every park is a type-colored clickable marker (national square / state circle / wilderness diamond / regional rounded square / county circle, with a simple icon). Hover shows a pointer; click opens the same detail panel as the list.
- Click → name, type, agency, straight-line distance, Dark Sky certification, camping score when present, highlights, amenities/activities
- Filters: type, **Dark Sky**, amenities/activities that exist, distance (when origin set), favorited, visited
- Collapsible side list of parks in the current viewport; distance sort if origin, else name
- Random → zoom + details
- Distance origin: browser GPS + draggable From pin (pin overrides GPS)
- Devise email/password; map works logged out; favorite/visited persist when logged in
- Loading, empty inventory, API error, no-filter-match
- Desktop sidebar + mobile map-first with a bottom sheet list

**Deferred**

- City / municipal parks
- Park polygons, clustering
- Address search and driving time
- Named lists, account deletion, Rails admin
- Scheduled re-ingest, production host
- Google OAuth until keys are provided

## API (JSON)

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/parks` | All in-state parks + filter vocab (`meta.dark_sky_count`, camping fields on each park) |
| GET | `/api/parks/:id` | Detail |
| GET | `/api/parks/random` | Uniform among ingested parks |
| PATCH | `/api/parks/:id/user_state` | `{ favorited, visited }` — auth required |
| GET | `/api/me` | Session + whether Google is enabled |
| POST | `/api/signup` `/api/login` | Email/password |
| DELETE | `/api/logout` | |

Cookie session. Vite proxies `/api` in development.
