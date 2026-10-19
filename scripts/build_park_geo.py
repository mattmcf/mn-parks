#!/usr/bin/env python3
"""Cross-check park lat/lng and rewrite db/data/parks.json when pins are wrong.

Writes db/data/park_geo.json (audit, same pattern as dark_sky.json /
park_reviews.json). Applies accepted corrections back into parks.json so the
map ships unit-level coordinates. Runtime never geocodes.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from ingest_lib import PARKS_JSON, load_parks  # noqa: E402
from park_geo import (  # noqa: E402
    OUT,
    apply_to_parks,
    build_payload,
    decide,
    gather_nominatim_hits,
    load_nps_visitor_centers,
    should_geocode,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Cross-check park pins against Nominatim / NPS visitor centers."
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Use cached Nominatim/NPS responses under MN_PARKS_CACHE.",
    )
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Substring of park name to check (repeatable). Default: county/national/regional.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write park_geo.json but do not rewrite parks.json.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    skip = args.skip_fetch or os.environ.get("PARKS_SKIP_FETCH") == "1"
    only = [s.lower() for s in args.only] or [
        s.lower() for s in (os.environ.get("PARKS_GEO_ONLY") or "").split(",") if s.strip()
    ]

    parks = load_parks()
    print(f"Cross-checking coordinates for {len(parks)} shipped parks…")
    nps_vcs = load_nps_visitor_centers(skip_fetch=skip)
    decisions = []
    geocoded = 0
    for park in parks:
        if only and not any(s in park["name"].lower() for s in only):
            continue
        hits = []
        vcs = nps_vcs.get(str(park.get("source_id") or "").lower(), [])
        if should_geocode(park) or vcs or only:
            if should_geocode(park) or only:
                hits = gather_nominatim_hits(park, skip_fetch=skip)
                geocoded += 1
                if geocoded % 20 == 0:
                    print(f"  Nominatim {geocoded} parks…")
        decisions.append(decide(park, hits, nps_vcs=vcs))

    payload = build_payload(decisions)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(
        f"Wrote {OUT}: checked {payload['counts']['checked']}, "
        f"corrected {payload['counts']['corrected']}, "
        f"flagged {payload['counts']['flagged']} "
        f"(Nominatim queries for {geocoded} parks)"
    )
    for row in decisions:
        if row.action == "corrected" or row.flagged:
            print(
                f"  {row.action:9} {row.name}: {row.original_latitude},{row.original_longitude} "
                f"-> {row.latitude},{row.longitude} ({row.miles} mi) {row.reason[:120]}"
            )

    if args.dry_run:
        print("Dry run: parks.json not rewritten.")
        return

    changed = apply_to_parks(parks, decisions)
    if not changed:
        print("No pin corrections to apply to parks.json.")
        return
    shipped = json.loads(PARKS_JSON.read_text())
    shipped["parks"] = parks
    shipped["geo_checked_at"] = payload["generated_at"]
    attribution = list(shipped.get("attribution") or [])
    note = (
        "Pin coordinates cross-checked during parks:refresh against OSM Nominatim "
        "(MN-biased), NPS visitor centers, and the Census Minnesota boundary. "
        "Audit: db/data/park_geo.json."
    )
    if note not in attribution:
        attribution.append(note)
    shipped["attribution"] = attribution
    PARKS_JSON.write_text(json.dumps(shipped, indent=2) + "\n")
    print(f"Updated {changed} park coordinates in {PARKS_JSON}")


if __name__ == "__main__":
    main()
