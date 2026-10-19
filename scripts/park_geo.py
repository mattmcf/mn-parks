"""Cross-check park pins against a second source before shipping parks.json.

Runtime (rails server / Vite) never calls Nominatim, Overpass, or NPS.
This module is used only by `parks:refresh` / `parks:refresh_geo`.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.ops import nearest_points

from ingest_lib import (
    CACHE,
    compact_name,
    haversine_miles,
    http_json,
    in_minnesota as in_minnesota_bbox,
    is_domain_only_source_url,
    strip_suffixes,
)

ROOT = Path(__file__).resolve().parents[1]
BOUNDARY_PATH = Path(__file__).resolve().parent / "data" / "mn_boundary.geojson"
OUT = ROOT / "db" / "data" / "park_geo.json"
PARKS_JSON = ROOT / "db" / "data" / "parks.json"

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NPS_VC_URL = "https://developer.nps.gov/api/v1/visitorcenters"

MN_VIEWBOX = "-97.5,49.4,-89.34,43.4"

# Administrative hits are the failure mode for Greater MN pins (township /
# county seat instead of the campground). Never auto-correct *to* these.
ADMIN_CLASSES = {"boundary", "place", "political"}
ADMIN_TYPES = {
    "administrative",
    "city",
    "town",
    "village",
    "hamlet",
    "county",
    "state",
    "township",
    "municipality",
    "suburb",
    "neighbourhood",
    "neighborhood",
}

UNIT_CLASS_TYPES = {
    ("leisure", "park"),
    ("leisure", "nature_reserve"),
    ("leisure", "recreation_ground"),
    ("tourism", "camp_site"),
    ("tourism", "picnic_site"),
    ("tourism", "attraction"),
    ("tourism", "information"),
    ("boundary", "national_park"),
    ("boundary", "protected_area"),
    ("landuse", "recreation_ground"),
    ("landuse", "forest"),
    ("natural", "water"),
    ("natural", "wood"),
    ("amenity", "ranger_station"),
}

STOPWORDS = {
    "the",
    "and",
    "of",
    "a",
    "park",
    "parks",
    "county",
    "regional",
    "state",
    "national",
    "campground",
    "recreation",
    "area",
    "reserve",
    "memorial",
    "public",
    "access",
}

# Pins that automated geocoders cannot resolve to the named unit. Keyed by
# (source, source_id). Human Maps/satellite review wins over Nominatim on
# refresh. Nessel was a guessed farmland point south of the township, not
# Rush Lake and not Rush Creek Park in Rush City.
MANUAL_OVERRIDES: dict[tuple[str, str], dict] = {
    ("curated_greater_mn_county", "county:nessel-campground-rush-creek"): {
        "latitude": 45.689118,
        "longitude": -93.054827,
        "check_name": "Rush Lake, Nessel Township, Chisago County",
        "check_source": "osm_nominatim_named_lake",
        "reason": (
            "Original pin (45.627, -93.137) sits in empty farmland south of "
            "Nessel Township — not on Rush Lake, not at Rush Creek Park in "
            "Rush City, and not a campground. Nominatim has no 'Nessel "
            "Campground'. Prefer the named lake in Nessel Township (OSM "
            "relation Rush Lake) over a township/city centroid."
        ),
    },
    ("curated_greater_mn_county", "county:arrowhead-point-county-park"): {
        "latitude": 43.73991496641728,
        "longitude": -93.55360626469496,
        "check_name": "Arrowhead Point County Park (Maps review)",
        "check_source": "human_maps_review",
        "reason": (
            "Matthew Maps review: curated centroid was 11 mi east of the "
            "Freeborn County unit. Pin moved onto the park."
        ),
    },
    ("curated_greater_mn_county", "county:bray-park"): {
        "latitude": 44.182884628060606,
        "longitude": -93.78960964428298,
        "managing_agency": "Blue Earth County Parks",
        "source_url": "https://www.blueearthcountymn.gov/181/Parks",
        "highlights": (
            "Blue Earth County park on Madison Lake — camping and lake access, "
            "not Martin County's Lake George park at Fairmont."
        ),
        "check_name": "Bray Park, Madison Lake (Maps review)",
        "check_source": "human_maps_review",
        "reason": (
            "Matthew Maps review: the Fairmont / Lake George pin was a "
            "different Bray. Moved onto Blue Earth County's Madison Lake unit."
        ),
    },
    ("curated_greater_mn_county", "county:snake-river-landing-pine-city"): {
        "latitude": 45.840293456991624,
        "longitude": -92.93316942339543,
        "check_name": "Snake River Landing, Pine City (Maps review)",
        "check_source": "human_maps_review",
        "reason": (
            "Matthew Maps review: this is Snake River Landing in Pine City, "
            "not Pine County 'Dalles' and not Aitkin's Snake River County Park."
        ),
    },
    ("curated_greater_mn_county", "county:daly-park"): {
        "latitude": 43.87411501149293,
        "longitude": -93.99934525778492,
        "highlights": (
            "Blue Earth County camping park near Mapleton / Sterling Township."
        ),
        "check_name": "Daly Park & Campground (Maps review)",
        "check_source": "human_maps_review",
        "reason": (
            "Matthew Maps review: curated Hall Lake guess was ~16 mi from the "
            "Blue Earth camping unit. Pin moved onto Daly Park near Mapleton."
        ),
    },
    ("curated_greater_mn_county", "county:red-rock-falls-county-park"): {
        "latitude": 44.122282251871425,
        "longitude": -95.10528353968522,
        "managing_agency": "Cottonwood County Parks",
        "source_url": "https://www.co.cottonwood.mn.us/",
        "highlights": (
            "Cottonwood County park at Red Rock Falls near Sanborn, not a "
            "Mower County Cedar River picnic near Austin."
        ),
        "check_name": "Red Rock Falls County Park, Sanborn (Maps review)",
        "check_source": "human_maps_review",
        "reason": (
            "Matthew Maps review: the Mower / Austin pin was the wrong county. "
            "Moved onto Cottonwood County's Red Rock Falls unit near Sanborn."
        ),
    },
    ("curated_greater_mn_county", "county:warner-lake-county-park"): {
        "latitude": 45.4225777283712,
        "longitude": -94.08401563362033,
        "highlights": "Stearns County park on Warner Lake near Clearwater.",
        "check_name": "Warner Lake County Park, Clearwater (Maps review)",
        "check_source": "human_maps_review",
        "reason": (
            "Matthew Maps review: curated pin west of Cold Spring was 16 mi "
            "from the Stearns unit. Moved onto Warner Lake near Clearwater."
        ),
    },
}

# Removed from inventory so refresh cannot resurrect them. Keyed by the
# source/source_id that parks.json used before the drop.
HUMAN_DROPS: dict[tuple[str, str], dict] = {
    ("curated_greater_mn_county", "county:ortonville-big-stone-county-park"): {
        "reason": (
            "Matthew Maps review: this is Big Stone Lake State Park (DNR "
            "SPK00115 already in inventory ~0.12 mi from the reviewed point). "
            "County duplicate removed."
        ),
    },
    ("curated_greater_mn_county", "county:rainy-lake-international-falls-county-dock"): {
        "reason": (
            "Matthew Maps review: remove the Koochiching county dock record."
        ),
    },
}

HUMAN_RENAMES: dict[tuple[str, str], dict] = {
    ("curated_greater_mn_county", "county:dalles-snake-river-county-park"): {
        "name": "Snake River Landing (Pine City)",
        "source_id": "county:snake-river-landing-pine-city",
        "reason": (
            "Matthew Maps review: this is Snake River Landing in Pine City, "
            "not Dalles / Snake River County Park."
        ),
    },
}

# Miles of disagreement before we move a pin onto a high-quality unit hit.
CORRECT_MILES = {
    "curated_greater_mn_county": 1.5,
    "county": 2.5,
    "regional": 3.0,
    "state": 0.4,
    "national": 10.0,
    "wilderness": 80.0,
}

# Hard cap: same-name hits farther than this are a different place (e.g. another
# Bald Eagle Lake). Outside-MN originals skip this cap.
MAX_CORRECT_MILES = {
    "curated_greater_mn_county": 10.0,
    "metrogis_collaborative_parks": 8.0,
    "met_council_regional_parks": 8.0,
    "mn_dnr_state_parks": 5.0,
    "nps_api": 80.0,
    "wilderness_connect_nwps": 80.0,
}

GENERIC_HIT_NAMES = {
    "park",
    "county park",
    "county forest",
    "public access",
    "boat launch",
    "fairgrounds",
    "square park",
}


@dataclass
class GeoHit:
    lat: float
    lon: float
    name: str
    display_name: str
    osm_class: str
    osm_type: str
    source: str
    quality: int = 0

    def in_admin(self) -> bool:
        return self.osm_class in ADMIN_CLASSES or self.osm_type in ADMIN_TYPES


@dataclass
class GeoDecision:
    name: str
    park_type: str
    source: str
    source_id: str
    action: str
    latitude: float
    longitude: float
    original_latitude: float
    original_longitude: float
    miles: float | None
    reason: str
    check_source: str | None
    check_name: str | None
    original_in_minnesota: bool
    check_in_minnesota: bool | None
    flagged: bool = False
    source_url: str | None = None
    source_url_hub: bool = False
    extra: dict = field(default_factory=dict)

    def as_json(self) -> dict:
        row = asdict(self)
        extra = row.pop("extra") or {}
        row.update(extra)
        return row


_MN_GEOM = None


def mn_polygon():
    global _MN_GEOM
    if _MN_GEOM is None:
        payload = json.loads(BOUNDARY_PATH.read_text())
        geom = payload["geometry"] if payload.get("type") == "Feature" else payload
        _MN_GEOM = shape(geom).buffer(0)
    return _MN_GEOM


def in_mn_polygon(lat: float, lon: float) -> bool:
    if lat is None or lon is None:
        return False
    geom = mn_polygon()
    point = Point(float(lon), float(lat))
    # 20m tolerance: Census 20m outlines miss some river-border parks.
    return bool(geom.covers(point) or geom.distance(point) <= 0.0002)


def snap_to_mn(lat: float, lon: float) -> tuple[float, float]:
    geom = mn_polygon()
    point = Point(float(lon), float(lat))
    if geom.covers(point) or geom.distance(point) <= 0.0002:
        return float(lat), float(lon)
    snapped = nearest_points(geom, point)[0]
    interior = geom.representative_point()
    dx, dy = interior.x - snapped.x, interior.y - snapped.y
    dist = (dx * dx + dy * dy) ** 0.5 or 1.0
    # Nudge ~80m into Minnesota so rounding cannot push the pin back to WI.
    nlon = snapped.x + dx / dist * 0.0008
    nlat = snapped.y + dy / dist * 0.0008
    return round(float(nlat), 6), round(float(nlon), 6)


def looks_swapped(lat: float, lon: float) -> bool:
    """True when values look like (longitude, latitude) stored in lat/lng fields."""
    return 43.4 <= float(lon) <= 49.4 and -97.5 <= float(lat) <= -89.34


def name_tokens(name: str) -> set[str]:
    tokens = set(re.findall(r"[a-z0-9]+", (name or "").lower()))
    return {t for t in tokens if t not in STOPWORDS and len(t) > 1}


def query_strings(park: dict) -> list[str]:
    name = (park.get("name") or "").strip()
    agency = park.get("managing_agency") or ""
    county = ""
    m = re.search(r"([A-Za-z][A-Za-z .'-]+ County)", agency)
    if m:
        county = m.group(1).strip()
    parts = [p.strip() for p in re.split(r"\s*/\s*|\s+[—–-]\s+|\(", name) if p.strip()]
    parts = [re.sub(r"[)]$", "", p).strip() for p in parts]
    dehyphen = name.replace("-", " ")
    queries: list[str] = []

    def add(q: str) -> None:
        q = re.sub(r"\s+", " ", q).strip(" ,")
        if q and q not in queries:
            queries.append(q)

    add(f"{name}, Minnesota")
    if dehyphen != name:
        add(f"{dehyphen}, Minnesota")
    if county:
        add(f"{name}, {county}, Minnesota")
    for part in parts:
        if part.lower() == name.lower():
            continue
        add(f"{part}, Minnesota")
        if county:
            add(f"{part}, {county}, Minnesota")
        if "camp" in name.lower() and "camp" not in part.lower():
            add(f"{part} Campground, Minnesota")
        if "park" not in part.lower():
            add(f"{part} Park, Minnesota")
        # Creek/river parks are often on a named lake in the same township.
        if re.search(r"\bcreek\b", part, re.I):
            add(f"{re.sub(r'(?i)creek', 'Lake', part)}, Minnesota")
    return queries


def geo_names_ok(park_name: str, hit_name: str) -> bool:
    """Stricter than intel names_match: no substring lakes ('Bald Eagle Lake')."""
    if not park_name or not hit_name:
        return False
    if compact_name(hit_name) in GENERIC_HIT_NAMES:
        return False
    if compact_name(park_name) == compact_name(hit_name):
        return True
    sa, sb = strip_suffixes(park_name), strip_suffixes(hit_name)
    if sa and sa == sb:
        return True
    pt, ht = name_tokens(park_name), name_tokens(hit_name)
    if pt and ht and pt == ht:
        return True
    # Slash aliases ("Dalles / Snake River County Park") — not hyphenated
    # compounds like "Bald Eagle-Otter Lakes - Bald Eagle Lake".
    for part in re.split(r"\s*/\s*", park_name):
        part = part.strip()
        if not part or part.lower() == park_name.lower():
            continue
        if compact_name(part) == compact_name(hit_name):
            return True
        if strip_suffixes(part) == strip_suffixes(hit_name) and strip_suffixes(part):
            return True
        if name_tokens(part) == ht and ht:
            return True
    return False


def score_hit(hit: GeoHit, park: dict) -> int:
    if hit.in_admin():
        return 0
    score = 1
    if (hit.osm_class, hit.osm_type) in UNIT_CLASS_TYPES:
        score += 5
    if hit.osm_class == "waterway":
        score += 1
    park_name = park.get("name") or ""
    if hit.osm_type == "camp_site" and re.search(r"camp", park_name, re.I):
        score += 3
    if hit.osm_type == "water" and re.search(r"\b(lake|pond|river|creek)\b", park_name, re.I):
        score += 3
    tokens = name_tokens(park_name)
    blob = f"{hit.name} {hit.display_name}".lower()
    overlap = sum(1 for t in tokens if t in blob)
    score += overlap * 2
    if geo_names_ok(park_name, hit.name):
        score += 6
    agency = park.get("managing_agency") or ""
    county = re.search(r"([A-Za-z][A-Za-z .'-]+ County)", agency)
    if county and county.group(1).lower() in blob:
        score += 1
    return score


def hit_from_nominatim(row: dict, park: dict) -> GeoHit | None:
    try:
        lat = float(row.get("lat"))
        lon = float(row.get("lon"))
    except (TypeError, ValueError):
        return None
    hit = GeoHit(
        lat=lat,
        lon=lon,
        name=row.get("name") or "",
        display_name=row.get("display_name") or "",
        osm_class=row.get("class") or "",
        osm_type=row.get("type") or "",
        source="nominatim",
    )
    hit.quality = score_hit(hit, park)
    return hit


def nominatim_cache_path(query: str) -> Path:
    digest = hashlib.sha256(query.encode()).hexdigest()[:24]
    return CACHE / "nominatim" / f"{digest}.json"


def nominatim_search(query: str, *, skip_fetch: bool) -> list[dict]:
    path = nominatim_cache_path(query)
    if path.exists():
        return json.loads(path.read_text())
    if skip_fetch:
        return []
    params = {
        "q": query,
        "format": "json",
        "limit": "5",
        "countrycodes": "us",
        "viewbox": MN_VIEWBOX,
        "addressdetails": "1",
        "extratags": "1",
        "namedetails": "1",
    }
    from urllib.parse import urlencode

    url = f"{NOMINATIM_URL}?{urlencode(params)}"
    time.sleep(1.05)
    data, _ = http_json(url, headers={"Accept-Language": "en"})
    rows = data if isinstance(data, list) else []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rows))
    return rows


def gather_nominatim_hits(park: dict, *, skip_fetch: bool) -> list[GeoHit]:
    hits: list[GeoHit] = []
    seen: set[tuple[float, float, str]] = set()
    for query in query_strings(park):
        rows = nominatim_search(query, skip_fetch=skip_fetch)
        for row in rows:
            hit = hit_from_nominatim(row, park)
            if not hit:
                continue
            key = (round(hit.lat, 5), round(hit.lon, 5), hit.name.lower())
            if key in seen:
                continue
            seen.add(key)
            hits.append(hit)
        # First query with a strong unit-level hit is enough.
        if any(h.quality >= 8 and not h.in_admin() for h in hits):
            break
    hits.sort(key=lambda h: h.quality, reverse=True)
    return hits


def load_nps_visitor_centers(*, skip_fetch: bool) -> dict[str, list[GeoHit]]:
    path = CACHE / "nps_visitorcenters.json"
    payload: dict
    if skip_fetch and path.exists():
        payload = json.loads(path.read_text())
    elif skip_fetch:
        return {}
    else:
        import os
        from urllib.parse import urlencode

        key = os.environ.get("NPS_API_KEY") or "DEMO_KEY"
        params = urlencode({"parkCode": "voya,grpo,pipe,miss,sacn", "limit": 50})
        url = f"{NPS_VC_URL}?{params}"
        try:
            payload, _ = http_json(url, headers={"X-Api-Key": key})
        except Exception as exc:
            print(f"NPS visitor centers fetch failed ({exc}); using cache if present.")
            if path.exists():
                payload = json.loads(path.read_text())
            else:
                return {}
        incoming = payload.get("data") or []
        if path.exists():
            existing = json.loads(path.read_text())
            if len(existing.get("data") or []) > len(incoming):
                print(
                    "NPS visitor centers fetch returned fewer records than cache; keeping cache."
                )
                payload = existing
        CACHE.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload))
    by_code: dict[str, list[GeoHit]] = {}
    for row in payload.get("data") or []:
        try:
            lat = float(row.get("latitude") or 0)
            lon = float(row.get("longitude") or 0)
        except (TypeError, ValueError):
            continue
        if not lat or not lon:
            continue
        code = (row.get("parkCode") or "").lower()
        hit = GeoHit(
            lat=lat,
            lon=lon,
            name=row.get("name") or "Visitor Center",
            display_name=row.get("name") or "",
            osm_class="tourism",
            osm_type="information",
            source="nps_visitorcenter",
            quality=12 if in_mn_polygon(lat, lon) else 4,
        )
        by_code.setdefault(code, []).append(hit)
    return by_code


def best_hit(hits: list[GeoHit], park: dict) -> GeoHit | None:
    park_name = park.get("name") or ""
    usable = [
        h
        for h in hits
        if h.quality >= 6
        and not h.in_admin()
        and geo_names_ok(park_name, h.name)
        and h.osm_class != "highway"
    ]
    if not usable:
        return None
    in_mn = [h for h in usable if in_mn_polygon(h.lat, h.lon)]
    pool = in_mn or usable

    def key(h: GeoHit) -> tuple:
        return (h.quality, 1 if compact_name(h.name) == compact_name(park_name) else 0)

    pool.sort(key=key, reverse=True)
    return pool[0]


def max_correct_miles(park: dict) -> float:
    return MAX_CORRECT_MILES.get(park.get("source") or "", 25.0)


def correction_threshold(park: dict) -> float:
    if park.get("source") == "curated_greater_mn_county":
        return CORRECT_MILES["curated_greater_mn_county"]
    return CORRECT_MILES.get(park.get("park_type") or "", 4.0)


def decide(
    park: dict,
    hits: list[GeoHit],
    *,
    nps_vcs: list[GeoHit] | None = None,
    overrides: dict[tuple[str, str], dict] | None = None,
) -> GeoDecision:
    lat = float(park["latitude"])
    lon = float(park["longitude"])
    orig_in = in_mn_polygon(lat, lon)
    key = (park.get("source") or "", str(park.get("source_id") or ""))
    table = overrides if overrides is not None else MANUAL_OVERRIDES
    override = table.get(key)
    all_hits = list(hits)
    if nps_vcs:
        all_hits.extend(nps_vcs)

    source_url = park.get("source_url") or ""
    base = dict(
        name=park["name"],
        park_type=park.get("park_type") or "",
        source=park.get("source") or "",
        source_id=str(park.get("source_id") or ""),
        original_latitude=lat,
        original_longitude=lon,
        original_in_minnesota=orig_in,
        source_url=source_url or None,
        source_url_hub=is_domain_only_source_url(source_url),
    )

    if looks_swapped(lat, lon) and in_mn_polygon(lon, lat):
        return GeoDecision(
            action="corrected",
            latitude=round(lon, 6),
            longitude=round(lat, 6),
            miles=haversine_miles(lat, lon, lon, lat),
            reason="Latitude and longitude appear swapped; reversing puts the pin in Minnesota.",
            check_source="swap_heuristic",
            check_name=park["name"],
            check_in_minnesota=True,
            flagged=False,
            **base,
        )

    if override:
        olat, olon = float(override["latitude"]), float(override["longitude"])
        miles = haversine_miles(lat, lon, olat, olon)
        if miles < 0.15 and not any(
            override.get(field) and park.get(field) != override.get(field)
            for field in ("managing_agency", "source_url", "highlights", "name")
        ):
            return GeoDecision(
                action="keep",
                latitude=lat,
                longitude=lon,
                miles=round(miles, 2),
                reason="Already on the documented unit point for this park.",
                check_source=override.get("check_source") or "manual_override",
                check_name=override.get("check_name"),
                check_in_minnesota=in_mn_polygon(olat, olon),
                flagged=False,
                extra={"override": True},
                **base,
            )
        return GeoDecision(
            action="corrected",
            latitude=round(olat, 6),
            longitude=round(olon, 6),
            miles=round(miles, 2),
            reason=override["reason"],
            check_source=override.get("check_source") or "manual_override",
            check_name=override.get("check_name"),
            check_in_minnesota=in_mn_polygon(olat, olon),
            flagged=False,
            extra={"override": True},
            **base,
        )

    hit = best_hit(all_hits, park)
    ptype = park.get("park_type") or ""

    if looks_swapped(lat, lon):
        return GeoDecision(
            action="flagged",
            latitude=lat,
            longitude=lon,
            miles=None,
            reason="Coordinates look swapped but the reversed pair is not inside Minnesota.",
            check_source=None,
            check_name=None,
            check_in_minnesota=None,
            flagged=True,
            **base,
        )

    if not orig_in:
        if hit and in_mn_polygon(hit.lat, hit.lon):
            miles = haversine_miles(lat, lon, hit.lat, hit.lon)
            return GeoDecision(
                action="corrected",
                latitude=round(hit.lat, 6),
                longitude=round(hit.lon, 6),
                miles=round(miles, 2),
                reason=(
                    f"Original pin is outside the Minnesota polygon; "
                    f"moved to {hit.source} unit point '{hit.name}'."
                ),
                check_source=hit.source,
                check_name=hit.display_name or hit.name,
                check_in_minnesota=True,
                flagged=False,
                **base,
            )
        snap_from_lat, snap_from_lon = lat, lon
        snap_src, snap_name = "mn_boundary_snap", "Minnesota boundary"
        if nps_vcs:
            near = min(
                nps_vcs,
                key=lambda h: mn_polygon().distance(Point(h.lon, h.lat)),
            )
            snap_from_lat, snap_from_lon = near.lat, near.lon
            snap_src, snap_name = near.source, near.display_name or near.name
        slat, slon = snap_to_mn(snap_from_lat, snap_from_lon)
        return GeoDecision(
            action="corrected",
            latitude=slat,
            longitude=slon,
            miles=round(haversine_miles(lat, lon, slat, slon), 2),
            reason=(
                "Pin is outside the Minnesota polygon (border HQ, river "
                "centroid, or cartographic-boundary miss). Snapped to the "
                f"Minnesota side from {snap_name}."
            ),
            check_source=snap_src,
            check_name=snap_name,
            check_in_minnesota=True,
            flagged=True,
            **base,
        )

    # Official DNR reference points and wilderness polygons are trusted unless
    # they already failed the MN polygon test above.
    if ptype in {"state", "wilderness"}:
        return GeoDecision(
            action="keep",
            latitude=lat,
            longitude=lon,
            miles=round(haversine_miles(lat, lon, hit.lat, hit.lon), 2) if hit else None,
            reason="Keep official GIS point/polygon representative (already inside Minnesota).",
            check_source=hit.source if hit else None,
            check_name=(hit.display_name if hit else None),
            check_in_minnesota=in_mn_polygon(hit.lat, hit.lon) if hit else None,
            flagged=False,
            **base,
        )

    if ptype == "national":
        # NPS API lat/lng is the official unit point. Only move when it is
        # outside MN (handled above) or a visitor center in MN is far *and*
        # the API point is not itself a unit-level location... we keep in-MN.
        miles = round(haversine_miles(lat, lon, hit.lat, hit.lon), 2) if hit else None
        return GeoDecision(
            action="keep",
            latitude=lat,
            longitude=lon,
            miles=miles,
            reason="Keep NPS Parks API coordinates; they already fall inside Minnesota.",
            check_source=hit.source if hit else None,
            check_name=(hit.display_name if hit else None),
            check_in_minnesota=in_mn_polygon(hit.lat, hit.lon) if hit else None,
            flagged=False,
            **base,
        )

    if not hit:
        admin = next((h for h in all_hits if h.in_admin()), None)
        flagged = bool(admin) and haversine_miles(lat, lon, admin.lat, admin.lon) < 3
        return GeoDecision(
            action="flagged" if flagged else "keep",
            latitude=lat,
            longitude=lon,
            miles=round(haversine_miles(lat, lon, admin.lat, admin.lon), 2) if admin else None,
            reason=(
                "Second source only returned an administrative place (township/"
                "city/county). Left the pin in place and flagged it — do not "
                "snap to a county seat."
                if flagged
                else "No unit-level second source (park, campground, named lake)."
            ),
            check_source=admin.source if admin else None,
            check_name=(admin.display_name if admin else None),
            check_in_minnesota=in_mn_polygon(admin.lat, admin.lon) if admin else None,
            flagged=flagged,
            **base,
        )

    miles = haversine_miles(lat, lon, hit.lat, hit.lon)
    threshold = correction_threshold(park)
    cap = max_correct_miles(park)
    check_in = in_mn_polygon(hit.lat, hit.lon)
    if miles > cap:
        return GeoDecision(
            action="flagged",
            latitude=lat,
            longitude=lon,
            miles=round(miles, 2),
            reason=(
                f"A same-name hit '{hit.name}' is {miles:.1f} miles away "
                f"(cap {cap:.0f} mi) — treated as a different place, pin left."
            ),
            check_source=hit.source,
            check_name=hit.display_name or hit.name,
            check_in_minnesota=check_in,
            flagged=True,
            **base,
        )
    if miles >= threshold and check_in:
        return GeoDecision(
            action="corrected",
            latitude=round(hit.lat, 6),
            longitude=round(hit.lon, 6),
            miles=round(miles, 2),
            reason=(
                f"{miles:.1f} miles from {hit.source} unit point "
                f"'{hit.name}' ({hit.osm_class}={hit.osm_type}); "
                f"moved onto the named unit rather than a township/polygon guess."
            ),
            check_source=hit.source,
            check_name=hit.display_name or hit.name,
            check_in_minnesota=True,
            flagged=False,
            **base,
        )
    return GeoDecision(
        action="keep",
        latitude=lat,
        longitude=lon,
        miles=round(miles, 2),
        reason=f"Agrees with {hit.source} '{hit.name}' within {miles:.1f} miles.",
        check_source=hit.source,
        check_name=hit.display_name or hit.name,
        check_in_minnesota=check_in,
        flagged=False,
        **base,
    )


def should_geocode(park: dict) -> bool:
    """Nominatim is for curated county pins, national units, and MN-boundary misses.

    MetroGIS / Met Council polygons are already unit geometry — do not scrape
    similarly named lakes across the state.
    """
    source = park.get("source") or ""
    lat, lon = float(park["latitude"]), float(park["longitude"])
    if looks_swapped(lat, lon) or not in_mn_polygon(lat, lon) or not in_minnesota_bbox(lat, lon):
        return True
    if source in {"curated_greater_mn_county", "nps_api"}:
        return True
    return False


def drop_decision(park: dict, spec: dict) -> GeoDecision:
    lat = float(park["latitude"])
    lon = float(park["longitude"])
    source_url = park.get("source_url") or ""
    return GeoDecision(
        name=park["name"],
        park_type=park.get("park_type") or "",
        source=park.get("source") or "",
        source_id=str(park.get("source_id") or ""),
        action="dropped",
        latitude=lat,
        longitude=lon,
        original_latitude=lat,
        original_longitude=lon,
        miles=None,
        reason=spec["reason"],
        check_source="human_maps_review",
        check_name=park["name"],
        original_in_minnesota=in_mn_polygon(lat, lon),
        check_in_minnesota=None,
        flagged=False,
        source_url=source_url or None,
        source_url_hub=is_domain_only_source_url(source_url),
        extra={"human_drop": True},
    )


def apply_human_edits(parks: list[dict]) -> tuple[list[dict], list[GeoDecision]]:
    """Rename/drop curated rows before Nominatim so refresh cannot resurrect them."""
    kept: list[dict] = []
    dropped: list[GeoDecision] = []
    for original in parks:
        park = dict(original)
        key = (park.get("source") or "", str(park.get("source_id") or ""))
        spec = HUMAN_DROPS.get(key)
        if spec:
            dropped.append(drop_decision(park, spec))
            continue
        rename = HUMAN_RENAMES.get(key)
        if rename:
            park["name"] = rename["name"]
            park["source_id"] = rename["source_id"]
            key = (park.get("source") or "", str(park.get("source_id") or ""))
        override = MANUAL_OVERRIDES.get(key)
        if override:
            for field in ("managing_agency", "source_url", "highlights", "name"):
                if override.get(field):
                    park[field] = override[field]
        kept.append(park)
    return kept, dropped


def apply_to_parks(parks: list[dict], decisions: list[GeoDecision]) -> int:
    by_key = {(d.source, d.source_id): d for d in decisions if d.action != "dropped"}
    changed = 0
    out: list[dict] = []
    for park in parks:
        key = (park.get("source") or "", str(park.get("source_id") or ""))
        if key in HUMAN_DROPS:
            changed += 1
            continue
        decision = by_key.get(key)
        if decision and decision.action == "corrected":
            park["latitude"] = decision.latitude
            park["longitude"] = decision.longitude
            changed += 1
        override = MANUAL_OVERRIDES.get(key)
        if override:
            for field in ("managing_agency", "source_url", "highlights", "name"):
                if override.get(field) and park.get(field) != override.get(field):
                    park[field] = override[field]
                    changed += 1
        hub = is_domain_only_source_url(park.get("source_url"))
        if park.get("source_url_hub") != hub:
            changed += 1
        park["source_url_hub"] = hub
        out.append(park)
    parks[:] = out
    return changed


def build_payload(decisions: list[GeoDecision]) -> dict:
    from datetime import datetime, timezone

    counts = {
        "checked": len(decisions),
        "corrected": sum(1 for d in decisions if d.action == "corrected"),
        "kept": sum(1 for d in decisions if d.action == "keep"),
        "flagged": sum(1 for d in decisions if d.flagged or d.action == "flagged"),
        "dropped": sum(1 for d in decisions if d.action == "dropped"),
        "source_url_hub": sum(1 for d in decisions if d.source_url_hub and d.action != "dropped"),
    }
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "nominatim+nps_visitorcenters+census_mn_boundary",
        "attribution": [
            "OpenStreetMap Nominatim (ODbL). Batch geocode during parks:refresh only; 1 req/s; runtime map never calls Nominatim.",
            "National Park Service Visitor Centers API for in-MN unit points on national parks.",
            "Minnesota outline: US Census Bureau cartographic boundary 20m (cb_2023_us_state_20m).",
            "Official source_url flagged source_url_hub when it is missing or only a domain (no path). Park-specific GIS URLs are kept; no Google scrape.",
        ],
        "counts": counts,
        "checks": [d.as_json() for d in decisions],
    }
