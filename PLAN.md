# Plan

Durable strategy for mittendran-archiv. Operator how-to lives in `README.md`.

## Product

**GitHub Pages is the thing:** a German-language map and place index for mitteNdran articles on [mittendran.de](https://www.mittendran.de/). Always link to the original. Git stores a short description and the fields the map sorts and filters on, not the article text.

English translation is **later**. **No PDF pipeline** — print PDFs / OCR are removed from this repo.

## Source model

| Tier | Source | Role |
|------|--------|------|
| **Only** | mittendran.de WordPress REST API | Capture posts into `articles/` |

## Publish rules (Pages)

- Publish `text_origin: wp` only.
- Map, place pages, and area lists link to **mittendran.de**. No copied article pages.
- Site language: **German**.
- Map: confirmed places from the WP text at import time; pins and lists link to the original post.

## Website-first loop

```
python3 scripts/fetch_wp.py --all --after YYYY-MM-DD --before YYYY-MM-DD
python3 scripts/pin_sweep.py --write     # missing pins: gazetteer + street regex + geocode
python3 scripts/build.py
```

Map popups show title, place, short description; click opens the original post.

Blog posts are not a 1:1 Heft TOC. For a print “Ausgabe”, import the **date window** around that issue.

## Data layout (folders, not a SQL database)

Git Markdown folders **are** the database. That fits Pages + diffs + backups.

| Path | Role |
|------|------|
| `articles/web/<date>__<wp-slug>/` | Default bucket for blog imports (sorted by date in the filename) |
| `articles/<issue>/…` | Optional Heft label when importing a date window |
| `docs/` | Generated static site (do not hand-edit) |
| `gazetteer/streets.yaml` | Curated place dictionary for pin detection |
| `tags.yaml` | Topic ids |

Browse order on the site = **newest date first**. Filter later via rubrik/tags in `meta.yaml` (index JSON), not by inventing a second DB.

**When a real DB would help:** full-text search across 2600+ posts, complex queries. Not needed for v1 Pages archive.

## Article folder contract

```
articles/web/<date>__<wp-slug>/   # or articles/<issue>/ when labeled
  meta.yaml      # description + about_years scraped at import; no full text
  hero.jpg       # optional, not published
```

| Field | Meaning |
|-------|---------|
| `title`, `slug`, `date`, `author`, `rubrik` | From WP. Date sorts the map; rubrik colors and filters it |
| `description` | Short plain-text hint scraped at import |
| `about_years` | Past years found in the post, for the history filter |
| `issue` | Optional Heft label |
| `source_url` | Canonical mittendran.de URL |
| `wp_post_id` | WordPress post id |
| `text_origin` | `wp` (or `sample`) |
| `tags` | ids from `tags.yaml` |
| `places[]` | map pins; `status: confirmed` only |

## Done

- Soft reboot: WP primary, German Pages, map from web text.
- **PDF purge:** deleted `local/pdfs`, page rasters, ~101 OCR article folders, and scripts `ingest` / `from_clip` / `ocr_translate` / `fetch_issue_pdfs` / `rebuild_article_text`.

## Next

- [x] Batch-import underway (~1200 of ~2600 WP posts in repo / on `docs/`).
- [ ] First git commit (local) — staged, needs user identity.
- [ ] Push remote + enable GitHub Pages on `/docs`.
- [ ] Continue `--all --max N` until corpus is complete (~1400 still missing).
- [ ] Pin quality pass (gazetteer / bad geocodes); ~317 articles still pinless.
- [ ] English later.

## Non-goals

- PDF download, OCR, crop UI.
- Second database or CMS.
- Waiting on English before publishing.
