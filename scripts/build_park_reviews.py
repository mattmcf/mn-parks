#!/usr/bin/env python3
"""Build db/data/park_reviews.json from official campground inventories.

Chosen source (ToS-safe): Minnesota DNR Parks & Trails camping units
(Geospatial Commons) plus NPS Campgrounds API for federal units.

Not used (ToS / no public developer API for storing ratings):
- The Dyrt — terms forbid robots/scrapers without written permission; no public API
- Campendium — no documented reuse API
- Google Places — caching/storing ratings is forbidden by the Places ToS
- Recreation.gov RIDB live API — encouraged for reuse, but requires an API key
  and the 571 MB bulk export is too large for this refresh. Optional RIDB_API_KEY
  is accepted if present; ratings are still not a documented RIDB field.

Camping score is therefore NOT a visitor-review average. It is an official
inventory score (0–5) computed from DNR camping-unit attributes. Parks without
official camping-unit records get no score (not guessed). NPS campgrounds
contribute campsite counts, official description snippets, and reservation URLs
without inventing a star rating.

Runtime never calls DNR, NPS, DarkSky, or review sites.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingest_lib import CACHE, ROOT, http_json, load_parks, names_match, unzip_url

OUT = ROOT / "db" / "data" / "park_reviews.json"
DNR_ZIP_URL = (
    "https://resources.gisdata.mn.gov/pub/gdrs/data/pub/us_mn_state_dnr/"
    "struc_parks_and_trails_campsites/gpkg_struc_parks_and_trails_campsites.zip"
)
DNR_DATASET_URL = (
    "https://gisdata.mn.gov/dataset/1d9ad17a-dafd-41b7-aee6-9db9cdfa067b"
)
NPS_CAMPGROUNDS_URL = "https://developer.nps.gov/api/v1/campgrounds"
RIDB_FACILITIES_URL = "https://ridb.recreation.gov/api/v1/facilities"

SCORE_KIND = "official_inventory"
SCORE_DEFINITION = (
    "0–5 official campsite inventory score from MN DNR Parks & Trails camping "
    "units — not a visitor-review average. "
    "size = min(1, log10(1 + unit_count) / log10(201)); "
    "electric / shower-listed / ADA / waterfront are shares of units; "
    "score = min(5, 2.0*size + 1.2*electric + 0.8*shower + 0.5*ADA + 0.5*waterfront), "
    "rounded to 1 decimal. Null when no official camping-unit record matches the park."
)


def truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"t", "true", "1", "yes"}


def has_shower(value: object) -> bool:
    text = str(value or "").strip().lower()
    return bool(text) and text not in {"unknown", "none", "n/a", "na", "null", "unspecified"}


def is_electric(row: sqlite3.Row) -> bool:
    if truthy(row["AMPS_30_FLAG"]) or truthy(row["AMPS_50_FLAG"]):
        return True
    return "electric" in str(row["CAMPSITE_TYPE_NAME"] or "").lower()


def inventory_score(units: list[sqlite3.Row]) -> float | None:
    n = len(units)
    if n == 0:
        return None
    electric = sum(1 for row in units if is_electric(row)) / n
    ada = sum(1 for row in units if truthy(row["ADA_ACCESSIBLE_FLAG"])) / n
    water = sum(1 for row in units if truthy(row["WATER_FRONT_FLAG"])) / n
    shower = sum(1 for row in units if has_shower(row["DISTANCE_TO_SHOWER"])) / n
    size = min(1.0, math.log10(1 + n) / math.log10(201))
    raw = 2.0 * size + 1.2 * electric + 0.8 * shower + 0.5 * ada + 0.5 * water
    return round(min(5.0, max(0.1, raw)), 1)


def dnr_snippet(units: list[sqlite3.Row]) -> str:
    n = len(units)
    types = Counter(
        (row["CAMPSITE_TYPE_NAME"] or row["CAMPING_UNIT_TYPE"] or "Campsite") for row in units
    )
    top = ", ".join(f"{count} {label.lower()}" for label, count in types.most_common(3))
    campgrounds = {row["CAMPGROUND_NAME"] for row in units if row["CAMPGROUND_NAME"]}
    if len(campgrounds) > 1:
        where = f" across {len(campgrounds)} campgrounds"
    elif len(campgrounds) == 1:
        where = f" at {next(iter(campgrounds))}"
    else:
        where = ""
    return f"{n} official DNR camping unit{'s' if n != 1 else ''}{where}, including {top}."


def fetch_dnr_gpkg() -> Path:
    dest = CACHE / "dnr_campsites"
    unzip_url(DNR_ZIP_URL, dest)
    gpkgs = list(dest.rglob("*.gpkg"))
    if not gpkgs:
        raise FileNotFoundError(f"No GeoPackage in {dest}")
    return gpkgs[0]


def cached_gpkg() -> Path:
    dest = CACHE / "dnr_campsites"
    gpkgs = list(dest.rglob("*.gpkg"))
    if not gpkgs:
        raise FileNotFoundError(f"No DNR campsite cache at {dest}")
    return gpkgs[0]


def load_dnr_units(gpkg: Path) -> dict[str, list[sqlite3.Row]]:
    con = sqlite3.connect(str(gpkg))
    con.row_factory = sqlite3.Row
    rows = list(con.execute("SELECT * FROM struc_parks_and_trails_campsites"))
    groups: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        unit_type = row["CONTAINING_MGMT_UNIT_TYPE_NAME"]
        if unit_type not in {"State Park", "State Recreation Area"}:
            continue
        name = row["CONTAINING_MGMT_UNIT_NAME"]
        if not name:
            continue
        groups[name].append(row)
    print(f"DNR camping units: {sum(len(v) for v in groups.values())} in {len(groups)} state parks/SRAs")
    return groups


def match_mgmt_unit(parks: list[dict], mgmt_name: str) -> dict | None:
    hits = [p for p in parks if names_match(mgmt_name, p["name"])]
    if len(hits) == 1:
        return hits[0]
    if not hits:
        return None
    stateish = [p for p in hits if p.get("park_type") == "state"]
    return (stateish or hits)[0]


def fetch_nps_campgrounds() -> list[dict]:
    key = os.environ.get("NPS_API_KEY") or "DEMO_KEY"
    start = 0
    rows: list[dict] = []
    while True:
        url = f"{NPS_CAMPGROUNDS_URL}?stateCode=MN&limit=50&start={start}"
        data, _ = http_json(url, headers={"X-Api-Key": key})
        batch = data.get("data") or []
        rows.extend(batch)
        total = int(data.get("total") or len(rows))
        start += len(batch)
        if not batch or start >= total:
            break
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "nps_campgrounds.json").write_text(json.dumps({"data": rows}))
    print(f"Fetched {len(rows)} NPS campground records for Minnesota")
    return rows


def load_cached_nps_campgrounds() -> list[dict]:
    path = CACHE / "nps_campgrounds.json"
    if not path.exists():
        return []
    return json.loads(path.read_text()).get("data") or []


def nps_site_count(row: dict) -> int | None:
    total = 0
    found = False
    for key in ("numberOfSitesReservable", "numberOfSitesFirstComeFirstServe"):
        raw = row.get(key)
        if raw in (None, ""):
            continue
        try:
            total += int(raw)
            found = True
        except (TypeError, ValueError):
            continue
    campsites = row.get("campsites") or {}
    if isinstance(campsites, dict):
        for key in ("totalSites", "electricalHookups", "group"):
            raw = campsites.get(key)
            try:
                n = int(raw)
            except (TypeError, ValueError):
                continue
            if n:
                found = True
                total = max(total, n if key == "totalSites" else total)
    return total if found else None


def fetch_ridb_mn() -> list[dict]:
    key = os.environ.get("RIDB_API_KEY")
    if not key:
        return []
    offset = 0
    rows: list[dict] = []
    while True:
        url = f"{RIDB_FACILITIES_URL}?state=MN&limit=50&offset={offset}&full=true"
        data, _ = http_json(url, headers={"apikey": key})
        batch = data.get("RECDATA") or []
        rows.extend(batch)
        meta = data.get("METADATA") or {}
        results = meta.get("RESULTS") or {}
        total = int(results.get("TOTAL_COUNT") or 0)
        offset += len(batch)
        if not batch or (total and offset >= total) or offset > 5000:
            break
    print(f"Fetched {len(rows)} RIDB facilities for Minnesota")
    return rows


def build(parks: list[dict], dnr_groups: dict[str, list[sqlite3.Row]], nps_cgs: list[dict], ridb: list[dict]) -> dict:
    retrieved = datetime.now(timezone.utc).isoformat()
    by_key: dict[tuple[str, str], dict] = {}

    for mgmt_name, units in dnr_groups.items():
        park = match_mgmt_unit(parks, mgmt_name)
        if not park:
            continue
        key = (park["source"], str(park["source_id"]))
        score = inventory_score(units)
        electric = sum(1 for row in units if is_electric(row))
        by_key[key] = {
            "source": park["source"],
            "source_id": str(park["source_id"]),
            "park_name": park["name"],
            "camping_score": score,
            "score_kind": SCORE_KIND,
            "campsite_count": len(units),
            "review_count": None,
            "electric_sites": electric,
            "snippet": dnr_snippet(units),
            "url": park.get("source_url") or DNR_DATASET_URL,
            "inventory_source": "mn_dnr_camping_units",
        }

    nps_parks = {str(p["source_id"]): p for p in parks if p.get("source") == "nps_api"}
    nps_by_code: dict[str, list[dict]] = defaultdict(list)
    for row in nps_cgs:
        code = str(row.get("parkCode") or "")
        if code:
            nps_by_code[code].append(row)

    for code, records in nps_by_code.items():
        park = nps_parks.get(code)
        if not park:
            continue
        key = (park["source"], str(park["source_id"]))
        site_total = 0
        snippets = []
        url = park.get("source_url")
        for rec in records:
            count = nps_site_count(rec)
            if count:
                site_total += count
            desc = (rec.get("description") or "").strip()
            if desc:
                snippets.append(desc.split(".")[0][:220].rstrip() + ".")
            url = rec.get("reservationUrl") or rec.get("url") or url
        existing = by_key.get(key)
        if existing:
            if site_total and not existing.get("campsite_count"):
                existing["campsite_count"] = site_total
            continue
        by_key[key] = {
            "source": park["source"],
            "source_id": str(park["source_id"]),
            "park_name": park["name"],
            "camping_score": None,
            "score_kind": SCORE_KIND,
            "campsite_count": site_total or None,
            "review_count": None,
            "electric_sites": None,
            "snippet": snippets[0] if snippets else None,
            "url": url,
            "inventory_source": "nps_campgrounds",
        }

    if ridb:
        for fac in ridb:
            fac_name = fac.get("FacilityName") or ""
            fac_type = (fac.get("FacilityTypeDescription") or "").lower()
            if "camp" not in fac_type and "camp" not in fac_name.lower():
                continue
            park = next((p for p in parks if names_match(fac_name, p["name"])), None)
            if not park:
                continue
            key = (park["source"], str(park["source_id"]))
            rec = by_key.get(key)
            url = fac.get("FacilityReservationURL")
            if rec:
                rec["url"] = rec.get("url") or url
            elif url:
                by_key[key] = {
                    "source": park["source"],
                    "source_id": str(park["source_id"]),
                    "park_name": park["name"],
                    "camping_score": None,
                    "score_kind": SCORE_KIND,
                    "campsite_count": None,
                    "review_count": None,
                    "electric_sites": None,
                    "snippet": None,
                    "url": url,
                    "inventory_source": "recreation_gov_ridb",
                }

    reviews = sorted(by_key.values(), key=lambda row: row["park_name"])
    scored = sum(1 for row in reviews if row.get("camping_score") is not None)
    return {
        "generated_at": retrieved,
        "retrieved_at": retrieved,
        "source": "mn_dnr_camping_units+nps_campgrounds",
        "source_urls": [DNR_DATASET_URL, "https://developer.nps.gov/api/v1/campgrounds"],
        "camping_score_definition": SCORE_DEFINITION,
        "attribution": [
            "Minnesota DNR Parks & Trails camping units via Minnesota Geospatial Commons (struc_parks_and_trails_campsites).",
            "National Park Service Campgrounds API (stateCode=MN) for federal campground counts and official descriptions.",
        ],
        "counts": {
            "parks_with_camping_intel": len(reviews),
            "parks_with_camping_score": scored,
        },
        "reviews": reviews,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh camping inventory / score artifact.")
    parser.add_argument("--skip-fetch", action="store_true")
    args = parser.parse_args()
    skip = args.skip_fetch or os.environ.get("PARKS_SKIP_FETCH") == "1"

    parks = load_parks()
    if skip:
        print(f"Skipping remote camping fetch; using cache at {CACHE}")
        gpkg = cached_gpkg()
        nps_cgs = load_cached_nps_campgrounds()
        ridb: list[dict] = []
    else:
        print("Fetching MN DNR camping units and NPS campgrounds…")
        gpkg = fetch_dnr_gpkg()
        try:
            nps_cgs = fetch_nps_campgrounds()
        except Exception as exc:
            print(f"NPS campgrounds fetch failed ({exc}); using cache if present.")
            nps_cgs = load_cached_nps_campgrounds()
        try:
            ridb = fetch_ridb_mn()
        except Exception as exc:
            print(f"RIDB fetch skipped ({exc}).")
            ridb = []

    payload = build(parks, load_dnr_units(gpkg), nps_cgs, ridb)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(
        f"Wrote {OUT}: {payload['counts']['parks_with_camping_intel']} parks with camping intel, "
        f"{payload['counts']['parks_with_camping_score']} with a camping score"
    )


if __name__ == "__main__":
    main()
