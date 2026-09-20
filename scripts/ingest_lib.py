"""Shared helpers for offline park-intel builders (Dark Sky, camping inventory)."""

from __future__ import annotations

import io
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = Path(os.environ.get("MN_PARKS_CACHE", "/tmp/mn-parks-data"))
PARKS_JSON = ROOT / "db" / "data" / "parks.json"
USER_AGENT = "mn-parks-refresh/1.0 (https://github.com/mattmcf/mn-parks)"

MN_WEST, MN_SOUTH, MN_EAST, MN_NORTH = -97.5, 43.4, -89.34, 49.4

SUFFIXES = (
    " regional park reserve",
    " park reserve",
    " regional park",
    " state recreation area",
    " state park",
    " state wayside",
    " state forest",
    " county park",
    " national monument",
    " national park",
    " national river and recreation area",
    " national scenic riverway",
    " wilderness",
)


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


def http_json(url: str, headers: dict | None = None) -> tuple[dict | list, dict]:
    req_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    last: Exception | None = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers=req_headers)
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read())
                hdrs = {k.lower(): v for k, v in resp.headers.items()}
                return body, hdrs
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            last = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch JSON {url}: {last}") from last


def unzip_url(url: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    raw = http_bytes(url)
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        zf.extractall(dest)


def load_parks() -> list[dict]:
    if not PARKS_JSON.exists():
        raise FileNotFoundError(f"Missing {PARKS_JSON}; run parks:refresh first.")
    payload = json.loads(PARKS_JSON.read_text())
    return list(payload.get("parks") or [])


def compact_name(name: str) -> str:
    n = (name or "").strip().lower().replace("&", "and")
    n = re.sub(r"[^a-z0-9]+", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def strip_suffixes(name: str) -> str:
    n = compact_name(name)
    changed = True
    while changed:
        changed = False
        for suffix in SUFFIXES:
            s = compact_name(suffix)
            if n.endswith(" " + s) or n.endswith(s):
                n = n[: -len(s)].strip()
                changed = True
    return n


def names_match(a: str, b: str) -> bool:
    ca, cb = compact_name(a), compact_name(b)
    if not ca or not cb:
        return False
    if ca == cb:
        return True
    sa, sb = strip_suffixes(a), strip_suffixes(b)
    if sa and sa == sb:
        return True
    if sa and sb and (sa in sb or sb in sa) and min(len(sa), len(sb)) >= 8:
        return True
    return False


def in_minnesota(lat: float | None, lon: float | None) -> bool:
    if lat is None or lon is None:
        return False
    return MN_SOUTH <= lat <= MN_NORTH and MN_WEST <= lon <= MN_EAST


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 3958.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def match_park(
    parks: list[dict],
    *,
    name: str,
    lat: float | None = None,
    lon: float | None = None,
    max_miles: float = 75.0,
) -> dict | None:
    """Match an official place to an existing park by name, then name+coords."""
    exact = [p for p in parks if names_match(name, p["name"])]
    if len(exact) == 1:
        hit = exact[0]
        if lat is not None and lon is not None:
            miles = haversine_miles(lat, lon, float(hit["latitude"]), float(hit["longitude"]))
            if miles > max_miles:
                return None
        return hit
    if len(exact) > 1 and lat is not None and lon is not None:
        ranked = sorted(
            exact,
            key=lambda p: haversine_miles(lat, lon, float(p["latitude"]), float(p["longitude"])),
        )
        if haversine_miles(lat, lon, float(ranked[0]["latitude"]), float(ranked[0]["longitude"])) <= max_miles:
            return ranked[0]
        return None
    if exact:
        return exact[0]
    if lat is None or lon is None:
        return None
    nearby = []
    for park in parks:
        miles = haversine_miles(lat, lon, float(park["latitude"]), float(park["longitude"]))
        if miles <= max_miles and names_match(name, park["name"]):
            nearby.append((miles, park))
    if not nearby:
        return None
    nearby.sort(key=lambda item: item[0])
    return nearby[0][1]
