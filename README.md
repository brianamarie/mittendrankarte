# mittendran-archiv

Unabhängiges **deutsches Textarchiv** (+ Karte) für Beiträge von [mittendran.de](https://www.mittendran.de/).

Produkt = GitHub Pages unter `docs/`: Karte, Ortsseiten und Bereichslisten. Der Beitragstext bleibt auf [mittendran.de](https://www.mittendran.de/); hier liegen Titel, Datum, Rubrik, Ort, ein kurzer Hinweis und der Link. **Kein PDF/OCR.** Strategie: [PLAN.md](PLAN.md).

## Import & bauen

```
python3 scripts/fetch_wp.py --url https://www.mittendran.de/zehn-neue-stolpersteine/
python3 scripts/fetch_wp.py --all --max 50
python3 scripts/fetch_wp.py --all --after 2026-05-01 --before 2026-07-01 --issue 51
python3 scripts/pin_sweep.py --write    # fehlende Orte aus dem Text
python3 scripts/build.py
```

Öffne `docs/index.html` (oder `python3 -m http.server` in `docs/`).

## Dateien = Datenbank

Kein SQL. Jeder Beitrag ist ein Ordner unter `articles/web/<datum>__<slug>/` (oder `articles/<heft>/…`). Die Site listet **neueste zuerst**. `meta.yaml` hält, was die Karte zum Sortieren und Filtern braucht (Datum, Rubrik, Orte, Kurzbeschreibung, Jahre im Text, Link). Der volle Beitragstext wird nicht gespeichert.

## Artikelordner

```
articles/web/2025-11-06__zehn-neue-stolpersteine/
  meta.yaml      # title, date, rubrik, description, about_years, source_url, places
  hero.jpg       # optional, nicht Teil der öffentlichen Seite
```

## Karte

Pins zeigen Vorschau-Text; Klick auf die Karte/Popup öffnet den Archiv-Beitrag.

```
python3 scripts/pin_sweep.py           # Report
python3 scripts/pin_sweep.py --write   # speichern
python3 scripts/build.py
```

http://127.0.0.1:8765/map.html (wenn `python3 -m http.server` in `docs/` läuft).

## Credit

mitteNdran ist ein ehrenamtliches Kiezmagazin (mitteNdran e.V.). Dieses Projekt ist ein unabhängiges Archiv-Hilfsmittel, keine offizielle Seite.
