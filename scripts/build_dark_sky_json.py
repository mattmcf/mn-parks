#!/usr/bin/env python3
"""Build db/data/dark_sky.json from DarkSky International's official place API.

Source: WordPress REST API for International Dark Sky Places
  https://darksky.org/wp-json/wp/v2/darksky_place
  https://darksky.org/wp-json/wp/v2/idsp_type

Runtime (rails server / Vite) never calls DarkSky. Empty/false unless a
certified Minnesota place matches an existing park by name (and coords when
both exist). Unmatched official places are stored but not guessed onto nearby
parks.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingest_lib import (
    CACHE,
    ROOT,
    http_json,
    in_minnesota,
    load_parks,
    match_park,
)

OUT = ROOT / "db" / "data" / "dark_sky.json"
WP_PLACES = "https://darksky.org/wp-json/wp/v2/darksky_place"
WP_TYPES = "https://darksky.org/wp-json/wp/v2/idsp_type"
FINDER_URL = "https://darksky.org/what-we-do/international-dark-sky-places/all-places/"

TAG_RE = re.compile(r"<[^>]+>")
WS_RE = re.compile(r"\s+")
COORD_PAIR_RE = re.compile(
    r"\[(-?\d{1,3}\.\d+)\s*,\s*(-?\d{1,3}\.\d+)\]"
)
MN_ADDR_RE = re.compile(r",\s*MN\b|, Minnesota\b|\bMN\s+\d{5}", re.I)
CANADA_ADDR_RE = re.compile(r"\bCanada\b|\bOntario\b|, ON\b", re.I)


def strip_html(raw: str) -> str:
    text = html.unescape(raw or "")
    text = TAG_RE.sub(" ", text)
    return WS_RE.sub(" ", text).strip()


def fetch_types() -> dict[int, dict]:
    data, _ = http_json(f"{WP_TYPES}?per_page=100")
    out: dict[int, dict] = {}
    for row in data or []:
        out[int(row["id"])] = {
            "slug": row.get("slug") or "",
            "name": row.get("name") or "",
        }
    return out


def fetch_places() -> list[dict]:
    page = 1
    places: list[dict] = []
    fields = "id,slug,title,link,idsp_type,content,date_gmt"
    while True:
        data, headers = http_json(
            f"{WP_PLACES}?per_page=100&page={page}&_fields={fields}"
        )
        batch = data or []
        places.extend(batch)
        total_pages = int(headers.get("x-wp-totalpages") or (page if len(batch) < 100 else page + 1))
        print(f"DarkSky places page {page}: {len(batch)}")
        if not batch or page >= total_pages:
            break
        page += 1
        if page > 20:
            break
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "darksky_places.json").write_text(json.dumps(places))
    return places


def load_cached_places() -> list[dict]:
    path = CACHE / "darksky_places.json"
    if not path.exists():
        raise FileNotFoundError(f"No DarkSky cache at {path}")
    return json.loads(path.read_text())


def extract_section(text: str, heading: str) -> str:
    pattern = re.compile(
        rf"{re.escape(heading)}\s+(.+?)(?=\s+(?:About|Designated|Category|Address|Contact|Land Area|Documents|Weather|More info)\b|$)",
        re.I,
    )
    match = pattern.search(text)
    return match.group(1).strip() if match else ""


def extract_coords(text: str) -> tuple[float | None, float | None]:
    for lat_s, lon_s in COORD_PAIR_RE.findall(text):
        lat, lon = float(lat_s), float(lon_s)
        if abs(lat) <= 90 and abs(lon) <= 180:
            return lat, lon
    return None, None


def extract_year(text: str, fallback: str | None) -> str | None:
    section = extract_section(text, "Designated")
    match = re.search(r"\b(19|20)\d{2}\b", section or text)
    if match:
        return match.group(0)
    if fallback:
        return fallback[:4]
    return None


def is_minnesota_certified(plain: str, lat: float | None, lon: float | None) -> bool:
    address = extract_section(plain, "Address")
    if address and CANADA_ADDR_RE.search(address) and not MN_ADDR_RE.search(address):
        return False
    if address and MN_ADDR_RE.search(address):
        return True
    if MN_ADDR_RE.search(plain) and not CANADA_ADDR_RE.search(address or ""):
        return True
    return in_minnesota(lat, lon)


def category_for(place: dict, types: dict[int, dict], plain: str) -> tuple[str, str]:
    from_html = extract_section(plain, "Category")
    ids = place.get("idsp_type") or []
    for tid in ids:
        info = types.get(int(tid)) or {}
        slug = info.get("slug") or ""
        if slug:
            label = from_html or info.get("name") or slug.replace("-", " ").title()
            return slug, label
    if from_html:
        slug = re.sub(r"[^a-z0-9]+", "-", from_html.lower()).strip("-")
        return slug, from_html
    return "international-dark-sky-place", "Dark Sky Place"


def build(places: list[dict], types: dict[int, dict], parks: list[dict]) -> dict:
    retrieved = datetime.now(timezone.utc).isoformat()
    official: list[dict] = []
    for place in places:
        title = html.unescape((place.get("title") or {}).get("rendered") or "").strip()
        html_content = (place.get("content") or {}).get("rendered") or ""
        plain = strip_html(html_content)
        lat, lon = extract_coords(html_content + " " + plain)
        if not is_minnesota_certified(plain, lat, lon):
            continue
        slug, label = category_for(place, types, plain)
        official.append(
            {
                "darksky_id": place.get("id"),
                "name": title,
                "category": slug,
                "category_label": label,
                "designated": extract_year(plain, place.get("date_gmt")),
                "latitude": lat,
                "longitude": lon,
                "address": extract_section(plain, "Address") or None,
                "darksky_url": place.get("link"),
            }
        )

    matched: list[dict] = []
    unmatched: list[dict] = []
    for item in official:
        park = match_park(
            parks,
            name=item["name"],
            lat=item["latitude"],
            lon=item["longitude"],
        )
        record = dict(item)
        if park:
            record["matched_source"] = park["source"]
            record["matched_source_id"] = str(park["source_id"])
            record["matched_park_name"] = park["name"]
            matched.append(record)
        else:
            record["reason"] = (
                "No existing park with a matching name"
                + (" and coordinates" if item["latitude"] is not None else "")
                + ". Not guessed onto nearby units."
            )
            unmatched.append(record)

    return {
        "generated_at": retrieved,
        "retrieved_at": retrieved,
        "source_url": WP_PLACES,
        "finder_url": FINDER_URL,
        "attribution": [
            "DarkSky International (formerly IDA) International Dark Sky Places via the official WordPress REST API (darksky_place).",
        ],
        "counts": {
            "official_minnesota": len(official),
            "matched": len(matched),
            "unmatched": len(unmatched),
        },
        "places": matched,
        "unmatched": unmatched,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh Dark Sky certified-place artifact.")
    parser.add_argument("--skip-fetch", action="store_true")
    args = parser.parse_args()
    skip = args.skip_fetch or os.environ.get("PARKS_SKIP_FETCH") == "1"

    parks = load_parks()
    types = fetch_types()
    if skip:
        print(f"Skipping DarkSky fetch; using cache at {CACHE}")
        places = load_cached_places()
    else:
        print("Fetching DarkSky International certified places…")
        places = fetch_places()
        CACHE.mkdir(parents=True, exist_ok=True)
        (CACHE / "darksky_types.json").write_text(json.dumps(types))

    payload = build(places, types, parks)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(
        f"Wrote {OUT}: {payload['counts']['official_minnesota']} Minnesota certified places, "
        f"{payload['counts']['matched']} matched, {payload['counts']['unmatched']} unmatched"
    )
    for row in payload["places"]:
        print(f"  matched {row['name']} -> {row['matched_park_name']} ({row['category']})")
    for row in payload["unmatched"]:
        print(f"  unmatched {row['name']}: {row['reason']}")


if __name__ == "__main__":
    main()
