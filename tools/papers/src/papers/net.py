"""Tiny HTTP helper. Tests patch `get`. Falls back to curl.exe if urllib SSL fails."""

from __future__ import annotations

import shutil
import ssl
import subprocess
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

UA = "MyAgent-papers/0.1 (https://github.com/LinZY6/MyAgent; research agent)"


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:
        ctx.set_ciphers("DEFAULT:@SECLEVEL=1")
    except ssl.SSLError:
        pass
    return ctx


def _urllib_get(url: str, timeout: int) -> tuple[int, bytes, str]:
    req = Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    try:
        with urlopen(req, timeout=timeout, context=_ssl_context() if url.startswith("https") else None) as resp:  # noqa: S310
            ctype = resp.headers.get("Content-Type") or ""
            return int(resp.status), resp.read(), ctype
    except HTTPError as e:
        body = e.read() if e.fp else b""
        return int(e.code), body, str(e.reason)
    except URLError as e:
        raise ConnectionError(str(e.reason or e)) from e


def _curl_get(url: str, timeout: int) -> tuple[int, bytes, str]:
    exe = shutil.which("curl.exe") or shutil.which("curl")
    if not exe:
        raise ConnectionError("curl not found")
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        hdr = Path(d) / "h.txt"
        bodyf = Path(d) / "b.bin"
        proc = subprocess.run(
            [
                exe,
                "-L",
                "-sS",
                "--max-time",
                str(timeout),
                "-A",
                UA,
                "-D",
                str(hdr),
                "-o",
                str(bodyf),
                url,
            ],
            capture_output=True,
            timeout=timeout + 8,
            check=False,
        )
        body = bodyf.read_bytes() if bodyf.is_file() else b""
        header_text = hdr.read_text(encoding="latin-1", errors="replace") if hdr.is_file() else ""
    code = 0
    ctype = ""
    for line in header_text.splitlines():
        if line.upper().startswith("HTTP/"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                code = int(parts[1])
        if line.lower().startswith("content-type:"):
            ctype = line.split(":", 1)[1].strip()
    if proc.returncode != 0 and not body:
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise ConnectionError(err or f"curl exit {proc.returncode}")
    return code or (200 if body else 0), body, ctype


def get(url: str, *, timeout: int = 30) -> tuple[int, bytes, str]:
    last_err: Exception | None = None
    for attempt in range(2):
        try:
            code, body, ctype = _urllib_get(url, timeout)
            if code in {502, 503, 504} and attempt == 0:
                time.sleep(1.2)
                continue
            return code, body, ctype
        except (ConnectionError, OSError, ssl.SSLError, TimeoutError) as e:
            last_err = e
            try:
                return _curl_get(url, timeout)
            except (ConnectionError, OSError, subprocess.SubprocessError, TimeoutError) as e2:
                last_err = e2
                if attempt == 0:
                    time.sleep(0.8)
                    continue
                raise ConnectionError(str(last_err)) from e2
    if last_err:
        raise ConnectionError(str(last_err))
    return 0, b"", ""
