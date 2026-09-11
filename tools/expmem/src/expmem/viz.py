"""Local graph visualizer: python -m expmem viz"""

from __future__ import annotations

import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse


def _pkg_root() -> Path:
    # src/expmem/viz.py -> expmem/
    return Path(__file__).resolve().parents[2]


def _html_path() -> Path:
    return _pkg_root() / "viz" / "index.html"


def discover_collections(roots: list[Path]) -> list[dict]:
    found: dict[str, Path] = {}
    for root in roots:
        if not root:
            continue
        root = Path(root).expanduser()
        if not root.exists():
            continue
        if root.is_file() and root.suffix.lower() == ".jsonl":
            found[root.parent.name] = root.resolve()
            continue
        if (root / "experiments.jsonl").is_file():
            found[root.name] = (root / "experiments.jsonl").resolve()
        if root.is_dir():
            for child in sorted(root.iterdir()):
                f = child / "experiments.jsonl"
                if child.is_dir() and f.is_file():
                    found[child.name] = f.resolve()
    rows = []
    for name, path in found.items():
        n = 0
        try:
            n = sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        except OSError:
            n = 0
        rows.append({"id": name, "path": str(path), "nodes": n})
    return rows


def _resolve_jsonl(raw: str, roots: list[Path]) -> Path:
    text = (raw or "").strip()
    if not text:
        raise FileNotFoundError("empty path")
    p = Path(text).expanduser()
    if p.is_dir():
        p = p / "experiments.jsonl"
    if not p.is_file() and p.suffix.lower() != ".jsonl":
        for root in roots:
            cand = Path(root) / text / "experiments.jsonl"
            if cand.is_file():
                p = cand
                break
            cand = Path(root) / text
            if cand.is_file():
                p = cand
                break
    p = p.resolve()
    if not p.is_file() or p.suffix.lower() != ".jsonl":
        raise FileNotFoundError(str(p))
    return p


def make_handler(html: Path, roots: list[Path]):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            return

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)

            if path in {"/", "/index.html"}:
                if not html.is_file():
                    self._send(404, b"viz/index.html missing", "text/plain; charset=utf-8")
                    return
                self._send(200, html.read_bytes(), "text/html; charset=utf-8")
                return

            if path == "/api/collections":
                body = json.dumps(discover_collections(roots), ensure_ascii=False).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
                return

            if path.startswith("/api/collection/"):
                name = unquote(path[len("/api/collection/") :]).strip()
                try:
                    target = _resolve_jsonl(name, roots)
                except FileNotFoundError as e:
                    self._send(404, str(e).encode("utf-8"), "text/plain; charset=utf-8")
                    return
                self._send(200, target.read_bytes(), "application/x-ndjson; charset=utf-8")
                return

            if path == "/api/open":
                raw = unquote((qs.get("path") or [""])[0])
                try:
                    target = _resolve_jsonl(raw, roots)
                except FileNotFoundError as e:
                    self._send(404, str(e).encode("utf-8"), "text/plain; charset=utf-8")
                    return
                self._send(200, target.read_bytes(), "application/x-ndjson; charset=utf-8")
                return

            self._send(404, b"not found", "text/plain; charset=utf-8")

    return Handler


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    open_browser: bool = True,
    extra_roots: Optional[list[Path]] = None,
) -> None:
    html = _html_path()
    roots = [_pkg_root() / "datasets"]
    if extra_roots:
        roots.extend(extra_roots)
    httpd = ThreadingHTTPServer((host, port), make_handler(html, roots))
    url = f"http://{host}:{port}/"
    print(f"expmem viz  {url}", flush=True)
    print(f"html        {html}", flush=True)
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    serve()
