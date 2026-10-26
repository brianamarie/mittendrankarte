"""Fill lat/lon on places that are still empty. Does not confirm them for the map."""
from __future__ import annotations

from pathlib import Path

import yaml
from geopy.extra.rate_limiter import RateLimiter
from geopy.geocoders import Nominatim

ROOT = Path(__file__).resolve().parents[1]
ARTICLES = ROOT / "articles"


def main() -> None:
    geolocator = Nominatim(user_agent="mittendran-archiv/0.1 (local archive)")
    geocode = RateLimiter(geolocator.geocode, min_delay_seconds=1.1)
    for meta_path in sorted(ARTICLES.rglob("meta.yaml")):
        if not meta_path.exists():
            continue
        meta = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
        changed = False
        for place in meta.get("places") or []:
            if place.get("lat") is not None and place.get("lon") is not None:
                continue
            q = f"{place.get('name')}, Berlin, Germany"
            loc = geocode(q, exactly_one=True, timeout=10)
            if not loc:
                print(f"no hit: {q}")
                continue
            place["lat"] = round(loc.latitude, 6)
            place["lon"] = round(loc.longitude, 6)
            place["status"] = place.get("status") or "auto"
            changed = True
            print(f"{q} -> {place['lat']}, {place['lon']}")
        if changed:
            meta_path.write_text(
                yaml.safe_dump(meta, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )


if __name__ == "__main__":
    main()
