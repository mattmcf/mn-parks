# MN Parks

Map-first website of **parks inside Minnesota**. Browse pins on a statewide map, filter by type and amenities, open details, jump to a random park, and — once you sign in — save favorites and mark parks visited.

This is a monorepo:

- Rails 8 JSON API + Postgres + Devise (`/`)
- Vite + React + TypeScript + Tailwind + shadcn/ui + MapLibre GL JS (`web/`)

The map is a React SPA. Rails does not render it.

## Run locally

You need Ruby 3.2+, Postgres, and Node 22+.

```bash
# Postgres database
createdb mn_parks_development   # or: bin/rails db:create

bundle install
bin/rails db:prepare            # migrate + seed 295 parks

cd web && npm install && cd ..
```

Copy `.env.example` if you want Google sign-in. Leave those vars blank to hide Google; email/password always works.

Start both processes (uncommon ports on purpose):

```bash
# API — http://127.0.0.1:3451
PORT=3451 bin/rails server -b 0.0.0.0

# SPA — http://127.0.0.1:4174  (proxies /api to Rails)
cd web && npm run dev
```

Open **http://127.0.0.1:4174**. The map, list, details, filters, and Random work logged out. Favorite and Visited prompt for sign-in.

### Ports

| Service | Port |
| --- | --- |
| Rails JSON API | **3451** |
| Vite SPA | **4174** |

### Optional Google OAuth

Set `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`. Callback URL:

`http://127.0.0.1:3451/api/auth/google_oauth2/callback`

Without those env vars, Google is omitted. The map still works.

## Data: what is real vs seeded

Rebuilt with `python3 scripts/build_parks_json.py` (needs the shapefiles cached under `/tmp/mn-parks-data` from Minnesota Geospatial Commons). Then `bin/rails db:seed`.

| Type | Count (v1 seed) | Source |
| --- | --- | --- |
| **State** | 74 | MN DNR Parks & Trails reference points (Geospatial Commons `bdry_dnr_lrs_prk`) — official coordinates for state parks and state recreation areas. Waysides omitted. |
| **National** | 5 | NPS Parks API (`stateCode=MN`): Voyageurs, Grand Portage, Pipestone, Mississippi NRRA, Saint Croix NSR. North Country NST omitted (trail, not an in-state park unit). |
| **Regional** | 70 | Metropolitan Council regional parks / park reserves (LPH Parks). Twin Cities system. |
| **County** | 146 | MetroGIS Collaborative Parks (county-owned units in the seven-county metro) **plus** curated Greater Minnesota county parks with real coordinates. |

Coordinates are real. Highlights and amenities are **sparse on purpose**: official GIS rarely includes a full amenity inventory. Empty states say “Not listed in our sources yet.” Do not treat amenity chips as complete.

**Not county-complete across all 87 counties.** Many counties do not publish park GIS. Greater MN points are a solid real-world seed, not a staff directory of every county picnic ground. City parks are deferred.

Refresh:

```bash
python3 scripts/build_parks_json.py
bin/rails parks:ingest
```

## What’s in vs deferred

**In this slice**

- Minnesota-bounded MapLibre map, parks as pins colored by type
- Click → name, type, agency, straight-line distance, highlights, amenities/activities
- Filters: type, amenities/activities that exist, distance (when origin set), favorited, visited
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
- Private GitHub repo name `mn-parks` (this codebase)

## API (JSON)

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/api/parks` | All in-state parks + filter vocab |
| GET | `/api/parks/:id` | Detail |
| GET | `/api/parks/random` | Uniform among ingested parks |
| PATCH | `/api/parks/:id/user_state` | `{ favorited, visited }` — auth required |
| GET | `/api/me` | Session + whether Google is enabled |
| POST | `/api/signup` `/api/login` | Email/password |
| DELETE | `/api/logout` | |

Cookie session. Vite proxies `/api` in development.
