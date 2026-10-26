"""Local archive and pin APIs. Article folders are the database. No PDF/crop."""
from __future__ import annotations

import json
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from articles_lib import (  # noqa: E402
    ARTICLES,
    article_public,
    find_article,
    geojson,
    list_articles,
    tag_book,
    maps_embed_url,
    maps_search_url,
    resolve_maps_url,
    search_places,
    set_article_tags,
    upsert_place,
)

LOCAL = ROOT / "local"


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(LOCAL), **kwargs)

    def send_json(self, obj, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path == "/api/tags":
            rows = []
            for tag_id, row in tag_book().items():
                rows.append(
                    {
                        "id": tag_id,
                        "de": row.get("de") or tag_id,
                        "en": row.get("en") or tag_id,
                    }
                )
            self.send_json(rows)
            return
        if path == "/api/articles":
            self.send_json([article_public(m) for m in list_articles()])
            return
        if path.startswith("/api/articles/"):
            slug = unquote(path.removeprefix("/api/articles/").strip("/"))
            meta = find_article(slug)
            if not meta:
                self.send_json({"error": "missing article"}, 404)
                return
            self.send_json(article_public(meta, include_text=True))
            return
        if path == "/api/geojson":
            self.send_json(geojson(include_auto=True))
            return
        if path == "/api/search-place":
            q = (query.get("q") or [""])[0].strip()
            self.send_json(
                {
                    "query": q,
                    "maps": maps_search_url(q) if q else None,
                    "embed": maps_embed_url(q) if q else None,
                    "results": search_places(q) if q else [],
                }
            )
            return
        if path.startswith("/articles/"):
            rel = unquote(path.removeprefix("/articles/"))
            target = (ARTICLES / rel).resolve()
            if ARTICLES.resolve() not in target.parents and target != ARTICLES.resolve():
                self.send_error(403)
                return
            if not target.is_file():
                self.send_error(404)
                return
            self.send_response(200)
            ctype = "image/png" if target.suffix.lower() == ".png" else "application/octet-stream"
            if target.suffix.lower() in {".jpg", ".jpeg"}:
                ctype = "image/jpeg"
            data = target.read_bytes()
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/pin":
            self.handle_pin()
            return
        if path == "/api/tags":
            self.handle_tags()
            return
        self.send_error(404)

    def handle_pin(self) -> None:
        data = self.read_json()
        slug = str(data.get("slug") or "")
        name = str(data.get("name") or "").strip()
        status = str(data.get("status") or "confirmed")
        if not slug or not name:
            self.send_json({"error": "slug and name required"}, 400)
            return
        lat = data.get("lat")
        lon = data.get("lon")
        maps_url = str(data.get("maps_url") or "").strip()
        if maps_url:
            hit = resolve_maps_url(maps_url)
            if not hit:
                self.send_json({"error": "could not read coordinates from that Google Maps link"}, 400)
                return
            lat, lon = hit
        try:
            article = upsert_place(
                slug,
                name,
                float(lat) if lat is not None else None,
                float(lon) if lon is not None else None,
                status,
            )
        except FileNotFoundError:
            self.send_json({"error": "missing article"}, 404)
            return
        self.send_json(article)

    def handle_tags(self) -> None:
        data = self.read_json()
        slug = str(data.get("slug") or "")
        tags = data.get("tags")
        if not slug:
            self.send_json({"error": "slug required"}, 400)
            return
        if not isinstance(tags, list):
            self.send_json({"error": "tags must be a list"}, 400)
            return
        try:
            article = set_article_tags(slug, tags)
        except FileNotFoundError:
            self.send_json({"error": "missing article"}, 404)
            return
        self.send_json(article)


def main() -> None:
    port = 8765
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"http://127.0.0.1:{port}/archive.html", flush=True)
    print(f"http://127.0.0.1:{port}/map.html", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
