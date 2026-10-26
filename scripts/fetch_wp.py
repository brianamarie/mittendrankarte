"""Fetch articles from mittendran.de (WordPress REST) into articles/ folders."""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from articles_lib import (  # noqa: E402
    ARTICLES,
    http_get,
    issue_dirname,
    load_meta,
    description_from_text,
    extract_about_years,
    places_from_text,
    slugify,
    unique_slug,
    write_meta,
)

API = "https://www.mittendran.de/wp-json/wp/v2"
UA = "mittendran-archiv/0.2 (+local archive helper)"

SERIES = {
    "spaziergang": {
        "search": "Spaziergang in die Vergangenheit",
        "slug_prefix": "spaziergang-in-die-vergangenheit",
    },
    "juedische": {
        "search": "Jüdische Geschichte im Lützow-Viertel",
        "slug_prefix": "juedische-geschichte-im-luetzow-viertel",
    },
    "kiez-geschichte": {
        "category": 5528,
        "search": None,
        "slug_prefix": None,
    },
}


class _HTMLToMarkdown(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0
        self._in_pre = False
        self._href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = dict(attrs)
        if tag in {"script", "style", "noscript"}:
            self._skip += 1
            return
        if self._skip:
            return
        if tag in {"p", "div", "section", "article", "br", "hr"}:
            self.parts.append("\n\n")
        elif tag in {"h1", "h2", "h3", "h4"}:
            self.parts.append("\n\n")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag == "a":
            self._href = ad.get("href")
        elif tag == "img":
            alt = (ad.get("alt") or "").strip()
            src = (ad.get("src") or "").strip()
            if alt and src:
                self.parts.append(f"\n\n![{alt}]({src})\n\n")
            elif src:
                self.parts.append(f"\n\n![]({src})\n\n")
        elif tag == "pre":
            self._in_pre = True
            self.parts.append("\n\n```\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style", "noscript"}:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag in {"p", "div", "section", "article", "h1", "h2", "h3", "h4", "ul", "ol"}:
            self.parts.append("\n\n")
        elif tag == "a" and self._href:
            self.parts.append(f" ({self._href})")
            self._href = None
        elif tag == "pre":
            self._in_pre = False
            self.parts.append("\n```\n\n")

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._in_pre:
            self.parts.append(data)
            return
        text = re.sub(r"[ \t]+", " ", data)
        if text.strip():
            self.parts.append(text)

    def text(self) -> str:
        raw = "".join(self.parts)
        raw = html.unescape(raw)
        raw = re.sub(r"\n{3,}", "\n\n", raw)
        return raw.strip()


def html_to_markdown(fragment: str) -> str:
    parser = _HTMLToMarkdown()
    parser.feed(fragment or "")
    parser.close()
    return parser.text()


def strip_title_html(raw: str) -> str:
    text = re.sub(r"<[^>]+>", "", raw or "")
    return html.unescape(text).strip()


def api_get(path: str, params: dict | None = None) -> tuple[object, dict]:
    qs = urllib.parse.urlencode(params or {}, doseq=True)
    url = f"{API}{path}" + (f"?{qs}" if qs else "")
    body_b, _ = http_get(url, timeout=60, retries=4)
    body = body_b.decode("utf-8", errors="replace")
    # WP total headers are not available via raw GET helper; callers that need
    # X-WP-Total use list pagination until an empty page.
    return json.loads(body), {}


def fetch_post_by_id(post_id: int) -> dict:
    # Do not restrict _fields — WordPress drops _embedded when fields are filtered.
    data, _ = api_get(f"/posts/{post_id}", {"_embed": "1"})
    if not isinstance(data, dict):
        raise SystemExit(f"unexpected post payload for id {post_id}")
    return data


def article_plaintext(folder: Path, meta: dict | None = None) -> str:
    """Text for pin detection. Uses a local de.md if one is still on disk, else the live post."""
    de = folder / "de.md"
    if de.exists():
        text = de.read_text(encoding="utf-8")
        if text.strip():
            return text
    meta = meta or {}
    post_id = meta.get("wp_post_id")
    if not post_id:
        return ""
    post = fetch_post_by_id(int(post_id))
    title = strip_title_html((post.get("title") or {}).get("rendered") or "")
    body_html = (post.get("content") or {}).get("rendered") or ""
    return f"# {title}\n\n{html_to_markdown(body_html)}\n"


def fetch_post_by_slug(slug: str) -> dict:
    data, _ = api_get("/posts", {"slug": slug, "_embed": "1", "per_page": "1"})
    if not isinstance(data, list) or not data:
        raise SystemExit(f"no post with slug {slug!r}")
    return data[0]


def scrape_author_from_page(url: str) -> str | None:
    """WP user REST is often locked; byline is still on the public HTML."""
    if not url:
        return None
    try:
        page = http_get(url, timeout=30, retries=2)[0].decode("utf-8", errors="replace")
    except Exception:
        return None
    patterns = [
        r'class="url fn n"[^>]*>([^<]+)',
        r'rel="author"[^>]*>([^<]+)',
        r'class="author vcard"[^>]*>.*?<a[^>]*>([^<]+)',
    ]
    for pat in patterns:
        m = re.search(pat, page, flags=re.I | re.S)
        if m:
            name = html.unescape(m.group(1)).strip()
            if name:
                return name
    return None


def slug_from_url(url: str) -> str:
    path = urllib.parse.urlparse(url).path.strip("/")
    if not path:
        raise SystemExit(f"cannot parse slug from {url}")
    return path.split("/")[-1]


def resolve_author(post: dict) -> str | None:
    embedded = post.get("_embedded") or {}
    authors = embedded.get("author") or []
    if authors and isinstance(authors[0], dict) and "name" in authors[0]:
        name = (authors[0].get("name") or "").strip()
        if name:
            return name
    return scrape_author_from_page(str(post.get("link") or ""))


def resolve_rubrik(post: dict) -> str | None:
    embedded = post.get("_embedded") or {}
    terms = embedded.get("wp:term") or []
    names: list[str] = []
    for group in terms:
        if not isinstance(group, list):
            continue
        for term in group:
            if not isinstance(term, dict):
                continue
            if term.get("taxonomy") != "category":
                continue
            name = strip_title_html(str(term.get("name") or ""))
            if name and name.lower() != "uncategorized":
                names.append(name)
    # Prefer a specific rubrik over the broad "Aus dem Kiez" bucket.
    for name in names:
        if name.lower() != "aus dem kiez":
            return name
    return names[0] if names else None


def resolve_featured_url(post: dict) -> str | None:
    embedded = post.get("_embedded") or {}
    media = embedded.get("wp:featuredmedia") or []
    if media and isinstance(media[0], dict):
        src = media[0].get("source_url")
        if src:
            return str(src)
    return None


def download(url: str, dest: Path) -> bool:
    # Percent-encode non-ASCII path characters (e.g. © in filenames).
    parts = urllib.parse.urlsplit(url)
    path = urllib.parse.quote(parts.path, safe="/:%")
    safe_url = urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))
    try:
        data, _ = http_get(safe_url, timeout=60, retries=3)
    except Exception as exc:
        print(f"  hero skip: {exc}")
        return False
    if len(data) < 200:
        return False
    dest.write_bytes(data)
    return True


def folder_for_new(post: dict, issue: str | None) -> Path:
    date = str(post.get("date") or "")[:10] or "undated"
    # Prefer the WordPress slug (stable, umlaut-aware) over slugify(title).
    wp_slug = slugify(str(post.get("slug") or "")) or slugify(
        strip_title_html((post.get("title") or {}).get("rendered") or "post")
    )
    base = f"{date}__{wp_slug}"
    if not issue:
        parent = ARTICLES / "web"
        parent.mkdir(parents=True, exist_ok=True)
        taken = {p.name for p in parent.iterdir()} if parent.exists() else set()
        candidate = base
        i = 2
        while candidate in taken or (parent / candidate).exists():
            candidate = f"{base}-{i}"
            i += 1
        return parent / candidate
    slug = unique_slug(base, issue=issue, sample=False)
    return ARTICLES / issue_dirname(issue) / slug


def write_article(
    post: dict,
    *,
    dest: Path | None = None,
    issue: str | None = None,
    keep_places: bool = True,
    keep_tags: bool = True,
    keep_print_source: bool = True,
    refresh_places: bool = False,
) -> Path:
    title = strip_title_html((post.get("title") or {}).get("rendered") or "")
    body_html = (post.get("content") or {}).get("rendered") or ""
    de_body = html_to_markdown(body_html)
    if not title:
        title = (post.get("slug") or "post").replace("-", " ")
    date = str(post.get("date") or "")[:10]
    author = resolve_author(post)
    rubrik = resolve_rubrik(post)
    link = post.get("link") or ""
    post_id = post.get("id")

    existing = load_meta(dest) if dest and dest.exists() else None
    if dest is None:
        dest = folder_for_new(post, issue)
    dest.mkdir(parents=True, exist_ok=True)

    slug = dest.name
    places = list((existing or {}).get("places") or []) if keep_places and existing else []
    if refresh_places or not places:
        places = places_from_text(f"{title}\n{de_body}", confirm=True)
    tags = list((existing or {}).get("tags") or []) if keep_tags and existing else []
    print_source = (existing or {}).get("source") if keep_print_source and existing else None
    issue_val = issue if issue is not None else (existing or {}).get("issue")

    plain = f"{title}\n\n{de_body}"
    description = description_from_text(plain)
    about_years = extract_about_years(plain, date)

    hero_url = resolve_featured_url(post)
    if hero_url:
        ext = Path(urllib.parse.urlparse(hero_url).path).suffix.lower() or ".jpg"
        if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
            ext = ".jpg"
        download(hero_url, dest / f"hero{ext}")

    meta = {
        "title": title,
        "slug": slug,
        "author": author,
        "date": date,
        "issue": issue_val,
        "rubrik": rubrik,
        "description": description,
        "about_years": about_years,
        "source_url": link,
        "wp_post_id": post_id,
        "text_origin": "wp",
        "sample": bool((existing or {}).get("sample")),
        "tags": tags,
        "source": print_source if isinstance(print_source, dict) else {},
        "places": places,
    }
    write_meta(dest, meta)
    return dest


def search_posts(query: str, *, per_page: int = 10, page: int = 1) -> list[dict]:
    data, _ = api_get(
        "/posts",
        {
            "search": query,
            "per_page": str(per_page),
            "page": str(page),
            "_fields": "id,date,slug,link,title",
        },
    )
    return list(data) if isinstance(data, list) else []


def list_category_posts(category_id: int, *, per_page: int = 10, page: int = 1) -> list[dict]:
    data, _ = api_get(
        "/posts",
        {
            "categories": str(category_id),
            "per_page": str(per_page),
            "page": str(page),
            "_fields": "id,date,slug,link,title",
        },
    )
    return list(data) if isinstance(data, list) else []


def fetch_series(name: str, limit: int) -> list[dict]:
    spec = SERIES.get(name)
    if not spec:
        raise SystemExit(f"unknown series {name!r}; choose from {sorted(SERIES)}")
    collected: list[dict] = []
    seen: set[int] = set()
    page = 1
    empty_pages = 0
    while len(collected) < limit and page <= 20:
        batch_size = 20
        if spec.get("category"):
            batch = list_category_posts(int(spec["category"]), per_page=batch_size, page=page)
        else:
            batch = search_posts(str(spec["search"]), per_page=batch_size, page=page)
        if not batch:
            break
        prefix = spec.get("slug_prefix")
        matched = 0
        for row in batch:
            post_id = int(row["id"])
            if post_id in seen:
                continue
            slug = str(row.get("slug") or "")
            if prefix and not slug.startswith(prefix):
                continue
            seen.add(post_id)
            collected.append(row)
            matched += 1
            if len(collected) >= limit:
                break
        empty_pages = empty_pages + 1 if matched == 0 else 0
        if empty_pages >= 3:
            break
        page += 1
        if len(batch) < batch_size:
            break
    return collected[:limit]


def already_have_wp_id(post_id: int) -> Path | None:
    for folder in ARTICLES.rglob("meta.yaml"):
        meta = load_meta(folder.parent)
        if meta and meta.get("wp_post_id") == post_id:
            return folder.parent
    return None


def index_wp_ids() -> dict[int, Path]:
    out: dict[int, Path] = {}
    for folder in ARTICLES.rglob("meta.yaml"):
        meta = load_meta(folder.parent)
        if not meta or meta.get("wp_post_id") is None:
            continue
        out[int(meta["wp_post_id"])] = folder.parent
    return out


def list_all_post_stubs(
    *,
    max_posts: int | None = None,
    after: str | None = None,
    before: str | None = None,
) -> list[dict]:
    """Page through /posts for ids (newest first). Optional ISO date bounds."""
    out: list[dict] = []
    page = 1
    per_page = 100
    while True:
        if max_posts is not None and len(out) >= max_posts:
            break
        params: dict[str, str] = {
            "per_page": str(per_page),
            "page": str(page),
            "_fields": "id,date,slug,link,title",
        }
        if after:
            params["after"] = after if "T" in after else f"{after}T00:00:00"
        if before:
            params["before"] = before if "T" in before else f"{before}T00:00:00"
        data, _headers = api_get("/posts", params)
        if not isinstance(data, list) or not data:
            break
        for row in data:
            out.append(row)
            if max_posts is not None and len(out) >= max_posts:
                break
        if len(data) < per_page:
            break
        page += 1
    return out[:max_posts] if max_posts is not None else out


def import_stubs(
    rows: list[dict],
    *,
    force: bool,
    issue: str | None,
    sleep_s: float,
    refresh_places: bool = False,
) -> None:
    known = index_wp_ids()
    wrote = skipped = errors = 0
    for i, row in enumerate(rows, 1):
        post_id = int(row["id"])
        existing = known.get(post_id)
        if existing and not force:
            print(f"[{i}/{len(rows)}] skip {post_id} already {existing.relative_to(ROOT)}", flush=True)
            skipped += 1
            continue
        try:
            post = fetch_post_by_id(post_id)
            dest = write_article(
                post,
                dest=existing if (force and existing) else None,
                issue=issue,
                refresh_places=refresh_places or force,
            )
            known[post_id] = dest
            print(f"[{i}/{len(rows)}] wrote {dest.relative_to(ROOT)}", flush=True)
            wrote += 1
        except Exception as exc:
            print(f"[{i}/{len(rows)}] ERROR {post_id}: {exc}", flush=True)
            errors += 1
        if sleep_s > 0:
            time.sleep(sleep_s)
    print(f"done wrote={wrote} skipped={skipped} errors={errors}", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", help="mittendran.de post URL")
    p.add_argument("--slug", help="WP post slug")
    p.add_argument("--id", type=int, help="WP post id")
    p.add_argument("--into", type=Path, help="Existing article folder to update in place")
    p.add_argument("--issue", default=None, help="Heft issue label stored in meta (optional)")
    p.add_argument("--series", choices=sorted(SERIES), help="Fetch a named selective series")
    p.add_argument("--all", action="store_true", help="Batch-import posts from the WP API (newest first)")
    p.add_argument("--after", help="Only posts on/after this date (YYYY-MM-DD), with --all")
    p.add_argument("--before", help="Only posts before this date (YYYY-MM-DD), with --all")
    p.add_argument("--max", type=int, default=None, help="Max posts for --all / override --limit for series")
    p.add_argument("--limit", type=int, default=5, help="Max posts for --series (default 5)")
    p.add_argument("--sleep", type=float, default=0.35, help="Seconds between API fetches (default 0.35)")
    p.add_argument("--force", action="store_true", help="Re-fetch even if wp_post_id already present")
    p.add_argument(
        "--refresh-places",
        action="store_true",
        help="Re-detect gazetteer places from German text (website-first pins)",
    )
    args = p.parse_args()

    if args.all:
        n = args.max if args.max is not None else None
        print(
            f"listing posts (max={n or 'all'}, after={args.after}, before={args.before})...",
            flush=True,
        )
        rows = list_all_post_stubs(max_posts=n, after=args.after, before=args.before)
        print(f"importing {len(rows)} posts...", flush=True)
        import_stubs(
            rows,
            force=args.force,
            issue=args.issue,
            sleep_s=args.sleep,
            refresh_places=args.refresh_places,
        )
        return

    if args.series:
        limit = args.max if args.max is not None else args.limit
        rows = fetch_series(args.series, limit)
        print(f"series {args.series}: {len(rows)} posts")
        import_stubs(
            rows,
            force=args.force,
            issue=args.issue,
            sleep_s=args.sleep,
            refresh_places=args.refresh_places,
        )
        return

    if not (args.url or args.slug or args.id):
        p.error("provide --url, --slug, --id, --series, or --all")

    if args.id:
        post = fetch_post_by_id(args.id)
    elif args.slug:
        post = fetch_post_by_slug(args.slug)
    else:
        post = fetch_post_by_slug(slug_from_url(args.url))

    into = args.into.resolve() if args.into else None
    if into and not into.exists():
        raise SystemExit(f"--into folder missing: {into}")
    if into is None and not args.force:
        hit = already_have_wp_id(int(post["id"]))
        if hit:
            print(f"already have wp_post_id={post['id']} at {hit.relative_to(ROOT)}")
            print("pass --force to refresh, or --into PATH to update another folder")
            return

    dest = write_article(
        post,
        dest=into,
        issue=args.issue,
        refresh_places=args.refresh_places or bool(into),
    )
    print(f"wrote {dest.relative_to(ROOT)}")
    print(f"  title: {strip_title_html((post.get('title') or {}).get('rendered') or '')}")
    print(f"  url:   {post.get('link')}")
    print(f"  id:    {post.get('id')}")


if __name__ == "__main__":
    main()
