"""Local mini-CMS for yaniktoim-cms.

Stdlib-only — no pip install needed. Starts an HTTP server on
http://localhost:8765 with:

  GET /                          → list of articles (cms/static/index.html)
  GET /editor.html               → editor split-screen (cms/static/editor.html)
  GET /preview/<art>             → re-render <art> and return HTML
  GET /api/articles              → JSON list of all manifest entries with zml
  GET /api/article/<art>         → JSON {zml: "<contents>", meta: {...}}
  POST /api/article/<art>        → body = ZML text → save zml/<art>.zml,
                                   backup → _backups/zml/<art>.<ts>.zml,
                                   re-render to site/<section>/<art>.html
                                   → returns JSON {ok: true, preview_path: "..."}
  GET /static/*                  → static assets

Usage:
  python cms/server.py [--port 8765]
"""
from __future__ import annotations
import os
import re
import sys
import json
import importlib.util
import datetime as dt
import urllib.parse
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ZML_DIR = ROOT / "zml"
SITE = ROOT / "site"
BACKUPS = ROOT / "_backups" / "zml"
STATIC = Path(__file__).resolve().parent / "static"
MANIFEST_PATH = ROOT / "manifest.json"


# ────── lazy-import 4_render.py (filename starts with a digit) ──────

def _load_renderer():
    spec = importlib.util.spec_from_file_location("r4", ROOT / "src" / "4_render.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RENDERER = _load_renderer()


# ────── manifest helpers ──────

def load_manifest() -> list[dict]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def manifest_by_art(manifest: list[dict]) -> dict[str, dict]:
    return {r["art"]: r for r in manifest if "art" in r}


# ────── article list (only those with existing ZML) ──────

def list_articles() -> list[dict]:
    """All manifest entries, marked with `has_zml`."""
    manifest = load_manifest()
    out = []
    for r in manifest:
        art = r.get("art")
        if not art:
            continue
        zml = ZML_DIR / f"{art}.zml"
        out.append({
            "art": art,
            "stem": r.get("stem"),
            "title": r.get("title", ""),
            "section": r.get("section", ""),
            "date_chosen": r.get("date_chosen", ""),
            "section_order": r.get("section_order"),
            "url": r.get("url", ""),
            "has_zml": zml.exists(),
        })
    # Sort: with ZML first (date desc), then without ZML (date desc).
    out.sort(key=lambda x: (not x["has_zml"], x["date_chosen"] or ""),
             reverse=False)
    # Inside each group date desc — apply secondary sort.
    have = [x for x in out if x["has_zml"]]
    havent = [x for x in out if not x["has_zml"]]
    have.sort(key=lambda x: x["date_chosen"] or "", reverse=True)
    havent.sort(key=lambda x: x["date_chosen"] or "", reverse=True)
    return have + havent


# ────── load / save one article ──────

def load_article(art: str) -> dict | None:
    manifest = load_manifest()
    by_art = manifest_by_art(manifest)
    rec = by_art.get(art)
    if not rec:
        return None
    zml_path = ZML_DIR / f"{art}.zml"
    if not zml_path.exists():
        return None
    return {
        "meta": {
            "art": art,
            "stem": rec.get("stem"),
            "title": rec.get("title", ""),
            "section": rec.get("section", ""),
            "date_chosen": rec.get("date_chosen", ""),
            "url": rec.get("url", ""),
        },
        "zml": zml_path.read_text(encoding="utf-8"),
    }


def save_article(art: str, new_zml: str) -> dict:
    """Backup current → write new → re-render. Return summary."""
    manifest = load_manifest()
    by_art = manifest_by_art(manifest)
    rec = by_art.get(art)
    if not rec:
        return {"ok": False, "error": f"art {art} not in manifest"}

    zml_path = ZML_DIR / f"{art}.zml"
    BACKUPS.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    if zml_path.exists():
        backup_path = BACKUPS / f"{art}.{ts}.zml"
        backup_path.write_text(
            zml_path.read_text(encoding="utf-8"), encoding="utf-8",
        )

    zml_path.write_text(new_zml, encoding="utf-8")

    # Re-render (full pipeline, in-process).
    try:
        zohar = (ROOT / "_logs" / "zohar_index.json")
        zohar_index = (json.loads(zohar.read_text(encoding="utf-8"))
                       if zohar.exists() else {"chapters": {}, "articles": {}})
        ctx_data = {
            "manifest": manifest,
            "manifest_by_art": by_art,
            "zohar_index": zohar_index,
        }
        html = RENDERER.render_article(art, ctx_data)
        section = rec.get("section", "_unsorted")
        out_dir = SITE / section
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{art}.html"
        out_path.write_text(html, encoding="utf-8")
        rel = out_path.relative_to(ROOT).as_posix()
        return {"ok": True, "rendered": rel, "backup": f"_backups/zml/{art}.{ts}.zml"}
    except Exception as e:
        return {
            "ok": False,
            "error": f"{type(e).__name__}: {e}",
            "traceback": traceback.format_exc(),
        }


# ────── transform (sync — long: 25s..15min depending on article) ──────

def transform_article(art: str) -> dict:
    """Run `python src/3_transform.py <art>` synchronously. Returns summary.
    Caller blocks until done (this is a long-running request)."""
    import subprocess
    cmd = [sys.executable, "-X", "utf8", str(ROOT / "src" / "3_transform.py"),
           art, "--force"]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            cwd=ROOT, timeout=1800,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "transform timeout (30 min)"}
    if proc.returncode != 0:
        return {
            "ok": False,
            "error": f"transform exit={proc.returncode}",
            "stdout": proc.stdout[-2000:],
            "stderr": proc.stderr[-2000:],
        }
    # Now render the ZML.
    zml = ZML_DIR / f"{art}.zml"
    if not zml.exists():
        return {
            "ok": False,
            "error": "transform completed but zml not found",
            "stdout": proc.stdout[-2000:],
        }
    rendered = save_article(art, zml.read_text(encoding="utf-8"))
    return {
        "ok": True,
        "transform_stdout": proc.stdout[-1500:],
        "render": rendered,
    }


# ────── HTTP handler ──────

class Handler(BaseHTTPRequestHandler):
    server_version = "yaniktoim-cms/0.1"

    def log_message(self, fmt, *args):
        # Compact log line.
        sys.stderr.write(
            f"[{self.log_date_time_string()}] {self.address_string()} {fmt % args}\n"
        )

    # --- routing helpers ---
    def _json(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _file(self, path: Path, content_type: str | None = None):
        if not path.is_file():
            self.send_error(404, f"Not found: {path.name}")
            return
        data = path.read_bytes()
        if content_type is None:
            content_type = self._guess_ct(path.name)
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _guess_ct(self, name: str) -> str:
        ext = name.rsplit(".", 1)[-1].lower()
        return {
            "html": "text/html; charset=utf-8",
            "css":  "text/css; charset=utf-8",
            "js":   "application/javascript; charset=utf-8",
            "json": "application/json; charset=utf-8",
            "jpg":  "image/jpeg",
            "jpeg": "image/jpeg",
            "png":  "image/png",
            "svg":  "image/svg+xml",
            "ico":  "image/x-icon",
        }.get(ext, "application/octet-stream")

    # --- GET ---
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        if path == "/" or path == "/index.html":
            return self._file(STATIC / "index.html", "text/html; charset=utf-8")
        if path == "/editor.html":
            return self._file(STATIC / "editor.html", "text/html; charset=utf-8")
        if path.startswith("/static/"):
            sub = path[len("/static/"):]
            return self._file(STATIC / sub)
        if path.startswith("/site/"):
            # Serve site/* for the preview iframe (incl. style.css, images).
            sub = path[len("/site/"):]
            return self._file(SITE / sub)
        if path == "/api/articles":
            return self._json(200, {"articles": list_articles()})
        m = re.match(r'^/api/article/([A-Za-z0-9]+)$', path)
        if m:
            art = m.group(1)
            data = load_article(art)
            if data is None:
                return self._json(404, {"ok": False, "error": "not found"})
            return self._json(200, {"ok": True, **data})
        m = re.match(r'^/preview/([A-Za-z0-9]+)$', path)
        if m:
            art = m.group(1)
            manifest = load_manifest()
            by_art = manifest_by_art(manifest)
            rec = by_art.get(art)
            if not rec:
                self.send_error(404, "no such art in manifest")
                return
            section = rec.get("section", "_unsorted")
            html_path = SITE / section / f"{art}.html"
            if not html_path.exists():
                save_article(art, (ZML_DIR / f"{art}.zml").read_text(encoding="utf-8"))
            # Inject <base> so relative paths (../style.css, ../<section>/<art>.html)
            # resolve to the CMS server's /site/<section>/ root.
            html = html_path.read_text(encoding="utf-8")
            base_href = f'/site/{section}/'
            html = re.sub(
                r'(<head[^>]*>)',
                lambda m: m.group(1) + f'\n<base href="{base_href}">',
                html, count=1,
            )
            body = html.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        # Convenience: /style.css → site/style.css
        if path == "/style.css":
            return self._file(SITE / "style.css", "text/css; charset=utf-8")
        self.send_error(404, "no route")

    # --- POST ---
    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        m = re.match(r'^/api/article/([A-Za-z0-9]+)$', path)
        if m:
            art = m.group(1)
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length).decode("utf-8") if length else ""
            try:
                payload = json.loads(body) if body else {}
            except json.JSONDecodeError:
                return self._json(400, {"ok": False, "error": "invalid JSON"})
            new_zml = payload.get("zml")
            if new_zml is None:
                return self._json(400, {"ok": False, "error": "missing 'zml'"})
            result = save_article(art, new_zml)
            return self._json(200 if result.get("ok") else 500, result)
        m = re.match(r'^/api/transform/([A-Za-z0-9]+)$', path)
        if m:
            art = m.group(1)
            # Discard request body (none expected).
            length = int(self.headers.get("Content-Length", "0"))
            if length:
                self.rfile.read(length)
            result = transform_article(art)
            return self._json(200 if result.get("ok") else 500, result)
        return self._json(404, {"ok": False, "error": "no route"})


# ────── main ──────

def main():
    port = 8765
    if "--port" in sys.argv:
        i = sys.argv.index("--port")
        port = int(sys.argv[i + 1])
    print(f"yaniktoim-cms editor → http://localhost:{port}/", flush=True)
    print(f"  ZML source: {ZML_DIR}", flush=True)
    print(f"  Output:     {SITE}", flush=True)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down…", flush=True)
        server.server_close()


if __name__ == "__main__":
    main()
