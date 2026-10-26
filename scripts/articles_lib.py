"""Load, save, geocode, and list article folders. Persistence lives in articles/*/meta.yaml."""
from __future__ import annotations

import json
import math
import re
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ARTICLES = ROOT / "articles"
GAZETTEER = ROOT / "gazetteer" / "streets.yaml"
USER_AGENT = "mittendran-archiv/0.2 (+local archive helper)"


def http_get(url: str, *, timeout: float = 60, retries: int = 4) -> tuple[bytes, str]:
    """GET bytes + final URL via curl -4 (urllib often hits broken IPv6 here)."""
    last: Exception | None = None
    for attempt in range(retries):
        try:
            proc = subprocess.run(
                [
                    "curl",
                    "-4",
                    "-fsSL",
                    "--retry",
                    "2",
                    "--retry-delay",
                    "1",
                    "--max-time",
                    str(int(timeout)),
                    "-A",
                    USER_AGENT,
                    "-w",
                    "\n%{url_effective}",
                    url,
                ],
                capture_output=True,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout:
                raw = proc.stdout
                if b"\n" in raw:
                    body, final = raw.rsplit(b"\n", 1)
                    return body, final.decode("utf-8", errors="replace").strip() or url
                return raw, url
            err = proc.stderr.decode("utf-8", errors="replace").strip()
            last = OSError(err or f"curl exit {proc.returncode}")
        except Exception as exc:  # noqa: BLE001
            last = exc
        time.sleep(0.8 * (attempt + 1))
    raise last or OSError(f"GET failed: {url}")


def slugify(text: str) -> str:
    s = (text or "").lower().strip()
    for src, dst in (
        ("ä", "ae"),
        ("ö", "oe"),
        ("ü", "ue"),
        ("ß", "ss"),
        ("à", "a"),
        ("é", "e"),
        ("è", "e"),
    ):
        s = s.replace(src, dst)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")[:80] or "clip"


def issue_dirname(issue: str | None, sample: bool = False) -> str:
    if sample:
        return "sample"
    text = "" if issue is None else str(issue).strip()
    if not text or text.lower() == "none":
        return "unfiled"
    return text


def iter_article_dirs() -> list[Path]:
    if not ARTICLES.exists():
        return []
    return sorted(path.parent for path in ARTICLES.rglob("meta.yaml"))


def unique_slug(slug: str, issue: str | None = None, sample: bool = False) -> str:
    taken = {folder.name for folder in iter_article_dirs()}
    candidate = slug
    i = 2
    parent = ARTICLES / issue_dirname(issue, sample)
    while candidate in taken or (parent / candidate).exists():
        candidate = f"{slug}-{i}"
        i += 1
    return candidate


# Rough Tiergarten-Süd / Lützowkiez bounding box for auto-confirming geocodes.
KIEZ_BBOX = (52.493, 52.515, 13.345, 13.385)  # south, north, west, east

STREET_RE = re.compile(
    r"\b([A-ZÄÖÜ][A-Za-zäöüÄÖÜß\-]{2,}(?:straße|strasse|str\.|platz|ufer|weg|allee|brücke|bruecke|gasse))\b",
    re.IGNORECASE,
)


def load_gazetteer() -> list[dict]:
    if not GAZETTEER.exists():
        return []
    data = yaml.safe_load(GAZETTEER.read_text(encoding="utf-8")) or {}
    return list(data.get("places") or [])


def _norm_place(name: str) -> str:
    s = (name or "").strip()
    s = re.sub(r"[Ss]tr\.$", "straße", s)
    s = s.replace("strasse", "straße").replace("Strasse", "Straße")
    s = s.replace("bruecke", "brücke").replace("Bruecke", "Brücke")
    # Title-case first letter after normalization
    if s and s[0].islower():
        s = s[0].upper() + s[1:]
    return s


def in_kiez_bbox(lat: float, lon: float) -> bool:
    south, north, west, east = KIEZ_BBOX
    return south <= lat <= north and west <= lon <= east


# House-number hits a little outside the strict Kiez box still belong on the map.
# This stays far inside Berlin, so a "Potsdamer Straße" in Potsdam does not qualify.
ADDRESS_BBOX = (52.488, 52.520, 13.338, 13.395)  # south, north, west, east
ADDRESS_CACHE = ROOT / "gazetteer" / "address_cache.json"
_LINEAR: dict[str, dict] | None = None
_ADDRESS_MEMO: dict | None = None
_LAST_PHOTON = 0.0
_LAST_NOMINATIM = 0.0
_PHOTON_DOWN = False


def in_address_bbox(lat: float, lon: float) -> bool:
    south, north, west, east = ADDRESS_BBOX
    return south <= lat <= north and west <= lon <= east


def _fold_key(name: str) -> str:
    s = (name or "").casefold().replace("ß", "ss")
    s = s.replace("straße", "strasse").replace("str.", "strasse")
    return re.sub(r"[^a-z0-9]+", "", s)


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def linear_places() -> dict[str, dict]:
    """Gazetteer streets and squares, keyed so 'Potsdamerstraße' matches 'Potsdamer Straße'."""
    global _LINEAR
    if _LINEAR is None:
        found: dict[str, dict] = {}
        for place in load_gazetteer():
            if place.get("kind") not in {"street", "square"} or not place.get("name"):
                continue
            found[_fold_key(str(place["name"]))] = place
        _LINEAR = found
    return _LINEAR


def canonical_linear(name: str) -> dict | None:
    return linear_places().get(_fold_key(name))


def _street_forms(street: str) -> list[str]:
    name = (street or "").strip()
    forms = {name}
    for src, dst in (
        ("straße", "strasse"),
        ("Straße", "Strasse"),
        ("strasse", "straße"),
        ("Strasse", "Straße"),
    ):
        if src in name:
            forms.add(name.replace(src, dst))
    more: set[str] = set()
    for form in forms:
        more.add(form.replace(" ", ""))
        for src in ("straße", "strasse", "Straße", "Strasse"):
            if form.endswith(src):
                stem = form[: -len(src)].rstrip()
                more.add(stem + "str.")
                more.add(stem + "straße")
                more.add(stem + "strasse")
    forms |= more
    return sorted((f for f in forms if len(f) >= 4), key=len, reverse=True)


def _md_title(text: str) -> str:
    for line in (text or "").splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
    return ""


def address_hits(text: str, street: str) -> list[tuple[str, int]]:
    """House numbers written on this street. Labels look like '74', '74a', '89-90'."""
    forms = _street_forms(street)
    if not forms:
        return []
    flat = re.sub(r"\s+", " ", text or "")
    alts = "|".join(re.escape(form) for form in forms)
    rx = re.compile(
        rf"(?i)(?<!\w)(?:{alts})\s+(?:nr\.?\s*)?(\d{{1,3}})"
        rf"(?:\s*[-–/]\s*(\d{{1,3}}))?([a-zA-Z])?(?!\w)"
    )
    hits: list[tuple[str, int]] = []
    for match in rx.finditer(flat):
        try:
            number = int(match.group(1))
        except ValueError:
            continue
        if not 1 <= number <= 250:
            continue
        end = match.group(2)
        letter = match.group(3)
        if end:
            try:
                number2 = int(end)
            except ValueError:
                number2 = 0
            if number < number2 <= number + 20 and number2 <= 250:
                label = f"{number}-{number2}"
            else:
                label = str(number)
        elif letter and letter.isalpha():
            label = f"{number}{letter.lower()}"
        else:
            label = str(number)
        hits.append((label, match.start()))
    return hits


def _base_number(label: str) -> str:
    return label.split("-", 1)[0].rstrip("abcdefghijklmnopqrstuvwxyz")


def _mode_label(hits: list[tuple[str, int]], base: str) -> str:
    labels = [label for label, _pos in hits if _base_number(label) == base]
    if not labels:
        return base
    top, count = Counter(labels).most_common(1)[0]
    if count / len(labels) >= 0.7:
        return top
    return base


def choose_address(text: str, street: str, title: str = "") -> str | None:
    """Pick the best house number on this street, so the pin is a building rather than the whole street.

    A single number in the title wins. Otherwise the number mentioned most often wins,
    and a tie goes to the one that appears first. One mention is enough.
    """
    title_hits = address_hits(title or "", street)
    title_bases: list[str] = []
    for label, _pos in title_hits:
        base = _base_number(label)
        if base not in title_bases:
            title_bases.append(base)
    if len(title_bases) == 1:
        return _mode_label(title_hits, title_bases[0])

    body = address_hits(text or "", street)
    if not body:
        return None
    counts = Counter(_base_number(label) for label, _pos in body)
    top_n = counts.most_common(1)[0][1]
    leaders = [base for base, count in counts.items() if count == top_n]
    first_at: dict[str, int] = {}
    for label, pos in body:
        base = _base_number(label)
        if base in leaders and base not in first_at:
            first_at[base] = pos
    best = min(leaders, key=lambda base: first_at.get(base, 10**9))
    return _mode_label(body, best)


def corner_partner(text: str, street: str) -> str | None:
    """Other street named in the same breath as 'Ecke' or 'Kreuzung'."""
    flat = re.sub(r"\s+", " ", text or "")
    forms = _street_forms(street)
    if not forms:
        return None
    street_re = re.compile("|".join(re.escape(form) for form in forms), re.I)
    found: list[tuple[int, str]] = []
    for place in linear_places().values():
        other = str(place.get("name") or "")
        if not other or _fold_key(other) == _fold_key(street):
            continue
        other_forms = _street_forms(other)[:4]
        other_re = re.compile("|".join(re.escape(form) for form in other_forms), re.I)
        for match in street_re.finditer(flat):
            window = flat[max(0, match.start() - 90) : match.end() + 90]
            if not re.search(r"\b(?:Ecke|Kreuzung)\b", window, re.I):
                continue
            if other_re.search(window):
                found.append((match.start(), other))
                break
    if not found:
        return None
    found.sort()
    return found[0][1]


def _load_address_cache() -> dict:
    global _ADDRESS_MEMO
    if _ADDRESS_MEMO is None:
        if ADDRESS_CACHE.exists():
            _ADDRESS_MEMO = json.loads(ADDRESS_CACHE.read_text(encoding="utf-8"))
        else:
            _ADDRESS_MEMO = {}
    return _ADDRESS_MEMO


def _save_address_cache() -> None:
    ADDRESS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    ADDRESS_CACHE.write_text(
        json.dumps(_load_address_cache(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _number_ok(wanted: str, got: str) -> bool:
    have = (got or "").casefold().replace(" ", "")
    need = wanted.casefold().replace(" ", "")
    if not have or not need:
        return False
    if "-" in need:
        start, end = need.split("-", 1)
        return have in {start, end, need, f"{start}/{end}"}
    return have == need


def _photon_houses(query: str) -> list[dict] | None:
    """House hits, or None when Photon cannot be reached (do not treat that as a miss)."""
    global _LAST_PHOTON, _PHOTON_DOWN
    if _PHOTON_DOWN:
        return None
    wait = 0.25 - (time.time() - _LAST_PHOTON)
    if wait > 0:
        time.sleep(wait)
    _LAST_PHOTON = time.time()
    url = "https://photon.komoot.io/api/?" + urllib.parse.urlencode(
        {
            "q": query,
            "limit": "5",
            "lang": "de",
            "lat": "52.5047",
            "lon": "13.3615",
        }
    )
    try:
        raw, _final = http_get(url, timeout=12, retries=1)
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        _PHOTON_DOWN = True
        print("  photon unavailable, using nominatim", flush=True)
        return None
    houses = []
    for feat in (data or {}).get("features") or []:
        props = feat.get("properties") or {}
        coords = (feat.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2 or not props.get("housenumber"):
            continue
        houses.append(
            {
                "street": str(props.get("street") or ""),
                "housenumber": str(props.get("housenumber") or ""),
                "city": str(props.get("city") or ""),
                "postcode": str(props.get("postcode") or ""),
                "lat": round(float(coords[1]), 6),
                "lon": round(float(coords[0]), 6),
            }
        )
    return houses


def _nominatim_houses(query: str) -> list[dict] | None:
    """House hits, or None when Nominatim cannot be reached."""
    global _LAST_NOMINATIM
    wait = 1.1 - (time.time() - _LAST_NOMINATIM)
    if wait > 0:
        time.sleep(wait)
    _LAST_NOMINATIM = time.time()
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {
            "q": query,
            "format": "json",
            "limit": "5",
            "countrycodes": "de",
            "addressdetails": "1",
        }
    )
    try:
        raw, _final = http_get(url, timeout=20, retries=2)
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        print(f"  nominatim failed: {query}", flush=True)
        return None
    houses = []
    for row in data or []:
        addr = row.get("address") or {}
        street = addr.get("road") or addr.get("pedestrian") or addr.get("footway") or ""
        number = addr.get("house_number") or ""
        if not street or not number:
            continue
        city = addr.get("city") or addr.get("town") or addr.get("suburb") or ""
        houses.append(
            {
                "street": str(street),
                "housenumber": str(number),
                "city": str(city),
                "postcode": str(addr.get("postcode") or ""),
                "lat": round(float(row["lat"]), 6),
                "lon": round(float(row["lon"]), 6),
            }
        )
    return houses


def _house_hit_ok(street: str, label: str, hit: dict) -> bool:
    if _fold_key(hit.get("street") or "") != _fold_key(street):
        return False
    if not _number_ok(label, str(hit.get("housenumber") or "")):
        return False
    if not in_address_bbox(float(hit["lat"]), float(hit["lon"])):
        return False
    city = str(hit.get("city") or "").casefold()
    if city and "berlin" not in city:
        return False
    postcode = str(hit.get("postcode") or "")
    if postcode and not postcode.startswith("10"):
        return False
    return True


def _label_span(label: str) -> tuple[int, int] | None:
    text = (label or "").lower().strip()
    if "-" in text:
        start, end = text.split("-", 1)
        start_m, end_m = re.match(r"\d+", start), re.match(r"\d+", end)
        if not start_m or not end_m:
            return None
        return int(start_m.group()), int(end_m.group())
    match = re.match(r"\d+", text)
    if not match:
        return None
    number = int(match.group())
    return number, number


def _surveyed_houses(street: str) -> list[tuple[int, float, float]]:
    """House numbers on this street that came from a geocoder, not from an earlier estimate."""
    points: list[tuple[int, float, float]] = []
    prefix = f"{street}|"
    for key, row in _load_address_cache().items():
        if not row.get("ok") or row.get("via") == "interpolated":
            continue
        if not str(key).startswith(prefix):
            continue
        span = _label_span(str(key).split("|", 1)[1])
        if not span:
            continue
        points.append((span[0], float(row["lat"]), float(row["lon"])))
    points.sort()
    deduped: list[tuple[int, float, float]] = []
    for point in points:
        if deduped and deduped[-1][0] == point[0]:
            continue
        deduped.append(point)
    return deduped


def _spacing_ok(gap: int, dist_km: float) -> bool:
    if gap <= 0 or gap > 50 or dist_km > 0.9:
        return False
    meters = dist_km * 1000 / gap
    return 4 <= meters <= 55


def _along(origin: tuple[int, float, float], nxt: tuple[int, float, float], target: int) -> tuple[float, float] | None:
    """Step from origin toward and beyond, using the spacing of the next known house."""
    gap = nxt[0] - origin[0]
    dist = _km(origin[1], origin[2], nxt[1], nxt[2])
    if not _spacing_ok(abs(gap), dist):
        return None
    delta = target - origin[0]
    if abs(delta) > 12:
        return None
    lat = origin[1] + (nxt[1] - origin[1]) / gap * delta
    lon = origin[2] + (nxt[2] - origin[2]) / gap * delta
    if _km(lat, lon, origin[1], origin[2]) > 0.22:
        return None
    if not in_address_bbox(lat, lon):
        return None
    return round(lat, 6), round(lon, 6)


def interpolate_house(street: str, label: str) -> tuple[float, float] | None:
    """Estimate a missing house from surveyed numbers on the same street.

    Between two known houses the pin is placed in proportion to the number.
    Just past either end it follows the same spacing, for a short distance only.
    """
    span = _label_span(label)
    if not span:
        return None
    target = span[0]
    points = _surveyed_houses(street)
    if not points:
        return None
    lower = [item for item in points if item[0] < target]
    higher = [item for item in points if item[0] > target]
    if any(item[0] == target for item in points):
        hit = next(item for item in points if item[0] == target)
        return hit[1], hit[2]
    if lower and higher:
        lo = max(lower, key=lambda item: item[0])
        hi = min(higher, key=lambda item: item[0])
        gap = hi[0] - lo[0]
        dist = _km(lo[1], lo[2], hi[1], hi[2])
        if _spacing_ok(gap, dist):
            fraction = (target - lo[0]) / gap
            return (
                round(lo[1] + fraction * (hi[1] - lo[1]), 6),
                round(lo[2] + fraction * (hi[2] - lo[2]), 6),
            )
    if len(points) >= 2 and target < points[0][0]:
        return _along(points[0], points[1], target)
    if len(points) >= 2 and target > points[-1][0]:
        return _along(points[-1], points[-2], target)
    return None


def geocode_house(street: str, label: str) -> tuple[float, float] | None:
    """Berlin house coordinate, cached. None if it isn't a clean match."""
    key = f"{street}|{label}"
    cache = _load_address_cache()
    if key in cache:
        row = cache[key]
        if row.get("ok"):
            return float(row["lat"]), float(row["lon"])
        guessed = interpolate_house(street, label)
        if guessed and in_address_bbox(guessed[0], guessed[1]):
            cache[key] = {"ok": True, "lat": guessed[0], "lon": guessed[1], "via": "interpolated"}
            _save_address_cache()
            print(f"  {street} {label} -> {guessed[0]}, {guessed[1]} (along the street)", flush=True)
            return guessed
        return None

    if "-" in label:
        start, end = label.split("-", 1)
        queries = [f"{street} {start}, Berlin", f"{street} {end}, Berlin"]
    else:
        queries = [f"{street} {label}, Berlin"]
    found: list[dict] = []
    reachable = False
    for query in queries:
        photon = _photon_houses(query)
        matched = [hit for hit in (photon or []) if _house_hit_ok(street, label, hit)]
        if matched:
            found.append(matched[0])
            reachable = True
            continue
        nominatim = _nominatim_houses(query)
        if nominatim is None and photon is None:
            continue
        reachable = True
        for hit in nominatim or []:
            if _house_hit_ok(street, label, hit):
                found.append(hit)
                break
    if not found:
        guessed = interpolate_house(street, label)
        if guessed and in_address_bbox(guessed[0], guessed[1]):
            cache[key] = {"ok": True, "lat": guessed[0], "lon": guessed[1], "via": "interpolated"}
            _save_address_cache()
            print(f"  {street} {label} -> {guessed[0]}, {guessed[1]} (between neighbors)", flush=True)
            return guessed
        if not reachable:
            print(f"  lookup failed, not cached: {street} {label}", flush=True)
            return None
        cache[key] = {"ok": False}
        _save_address_cache()
        print(f"  no house match: {street} {label}", flush=True)
        return None
    if len(found) == 1 or _km(found[0]["lat"], found[0]["lon"], found[1]["lat"], found[1]["lon"]) > 0.25:
        lat, lon = found[0]["lat"], found[0]["lon"]
    else:
        lat = round(sum(hit["lat"] for hit in found) / len(found), 6)
        lon = round(sum(hit["lon"] for hit in found) / len(found), 6)
    cache[key] = {"ok": True, "lat": lat, "lon": lon}
    _save_address_cache()
    print(f"  {street} {label} -> {lat}, {lon}", flush=True)
    return lat, lon


def geocode_corner(street: str, other: str) -> tuple[float, float] | None:
    """Coordinate where two Kiez streets meet. Cached."""
    global _LAST_NOMINATIM
    left, right = sorted((street, other), key=str.casefold)
    key = f"corner|{left}|{right}"
    cache = _load_address_cache()
    if key in cache:
        row = cache[key]
        if not row.get("ok"):
            return None
        return float(row["lat"]), float(row["lon"])
    wait = 1.1 - (time.time() - _LAST_NOMINATIM)
    if wait > 0:
        time.sleep(wait)
    _LAST_NOMINATIM = time.time()
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode(
        {
            "q": f"{street} Ecke {other}, Berlin",
            "format": "json",
            "limit": "3",
            "countrycodes": "de",
            "viewbox": "13.338,52.520,13.395,52.488",
            "bounded": "1",
        }
    )
    hit = None
    try:
        raw, _final = http_get(url, timeout=20, retries=2)
        for row in json.loads(raw.decode("utf-8")) or []:
            lat, lon = float(row["lat"]), float(row["lon"])
            if in_address_bbox(lat, lon):
                hit = (round(lat, 6), round(lon, 6))
                break
    except Exception:
        print(f"  corner lookup failed: {street} / {other}", flush=True)
        return None
    if not hit:
        cache[key] = {"ok": False}
        _save_address_cache()
        print(f"  no corner: {street} / {other}", flush=True)
        return None
    cache[key] = {"ok": True, "lat": hit[0], "lon": hit[1], "via": "corner"}
    _save_address_cache()
    print(f"  {street} / {other} -> {hit[0]}, {hit[1]}", flush=True)
    return hit


def refine_linear_places(text: str, title: str, places: list[dict]) -> list[dict]:
    """Split a street or square pin to a house when the article supports it.

    Spelling variants (Potsdamerstraße / Potsdamer Straße) collapse to the gazetteer
    name. A street pin geocoded kilometers away (often Potsdam) is pulled back to
    the gazetteer point when no house number is clear.
    """
    order: list[str] = []
    by: dict[str, dict] = {}
    handled: set[str] = set()

    def add(item: dict) -> None:
        key = str(item.get("name") or "").strip().casefold()
        if not key:
            return
        if key not in by:
            order.append(key)
            by[key] = item
            return
        if by[key].get("status") != "confirmed" and item.get("status") == "confirmed":
            by[key] = item

    for place in places or []:
        item = dict(place)
        name = str(item.get("name") or "").strip()
        gaz = canonical_linear(name) if item.get("status") == "confirmed" else None
        if not gaz:
            add(item)
            continue
        street = str(gaz.get("name") or name)
        if street.casefold() in handled:
            continue
        handled.add(street.casefold())
        chosen = choose_address(text, street, title)
        hit = geocode_house(street, chosen) if chosen else None
        if hit:
            add(
                {
                    "name": f"{street} {chosen}",
                    "lat": hit[0],
                    "lon": hit[1],
                    "osm_id": None,
                    "status": "confirmed",
                    "via": "address",
                }
            )
            continue
        partner = corner_partner(text, street)
        corner = geocode_corner(street, partner) if partner else None
        if corner:
            add(
                {
                    "name": f"{street} / {partner}",
                    "lat": corner[0],
                    "lon": corner[1],
                    "osm_id": None,
                    "status": "confirmed",
                    "via": "corner",
                }
            )
            continue
        item["name"] = street
        gaz_lat, gaz_lon = gaz.get("lat"), gaz.get("lon")
        lat, lon = item.get("lat"), item.get("lon")
        if gaz_lat is not None and gaz_lon is not None:
            far = (
                lat is None
                or lon is None
                or _km(float(lat), float(lon), float(gaz_lat), float(gaz_lon)) > 2
            )
            if far:
                item["lat"] = gaz_lat
                item["lon"] = gaz_lon
                item["via"] = "gazetteer"
        add(item)
    return [by[key] for key in order]


def guess_places(text: str) -> list[dict]:
    """Gazetteer substring hits + regex street/platz extraction."""
    found = []
    seen: set[str] = set()
    blob = text or ""
    blob_cf = blob.casefold()

    for place in load_gazetteer():
        name = place.get("name")
        if not name:
            continue
        # Case-insensitive; allow ss/ß and straße/strasse variants.
        variants = {
            str(name),
            str(name).replace("ß", "ss"),
            str(name).replace("straße", "strasse"),
            str(name).replace("Straße", "Strasse"),
        }
        if not any(v.casefold() in blob_cf for v in variants if len(v) >= 3):
            continue
        # Skip ultra-short tokens (e.g. HAL) unless spaced as a word.
        if len(str(name)) <= 3:
            if not re.search(rf"(?<!\w){re.escape(str(name))}(?!\w)", blob, flags=re.I):
                continue
        key = _norm_place(str(name))
        if key in seen:
            continue
        seen.add(key)
        # "Spielplatz … an der Luiseninsel" is the playground beside the island,
        # not the Philharmonie mentioned later as a landmark.
        if key == "Luiseninsel" and re.search(r"spielplatz", blob, re.I):
            key = "Spielplatz Luiseninsel"
            if key in seen:
                continue
            seen.add(key)
        found.append(
            {
                "name": key,
                "lat": place.get("lat"),
                "lon": place.get("lon"),
                "osm_id": place.get("osm_id"),
                "status": "auto",
                "via": "gazetteer",
            }
        )

    for match in STREET_RE.findall(blob):
        key = _norm_place(match)
        if key in seen or len(key) < 6:
            continue
        seen.add(key)
        found.append(
            {
                "name": key,
                "lat": None,
                "lon": None,
                "osm_id": None,
                "status": "auto",
                "via": "regex",
            }
        )
    return found


def confirm_places(places: list[dict]) -> list[dict]:
    """Confirm gazetteer hits, or regex geocodes that land in the Kiez bbox."""
    gaz_names = {_norm_place(str(p.get("name") or "")) for p in load_gazetteer() if p.get("name")}
    out = []
    for place in places:
        item = dict(place)
        name = _norm_place(str(item.get("name") or ""))
        item["name"] = name
        lat, lon = item.get("lat"), item.get("lon")
        if lat is None or lon is None:
            out.append(item)
            continue
        if name in gaz_names or item.get("via") == "gazetteer":
            item["status"] = "confirmed"
        elif in_kiez_bbox(float(lat), float(lon)):
            item["status"] = "confirmed"
        out.append(item)
    return out


# Back-compat alias
def confirm_gazetteer_places(places: list[dict]) -> list[dict]:
    return confirm_places(places)


def places_from_text(text: str, *, confirm: bool = True) -> list[dict]:
    places = fill_missing_coords(guess_places(text))
    if confirm:
        places = confirm_places(places)
    return refine_linear_places(text, _md_title(text), places)


def maps_search_url(query: str) -> str:
    q = urllib.parse.quote(f"{query.strip()}, Berlin")
    return f"https://www.google.com/maps/search/?api=1&query={q}"


def maps_embed_url(query: str) -> str:
    q = urllib.parse.quote(f"{query.strip()}, Berlin")
    return f"https://www.google.com/maps?q={q}&hl=en&z=17&output=embed"


def parse_google_maps_url(url: str) -> tuple[float, float] | None:
    text = (url or "").strip()
    if not text:
        return None
    patterns = [
        r"@(-?\d+\.\d+),(-?\d+\.\d+)",
        r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)",
        r"[?&](?:q|query|ll)=(-?\d+\.\d+),(-?\d+\.\d+)",
        r"/dir/(-?\d+\.\d+),(-?\d+\.\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, text)
        if not m:
            continue
        lat, lon = float(m.group(1)), float(m.group(2))
        if abs(lat) <= 90 and abs(lon) <= 180:
            return round(lat, 6), round(lon, 6)
    return None


def resolve_maps_url(url: str) -> tuple[float, float] | None:
    hit = parse_google_maps_url(url)
    if hit:
        return hit
    text = (url or "").strip()
    if "goo.gl" not in text and "maps.app.goo.gl" not in text:
        return None
    try:
        _body, final = http_get(text, timeout=12, retries=2)
        return parse_google_maps_url(final)
    except Exception:
        return None


def parse_typed_coords(query: str) -> tuple[float, float] | None:
    m = re.match(r"^\s*(-?\d+\.\d+)\s*,\s*(-?\d+\.\d+)\s*$", query or "")
    if not m:
        return None
    lat, lon = float(m.group(1)), float(m.group(2))
    if abs(lat) <= 90 and abs(lon) <= 180:
        return round(lat, 6), round(lon, 6)
    return None


def _nominatim(query: str, limit: int) -> list[dict]:
    url = (
        "https://nominatim.openstreetmap.org/search?"
        + urllib.parse.urlencode(
            {
                "q": query,
                "format": "json",
                "limit": str(limit),
                "countrycodes": "de",
            }
        )
    )
    try:
        raw, _ = http_get(url, timeout=12, retries=2)
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return []
    out = []
    for row in data or []:
        name = row.get("display_name") or query
        out.append(
            {
                "name": name.split(",")[0].strip() or query,
                "label": name,
                "lat": round(float(row["lat"]), 6),
                "lon": round(float(row["lon"]), 6),
            }
        )
    return out


def _photon(query: str, limit: int) -> list[dict]:
    url = (
        "https://photon.komoot.io/api/?"
        + urllib.parse.urlencode(
            {
                "q": query,
                "limit": str(limit),
                "lang": "de",
                "lat": "52.5047",
                "lon": "13.3615",
            }
        )
    )
    try:
        raw, _ = http_get(url, timeout=12, retries=2)
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        return []
    out = []
    for feat in (data or {}).get("features") or []:
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or []
        if len(coords) < 2:
            continue
        props = feat.get("properties") or {}
        street = " ".join(
            str(p) for p in (props.get("street"), props.get("housenumber")) if p
        )
        name = props.get("name") or street or query
        label = ", ".join(
            str(p) for p in (name, props.get("city") or "Berlin") if p
        )
        out.append(
            {
                "name": name,
                "label": label,
                "lat": round(float(coords[1]), 6),
                "lon": round(float(coords[0]), 6),
            }
        )
    return out


def search_places(query: str, limit: int = 5) -> list[dict]:
    q = (query or "").strip()
    if not q:
        return []
    typed = parse_typed_coords(q)
    if typed:
        lat, lon = typed
        return [{"name": q, "label": q, "lat": lat, "lon": lon}]
    hits = _nominatim(f"{q}, Berlin, Germany", limit)
    if not hits:
        hits = _nominatim(q, limit)
    if not hits:
        hits = _photon(f"{q}, Berlin", limit)
    if not hits:
        hits = _photon(q, limit)
    return hits[:limit]


def geocode_berlin(name: str) -> tuple[float, float] | None:
    hits = search_places(name, limit=1)
    if not hits:
        return None
    return hits[0]["lat"], hits[0]["lon"]


def fill_missing_coords(places: list[dict]) -> list[dict]:
    out = []
    for place in places:
        item = dict(place)
        if item.get("lat") is None or item.get("lon") is None:
            hit = geocode_berlin(str(item.get("name") or ""))
            if hit:
                item["lat"], item["lon"] = hit
        out.append(item)
    return out


_ABOUT_YEAR_RE = re.compile(r"\b((?:1[7-9]|20)\d{2})\b")


def extract_about_years(text: str, publish_date: str) -> list[int]:
    """Past years the article is about (not the publish year / last-year asides)."""
    pub = (publish_date or "").strip()
    pub_y = int(pub[:4]) if len(pub) >= 4 and pub[:4].isdigit() else 2100
    found: set[int] = set()
    for match in _ABOUT_YEAR_RE.finditer(text or ""):
        year = int(match.group(1))
        if year < 1700 or year >= pub_y:
            continue
        if year < 2000 or year <= pub_y - 10:
            found.add(year)
    return sorted(found)


def description_from_text(text: str, limit: int = 220) -> str:
    """Short plain-text hint for the map. Not the article."""
    lines = []
    for line in (text or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("!["):
            continue
        s = re.sub(r"!\[([^\]]*)\]\([^)]+\)", "", s)
        s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
        lines.append(s)
    blob = re.sub(r"\s+", " ", " ".join(lines)).strip()
    if len(blob) <= limit:
        return blob
    cut = blob[: limit - 1].rsplit(" ", 1)[0]
    return (cut or blob[: limit - 1]).rstrip(".,;:") + "…"


def write_meta(folder: Path, meta: dict) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "meta.yaml").write_text(
        yaml.safe_dump(meta, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def load_meta(folder: Path) -> dict | None:
    path = folder / "meta.yaml"
    if not path.exists():
        return None
    meta = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    meta["_folder"] = folder
    meta["slug"] = meta.get("slug") or folder.name
    return meta


def list_articles() -> list[dict]:
    items = []
    for folder in iter_article_dirs():
        meta = load_meta(folder)
        if meta:
            items.append(meta)
    items.sort(key=lambda m: str(m.get("date") or ""), reverse=True)
    return items


def tag_book() -> dict[str, dict]:
    path = ROOT / "tags.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    book = {}
    for row in data.get("tags") or []:
        tag_id = str(row.get("id") or "").strip()
        if tag_id:
            book[tag_id] = row
    return book


def season_book() -> dict[str, dict]:
    path = ROOT / "tags.yaml"
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    book = {}
    for row in data.get("seasons") or []:
        season_id = str(row.get("id") or "").strip()
        if season_id:
            book[season_id] = row
    return book


ISSUE_PUBLISHED = {
    "48": {"year": 2025, "label": "Frühling 2025"},
    "49": {"year": 2025, "label": "Sommer 2025"},
    "50": {"year": 2025, "label": "Winter 2025"},
    "51": {"year": 2026, "label": "Frühling 2026"},
}


def article_time(meta: dict) -> dict:
    raw = meta.get("time") or {}
    issue = str(meta.get("issue") or (meta.get("source") or {}).get("issue") or "")
    published = ISSUE_PUBLISHED.get(issue, {})
    written_year = raw.get("written_year") or published.get("year")
    written_label = raw.get("written_label") or published.get("label")
    about_start = raw.get("about_start")
    about_end = raw.get("about_end")
    about_label = raw.get("about_label")
    historical = "geschichte" in (meta.get("tags") or [])
    return {
        "written_year": None if written_year is None else int(written_year),
        "written_label": written_label,
        "about_start": None if about_start is None else int(about_start),
        "about_end": None if about_end is None else int(about_end),
        "about_label": about_label,
        "historical": historical,
    }


def article_when(meta: dict) -> dict:
    raw = meta.get("when") or {}
    seasons = [str(item) for item in (raw.get("seasons") or [])]
    book = season_book()
    return {
        "seasonal": bool(raw.get("seasonal")),
        "event": bool(raw.get("event")),
        "recurring": bool(raw.get("recurring")),
        "seasons": seasons,
        "season_labels": [str((book.get(item) or {}).get("de") or item) for item in seasons],
    }


def tag_labels(tag_ids: list) -> list[str]:
    book = tag_book()
    labels = []
    for raw in tag_ids or []:
        row = book.get(str(raw))
        labels.append(str(row.get("de") if row else raw))
    return labels


def _fold_text(text: str) -> str:
    s = (text or "").lower()
    return (
        s.replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )


TAG_HINTS = {
    "kunst-kultur": (
        "kunst",
        "kultur",
        "galerie",
        "malschule",
        "kuenstler",
        "künstler",
        "buchkunst",
        "ausstellung",
        "illustration",
        "frontview",
    ),
    "restaurant-essen": (
        "restaurant",
        "mittagstisch",
        "omakase",
        "brunch",
        "gastronomie",
        "kneipe",
        "cafe",
        "café",
        "kaffee",
        "wintergarten",
        "koch",
        "speisen",
        "imbiss",
    ),
    "laden": (
        "woolworth",
        "antiquariat",
        "apotheke",
        "geschaeft",
        "spati",
        "spaeti",
        "mode ",
        "buchhandlung",
        "laden",
    ),
    "geschichte": (
        "geschichte",
        "historisch",
        "kolonial",
        "stolperstein",
        "stolpersteine",
        "reichstag",
        "weltkrieg",
        "juedisch",
        "jüdisch",
        "synagoge",
    ),
    "kinder": (
        "kinder",
        "spielplatz",
        "kita",
        "schule",
        "kinderzimmer",
        "spiel",
    ),
    "nachbarschaft": (
        "nachbarschaft",
        "stadtteilverein",
        "obdachlos",
        "engagement",
        "nachbarn",
    ),
    "kirche": ("kirche", "pfarr", "gemeinde", "synagoge"),
    "park": ("spielplatz", "gleisdreieck", "volkspark", "tiergarten park", "gartenrestaurant"),
    "gruen": ("gruenflaeche", "grünfläche", "baeume", "bäume", "klima", "gruenzug"),
    "musik": ("musik", "konzert", "orchester", "chor"),
    "film": ("film", "kino", "kintopp", "grenzkino"),
    "stadt": (
        "u-bahn",
        "ubahn",
        "bahnhof",
        "wohnraum",
        "gentrifizierung",
        "bauen",
        "wohnung",
    ),
    "gesundheit": ("apotheke", "gesundheit", "arzt", "barriere", "pflege", "bad ", "baeder", "bäder"),
}


def guess_tags(text: str) -> list[str]:
    blob = _fold_text(text)
    hits = []
    for tag_id, needles in TAG_HINTS.items():
        for needle in needles:
            n = _fold_text(needle).strip()
            if len(n) < 4:
                continue
            if re.search(rf"(^|[^a-z0-9]){re.escape(n)}([^a-z0-9]|$)", blob):
                hits.append(tag_id)
                break
            if len(n) >= 6 and n in blob:
                hits.append(tag_id)
                break
    return hits


def article_guess_blob(meta: dict) -> str:
    folder: Path = meta["_folder"]
    parts = [str(meta.get("title") or ""), str(meta.get("slug") or "")]
    de = folder / "de.md"
    if de.exists():
        parts.append(de.read_text(encoding="utf-8")[:3500])
    elif meta.get("description"):
        parts.append(str(meta.get("description")))
    return "\n".join(parts)


def set_article_tags(slug: str, tag_ids: list) -> dict:
    meta = find_article(slug)
    if not meta:
        raise FileNotFoundError(slug)
    folder: Path = meta["_folder"]
    book = tag_book()
    clean = []
    seen = set()
    for raw in tag_ids or []:
        tag_id = str(raw).strip()
        if tag_id in book and tag_id not in seen:
            seen.add(tag_id)
            clean.append(tag_id)
    meta["tags"] = clean
    write_meta(folder, {k: v for k, v in meta.items() if not str(k).startswith("_")})
    return article_public(load_meta(folder), include_text=True)


def article_public(meta: dict, include_text: bool = False) -> dict:
    folder: Path = meta["_folder"]
    clip = next((n for n in ("clip.png", "clip.jpg", "hero.jpg", "hero.png") if (folder / n).exists()), None)
    out = {
        "title": meta.get("title") or meta["slug"],
        "slug": meta["slug"],
        "date": None if meta.get("date") is None else str(meta.get("date")),
        "issue": meta.get("issue"),
        "author": meta.get("author"),
        "rubrik": meta.get("rubrik"),
        "source_url": meta.get("source_url"),
        "wp_post_id": meta.get("wp_post_id"),
        "text_origin": meta.get("text_origin") or ("wp" if meta.get("wp_post_id") else "ocr"),
        "sample": bool(meta.get("sample")),
        "tags": list(meta.get("tags") or []),
        "tag_labels": tag_labels(meta.get("tags") or []),
        "tags_guessed": [],
        "themes": [],
        "theme_labels": [],
        "theme_guessed": False,
        "when": article_when(meta),
        "time": article_time(meta),
        "places": meta.get("places") or [],
        "source": meta.get("source") or {},
        "clip": f"/articles/{folder.relative_to(ARTICLES).as_posix()}/{clip}" if clip else None,
        "has_clip": bool(clip),
    }
    saved = [str(t) for t in (out["tags"] or []) if t]
    guessed = guess_tags(article_guess_blob(meta))
    themes = saved or guessed
    out["tags"] = saved
    out["tag_labels"] = tag_labels(saved)
    out["tags_guessed"] = guessed
    out["themes"] = themes
    out["theme_labels"] = tag_labels(themes)
    out["theme_guessed"] = not saved and bool(guessed)
    if include_text:
        de = folder / "de.md"
        en = folder / "en.md"
        out["de"] = de.read_text(encoding="utf-8") if de.exists() else ""
        out["en"] = en.read_text(encoding="utf-8") if en.exists() else ""
    return out


def find_article(slug: str) -> dict | None:
    for folder in iter_article_dirs():
        meta = load_meta(folder)
        if meta and (meta.get("slug") == slug or folder.name == slug):
            return meta
    return None


def clips_for_issue(issue: str) -> list[dict]:
    out = []
    for meta in list_articles():
        src = meta.get("source") or {}
        if str(src.get("issue") or "") != str(issue):
            continue
        boxes = src.get("boxes") if isinstance(src.get("boxes"), list) else None
        pieces = []
        if boxes:
            for item in boxes:
                if not isinstance(item, dict):
                    continue
                box = item.get("box")
                page = item.get("page") or src.get("page")
                if box and page:
                    pieces.append({"page": page, "box": box})
        elif src.get("box") and src.get("page"):
            pieces.append({"page": src.get("page"), "box": src.get("box")})
        for piece in pieces:
            out.append(
                {
                    "slug": meta["slug"],
                    "title": meta.get("title") or meta["slug"],
                    "page": piece["page"],
                    "box": piece["box"],
                }
            )
    return out


def geojson(include_auto: bool = True) -> dict:
    features = []
    for meta in list_articles():
        public = article_public(meta)
        for place in public["places"]:
            status = place.get("status")
            if status == "confirmed" or (include_auto and status == "auto"):
                if place.get("lat") is None or place.get("lon") is None:
                    continue
                features.append(
                    {
                        "type": "Feature",
                        "geometry": {
                            "type": "Point",
                            "coordinates": [float(place["lon"]), float(place["lat"])],
                        },
                        "properties": {
                            "title": public["title"],
                            "place": place.get("name") or "",
                            "status": status,
                            "slug": public["slug"],
                            "tags": public["tags"],
                            "tag_labels": public["tag_labels"],
                            "when": public["when"],
                            "time": public["time"],
                            "url": f"article.html?slug={public['slug']}",
                        },
                    }
                )
    return {"type": "FeatureCollection", "features": features}


def upsert_place(slug: str, name: str, lat: float | None, lon: float | None, status: str) -> dict:
    meta = find_article(slug)
    if not meta:
        raise FileNotFoundError(slug)
    folder: Path = meta["_folder"]
    places = list(meta.get("places") or [])
    match = None
    for place in places:
        if place.get("name") == name:
            match = place
            break
    if match is None:
        match = {"name": name, "lat": None, "lon": None, "osm_id": None, "status": status}
        places.append(match)
    if lat is not None and lon is not None:
        match["lat"] = round(float(lat), 6)
        match["lon"] = round(float(lon), 6)
    elif match.get("lat") is None or match.get("lon") is None:
        hit = geocode_berlin(name)
        if hit:
            match["lat"], match["lon"] = hit
    match["status"] = status
    meta["places"] = places
    clean = {k: v for k, v in meta.items() if not str(k).startswith("_")}
    write_meta(folder, clean)
    return article_public(load_meta(folder), include_text=True)
