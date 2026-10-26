"""Smart pin sweep: find missing places in the live post (or a leftover de.md), geocode, report coverage.

Usage:
  python3 scripts/pin_sweep.py              # report only
  python3 scripts/pin_sweep.py --write      # update meta.yaml for articles lacking pins
  python3 scripts/pin_sweep.py --write --all  # refresh all WP articles
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from articles_lib import (  # noqa: E402
    ARTICLES,
    geocode_berlin,
    load_meta,
    places_from_text,
    refine_linear_places,
    write_meta,
)
import articles_lib  # noqa: E402
from fetch_wp import article_plaintext  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--write", action="store_true", help="Write places into meta.yaml")
    p.add_argument("--all", action="store_true", help="Resweep even if pins already exist")
    p.add_argument("--sleep", type=float, default=1.05, help="Geocode pause (Nominatim)")
    p.add_argument("--limit", type=int, default=0, help="Max articles to write (0 = no limit)")
    args = p.parse_args()

    if args.sleep > 0:
        _orig = geocode_berlin

        def _slow(name: str):
            time.sleep(args.sleep)
            return _orig(name)

        articles_lib.geocode_berlin = _slow

    total = missing = written = gained = 0
    for meta_path in sorted(ARTICLES.rglob("meta.yaml")):
        meta = load_meta(meta_path.parent)
        if not meta or meta.get("text_origin") != "wp":
            continue
        total += 1
        conf = [
            x
            for x in (meta.get("places") or [])
            if x.get("status") == "confirmed" and x.get("lat") is not None
        ]
        if conf and not args.all:
            continue
        missing += 1
        text = article_plaintext(meta_path.parent, meta)
        if not text.strip():
            continue
        places = places_from_text(text, confirm=True)
        new_conf = [x for x in places if x.get("status") == "confirmed" and x.get("lat") is not None]
        print(
            f"{meta_path.parent.relative_to(ROOT)}: "
            f"{len(conf)} → {len(new_conf)} pins "
            f"({', '.join(x['name'] for x in new_conf[:5])})",
            flush=True,
        )
        if not args.write:
            continue
        if args.limit and written >= args.limit:
            break
        # Keep prior confirmed names not rediscovered
        by = {str(x.get("name")): x for x in places}
        for old in conf:
            name = str(old.get("name") or "")
            if name and name not in by:
                by[name] = old
        meta["places"] = refine_linear_places(
            text, str(meta.get("title") or ""), list(by.values())
        )
        write_meta(meta_path.parent, {k: v for k, v in meta.items() if not str(k).startswith("_")})
        written += 1
        gained += max(0, len(new_conf) - len(conf))

    mode = "WRITE" if args.write else "DRY-RUN"
    print(
        f"[{mode}] wp={total} needing_sweep={missing} "
        f"written={written} pin_gain~={gained}",
        flush=True,
    )
    if not args.write:
        print("Re-run with --write to save. Then: python3 scripts/build.py", flush=True)


if __name__ == "__main__":
    main()
