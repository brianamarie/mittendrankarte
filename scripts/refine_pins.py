"""Split street and square pins to a house number when the article is about one building.

A walking tour that names several houses stays on the street. A pin geocoded in the
wrong city is pulled back to the gazetteer point.

Usage:
  python3 scripts/refine_pins.py            # self-check, then report (no meta writes)
  python3 scripts/refine_pins.py --write    # update meta.yaml
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from articles_lib import (  # noqa: E402
    ARTICLES,
    choose_address,
    load_meta,
    refine_linear_places,
    write_meta,
)
from fetch_wp import article_plaintext  # noqa: E402


def _check() -> None:
    samples = [
        ("in der Lützowstraße 74 wurde ein Bad gebaut", "", "74"),
        ("Lützowstraße 74a ist offen", "", "74a"),
        ("das Haus Lützowstraße 89/90", "", "89-90"),
        ("heute Lützowstr. 27", "", "27"),
        ("nur die Lützowstraße ohne Nummer", "", None),
        ("Lützowstraße 74 wurde eröffnet", "", "74"),
        ("Potsdamerstraße 29 steht leer", "", "29"),
        ("Genthiner Straße 5a", "", "5a"),
    ]
    for text, title, expect in samples:
        street = "Potsdamer Straße" if "Potsdamer" in text else "Lützowstraße"
        if "Genthiner" in text:
            street = "Genthiner Straße"
        got = choose_address(text, street, title)
        if got != expect:
            raise SystemExit(f"choose_address failed: {text!r} -> {got!r}, expected {expect!r}")
    late = ("wort " * 400) + " Lützowstraße 50 am Ende"
    if choose_address(late, "Lützowstraße", "") != "50":
        raise SystemExit("a single house number should be used even late in the text")
    lead = "Lützowstraße 50 liegt hier. " + ("wort " * 400)
    if choose_address(lead, "Lützowstraße", "") != "50":
        raise SystemExit("a house number in the opening should be used")
    body = "Lützowstraße 74 und später Lützowstraße 89 und Lützowstraße 10"
    got = choose_address(body, "Lützowstraße", "Eine Solequelle in der Lützowstraße 74")
    if got != "74":
        raise SystemExit(f"title should win, got {got!r}")
    mixed = "Lützowstraße 10 und Lützowstraße 12 im selben Absatz"
    if choose_address(mixed, "Lützowstraße", "") != "10":
        raise SystemExit("the first of two houses should be the estimate")
    print("self-check ok", flush=True)


def _sig(places: list[dict]) -> list[tuple]:
    rows = []
    for place in places or []:
        lat, lon = place.get("lat"), place.get("lon")
        rows.append(
            (
                place.get("name"),
                None if lat is None else round(float(lat), 6),
                None if lon is None else round(float(lon), 6),
                place.get("status"),
                place.get("via"),
            )
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Write places into meta.yaml")
    args = parser.parse_args()
    _check()

    moved = snapped = written = 0
    examples: list[str] = []
    for meta_path in sorted(ARTICLES.rglob("meta.yaml")):
        meta = load_meta(meta_path.parent)
        if not meta or meta.get("sample"):
            continue
        if meta.get("text_origin") != "wp" or not meta.get("source_url"):
            continue
        text = article_plaintext(meta_path.parent, meta)
        if not text.strip():
            continue
        old = list(meta.get("places") or [])
        new = refine_linear_places(text, str(meta.get("title") or ""), old)
        if _sig(new) == _sig(old):
            continue
        old_names = {str(p.get("name") or "") for p in old if p.get("status") == "confirmed"}
        new_names = {str(p.get("name") or "") for p in new if p.get("status") == "confirmed"}
        gained = sorted(new_names - old_names)
        lost = sorted(old_names - new_names)
        for name in gained:
            if any(ch.isdigit() for ch in name):
                moved += 1
        if any(name in old_names and name not in new_names for name in lost):
            pass
        if gained or lost:
            if any("gazetteer" == p.get("via") and p.get("name") in old_names for p in new):
                snapped += 1
        if len(examples) < 12 and gained:
            examples.append(
                f"{meta.get('title')}: {', '.join(lost) or '—'} → {', '.join(gained)}"
            )
        if not args.write:
            continue
        clean = {k: v for k, v in meta.items() if not str(k).startswith("_")}
        clean["places"] = new
        write_meta(meta_path.parent, clean)
        written += 1

    mode = "WRITE" if args.write else "DRY-RUN"
    print(f"[{mode}] address_pins={moved} articles_rewritten={written}", flush=True)
    for line in examples:
        print(" ", line, flush=True)
    if not args.write:
        print("Re-run with --write to save. Then: python3 scripts/build.py", flush=True)


if __name__ == "__main__":
    main()
