"""Download one arXiv paper and extract text. Return metadata + outline, never the body."""

from __future__ import annotations

import io
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from xml.etree import ElementTree as ET

import random
from urllib.parse import urlencode

from papers.htmltext import html_to_text, looks_like_paper_html, outline_from_text
from papers.ids import atom_id, normalize_arxiv_id
from papers import net
from papers.store import paper_dir, public_card, save_meta, save_text
from papers.textext import tex_to_text

ATOM = "http://www.w3.org/2005/Atom"
GetFn = Callable[[str], tuple[int, bytes, str]]


def _utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _decode(body: bytes) -> str:
    for enc in ("utf-8", "latin-1"):
        try:
            return body.decode(enc)
        except UnicodeDecodeError:
            continue
    return body.decode("utf-8", errors="replace")


def _parse_entries(body: bytes) -> list[dict[str, str]]:
    root = ET.fromstring(body)
    hits: list[dict[str, str]] = []
    for entry in root.findall(f"{{{ATOM}}}entry"):
        title = " ".join((entry.findtext(f"{{{ATOM}}}title") or "").split())
        summary = " ".join((entry.findtext(f"{{{ATOM}}}summary") or "").split())[:500]
        ident = entry.findtext(f"{{{ATOM}}}id") or ""
        try:
            paper_id = normalize_arxiv_id(ident)
        except ValueError:
            continue
        hits.append({"paper_id": paper_id, "title": title, "summary": summary, "url": ident})
    return hits


def _search_query(params: dict[str, Any]) -> str:
    q = str(params.get("query") or "").strip()
    cat = str(params.get("category") or params.get("cat") or "").strip()
    if q.lower().startswith("cat:") or q.lower().startswith("all:"):
        return q
    if q and cat:
        return f"cat:{cat} AND all:{q}"
    if q:
        return f"all:{q}"
    if cat:
        return f"cat:{cat}"
    return "cat:cs.LG"


def _list_arxiv(get: GetFn, query: str, *, start: int, limit: int) -> list[dict[str, str]]:
    params = urlencode(
        {
            "search_query": query,
            "start": max(0, start),
            "max_results": max(1, min(int(limit), 10)),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
    )
    url = f"https://export.arxiv.org/api/query?{params}"
    try:
        code, body, _ = get(url)
    except ConnectionError:
        return []
    if code != 200 or not body:
        return []
    try:
        return _parse_entries(body)
    except ET.ParseError:
        return []


def random_paper(params: dict[str, Any], *, repo: Path, get: GetFn | None = None) -> dict[str, Any]:
    getter = get or (lambda url: net.get(url, timeout=45))
    seed = params.get("seed")
    rng = random.Random(int(seed)) if seed not in (None, "") else random.Random()
    query = _search_query(params)
    start = rng.randrange(0, 800)
    hits = _list_arxiv(getter, query, start=start, limit=8)
    if not hits:
        hits = _list_arxiv(getter, query, start=0, limit=8)
    if not hits:
        return {"ok": False, "error": f"no arXiv hits for {query!r}"}
    order = list(hits)
    rng.shuffle(order)
    last: dict[str, Any] = {}
    for hit in order[:3]:
        last = fetch_paper({**params, "paper_id": hit["paper_id"]}, repo=repo, get=getter)
        if last.get("ok"):
            last["picked_from"] = query
            last["hint"] = (
                "Picked and downloaded for you. Read with read_paper(paper_id=..., section='Abstract'). "
                "Do not ingest the whole file."
            )
            return last
    last = last or {"ok": False, "error": "fetch failed"}
    last["picked_from"] = query
    return last


def _atom_meta(paper_id: str, get: GetFn) -> dict[str, str]:
    url = f"https://export.arxiv.org/api/query?id_list={paper_id}&max_results=1"
    out = {"title": "", "summary": "", "url": f"https://arxiv.org/abs/{paper_id}"}
    try:
        code, body, _ = get(url)
    except ConnectionError:
        return out
    if code != 200 or not body:
        return out
    root = ET.fromstring(body)
    entry = root.find(f"{{{ATOM}}}entry")
    if entry is None:
        return out
    title = " ".join((entry.findtext(f"{{{ATOM}}}title") or "").split())
    summary = " ".join((entry.findtext(f"{{{ATOM}}}summary") or "").split())[:500]
    ident = entry.findtext(f"{{{ATOM}}}id") or out["url"]
    return {"title": title, "summary": summary, "url": ident}


def _try_html(paper_id: str, get: GetFn) -> tuple[str, str] | None:
    urls = (
        f"https://arxiv.org/html/{paper_id}",
        f"https://ar5iv.labs.arxiv.org/html/{paper_id}",
        f"https://ar5iv.org/html/{paper_id}",
    )
    for url in urls:
        try:
            code, body, ctype = get(url)
        except ConnectionError:
            continue
        if code != 200 or not body:
            continue
        if "html" not in (ctype or "").lower() and not body.lstrip().lower().startswith(b"<!doctype") and b"<html" not in body[:400].lower():
            continue
        html = _decode(body)
        if not looks_like_paper_html(html):
            continue
        text = html_to_text(html)
        if len(text) < 200:
            continue
        source = "arxiv_html" if "arxiv.org/html" in url else "ar5iv"
        return text, source
    return None


def _try_tex(paper_id: str, get: GetFn) -> tuple[str, str] | None:
    urls = (
        f"https://arxiv.org/e-print/{paper_id}",
        f"https://export.arxiv.org/e-print/{paper_id}",
    )
    for url in urls:
        try:
            code, body, _ = get(url)
        except ConnectionError:
            continue
        if code != 200 or not body or len(body) < 64:
            continue
        if body[:5] == b"%PDF-":
            continue
        try:
            tf = tarfile.open(fileobj=io.BytesIO(body), mode="r:*")
        except tarfile.TarError:
            raw = _decode(body)
            if "\\documentclass" in raw or "\\begin{document}" in raw:
                return tex_to_text(raw), "tex"
            continue
        tex_blobs: list[tuple[int, str]] = []
        try:
            for info in tf.getmembers():
                if not info.isfile() or not info.name.lower().endswith(".tex"):
                    continue
                f = tf.extractfile(info)
                if f is None:
                    continue
                blob = f.read()
                tex_blobs.append((len(blob), _decode(blob)))
        finally:
            tf.close()
        if not tex_blobs:
            continue
        tex_blobs.sort(reverse=True)
        chosen = tex_blobs[0][1]
        for _n, blob in tex_blobs:
            if "\\documentclass" in blob or "\\begin{document}" in blob:
                chosen = blob
                break
        text = tex_to_text(chosen)
        if len(text) < 400:
            continue
        return text, "tex"
    return None


def _try_pypdf(pdf: bytes) -> str | None:
    try:
        from pypdf import PdfReader  # type: ignore
    except ImportError:
        return None
    try:
        reader = PdfReader(io.BytesIO(pdf))
    except Exception:
        return None
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    text = "\n".join(parts).strip()
    return text + "\n" if len(text) > 400 else None


def _save_pdf(folder: Path, paper_id: str, get: GetFn) -> bool:
    urls = (
        f"https://arxiv.org/pdf/{paper_id}.pdf",
        f"https://export.arxiv.org/pdf/{paper_id}",
    )
    for url in urls:
        try:
            code, body, _ = get(url)
        except ConnectionError:
            continue
        if code != 200 or not body or body[:5] != b"%PDF-":
            continue
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "source.pdf").write_bytes(body)
        return True
    return False


def fetch_paper(params: dict[str, Any], *, repo: Path, get: GetFn | None = None) -> dict[str, Any]:
    from papers.store import load_meta, papers_root, require_text

    getter = get or (lambda url: net.get(url, timeout=45))
    paper_id = normalize_arxiv_id(str(params.get("paper_id") or params.get("id") or ""))
    root = papers_root(params, repo=repo)
    folder = paper_dir(root, paper_id)
    force = bool(params.get("force"))
    if not force and (folder / "paper.txt").is_file():
        meta = load_meta(folder) or {}
        try:
            require_text(folder)
        except FileNotFoundError:
            pass
        else:
            card = public_card(meta, folder)
            card["ok"] = True
            card["cached"] = True
            return card

    meta_abs = _atom_meta(paper_id, getter)
    extracted: tuple[str, str] | None = _try_html(paper_id, getter)
    if extracted is None:
        extracted = _try_tex(paper_id, getter)
    pdf_ok = _save_pdf(folder, paper_id, getter)
    if extracted is None and pdf_ok:
        pdf_bytes = (folder / "source.pdf").read_bytes()
        pdf_text = _try_pypdf(pdf_bytes)
        if pdf_text:
            extracted = (pdf_text, "pdf")

    if extracted is None:
        return {
            "ok": False,
            "error": "could not extract text (no HTML/TeX; PDF needs pypdf). PDF saved if download succeeded.",
            "paper_id": atom_id(paper_id),
            "dir": str(folder),
            "pdf": pdf_ok,
        }

    text, source = extracted
    stats = save_text(folder, text)
    sections = outline_from_text(text)
    title = meta_abs["title"] or (sections[0]["title"] if sections else "")
    meta = {
        "paper_id": atom_id(paper_id),
        "arxiv_id": paper_id,
        "title": title,
        "summary": meta_abs["summary"],
        "url": meta_abs["url"],
        "source": source,
        "fetched_at": _utc(),
        "sections": sections,
        **stats,
    }
    save_meta(folder, meta)
    card = public_card(meta, folder)
    card["ok"] = True
    card["cached"] = False
    card["pdf"] = pdf_ok
    return card
