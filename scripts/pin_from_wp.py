"""Detect / confirm map pins from the live WP post (or a leftover de.md)."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from articles_lib import (  # noqa: E402
    confirm_gazetteer_places,
    fill_missing_coords,
    geocode_berlin,
    guess_places,
    load_gazetteer,
    load_meta,
    refine_linear_places,
    write_meta,
)
import articles_lib  # noqa: E402
from fetch_wp import article_plaintext  # noqa: E402

ARTICLES = ROOT / "articles"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--all-origins", action="store_true", help="Include OCR folders too")
    p.add_argument("--sleep", type=float, default=1.1, help="Pause between geocode calls")
    args = p.parse_args()
    wp_only = not args.all_origins

    if args.sleep > 0:
        _orig = geocode_berlin

        def _slow(name: str):
            time.sleep(args.sleep)
            return _orig(name)

        articles_lib.geocode_berlin = _slow

    updated = 0
    pins = 0
    for meta_path in sorted(ARTICLES.rglob("meta.yaml")):
        folder = meta_path.parent
        meta = load_meta(folder)
        if not meta:
            continue
        origin = meta.get("text_origin") or ("wp" if meta.get("wp_post_id") else "ocr")
        if wp_only and origin != "wp":
            continue
        text = article_plaintext(folder, meta)
        if not text.strip():
            continue
        guessed = guess_places(text)
        old = {str(x.get("name")): x for x in (meta.get("places") or [])}
        for g in guessed:
            name = str(g.get("name") or "")
            if g.get("lat") is None and name in old and old[name].get("lat") is not None:
                g["lat"] = old[name]["lat"]
                g["lon"] = old[name]["lon"]
        places = confirm_gazetteer_places(fill_missing_coords(guessed))
        by_name = {str(x.get("name")): x for x in places}
        gaz = {str(p.get("name")) for p in load_gazetteer() if p.get("name")}
        for place in meta.get("places") or []:
            if place.get("status") != "confirmed":
                continue
            name = str(place.get("name") or "")
            # Drop junk leftover pins (bare numbers, OCR debris); keep gazetteer names.
            if name in by_name:
                continue
            if name in gaz or (len(name) >= 6 and not name.isdigit() and "http" not in name):
                by_name[name] = place
        merged = list(by_name.values())
        # Strip known garbage short tokens
        merged = [
            p
            for p in merged
            if len(str(p.get("name") or "")) >= 4 and not str(p.get("name")).isdigit()
        ]
        merged = refine_linear_places(text, str(meta.get("title") or ""), merged)
        meta["places"] = merged
        write_meta(folder, {k: v for k, v in meta.items() if not str(k).startswith("_")})
        conf = sum(1 for x in merged if x.get("status") == "confirmed")
        pins += conf
        updated += 1
        print(f"{folder.relative_to(ROOT)}: {conf} confirmed / {len(merged)} places")
    print(f"updated {updated} articles, {pins} confirmed pins total")


if __name__ == "__main__":
    main()
