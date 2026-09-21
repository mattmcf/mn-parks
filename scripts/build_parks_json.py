#!/usr/bin/env python3
"""Build db/data/parks.json from official MN GIS + NPS, plus Greater MN county parks.

Sources:
- MN DNR state park / recreation area reference points (Geospatial Commons shapefile)
- NPS API parks with Minnesota extent
- Metropolitan Council regional parks (ArcGIS GeoJSON)
- MetroGIS Collaborative Parks county-owned units (shapefile)
- Curated Greater Minnesota county parks with real coordinates
- National Wilderness Preservation System polygons (Wilderness Connect GIS)
"""

from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import shapefile
from pyproj import Transformer
from shapely.geometry import shape
from shapely.ops import unary_union

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "db" / "data" / "parks.json"
CACHE = Path(os.environ.get("MN_PARKS_CACHE", "/tmp/mn-parks-data"))

USER_AGENT = "mn-parks-refresh/1.0 (https://github.com/mattmcf/mn-parks)"

DNR_ZIP_URL = (
    "https://resources.gisdata.mn.gov/pub/gdrs/data/pub/us_mn_state_dnr/"
    "bdry_dnr_lrs_prk/shp_bdry_dnr_lrs_prk.zip"
)
METRO_ZIP_URL = (
    "https://resources.gisdata.mn.gov/pub/gdrs/data/pub/us_mn_state_metrogis/"
    "bdry_metro_colabtiv_parks/shp_bdry_metro_colabtiv_parks.zip"
)
METC_QUERY_URL = (
    "https://arcgis.metc.state.mn.us/arcgis/rest/services/LPH/Parks_CD/"
    "FeatureServer/1/query"
)
NPS_API_URL = "https://developer.nps.gov/api/v1/parks"
WILDERNESS_ZIP_URL = "https://wilderness.net/GIS/Wilderness_Areas.zip"

DNR_HUB_URL = "https://www.dnr.state.mn.us/state_parks/index.html"
METC_HUB_URL = "https://metrocouncil.org/Parks.aspx"

TO_WGS = Transformer.from_crs(26915, 4326, always_xy=True)
WEB_MERCATOR_TO_WGS = Transformer.from_crs(3857, 4326, always_xy=True)

_URL_CACHE: dict[str, str | None] = {}


def rec_get(record: dict, *candidates: str) -> str:
    """Read a shapefile field by full name or 10-char DBF truncation."""
    keys = list(record)
    lower = {k.lower(): k for k in keys}
    for cand in candidates:
        if cand in record and record[cand] not in (None, ""):
            return str(record[cand])
        key = lower.get(cand.lower())
        if key is not None and record[key] not in (None, ""):
            return str(record[key])
        prefix = cand[:10]
        for k in keys:
            if k.startswith(prefix) and record[k] not in (None, ""):
                return str(record[k])
    return ""


def http_bytes(url: str, headers: dict | None = None, timeout: int = 120) -> bytes:
    req_headers = {"User-Agent": USER_AGENT}
    if headers:
        req_headers.update(headers)
    last: Exception | None = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last}") from last


def http_json(url: str, headers: dict | None = None) -> dict:
    return json.loads(http_bytes(url, headers=headers))


def unzip_url(url: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    raw = http_bytes(url)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        zf.extractall(dest)


def fetch_nps() -> None:
    key = os.environ.get("NPS_API_KEY") or "DEMO_KEY"
    parks: list[dict] = []
    start = 0
    while True:
        params = urllib.parse.urlencode(
            {"stateCode": "MN", "limit": 50, "start": start}
        )
        data = http_json(
            f"{NPS_API_URL}?{params}",
            headers={"X-Api-Key": key},
        )
        batch = data.get("data") or []
        parks.extend(batch)
        total = int(data.get("total") or len(parks))
        start += len(batch)
        if not batch or start >= total:
            break
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "nps.json").write_text(json.dumps({"data": parks}))
    print(f"Fetched {len(parks)} NPS units for Minnesota")


def nps_from_existing_asset() -> None:
    """Keep previously shipped national parks if the NPS API is unavailable."""
    if not OUT.exists():
        raise RuntimeError("NPS fetch failed and db/data/parks.json is missing.")
    payload = json.loads(OUT.read_text())
    data = []
    for park in payload.get("parks") or []:
        if park.get("park_type") != "national":
            continue
        data.append(
            {
                "fullName": park["name"],
                "name": park["name"],
                "latitude": park["latitude"],
                "longitude": park["longitude"],
                "parkCode": park.get("source_id"),
                "id": park.get("source_id"),
                "url": park.get("source_url") or "",
                "description": park.get("highlights") or "",
                "designation": "",
                "activities": [{"name": a} for a in (park.get("amenities") or [])],
            }
        )
    if not data:
        raise RuntimeError("NPS fetch failed and the shipped file has no national parks.")
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "nps.json").write_text(json.dumps({"data": data}))
    print(f"NPS API unavailable; reused {len(data)} national parks from {OUT}")


def fetch_met_council() -> None:
    features: list[dict] = []
    offset = 0
    page_size = 1000
    while True:
        params = urllib.parse.urlencode(
            {
                "where": "1=1",
                "outFields": "*",
                "outSR": "4326",
                "returnGeometry": "true",
                "f": "geojson",
                "resultOffset": offset,
                "resultRecordCount": page_size,
            }
        )
        data = http_json(f"{METC_QUERY_URL}?{params}")
        batch = data.get("features") or []
        features.extend(batch)
        if data.get("exceededTransferLimit") or len(batch) >= page_size:
            offset += len(batch)
            if not batch:
                break
            continue
        break
    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "metc.json").write_text(
        json.dumps({"type": "FeatureCollection", "features": features})
    )
    print(f"Fetched {len(features)} Met Council regional park features")


def find_shp(folder: Path, hint: str = "") -> Path:
    shps = sorted(p for p in folder.rglob("*.shp") if not p.name.startswith("."))
    if not shps:
        raise FileNotFoundError(f"No shapefile in {folder}")
    if hint:
        hinted = [p for p in shps if hint.lower() in p.name.lower()]
        if hinted:
            return hinted[0]
    return shps[0]


def fetch_sources() -> None:
    print("Fetching official park sources (DNR, NPS, Met Council, MetroGIS, wilderness)…")
    unzip_url(DNR_ZIP_URL, CACHE / "dnr")
    shp = CACHE / "dnr" / "dnr_management_units_prk_ref_pts.shp"
    if not shp.exists():
        raise FileNotFoundError(f"DNR reference-point shapefile missing at {shp}")
    unzip_url(METRO_ZIP_URL, CACHE / "metro")
    metro_shp = CACHE / "metro" / "MetroCollaborativeParks.shp"
    if not metro_shp.exists():
        raise FileNotFoundError(f"MetroGIS shapefile missing at {metro_shp}")
    unzip_url(WILDERNESS_ZIP_URL, CACHE / "wilderness")
    find_shp(CACHE / "wilderness", "wild")
    fetch_met_council()
    try:
        fetch_nps()
    except Exception as exc:
        print(f"NPS API fetch failed ({exc}); falling back to shipped national parks.")
        nps_from_existing_asset()

MN_WEST, MN_SOUTH, MN_EAST, MN_NORTH = -97.5, 43.4, -89.34, 49.4

SKIP_FUNC = {
    "neighborhood park",
    "neighborhood park/playground",
    "neighborhood playfield",
    "mini-park",
    "mini park",
    "tot lot/mini-park",
    "city park",
    "trail corridor",
    "inholding",
    "boat landing",
    "recreational center",
    "community playfield",
    "community play field",
    "community athletic complex",
    "lineal park",
}

AMENITY_VOCAB = {
    "hiking": "Hiking trails",
    "camping": "Camping",
    "swimming": "Swimming",
    "fishing": "Fishing",
    "boating": "Boating",
    "picnic": "Picnic areas",
    "visitor_center": "Visitor center",
    "playground": "Playground",
    "biking": "Biking",
    "wildlife": "Wildlife viewing",
    "climbing": "Climbing",
    "horseback": "Horseback riding",
    "disc_golf": "Disc golf",
    "beach": "Beach",
    "canoeing": "Canoeing / kayaking",
    "cross_country_skiing": "Cross-country skiing",
    "snowshoeing": "Snowshoeing",
    "winter_sports": "Winter sports",
    "waterfall": "Waterfall",
    "historic": "Historic site",
}

ACTIVITY_FROM_AMENITY = {
    "hiking": "hiking",
    "camping": "camping",
    "swimming": "swimming",
    "fishing": "fishing",
    "boating": "boating",
    "biking": "biking",
    "climbing": "climbing",
    "horseback": "horseback riding",
    "disc_golf": "disc golf",
    "canoeing": "paddling",
    "cross_country_skiing": "cross-country skiing",
    "snowshoeing": "snowshoeing",
    "winter_sports": "winter sports",
    "wildlife": "wildlife watching",
}

NPS_ACTIVITY_MAP = {
    "hiking": "hiking",
    "front-country hiking": "hiking",
    "backcountry hiking": "hiking",
    "camping": "camping",
    "backcountry camping": "camping",
    "canoe or kayak camping": "camping",
    "swimming": "swimming",
    "fishing": "fishing",
    "boating": "boating",
    "paddling": "canoeing",
    "canoeing": "canoeing",
    "kayaking": "canoeing",
    "biking": "biking",
    "mountain biking": "biking",
    "road biking": "biking",
    "picnicking": "picnic",
    "wildlife watching": "wildlife",
    "birdwatching": "wildlife",
    "climbing": "climbing",
    "cross-country skiing": "cross_country_skiing",
    "snowshoeing": "snowshoeing",
    "visitor center": "visitor_center",
    "museum exhibits": "visitor_center",
    "guided tours": "visitor_center",
    "stargazing": "wildlife",
    "astronomy": "wildlife",
}

HIGHLIGHTS = {
    "itasca state park": "Headwaters of the Mississippi, old-growth red and white pine, and a paved loop around the lake. Minnesota's oldest state park.",
    "split rock lighthouse state park": "Cliff-top lighthouse above Lake Superior, pebble beaches, and the Superior Hiking Trail running the shoreline.",
    "gooseberry falls state park": "A stacked set of waterfalls on the Gooseberry River, plus Lake Superior shoreline a short walk from the visitor center.",
    "tettegouche state park": "High palisades on Lake Superior, inland lakes, and the Palisade Head / Shovel Point climbing faces.",
    "temperance river state park": "A gorge so narrow the river looks like it disappears, with Superior Hiking Trail access on both sides of Hwy 61.",
    "cascade river state park": "A staircase of cascades falling toward Lake Superior, with trails that climb into maple-birch highland.",
    "judge c.r. magney state park": "Hike to Devil's Kettle, where part of the Brule River pours into a pothole and does not obviously come back out.",
    "jay cooke state park": "The St. Louis River swinging bridge, basalt gorge, and a web of trails through the Nemadji State Forest edge.",
    "fort snelling state park": "River confluence of the Minnesota and Mississippi, fort overlooks, and a rare urban floodplain forest.",
    "minneopa state park": "Double waterfall on Minneopa Creek and a bison range on the prairie bluff above the Minnesota River.",
    "blue mounds state park": "Sioux quartzite cliff, a bison herd, and one of the best stargazing skies in southwest Minnesota.",
    "forestville mystery cave state park": "Minnesota's longest cave plus a restored 19th-century townsite in the Root River valley.",
    "whitewater state park": "Limestone bluffs, a cold trout stream, and some of the steepest hiking in the southeast.",
    "a.w.s.s. state park": "",
    "voyageurs national park": "A water-first national park of connected lakes, houseboat camps, and glacially scoured islands on the Canadian border.",
    "grand portage national monument": "The reconstructed North West Company depot and the historic 8.5-mile portage from Lake Superior toward the border lakes.",
    "pipestone national monument": "The quarries where Dakota and other nations still quarry pipestone, with a circle trail past Winnewissa Falls.",
    "mississippi national river and recreation area": "A 72-mile national river corridor through the Twin Cities — locks, gorge, and floodplain rather than a single gate.",
    "saint croix national scenic riverway": "A protected, mostly undeveloped river on the Minnesota–Wisconsin line, built for paddling rather than motors.",
    "central mississippi riverfront": "Downtown Minneapolis riverfront, Stone Arch Bridge views, and the only gorge on the Upper Mississippi.",
    "como": "Saint Paul's Como Park: the conservatory, zoo, lakeside paths, and a regional park that still feels like a neighborhood commons.",
    "minnehaha": "Minnehaha Falls drops 53 feet a few minutes from the light rail, then the creek runs out to the Mississippi.",
    "lebanon hills": "Dakota County's big one: lakes, mountain-bike trail, campground, and a visitor center that actually helps you pick a loop.",
    "elm creek": "A Three Rivers park reserve with a busy waterpark, dog off-leash area, and enough trail that you can lose the suburbs.",
    "hyland-bush-anderson lakes": "Ski jumps on the horizon, mountain-bike trail in the woods, and three lakes inside Bloomington / Bloomington's edge.",
    "cleary lake": "A Scott County / Three Rivers lake park known for the golf course, campground, and a calm paddle.",
    "bunker hills": "Anoka County's year-round park: campground, waterpark, stables, and a dune-ish landscape that does not look like the rest of the metro.",
    "lake elmo park reserve": "Washington County's large reserve east of the metro — swimming pond, campground, and enough dirt road that it feels farther than it is.",
    "quarry park and nature preserve": "Stearns County granite quarries now filled with water, climbing walls, and a trail system on the edge of Waite Park / St. Cloud.",
    "chester woods park": "Olmsted County's camping and trail park east of Rochester, with a reservoir and a reliable shoulder-season loop.",
    "boundary waters canoe area wilderness": "A million-acre canoe-country wilderness in Superior National Forest: linked lakes, portages, and the Canadian border, with no roads through the interior.",
    "agassiz wilderness": "A 4,000-acre wilderness inside Agassiz National Wildlife Refuge — marsh, bog, and aspen on the glacial Lake Agassiz plain.",
    "tamarac wilderness": "The wild core of Tamarac National Wildlife Refuge: lakes, bog, and forest on the prairie–woodland transition in Becker County.",
}


def normalize_url(url: str) -> str:
    u = (url or "").strip()
    if not u or u.lower() in {"none", "null", "n/a", "-"}:
        return ""
    if u.startswith("//"):
        u = "https:" + u
    elif "://" not in u:
        u = "https://" + u.lstrip("/")
    return u


def is_unit_page(url: str) -> bool:
    """True for official per-unit pages (DNR park id, NPS unit, wilderness ID)."""
    u = normalize_url(url).lower()
    if not u:
        return False
    if re.search(r"/state_parks/park\.html\?id=(spk|sra)\d{5}\b", u):
        return True
    if re.search(r"nps\.gov/[a-z0-9]{3,8}(?:/|$)", u) and "nps.gov/index" not in u:
        return True
    if "/visit-wilderness/" in u and "id=" in u:
        return True
    if re.search(r"fws\.gov/refuge/[\w-]+", u):
        return True
    if "boundary-waters-canoe-area" in u:
        return True
    return False


def is_hub_url(url: str) -> bool:
    """Generic parks index, county homepage, or reused city map — not a unit page."""
    u = normalize_url(url)
    if not u:
        return True
    if is_unit_page(u):
        return False
    parsed = urllib.parse.urlparse(u)
    path = (parsed.path or "/").rstrip("/") or "/"
    low = u.lower()
    if path == "/":
        return True
    if low.rstrip("/") in {DNR_HUB_URL.lower(), METC_HUB_URL.lower()}:
        return True
    hub_bits = (
        "/state_parks/index.html",
        "/state_parks/list.html",
        "/state_parks/list_alpha.html",
        "/parks.aspx",
        "/residents/parks-recreation",
        "/departments-a-z/public-works/parks-recreation",
        "/documentcenter/",
    )
    if any(bit in low for bit in hub_bits):
        return True
    if path.lower().endswith(".pdf"):
        return True
    if re.search(r"/(parks|parks-recreation|recreation/parks)/?$", path, re.I):
        return True
    return False


def distinctive_tokens(name: str) -> list[str]:
    stop = {
        "the", "and", "of", "park", "parks", "regional", "reserve", "county",
        "state", "national", "area", "recreation", "monument", "scenic",
        "riverway", "wilderness",
    }
    tokens = re.findall(r"[a-z0-9]+", (name or "").lower())
    return [t for t in tokens if t not in stop and len(t) >= 3]


def url_matches_name(url: str, name: str) -> bool:
    blob = urllib.parse.unquote(normalize_url(url).lower())
    hits = [t for t in distinctive_tokens(name) if t in blob]
    if not hits:
        return False
    score = sum(len(t) for t in hits)
    return score >= 6 or len(hits) >= 2 or (len(hits) == 1 and len(hits[0]) >= 4)


def follow_url(url: str) -> str | None:
    """Return the final URL if the page exists, None on 404, original on network doubt."""
    url = normalize_url(url)
    if not url:
        return None
    if url in _URL_CACHE:
        return _URL_CACHE[url]
    last_error: Exception | None = None
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method=method)
            with urllib.request.urlopen(req, timeout=25) as resp:
                if 200 <= resp.status < 400:
                    landed = resp.geturl() or url
                    if is_hub_url(landed) and not is_unit_page(url):
                        _URL_CACHE[url] = None
                        return None
                    _URL_CACHE[url] = url
                    return url
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in (404, 410):
                _URL_CACHE[url] = None
                return None
            if exc.code in (405, 501, 403, 406) and method == "HEAD":
                continue
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            continue
    # Network / method issues: keep a constructed official URL rather than inventing a substitute.
    if last_error:
        print(f"  URL check inconclusive for {url}: {last_error}")
    _URL_CACHE[url] = url
    return url


def pick_best_url(name: str, urls: list[str], fallback: str = "") -> str:
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for raw in urls:
        u = normalize_url(raw)
        if not u or u in seen:
            continue
        seen.add(u)
        if is_unit_page(u) or url_matches_name(u, name):
            ranked.append((3, u))
        elif is_hub_url(u):
            ranked.append((1, u))
        else:
            ranked.append((2, u))
    if not ranked:
        return normalize_url(fallback)
    ranked.sort(key=lambda item: item[0], reverse=True)
    return ranked[0][1]


def dnr_park_url(code: str) -> str:
    code = (code or "").strip().lower()
    if not re.fullmatch(r"(spk|sra)\d{5}", code):
        return DNR_HUB_URL
    candidate = f"https://www.dnr.state.mn.us/state_parks/park.html?id={code}"
    final = follow_url(candidate)
    if final is None or is_hub_url(final):
        return DNR_HUB_URL
    return candidate


def wilderness_agency_url(name: str, agency: str, gis_url: str) -> str:
    """Prefer a verified land-manager page; otherwise the GIS-provided wilderness URL."""
    candidates: list[str] = []
    if agency == "FS" and name == "Boundary Waters Canoe Area Wilderness":
        candidates.append(
            "https://www.fs.usda.gov/r09/superior/recreation/boundary-waters-canoe-area-wilderness"
        )
    if agency == "FWS" and name == "Agassiz Wilderness":
        candidates.append("https://www.fws.gov/refuge/agassiz")
    if agency == "FWS" and name == "Tamarac Wilderness":
        candidates.append("https://www.fws.gov/refuge/tamarac")
    for candidate in candidates:
        final = follow_url(candidate)
        if final and not is_hub_url(final) and (url_matches_name(final, name) or is_unit_page(final)):
            return candidate
    return normalize_url(gis_url)


def in_minnesota(lat: float, lon: float) -> bool:
    return MN_SOUTH <= lat <= MN_NORTH and MN_WEST <= lon <= MN_EAST


def norm_name(name: str) -> str:
    n = (name or "").strip().lower()
    n = n.replace("&", "and")
    n = re.sub(r"\s+", " ", n)
    for suffix in (
        " regional park reserve",
        " park reserve",
        " regional park",
        " state recreation area",
        " state park",
        " state wayside",
        " county park",
        " national monument",
        " national park",
        " national river and recreation area",
        " national scenic riverway",
        " canoe area wilderness",
        " wilderness",
    ):
        if n.endswith(suffix.strip()) is False:
            n = n.replace(suffix, "")
    n = n.replace("regional park", "").replace("park reserve", "")
    return re.sub(r"\s+", " ", n).strip(" -")


def slug(name: str, ptype: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return f"{ptype}:{base}"


def centroid_utm(shp) -> tuple[float, float] | None:
    pts = shp.points
    if not pts:
        return None
    if shp.shapeType in (1, 11, 21):  # point
        x, y = pts[0]
        return TO_WGS.transform(x, y)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return TO_WGS.transform(sum(xs) / len(xs), sum(ys) / len(ys))


def centroid_geojson(geom) -> tuple[float, float] | None:
    if not geom:
        return None
    try:
        g = shape(geom)
        if g.is_empty:
            return None
        c = g.centroid
        return float(c.x), float(c.y)
    except Exception:
        return None


def highlights_for(name: str) -> str:
    key = name.strip().lower()
    if key in HIGHLIGHTS:
        return HIGHLIGHTS[key]
    n = norm_name(name)
    for k, v in HIGHLIGHTS.items():
        if n and n in k or k in n or k in key:
            if v:
                return v
    return ""


def parse_features(text: str) -> list[str]:
    t = (text or "").lower()
    found: list[str] = []
    mapping = [
        ("hike", "hiking"),
        ("trail", "hiking"),
        ("camp", "camping"),
        ("swim", "swimming"),
        ("beach", "beach"),
        ("fish", "fishing"),
        ("boat", "boating"),
        ("canoe", "canoeing"),
        ("kayak", "canoeing"),
        ("picnic", "picnic"),
        ("visitor", "visitor_center"),
        ("play", "playground"),
        ("bike", "biking"),
        ("mountain bike", "biking"),
        ("wildlife", "wildlife"),
        ("bird", "wildlife"),
        ("climb", "climbing"),
        ("horse", "horseback"),
        ("disc", "disc_golf"),
        ("ski", "cross_country_skiing"),
        ("snowshoe", "snowshoeing"),
        ("waterfall", "waterfall"),
        ("falls", "waterfall"),
        ("historic", "historic"),
        ("lighthouse", "historic"),
    ]
    for needle, key in mapping:
        if needle in t and key not in found:
            found.append(key)
    return found


def activities_from(amenities: list[str]) -> list[str]:
    out = []
    for a in amenities:
        act = ACTIVITY_FROM_AMENITY.get(a)
        if act and act not in out:
            out.append(act)
    return out


def make_park(
    *,
    name: str,
    park_type: str,
    lat: float,
    lon: float,
    managing_agency: str,
    source: str,
    source_id: str,
    source_url: str,
    highlights: str = "",
    amenities: list[str] | None = None,
    activities: list[str] | None = None,
) -> dict | None:
    if not name or lat is None or lon is None:
        return None
    if not in_minnesota(lat, lon):
        return None
    am = amenities or []
    acts = activities or activities_from(am)
    return {
        "name": name.strip(),
        "park_type": park_type,
        "latitude": round(float(lat), 6),
        "longitude": round(float(lon), 6),
        "managing_agency": (managing_agency or "").strip(),
        "source": source,
        "source_id": str(source_id),
        "source_url": source_url or "",
        "highlights": highlights or highlights_for(name),
        "amenities": am,
        "activities": acts,
        "in_minnesota": True,
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
    }


_METRO_URLS: dict[str, list[str]] | None = None


def metro_url_index() -> dict[str, list[str]]:
    """PARK_URL values from MetroGIS, keyed by normalized park name."""
    global _METRO_URLS
    if _METRO_URLS is not None:
        return _METRO_URLS
    path = CACHE / "metro" / "MetroCollaborativeParks"
    if not path.with_suffix(".shp").exists():
        _METRO_URLS = {}
        return _METRO_URLS
    sf = shapefile.Reader(str(path))
    fields = [f[0] for f in sf.fields[1:]]
    index: dict[str, list[str]] = defaultdict(list)
    for rec in sf.iterRecords():
        d = dict(zip(fields, rec))
        name = (d.get("PARKNAME") or "").strip()
        url = normalize_url(d.get("PARK_URL") or "")
        if not name or not url:
            continue
        key = norm_name(name)
        if url not in index[key]:
            index[key].append(url)
    _METRO_URLS = dict(index)
    return _METRO_URLS


def metro_urls_for(name: str) -> list[str]:
    if not name:
        return []
    return list(metro_url_index().get(norm_name(name), []))


def load_dnr() -> list[dict]:
    path = CACHE / "dnr" / "dnr_management_units_prk_ref_pts"
    sf = shapefile.Reader(str(path))
    fields = [f[0] for f in sf.fields[1:]]
    parks = []
    for rec, shp in zip(sf.records(), sf.shapes()):
        d = dict(zip(fields, rec))
        unit = rec_get(d, "MGMT_UNIT_TYPE_NAME", "MGMT_UNIT_")
        if unit not in ("State Park", "State Recreation Area"):
            continue
        xy = centroid_utm(shp)
        if not xy:
            continue
        lon, lat = xy
        name = rec_get(d, "PAT_MGMT_UNIT_NAME", "PAT_MGMT_U")
        code = rec_get(d, "LAM_PROGRAM_PROJECT_CODE", "LAM_PROGRA")
        amenities = parse_features(name)
        extra = STATE_PARK_AMENITIES.get(name.lower(), [])
        for a in extra:
            if a not in amenities:
                amenities.append(a)
        parks.append(
            make_park(
                name=name,
                park_type="state",
                lat=lat,
                lon=lon,
                managing_agency="Minnesota DNR Parks & Trails",
                source="mn_dnr_state_parks",
                source_id=code or name,
                source_url=dnr_park_url(code),
                amenities=amenities,
            )
        )
    return [p for p in parks if p]


STATE_PARK_AMENITIES = {
    "itasca state park": ["camping", "swimming", "biking", "visitor_center", "fishing", "boating", "beach", "cross_country_skiing"],
    "split rock lighthouse state park": ["visitor_center", "historic", "camping", "beach"],
    "gooseberry falls state park": ["waterfall", "visitor_center", "camping"],
    "tettegouche state park": ["camping", "climbing", "waterfall", "visitor_center", "fishing"],
    "temperance river state park": ["camping", "waterfall", "fishing"],
    "cascade river state park": ["camping", "waterfall", "cross_country_skiing"],
    "judge c.r. magney state park": ["waterfall", "camping"],
    "jay cooke state park": ["camping", "cross_country_skiing", "visitor_center", "biking"],
    "fort snelling state park": ["visitor_center", "historic", "biking", "cross_country_skiing", "fishing"],
    "minneopa state park": ["waterfall", "wildlife", "camping"],
    "blue mounds state park": ["wildlife", "camping", "climbing", "visitor_center"],
    "forestville mystery cave state park": ["visitor_center", "historic", "camping", "horseback"],
    "whitewater state park": ["camping", "fishing", "visitor_center"],
    "a.w.s.s. state park": [],
    "banning state park": ["camping", "canoeing", "fishing"],
    "bear head lake state park": ["camping", "swimming", "fishing", "boating", "beach"],
    "frontenac state park": ["camping", "wildlife", "cross_country_skiing"],
    "lake maria state park": ["camping", "canoeing", "wildlife"],
    "mille lacs kathio state park": ["camping", "historic", "visitor_center", "swimming"],
    "savanna portage state park": ["camping", "boating", "fishing", "swimming"],
    "scenic state park": ["camping", "swimming", "boating", "fishing", "beach"],
    "st. croix state park": ["camping", "horseback", "canoeing", "swimming", "visitor_center"],
    "wild river state park": ["camping", "canoeing", "horseback", "cross_country_skiing"],
    "william o'brien state park": ["camping", "canoeing", "swimming", "cross_country_skiing"],
    "afton state park": ["hiking", "cross_country_skiing", "swimming"],
    "sibley state park": ["camping", "swimming", "boating", "visitor_center"],
    "glacial lakes state park": ["camping", "swimming", "horseback", "boating"],
    "maplewood state park": ["camping", "swimming", "horseback", "boating"],
    "buffalo river state park": ["camping", "wildlife"],
    "lake bemidji state park": ["camping", "swimming", "biking", "visitor_center", "beach"],
    "zippel bay state park": ["camping", "beach", "boating", "fishing"],
    "grand portage state park": ["waterfall", "visitor_center"],
    "interstate state park": ["climbing", "visitor_center", "boating"],
    "nerstrand big woods state park": ["waterfall", "hiking"],
    "great river bluffs state park": ["camping", "wildlife"],
    "lake vermilion-soudan underground mine state park": ["visitor_center", "historic", "boating", "fishing"],
    "cuyuna country state recreation area": ["biking", "camping", "boating", "fishing", "swimming"],
    "big bog state recreation area": ["visitor_center", "wildlife", "biking", "camping"],
    "garden island state recreation area": ["boating", "camping", "fishing"],
}


def load_nps() -> list[dict]:
    path = CACHE / "nps.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text())["data"]
    parks = []
    skip = {"National Scenic Trail"}
    for p in data:
        if p.get("designation") in skip:
            continue
        try:
            lat = float(p.get("latitude") or 0)
            lon = float(p.get("longitude") or 0)
        except (TypeError, ValueError):
            continue
        am = []
        for act in p.get("activities") or []:
            mapped = NPS_ACTIVITY_MAP.get((act.get("name") or "").lower())
            if mapped and mapped not in am:
                am.append(mapped)
        desc = (p.get("description") or "").strip()
        # Original short highlight: first sentence only, government work.
        highlights = ""
        if desc:
            highlights = re.split(r"(?<=\.)\s", desc, maxsplit=1)[0]
            if len(highlights) > 280:
                highlights = highlights[:277] + "…"
        parks.append(
            make_park(
                name=p.get("fullName") or p.get("name"),
                park_type="national",
                lat=lat,
                lon=lon,
                managing_agency="National Park Service",
                source="nps_api",
                source_id=p.get("parkCode") or p.get("id"),
                source_url=p.get("url") or "",
                highlights=highlights_for(p.get("fullName") or "") or highlights,
                amenities=am,
            )
        )
    return [x for x in parks if x]


def load_regional() -> list[dict]:
    path = CACHE / "metc.json"
    data = json.loads(path.read_text())
    groups: dict[str, list] = defaultdict(list)
    for feat in data["features"]:
        props = feat["properties"]
        category = props.get("Category") or ""
        if category not in ("Regional Park", "Park Reserve", "Special Recreation Feature"):
            continue
        if props.get("ImplementationPhase") == "Planned":
            continue
        name = (props.get("UnitName") or "").strip()
        if not name:
            continue
        groups[name].append(feat)

    parks = []
    for name, feats in groups.items():
        geoms = []
        agency = ""
        for f in feats:
            p = f["properties"]
            agency = agency or (p.get("AgencyManager") or "")
            if f.get("geometry"):
                try:
                    geoms.append(shape(f["geometry"]))
                except Exception:
                    pass
        if not geoms:
            continue
        merged = unary_union(geoms)
        c = merged.centroid
        amenities = []
        extra = REGIONAL_AMENITIES.get(name.lower(), [])
        for a in extra:
            if a not in amenities:
                amenities.append(a)
        display = f"{name} Regional Park" if "park" not in name.lower() else name
        parks.append(
            make_park(
                name=display,
                park_type="regional",
                lat=c.y,
                lon=c.x,
                managing_agency=agency or "Metropolitan Council Regional Parks",
                source="met_council_regional_parks",
                source_id=name,
                source_url=pick_best_url(
                    display,
                    metro_urls_for(name) + metro_urls_for(display),
                    fallback=METC_HUB_URL,
                ),
                amenities=amenities,
            )
        )
    return [p for p in parks if p]


REGIONAL_AMENITIES = {
    "lebanon hills": ["camping", "biking", "swimming", "visitor_center", "cross_country_skiing", "fishing"],
    "elm creek": ["swimming", "biking", "visitor_center", "playground", "cross_country_skiing"],
    "hyland-bush-anderson lakes": ["biking", "winter_sports", "swimming", "visitor_center"],
    "baker": ["camping", "boating", "swimming", "biking", "visitor_center"],
    "cleary lake": ["camping", "swimming", "boating"],
    "bunker hills": ["camping", "horseback", "swimming", "visitor_center", "playground"],
    "lake elmo": ["camping", "swimming", "boating", "visitor_center"],
    "como": ["visitor_center", "playground", "historic", "picnic"],
    "minnehaha": ["waterfall", "biking", "historic"],
    "central mississippi riverfront": ["biking", "historic", "visitor_center"],
    "bryant lake": ["boating", "swimming", "fishing"],
    "fish lake": ["boating", "fishing", "swimming"],
    "clifton e. french": ["swimming", "visitor_center", "fishing", "boating"],
    "crow-hassan": ["horseback", "wildlife", "cross_country_skiing"],
    "carver": ["boating", "swimming", "camping", "visitor_center"],
    "battle creek": ["biking", "hiking"],
    "cottage grove ravine": ["hiking", "cross_country_skiing", "picnic"],
    "square lake": ["swimming", "fishing", "boating"],
    "big marine": ["boating", "swimming", "fishing"],
    "lake minnewashta": ["swimming", "boating", "picnic"],
    "baylor": ["camping", "swimming", "boating"],
    "cedar lake farm": ["camping", "swimming", "boating"],
    "coon rapids dam": ["fishing", "visitor_center", "biking"],
}


def load_metro_county(regional_names: set[str]) -> list[dict]:
    path = CACHE / "metro" / "MetroCollaborativeParks"
    sf = shapefile.Reader(str(path))
    fields = [f[0] for f in sf.fields[1:]]
    buckets: dict[str, list] = defaultdict(list)
    for i in range(len(sf)):
        try:
            rec = sf.record(i)
            shp = sf.shape(i)
        except shapefile.ShapefileException:
            continue
        d = dict(zip(fields, rec))
        if str(d.get("OWNERTYPE")) != "03":
            continue
        func = (d.get("FUNC_TYPE") or "").strip().lower()
        if func in SKIP_FUNC:
            continue
        name = (d.get("PARKNAME") or "").strip()
        if not name:
            continue
        nn = norm_name(name)
        if nn in regional_names:
            continue
        acres = float(d.get("PARK_ACRES") or 0)
        if acres and acres < 20 and func not in ("county park", "conservation area", "park reserve", "regional park", "community park"):
            continue
        buckets[name].append((d, shp))

    parks = []
    for name, items in buckets.items():
        d0 = items[0][0]
        lons, lats = [], []
        for d, shp in items:
            xy = centroid_utm(shp)
            if xy:
                lons.append(xy[0])
                lats.append(xy[1])
        if not lats:
            continue
        lon = sum(lons) / len(lons)
        lat = sum(lats) / len(lats)
        feats = " ".join((d.get("SPEC_FEAT") or "") for d, _ in items)
        amenities = parse_features(feats)
        agency = d0.get("AGENCYNAME") or d0.get("LANDOWNER") or "County parks"
        urls = [d.get("PARK_URL") or "" for d, _ in items]
        parks.append(
            make_park(
                name=name,
                park_type="county",
                lat=lat,
                lon=lon,
                managing_agency=agency,
                source="metrogis_collaborative_parks",
                source_id=str(d0.get("PARKID") or name),
                source_url=pick_best_url(name, urls),
                amenities=amenities,
            )
        )
    return [p for p in parks if p]


GREATER_MN_COUNTY = [
    # name, lat, lon, county/agency, url, amenities, highlights
    ("Chester Woods Park", 44.0236, -92.3335, "Olmsted County Parks", "https://www.olmstedcounty.gov/residents/parks-recreation", ["camping", "hiking", "fishing", "boating", "picnic", "playground"], "Olmsted County reservoir park east of Rochester with camping, a swimming beach in season, and a trail that actually loops."),
    ("Oxbow Park & Zollman Zoo", 44.0869, -92.6442, "Olmsted County Parks", "https://www.olmstedcounty.gov/residents/parks-recreation", ["hiking", "picnic", "playground", "wildlife", "visitor_center"], "A wooded oxbow of the Zumbro with a small zoo of Minnesota animals — county park, not a city lot."),
    ("Quarry Park & Nature Preserve", 45.5334, -94.2471, "Stearns County Parks", "https://co.stearns.mn.us/Recreation/Parks", ["hiking", "climbing", "swimming", "biking", "picnic", "wildlife"], "Flooded granite quarries on the edge of St. Cloud, with climbing walls, swimming holes, and a trail network through oak savanna."),
    ("Warner Lake County Park", 45.4472, -94.4067, "Stearns County Parks", "https://co.stearns.mn.us/Recreation/Parks", ["hiking", "fishing", "picnic", "swimming", "camping"], "A quieter Stearns County lake park west of Cold Spring."),
    ("Mississippi River County Park", 45.6145, -94.1934, "Stearns County Parks", "https://co.stearns.mn.us/Recreation/Parks", ["hiking", "fishing", "picnic", "canoeing"], "Stearns County park on the Mississippi north of St. Cloud, built for river access more than playgrounds."),
    ("Bertram Chain of Lakes Regional Park", 45.2373, -93.9474, "Wright County Parks", "https://www.co.wright.mn.us/148/Parks-Recreation", ["hiking", "swimming", "biking", "picnic", "fishing", "camping"], "Wright County's chain-of-lakes park near Monticello — swimming, trail, and enough water that a bike loop is not the whole visit."),
    ("Collinwood Regional Park", 45.0808, -94.1657, "Wright County Parks", "https://www.co.wright.mn.us/148/Parks-Recreation", ["camping", "swimming", "boating", "fishing", "picnic"], "Wright County park on Collinwood Lake with a campground that fills on summer weekends."),
    ("Lake Koronis Regional Park", 45.3296, -94.7169, "Stearns County Parks", "https://co.stearns.mn.us/Recreation/Parks", ["camping", "swimming", "boating", "fishing", "picnic"], "Camping and lake access on Koronis, west of Paynesville."),
    ("Bend in the River Regional Park", 45.6431, -94.1948, "Benton County Parks", "https://www.co.benton.mn.us/", ["hiking", "picnic", "fishing", "wildlife"], "Benton County park on a Mississippi bend north of Rice, with bluff trail and river views."),
    ("Lake Brophy County Park", 45.8934, -95.4182, "Douglas County Parks", "https://www.douglascountymn.gov/", ["camping", "swimming", "boating", "fishing", "picnic"], "Douglas County park west of Alexandria — classic west-central Minnesota lake camping."),
    ("Spruce Center Springs County Park", 45.799, -95.062, "Douglas County Parks", "https://www.douglascountymn.gov/", ["picnic", "hiking", "fishing"], "A spring-fed county park east of Osakis."),
    ("Cannon River Wilderness Area", 44.4374, -93.3269, "Rice County Parks", "https://www.ricecountymn.gov/", ["hiking", "camping", "fishing", "wildlife", "canoeing"], "Rice County's wildest tract: a steep, wooded canyon of the Cannon between Faribault and Northfield."),
    ("Shager Park", 44.3542, -93.2681, "Rice County Parks", "https://www.ricecountymn.gov/", ["swimming", "picnic", "playground", "boating", "fishing"], "Rice County park on Circle Lake with a swimming beach and a busy summer picnic ground."),
    ("Rapidan Dam County Park", 44.0973, -94.0664, "Blue Earth County Parks", "https://www.blueearthcountymn.gov/181/Parks", ["fishing", "picnic", "hiking", "wildlife"], "Blue Earth County park at the Rapidan Dam on the Blue Earth River, known for fishing below the dam."),
    ("Daly Park", 44.0536, -94.2197, "Blue Earth County Parks", "https://www.blueearthcountymn.gov/181/Parks", ["camping", "swimming", "fishing", "picnic", "playground"], "Blue Earth County camping park on Hall Lake southwest of Mankato."),
    ("Bray Park", 43.6431, -94.4614, "Martin County Parks", "https://www.co.martin.mn.us/", ["camping", "swimming", "fishing", "picnic", "boating"], "Martin County park on Lake George at Fairmont — beach, campground, and a classic southern-Minnesota county lake."),
    ("Kilen Woods is state", 0, 0, "", "", [], ""),  # placeholder skipped
    ("Pinawa Howling Wildlife Management Area skip", 0, 0, "", "", [], ""),
    ("Lake Louise is state skip", 0, 0, "", "", [], ""),
    ("Sibley County Park (High Island Creek)", 44.541, -94.396, "Sibley County Parks", "https://www.sibleycounty.gov/", ["picnic", "hiking", "fishing"], "A small Sibley County park along High Island Creek near Arlington."),
    ("Nessel Campground / Rush Creek", 45.627, -93.137, "Chisago County Parks", "https://www.chisagocounty.us/", ["camping", "fishing", "picnic"], "Chisago County camping near Rush Lake / Nessel — one of the county's rural parks outside the St. Croix corridor."),
    ("Ojiketa Regional Park", 45.4195, -92.6478, "Chisago County Parks", "https://www.chisagocounty.us/", ["swimming", "picnic", "boating", "hiking"], "Chisago County park on South Center Lake in Lindstrom."),
    ("KiChiSaga Park", 45.388, -92.845, "Chisago County Parks", "https://www.chisagocounty.us/", ["picnic", "hiking", "playground", "fishing"], "Chisago County park near Chisago City with lake access and a large picnic shelter."),
    ("Spring Lake Park Reserve is dakota regional", 0, 0, "", "", [], ""),
    ("Boulder Lake Conservation Area", 47.0194, -92.2006, "St. Louis County Parks", "https://www.stlouiscountymn.gov/departments-a-z/public-works/parks-recreation", ["hiking", "biking", "fishing", "boating", "wildlife"], "St. Louis County forest north of Duluth: gravel roads, a reservoir, and enough acreage that it feels like a state forest."),
    ("Chub Lake Park", 46.666, -92.428, "Carlton County Parks", "https://www.co.carlton.mn.us/", ["swimming", "picnic", "fishing", "boating"], "Carlton County park on Chub Lake with a swimming beach and fishing access, separate from Jay Cooke."),
    ("Moose Lake County Park", 46.454, -92.761, "Carlton County Parks", "https://www.co.carlton.mn.us/", ["camping", "swimming", "picnic", "fishing"], "Carlton County park on Moose Lake — campground and beach, separate from Moose Lake State Park."),
    ("Thomson Dam / Jay Cooke adjacent skip", 0, 0, "", "", [], ""),
    ("Itasca County Fairgrounds Park skip", 0, 0, "", "", [], ""),
    ("Winnibigoshish Recreation Area (county)", 47.430, -94.360, "Itasca County Parks", "https://www.co.itasca.mn.us/", ["camping", "boating", "fishing", "swimming", "picnic"], "Itasca County camping and lake access on Lake Winnibigoshish, one of the big waters of the north."),
    ("McCarthy Beach is state skip", 0, 0, "", "", [], ""),
    ("Bennett Valley / Mesabi skip", 0, 0, "", "", [], ""),
    ("Pebble Lake Park", 46.252, -96.075, "Otter Tail County Parks", "https://ottertailcountymn.us/", ["swimming", "picnic", "playground", "fishing"], "Otter Tail County park on Pebble Lake at Fergus Falls."),
    ("Inspiration Peak is wayside skip", 0, 0, "", "", [], ""),
    ("Maplewood is state skip", 0, 0, "", "", [], ""),
    ("Dunton Locks County Park", 46.7186, -95.6957, "Becker County Parks", "https://www.co.becker.mn.us/", ["boating", "fishing", "picnic", "hiking"], "Becker County park on the Pelican River chain at Detroit Lakes, with locks leftover from the old navigation scheme."),
    ("Muskrat Lake County Park", 46.845, -95.845, "Becker County Parks", "https://www.co.becker.mn.us/", ["camping", "fishing", "picnic", "swimming"], "A smaller Becker County lake park northwest of Detroit Lakes."),
    ("Buffalo River is state skip", 0, 0, "", "", [], ""),
    ("Red River SRA is state skip", 0, 0, "", "", [], ""),
    ("Old Mill State Park is state skip", 0, 0, "", "", [], ""),
    ("Lake Bronson is state skip", 0, 0, "", "", [], ""),
    ("Hayes Lake is state skip", 0, 0, "", "", [], ""),
    ("Zippel Bay is state skip", 0, 0, "", "", [], ""),
    ("Franz Jevne is state skip", 0, 0, "", "", [], ""),
    ("Garden Island is state skip", 0, 0, "", "", [], ""),
    ("Big Bog is state skip", 0, 0, "", "", [], ""),
    ("Lake Bemidji is state skip", 0, 0, "", "", [], ""),
    ("Movil Maze / Hubbard skip", 0, 0, "", "", [], ""),
    ("Heartland Park", 46.924, -95.062, "Hubbard County Parks", "https://www.co.hubbard.mn.us/", ["camping", "picnic", "fishing"], "Hubbard County park near Park Rapids on the Heartland Trail corridor."),
    ("Mantrap Township / County access", 47.067, -94.917, "Hubbard County Parks", "https://www.co.hubbard.mn.us/", ["boating", "fishing", "picnic"], "County lake access on the Mantrap chain north of Park Rapids."),
    ("Gull Lake Recreation Area (county/federal mix)", 46.412, -94.354, "Crow Wing County Parks", "https://crowwing.gov/181/Parks", ["camping", "swimming", "boating", "fishing", "picnic"], "Crow Wing County / Corps recreation on Gull Lake west of Brainerd."),
    ("Lum Park is city skip", 0, 0, "", "", [], ""),
    ("Crow Wing State Park is state skip", 0, 0, "", "", [], ""),
    ("Cuyuna is state skip", 0, 0, "", "", [], ""),
    ("Mille Lacs Kathio is state skip", 0, 0, "", "", [], ""),
    ("Father Hennepin is state skip", 0, 0, "", "", [], ""),
    ("Wealthwood / Mille Lacs County Park", 46.206, -93.616, "Mille Lacs County Parks", "https://www.millelacs.mn.gov/", ["boating", "fishing", "picnic", "camping"], "Mille Lacs County park on the south shore, aimed at fishing access more than hiking."),
    ("Onamia Lake County Park", 46.070, -93.670, "Mille Lacs County Parks", "https://www.millelacs.mn.gov/", ["swimming", "picnic", "fishing"], "A smaller Mille Lacs County park on Lake Onamia."),
    ("Izaty's / county skip", 0, 0, "", "", [], ""),
    ("Savanna Portage is state skip", 0, 0, "", "", [], ""),
    ("Aitkin County Campground (Ripple Lake)", 46.533, -93.710, "Aitkin County Parks", "https://www.co.aitkin.mn.us/", ["camping", "fishing", "boating", "picnic"], "Aitkin County camping on Ripple Lake, a typical north-central county campground."),
    ("Jacobson Campground", 47.004, -93.416, "Aitkin County Parks", "https://www.co.aitkin.mn.us/", ["camping", "fishing", "boating", "picnic"], "Aitkin County Mississippi River campground at Jacobson."),
    ("Savanna State Forest county access skip", 0, 0, "", "", [], ""),
    ("Banning is state skip", 0, 0, "", "", [], ""),
    ("St. Croix is state skip", 0, 0, "", "", [], ""),
    ("Chengwatana / Pine County Park", 45.824, -92.969, "Pine County Parks", "https://www.co.pine.mn.us/", ["hiking", "picnic", "wildlife"], "Pine County parkland on the edge of Chengwatana State Forest near Pine City."),
    ("Dalles / Snake River County Park", 45.826, -93.010, "Pine County Parks", "https://www.co.pine.mn.us/", ["canoeing", "fishing", "picnic"], "Snake River access in Pine County, used as a paddling put-in toward the St. Croix."),
    ("Wild River is state skip", 0, 0, "", "", [], ""),
    ("Interstate is state skip", 0, 0, "", "", [], ""),
    ("William O'Brien is state skip", 0, 0, "", "", [], ""),
    ("Afton is state skip", 0, 0, "", "", [], ""),
    ("Frontenac is state skip", 0, 0, "", "", [], ""),
    ("Lake Pepin / Goodhue County Park (Frontenac vicinity skip)", 0, 0, "", "", [], ""),
    ("Byllesby is dakota regional skip", 0, 0, "", "", [], ""),
    ("Coverne / Treasure Island skip", 0, 0, "", "", [], ""),
    ("Nerstrand is state skip", 0, 0, "", "", [], ""),
    ("Rice County Faribault park skip city", 0, 0, "", "", [], ""),
    ("Sakatah is state skip", 0, 0, "", "", [], ""),
    ("Norseland / Nicollet County Park", 44.459, -94.281, "Nicollet County Parks", "https://www.co.nicollet.mn.us/", ["picnic", "hiking"], "A small Nicollet County wayside-style park west of St. Peter."),
    ("Seven Mile Creek County Park", 44.273, -94.036, "Nicollet County Parks", "https://www.co.nicollet.mn.us/", ["hiking", "picnic", "fishing", "wildlife"], "Nicollet County park southwest of St. Peter with a trout stream and a surprisingly steep trail system."),
    ("Flandrau is state skip", 0, 0, "", "", [], ""),
    ("Minneopa is state skip", 0, 0, "", "", [], ""),
    ("Beaver Creek Valley is state skip", 0, 0, "", "", [], ""),
    ("Forestville is state skip", 0, 0, "", "", [], ""),
    ("Whitewater is state skip", 0, 0, "", "", [], ""),
    ("Great River Bluffs is state skip", 0, 0, "", "", [], ""),
    ("John A. Latsch is state skip", 0, 0, "", "", [], ""),
    ("Carley is state skip", 0, 0, "", "", [], ""),
    ("Beaver Creek skip", 0, 0, "", "", [], ""),
    ("Root River County Park (Riverside)", 43.805, -92.187, "Fillmore County Parks", "https://www.co.fillmore.mn.us/", ["canoeing", "picnic", "fishing", "hiking"], "Fillmore County access on the Root River near Lanesboro's orbit — put-in more than campground."),
    ("Forest Resource Center / county skip", 0, 0, "", "", [], ""),
    ("Houston County Money Creek Campground", 43.821, -91.642, "Houston County Parks", "https://www.co.houston.mn.us/", ["camping", "fishing", "picnic", "hiking"], "Houston County campground in the Money Creek valley, in the driftless blufflands."),
    ("Winona County Whitewater-adjacent skip", 0, 0, "", "", [], ""),
    ("Garvin Heights is city skip", 0, 0, "", "", [], ""),
    ("Apple Blossom / county overlook", 43.996, -91.430, "Winona County Parks", "https://www.co.winona.mn.us/", ["picnic", "hiking"], "Winona County Apple Blossom Drive overlook park above the Mississippi."),
    ("Olmsted Chester already listed", 0, 0, "", "", [], ""),
    ("Mower County Lake Louise is state skip", 0, 0, "", "", [], ""),
    ("Red Rock Falls County Park", 43.666, -92.973, "Mower County Parks", "https://www.co.mower.mn.us/", ["picnic", "hiking", "fishing"], "Mower County park on the Cedar River with a small falls and a picnic ground near Austin's orbit."),
    ("Shooting Star Trailhead (county)", 43.615, -92.730, "Mower County Parks", "https://www.co.mower.mn.us/", ["biking", "picnic"], "County trailhead on the Shooting Star State Trail in southern Mower County."),
    ("Freeborn County Albert Lea lake park (Myre-Big Island is state)", 0, 0, "", "", [], ""),
    ("Arrowhead Point County Park", 43.652, -93.368, "Freeborn County Parks", "https://www.co.freeborn.mn.us/", ["camping", "swimming", "boating", "fishing", "picnic"], "Freeborn County park on Fountain Lake / Albert Lea waters, separate from Myre-Big Island State Park."),
    ("Faribault County Blue Earth River Park", 43.711, -94.101, "Faribault County Parks", "https://www.co.faribault.mn.us/", ["picnic", "fishing", "hiking"], "Faribault County park along the Blue Earth River near Blue Earth."),
    ("Jackson County Belmont Park", 43.621, -95.010, "Jackson County Parks", "https://www.co.jackson.mn.us/", ["camping", "swimming", "picnic", "boating"], "Jackson County park on Belmont Park / Loon Lake area west of Jackson."),
    ("Kilen Woods is state skip2", 0, 0, "", "", [], ""),
    ("Brown County Flandrau adjacent skip", 0, 0, "", "", [], ""),
    ("Lake Hanska County Park", 44.121, -94.527, "Brown County Parks", "https://www.co.brown.mn.us/", ["camping", "swimming", "fishing", "picnic", "boating"], "Brown County park on Lake Hanska — the county's main lake park besides Flandrau in New Ulm."),
    ("Redwood County Ramsey Park is city skip", 0, 0, "", "", [], ""),
    ("Renville County Vicksburg County Park", 44.581, -95.025, "Renville County Parks", "https://www.renvillecountymn.com/", ["hiking", "picnic", "wildlife", "historic"], "Renville County park on the Minnesota River bluff near the old Vicksburg townsite."),
    ("Joseph R. Brown is wayside skip", 0, 0, "", "", [], ""),
    ("Upper Sioux is state skip", 0, 0, "", "", [], ""),
    ("Lac qui Parle is state skip", 0, 0, "", "", [], ""),
    ("Big Stone Lake is state skip", 0, 0, "", "", [], ""),
    ("Ortonville / Big Stone County Park", 45.305, -96.445, "Big Stone County Parks", "https://www.bigstonecounty.org/", ["boating", "fishing", "picnic", "swimming"], "Big Stone County lake access on Big Stone Lake in Ortonville, separate from the state park units."),
    ("Traverse County Mud Lake Park", 45.819, -96.498, "Traverse County Parks", "https://www.co.traverse.mn.us/", ["boating", "fishing", "picnic"], "Traverse County park on Lake Traverse / Mud Lake, a prairie pothole reservoir on the Dakota line."),
    ("Wheaton City is city skip", 0, 0, "", "", [], ""),
    ("Stevens County Perkins Park", 45.584, -95.911, "Stevens County Parks", "https://www.co.stevens.mn.us/", ["camping", "swimming", "picnic", "fishing"], "Stevens County park on Perkins Lake near Hancock."),
    ("Pope County Glacial Lakes is state skip", 0, 0, "", "", [], ""),
    ("Barsness Park (county/city Glenwood mix)", 45.650, -95.390, "Pope County Parks", "https://www.co.pope.mn.us/", ["hiking", "picnic", "swimming", "playground"], "Pope County / Glenwood park on Lake Minnewaska with bluff trail above the lake."),
    ("Starbuck Marina County Park", 45.614, -95.531, "Pope County Parks", "https://www.co.pope.mn.us/", ["boating", "fishing", "picnic", "swimming"], "Pope County marina park at Starbuck on Lake Minnewaska."),
    ("Kandiyohi County Sibley is state skip", 0, 0, "", "", [], ""),
    ("Big Kandiyohi Lake County Park", 45.002, -94.981, "Kandiyohi County Parks", "https://www.kcmn.us/", ["camping", "boating", "fishing", "picnic"], "Kandiyohi County park on Big Kandiyohi Lake south of Willmar."),
    ("Green Lake County Park", 45.236, -94.907, "Kandiyohi County Parks", "https://www.kcmn.us/", ["swimming", "boating", "picnic", "fishing"], "Kandiyohi County access on Green Lake at Spicer, beside but not the same as Sibley State Park."),
    ("Meeker County Lake Ripley Park", 45.121, -94.527, "Meeker County Parks", "https://www.co.meeker.mn.us/", ["swimming", "boating", "picnic", "fishing"], "Meeker County park on Lake Ripley at Litchfield."),
    ("Greenleaf Lake is SRA skip", 0, 0, "", "", [], ""),
    ("McLeod County Buffalo Creek Park", 44.771, -94.191, "McLeod County Parks", "https://www.co.mcleod.mn.us/", ["picnic", "hiking", "fishing"], "McLeod County park along Buffalo Creek near Glencoe."),
    ("Lake Marion County Park", 44.710, -94.353, "McLeod County Parks", "https://www.co.mcleod.mn.us/", ["camping", "swimming", "boating", "fishing", "picnic"], "McLeod County's lake park on Marion, the county's main swim-and-camp unit."),
    ("Renville already listed", 0, 0, "", "", [], ""),
    ("Chippewa County Swift Falls County Park", 45.215, -95.441, "Swift County Parks", "https://www.swiftcounty.com/", ["camping", "fishing", "picnic", "hiking"], "Swift County park at Swift Falls on the Pomme de Terre — a wooded gorge in an otherwise open county."),
    ("Monson Lake is state skip", 0, 0, "", "", [], ""),
    ("Lac qui Parle County Watson Sag Park", 45.010, -95.800, "Lac qui Parle County Parks", "https://www.lqpco.com/", ["boating", "fishing", "picnic"], "County access on the Lac qui Parle reservoir system near Watson."),
    ("Yellow Medicine County Timm Park", 44.728, -95.753, "Yellow Medicine County Parks", "https://www.co.ym.mn.gov/", ["camping", "swimming", "picnic", "fishing"], "Yellow Medicine County park on Timm Lake near Canby."),
    ("Lincoln County Hole-in-the-Mountain skip SNA", 0, 0, "", "", [], ""),
    ("Lake Benton County Park", 44.261, -96.288, "Lincoln County Parks", "https://www.co.lincoln.mn.us/", ["camping", "swimming", "boating", "fishing", "picnic"], "Lincoln County park on Lake Benton, a wind-power prairie lake on the Buffalo Ridge."),
    ("Pipestone County Split Rock Creek is state skip", 0, 0, "", "", [], ""),
    ("Pipestone NM is national skip", 0, 0, "", "", [], ""),
    ("Rock County Blue Mounds is state skip", 0, 0, "", "", [], ""),
    ("Touch the Sky Prairie skip", 0, 0, "", "", [], ""),
    ("Nobles County Lake Bella Park", 43.620, -95.808, "Nobles County Parks", "https://www.co.nobles.mn.us/", ["camping", "swimming", "fishing", "picnic", "boating"], "Nobles County park on Lake Bella north of Worthington."),
    ("Murray County Lake Shetek is state skip", 0, 0, "", "", [], ""),
    ("End-O-Line / county skip city", 0, 0, "", "", [], ""),
    ("Cottonwood County Talcot Lake County Park", 43.890, -95.448, "Cottonwood County Parks", "https://www.co.cottonwood.mn.us/", ["camping", "boating", "fishing", "picnic", "wildlife"], "Cottonwood County / WMA-adjacent park on Talcot Lake west of Windom."),
    ("Mountain Lake County Park", 43.939, -94.926, "Cottonwood County Parks", "https://www.co.cottonwood.mn.us/", ["camping", "swimming", "picnic", "fishing"], "Cottonwood County park at Mountain Lake."),
    ("Watonwan County Ewy Park", 43.982, -94.627, "Watonwan County Parks", "https://www.co.watonwan.mn.us/", ["picnic", "fishing", "playground"], "Watonwan County park near St. James."),
    ("Madelia Lakes County Park", 44.046, -94.415, "Watonwan County Parks", "https://www.co.watonwan.mn.us/", ["swimming", "picnic", "fishing", "boating"], "Watonwan County lake park at Madelia."),
    ("Waseca County Clear Lake Park", 44.076, -93.507, "Waseca County Parks", "https://www.co.waseca.mn.us/", ["swimming", "boating", "picnic", "fishing", "playground"], "Waseca County park on Clear Lake — the county seat's main swim beach, county-operated."),
    ("Steele County Oak Glen County Park", 44.022, -93.094, "Steele County Parks", "https://www.co.steele.mn.us/", ["camping", "hiking", "picnic", "fishing"], "Steele County park northeast of Owatonna with camping and a wooded loop."),
    ("Dodge County Mantorville park skip city", 0, 0, "", "", [], ""),
    ("Rice Lake State Park is state skip", 0, 0, "", "", [], ""),
    ("Dodge County Wasioja park", 44.079, -92.819, "Dodge County Parks", "https://www.co.dodge.mn.us/", ["picnic", "historic", "hiking"], "Dodge County park at Wasioja, next to the Civil War recruiting station ruins."),
    ("Goodhue County Lake Byllesby (Goodhue side)", 44.525, -92.939, "Goodhue County Parks", "https://co.goodhue.mn.us/", ["boating", "fishing", "picnic", "hiking"], "Goodhue County's side of Lake Byllesby — boat access and picnic, paired with Dakota County's regional park across the water."),
    ("Sturgeon Lake County Park", 46.381, -92.824, "Pine County Parks", "https://www.co.pine.mn.us/", ["camping", "swimming", "boating", "fishing", "picnic"], "Pine County park on Sturgeon Lake, a typical Hinckley-area county campground."),
    ("Sandstone / Banning adjacent skip", 0, 0, "", "", [], ""),
    ("Kanabec County Ann Lake Park", 45.952, -93.294, "Kanabec County Parks", "https://www.kanabeccounty.org/", ["camping", "swimming", "fishing", "picnic"], "Kanabec County park on Ann Lake west of Mora."),
    ("Isanti County Springvale County Park", 45.619, -93.294, "Isanti County Parks", "https://www.co.isanti.mn.us/", ["hiking", "picnic", "fishing", "wildlife"], "Isanti County park on the Rum River north of Cambridge."),
    ("Mille Lacs already listed", 0, 0, "", "", [], ""),
    ("Sherburne County Woodland Trails Park", 45.445, -93.650, "Sherburne County Parks", "https://www.co.sherburne.mn.us/", ["hiking", "picnic", "wildlife", "biking"], "Sherburne County trail park near Elk River — oak woodland, not the federal refuge."),
    ("Gramse County Park", 45.460, -93.909, "Sherburne County Parks", "https://www.co.sherburne.mn.us/", ["hiking", "picnic", "fishing"], "Sherburne County park west of Big Lake."),
    ("Lake Maria is state skip", 0, 0, "", "", [], ""),
    ("Montissippi County Park", 45.305, -93.760, "Wright County Parks", "https://www.co.wright.mn.us/148/Parks-Recreation", ["hiking", "picnic", "fishing", "canoeing"], "Wright County park at the Mississippi in Monticello, with river trail and a busy summer picnic ground."),
    ("Stanley Eddy Memorial Park", 45.314, -94.019, "Wright County Parks", "https://www.co.wright.mn.us/148/Parks-Recreation", ["hiking", "picnic", "wildlife"], "Wright County woodland park east of Maple Lake."),
    ("Clearwater / Wright already", 0, 0, "", "", [], ""),
    ("Lake Alexander County Park", 46.205, -94.478, "Morrison County Parks", "https://www.co.morrison.mn.us/", ["camping", "swimming", "boating", "fishing", "picnic"], "Morrison County park on Lake Alexander west of Little Falls."),
    ("Charles A. Lindbergh is state skip", 0, 0, "", "", [], ""),
    ("Belle Prairie County Park", 46.016, -94.348, "Morrison County Parks", "https://www.co.morrison.mn.us/", ["picnic", "hiking", "fishing"], "Morrison County park on the Mississippi north of Little Falls."),
    ("Crow Wing already", 0, 0, "", "", [], ""),
    ("Cass County Stony Point", 47.148, -94.519, "Cass County Parks", "https://www.co.cass.mn.us/", ["boating", "fishing", "picnic", "swimming"], "Cass County park on Leech Lake at Stony Point — fishing access more than a city playground."),
    ("Deep Portage / county skip private", 0, 0, "", "", [], ""),
    ("Winnibigoshish already listed itasca", 0, 0, "", "", [], ""),
    ("Koochiching County Franz Jevne adjacent skip", 0, 0, "", "", [], ""),
    ("Rainy Lake / International Falls county dock", 48.609, -93.351, "Koochiching County Parks", "https://www.co.koochiching.mn.us/", ["boating", "fishing", "picnic"], "Koochiching County public access on Rainy Lake at International Falls."),
    ("Voyageurs is national skip", 0, 0, "", "", [], ""),
    ("Lake of the Woods County Zippel adjacent skip", 0, 0, "", "", [], ""),
    ("Baudette Riverfront County Park", 48.712, -94.599, "Lake of the Woods County Parks", "https://www.co.lake-of-the-woods.mn.us/", ["picnic", "fishing", "boating"], "County riverfront park in Baudette on the Rainy River."),
    ("Roseau County Hayes adjacent skip", 0, 0, "", "", [], ""),
    ("Roseau River County Park", 48.846, -95.762, "Roseau County Parks", "https://www.co.roseau.mn.us/", ["picnic", "fishing", "wildlife"], "Roseau County park on the Roseau River, a small prairie-county unit."),
    ("Kittson County Lake Bronson adjacent skip", 0, 0, "", "", [], ""),
    ("Hallock County Park", 48.774, -96.943, "Kittson County Parks", "https://www.co.kittson.mn.us/", ["picnic", "playground"], "Kittson County park in Hallock — one of the few county-operated parks in the far northwest."),
    ("Marshall County Old Mill is state skip", 0, 0, "", "", [], ""),
    ("Florian Park", 48.441, -96.637, "Marshall County Parks", "https://www.co.marshall.mn.us/", ["camping", "swimming", "picnic", "fishing"], "Marshall County park at Florian, a wooded oasis in the Red River Valley."),
    ("Pennington County Higginbotham Park skip city", 0, 0, "", "", [], ""),
    ("Red Lake County Brooks Park", 47.811, -96.009, "Red Lake County Parks", "https://www.co.red-lake.mn.us/", ["picnic", "playground"], "Red Lake County park at Brooks."),
    ("Polk County Red River SRA is state skip", 0, 0, "", "", [], ""),
    ("McIntosh County Park", 47.667, -95.886, "Polk County Parks", "https://www.co.polk.mn.us/", ["picnic", "playground", "hiking"], "Polk County park at McIntosh in the beach-ridge lake country."),
    ("Norman County Twin Valley Park", 47.268, -96.257, "Norman County Parks", "https://www.co.norman.mn.us/", ["picnic", "playground"], "Norman County park at Twin Valley."),
    ("Clay County Buffalo River is state skip", 0, 0, "", "", [], ""),
    ("Bierman Park", 46.992, -96.356, "Clay County Parks", "https://claycountymn.gov/", ["picnic", "playground", "hiking"], "Clay County park east of Moorhead, a prairie-county picnic ground rather than a lake resort."),
    ("Wilkin County Breckenridge park skip city", 0, 0, "", "", [], ""),
    ("Otter Tail already", 0, 0, "", "", [], ""),
    ("Grant County Pomme de Terre Park", 45.928, -95.986, "Grant County Parks", "https://www.co.grant.mn.us/", ["camping", "swimming", "fishing", "picnic", "boating"], "Grant County park on the Pomme de Terre River / reservoir near Elbow Lake."),
    ("Wadena County Sunnybrook Park", 46.438, -95.136, "Wadena County Parks", "https://www.co.wadena.mn.us/", ["camping", "picnic", "fishing", "hiking"], "Wadena County park with camping along the Leaf River system."),
    ("Todd County Battle Point Park", 45.981, -94.875, "Todd County Parks", "https://www.co.todd.mn.us/", ["camping", "swimming", "boating", "fishing", "picnic"], "Todd County park on Lake Osakis — battle-point camping and a swim beach."),
    ("Long Prairie River County Park", 45.975, -94.860, "Todd County Parks", "https://www.co.todd.mn.us/", ["canoeing", "picnic", "fishing"], "Todd County access on the Long Prairie River."),
    ("Cass already", 0, 0, "", "", [], ""),
    ("Hubbard already", 0, 0, "", "", [], ""),
    ("Clearwater County Itasca adjacent skip", 0, 0, "", "", [], ""),
    ("Lower Rice Lake County Park", 47.381, -95.269, "Clearwater County Parks", "https://www.co.clearwater.mn.us/", ["boating", "fishing", "picnic"], "Clearwater County access on Lower Rice Lake, wild-rice country west of Itasca."),
    ("Mahnomen County North Twin Park", 47.325, -95.809, "Mahnomen County Parks", "https://www.co.mahnomen.mn.us/", ["camping", "swimming", "fishing", "picnic", "boating"], "Mahnomen County park on North Twin Lake."),
    ("Becker already", 0, 0, "", "", [], ""),
    ("Lake County Gooseberry is state skip", 0, 0, "", "", [], ""),
    ("Two Harbors / county skip city", 0, 0, "", "", [], ""),
    ("Silver Bay Lax Lake County Park", 47.341, -91.196, "Lake County Parks", "https://www.co.lake.mn.us/", ["camping", "swimming", "fishing", "picnic", "boating"], "Lake County park on Lax Lake inland from Silver Bay — a quieter alternative to the Hwy 61 state parks."),
    ("Cook County Devil Track Lake Park", 47.829, -90.412, "Cook County Parks", "https://www.co.cook.mn.us/", ["camping", "boating", "fishing", "picnic", "swimming"], "Cook County park on Devil Track Lake north of Grand Marais."),
    ("Cascade is state skip", 0, 0, "", "", [], ""),
    ("Judge Magney is state skip", 0, 0, "", "", [], ""),
    ("Grand Portage is state/nps skip", 0, 0, "", "", [], ""),
    ("St. Louis County Banning skip", 0, 0, "", "", [], ""),
    ("Peyton Ponds / Embarrass skip", 0, 0, "", "", [], ""),
    ("Hoyt Lakes Colby Lake County Park", 47.519, -92.138, "St. Louis County Parks", "https://www.stlouiscountymn.gov/departments-a-z/public-works/parks-recreation", ["boating", "fishing", "picnic", "swimming"], "St. Louis County park on Colby Lake at Hoyt Lakes on the Iron Range."),
    ("Gilbert / Lake Ore-be-gone skip city", 0, 0, "", "", [], ""),
    ("Ely / Miners Lake skip city", 0, 0, "", "", [], ""),
    ("Pfeiffer Lake County Park", 47.741, -92.286, "St. Louis County Parks", "https://www.stlouiscountymn.gov/departments-a-z/public-works/parks-recreation", ["camping", "swimming", "fishing", "picnic", "boating"], "St. Louis County park on Pfeiffer Lake north of Virginia."),
    ("Kabetogama / county skip NPS", 0, 0, "", "", [], ""),
]


def load_greater_mn(existing_names: set[str]) -> list[dict]:
    parks = []
    for row in GREATER_MN_COUNTY:
        name, lat, lon, agency, url, amenities, highlights = row
        if not lat or "skip" in name.lower():
            continue
        if isinstance(amenities, tuple) or (amenities and isinstance(amenities[0], list)):
            continue
        if not isinstance(highlights, str):
            continue
        nn = norm_name(name)
        if nn in existing_names:
            continue
        parks.append(
            make_park(
                name=name,
                park_type="county",
                lat=lat,
                lon=lon,
                managing_agency=agency,
                source="curated_greater_mn_county",
                source_id=slug(name, "county"),
                source_url=normalize_url(url),
                highlights=highlights,
                amenities=amenities if isinstance(amenities, list) else ["picnic"],
            )
        )
    return [p for p in parks if p]


WILDERNESS_AGENCY_LABEL = {
    "FS": "USDA Forest Service",
    "FWS": "U.S. Fish and Wildlife Service",
    "NPS": "National Park Service",
    "BLM": "Bureau of Land Management",
}

WILDERNESS_AMENITIES = {
    "boundary waters canoe area wilderness": [
        "canoeing", "camping", "fishing", "wildlife", "hiking",
    ],
    "agassiz wilderness": ["wildlife", "hiking"],
    "tamarac wilderness": ["wildlife", "hiking", "canoeing", "fishing"],
}


def wilderness_agency_label(name: str, agency: str, description: str) -> str:
    base = WILDERNESS_AGENCY_LABEL.get(agency, agency or "National Wilderness Preservation System")
    text = f"{name} {description}".lower()
    if agency == "FS" and "superior national forest" in text:
        return "USDA Forest Service, Superior National Forest"
    if agency == "FWS" and "agassiz" in name.lower():
        return "U.S. Fish and Wildlife Service, Agassiz National Wildlife Refuge"
    if agency == "FWS" and "tamarac" in name.lower():
        return "U.S. Fish and Wildlife Service, Tamarac National Wildlife Refuge"
    return base


def centroid_web_mercator(shp) -> tuple[float, float] | None:
    try:
        geom = shape(shp.__geo_interface__)
        if geom.is_empty:
            return None
        c = geom.centroid
        return WEB_MERCATOR_TO_WGS.transform(c.x, c.y)
    except Exception:
        return None


def load_wilderness() -> list[dict]:
    """Federal wilderness units in Minnesota from the NWPS shapefile (all agencies)."""
    folder = CACHE / "wilderness"
    if not folder.exists():
        print("Wilderness shapefile cache missing; skipping wilderness units.")
        return []
    path = find_shp(folder, "wild")
    sf = shapefile.Reader(str(path.with_suffix("")))
    fields = [f[0] for f in sf.fields[1:]]
    groups: dict[str, list] = defaultdict(list)
    for rec, shp in zip(sf.records(), sf.shapes()):
        d = dict(zip(fields, rec))
        if str(d.get("STATE") or "").upper() != "MN":
            continue
        name = (d.get("NAME") or "").strip()
        if not name:
            continue
        groups[name].append((d, shp))

    parks = []
    for name, items in groups.items():
        d0 = items[0][0]
        geoms = []
        for _, shp in items:
            try:
                g = shape(shp.__geo_interface__)
                if not g.is_empty:
                    geoms.append(g)
            except Exception:
                continue
        if geoms:
            merged = unary_union(geoms)
            c = merged.centroid
            lon, lat = WEB_MERCATOR_TO_WGS.transform(c.x, c.y)
        else:
            xy = centroid_web_mercator(items[0][1])
            if not xy:
                continue
            lon, lat = xy
        agency = (d0.get("Agency") or "").strip()
        description = (d0.get("Descriptio") or d0.get("Description") or "").strip()
        gis_url = d0.get("URL") or ""
        wid = d0.get("WID") or name
        amenities = parse_features(f"{name} {description}")
        for extra in WILDERNESS_AMENITIES.get(name.lower(), []):
            if extra not in amenities:
                amenities.append(extra)
        highlight = highlights_for(name)
        if not highlight and description:
            highlight = re.split(r"(?<=\.)\s", description, maxsplit=1)[0]
            if len(highlight) > 280:
                highlight = highlight[:277] + "…"
        parks.append(
            make_park(
                name=name,
                park_type="wilderness",
                lat=lat,
                lon=lon,
                managing_agency=wilderness_agency_label(name, agency, description),
                source="wilderness_connect_nwps",
                source_id=str(wid),
                source_url=wilderness_agency_url(name, agency, gis_url),
                highlights=highlight,
                amenities=amenities,
            )
        )
    loaded = [p for p in parks if p]
    print(f"Loaded {len(loaded)} Minnesota wilderness units")
    for park in loaded:
        print(f"  wilderness {park['name']} {park['latitude']},{park['longitude']} {park['source_url']}")
    return loaded


def dedup(parks: list[dict]) -> list[dict]:
    """Keep first of similar names within ~1.2 km. Prefer national/wilderness > state > regional > county."""
    rank = {"national": 0, "wilderness": 0, "state": 1, "regional": 2, "county": 3}
    parks = sorted(parks, key=lambda p: (rank.get(p["park_type"], 9), p["name"]))
    kept: list[dict] = []

    def hav(a, b):
        r = 6371.0
        p1, p2 = math.radians(a["latitude"]), math.radians(b["latitude"])
        dp = p2 - p1
        dl = math.radians(b["longitude"] - a["longitude"])
        h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return 2 * r * math.asin(min(1, math.sqrt(h)))

    for p in parks:
        n = norm_name(p["name"])
        dup = False
        for k in kept:
            if n and n == norm_name(k["name"]) and hav(p, k) < 8:
                dup = True
                break
            if hav(p, k) < 1.2 and n and (n in norm_name(k["name"]) or norm_name(k["name"]) in n):
                dup = True
                break
        if not dup:
            kept.append(p)
    return kept


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch official MN park sources and write db/data/parks.json."
    )
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Rebuild from files already in MN_PARKS_CACHE (default /tmp/mn-parks-data).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    skip_fetch = args.skip_fetch or os.environ.get("PARKS_SKIP_FETCH") == "1"
    if skip_fetch:
        print(f"Skipping remote fetch; using cache at {CACHE}")
    else:
        fetch_sources()

    dnr = load_dnr()
    nps = load_nps()
    wilderness = load_wilderness()
    regional = load_regional()
    regional_names = {norm_name(p["name"]) for p in regional}
    metro_county = load_metro_county(regional_names)
    existing = {norm_name(p["name"]) for p in dnr + nps + wilderness + regional + metro_county}
    greater = load_greater_mn(existing)
    parks = dedup(
        [p for p in (dnr + nps + wilderness + regional + metro_county + greater) if p]
    )
    parks.sort(key=lambda p: (p["park_type"], p["name"]))
    counts = defaultdict(int)
    for p in parks:
        counts[p["park_type"]] += 1
    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "counts": dict(counts),
        "attribution": [
            "Minnesota DNR Parks & Trails reference points via Minnesota Geospatial Commons (bdry_dnr_lrs_prk).",
            "National Park Service Parks API (stateCode=MN).",
            "National Wilderness Preservation System boundaries via Wilderness Connect GIS (federal wilderness in Minnesota, including Superior National Forest).",
            "Metropolitan Council Regional Parks (LPH/Parks_CD).",
            "MetroGIS Collaborative Parks (county-owned units in the seven-county metro).",
            "Greater Minnesota county parks: curated points with real coordinates; not every one of 87 counties publishes GIS.",
        ],
        "parks": parks,
    }
    OUT.write_text(json.dumps(payload, indent=2))
    print(f"Wrote {len(parks)} parks to {OUT}")
    print(dict(counts))


if __name__ == "__main__":
    main()
