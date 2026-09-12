"""Read-only local viewer for Pi agent session JSONL. Does not write labs or pick experiments."""

from __future__ import annotations

import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
HTML = HERE / "index.html"
ENV_SESSIONS = "TRACEVIZ_SESSIONS"


def sessions_root() -> Path:
    raw = (os.environ.get(ENV_SESSIONS) or "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / ".pi" / "agent" / "sessions").resolve()


def is_within(path: Path, root: Path) -> bool:
    p = os.path.normcase(str(path.resolve()))
    r = os.path.normcase(str(root.resolve()))
    if p == r:
        return True
    prefix = r if r.endswith(os.sep) else r + os.sep
    return p.startswith(prefix)


def safe_session(rel: str, root: Path | None = None) -> Path:
    root = (root or sessions_root()).resolve()
    text = (rel or "").replace("\\", "/").lstrip("/")
    if not text or ".." in Path(text).parts:
        raise FileNotFoundError("invalid path")
    target = (root / text).resolve()
    if not is_within(target, root):
        raise FileNotFoundError("outside sessions root")
    if target.suffix.lower() != ".jsonl" or not target.is_file():
        raise FileNotFoundError(str(target))
    return target


def _preview(path: Path, limit: int = 40) -> dict[str, Any]:
    cwd = ""
    model = ""
    preview = ""
    n_msg = 0
    try:
        with path.open(encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                typ = obj.get("type")
                if typ == "session":
                    cwd = str(obj.get("cwd") or "")
                elif typ == "model_change":
                    model = str(obj.get("modelId") or obj.get("model") or "")
                elif typ == "message":
                    n_msg += 1
                    msg = obj.get("message") or {}
                    if not preview and msg.get("role") == "user":
                        preview = _first_text(msg.get("content")).replace("\n", " ").strip()[:180]
                if i >= limit and preview:
                    break
        if n_msg == 0:
            with path.open(encoding="utf-8") as f:
                n_msg = sum(1 for line in f if line.strip())
    except OSError:
        pass
    return {"cwd": cwd, "model": model, "preview": preview, "messages": n_msg}


def _first_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                return str(part.get("text") or "")
            if isinstance(part, dict) and part.get("text"):
                return str(part.get("text") or "")
    return ""


def list_sessions(root: Path | None = None) -> list[dict[str, Any]]:
    root = (root or sessions_root())
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        st = path.stat()
        meta = _preview(path)
        rows.append(
            {
                "id": path.stem,
                "rel": rel,
                "name": path.name,
                "bytes": st.st_size,
                "mtime": int(st.st_mtime),
                **meta,
            }
        )
    return rows


def make_handler(html: Path, root_fn):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args) -> None:
            return

        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            path = parsed.path
            qs = parse_qs(parsed.query)
            root = root_fn()

            if path in {"/", "/index.html"}:
                if not html.is_file():
                    self._send(404, b"index.html missing", "text/plain; charset=utf-8")
                    return
                self._send(200, html.read_bytes(), "text/html; charset=utf-8")
                return

            if path == "/api/sessions":
                body = json.dumps(
                    {"ok": True, "root": str(root), "sessions": list_sessions(root)},
                    ensure_ascii=False,
                ).encode("utf-8")
                self._send(200, body, "application/json; charset=utf-8")
                return

            if path == "/api/session":
                rel = unquote((qs.get("rel") or [""])[0])
                try:
                    target = safe_session(rel, root)
                except FileNotFoundError as e:
                    self._send(404, str(e).encode("utf-8"), "text/plain; charset=utf-8")
                    return
                self._send(200, target.read_bytes(), "application/x-ndjson; charset=utf-8")
                return

            self._send(404, b"not found", "text/plain; charset=utf-8")

    return Handler


def serve(*, host: str = "127.0.0.1", port: int = 8766, open_browser: bool = True) -> None:
    if not HTML.is_file():
        raise SystemExit(f"missing {HTML}")
    httpd = ThreadingHTTPServer((host, port), make_handler(HTML, sessions_root))
    url = f"http://{host}:{port}/"
    print(f"traceviz  {url}", flush=True)
    print(f"sessions  {sessions_root()}", flush=True)
    if open_browser:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    host = "127.0.0.1"
    port = 8766
    open_browser = True
    i = 0
    while i < len(argv):
        if argv[i] == "--port" and i + 1 < len(argv):
            port = int(argv[i + 1])
            i += 2
            continue
        if argv[i] == "--host" and i + 1 < len(argv):
            host = argv[i + 1]
            i += 2
            continue
        if argv[i] == "--no-browser":
            open_browser = False
            i += 1
            continue
        i += 1
    serve(host=host, port=port, open_browser=open_browser)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
