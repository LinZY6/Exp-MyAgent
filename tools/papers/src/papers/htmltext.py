"""HTML → plain text with markdown headings. Outline from those headings."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Any

_SKIP_TAGS = frozenset(
    {"script", "style", "svg", "nav", "noscript", "button", "form", "footer", "header", "iframe"}
)
_SKIP_CLASS = ("ltx_page_logo", "ltx_pagination", "ltx_navigation", "ltx_TOC", "ltx_page_footer")
_BLOCK = frozenset(
    {"p", "div", "li", "tr", "section", "article", "blockquote", "pre", "figcaption", "dt", "dd"}
)
_HEAD = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### "}
_HEADING_LINE = re.compile(r"^(#{1,4})\s+(.+)$")
_NUMBERED = re.compile(r"^((?:\d+\.)+\d+|\d+)\s+(.{3,120})$")
_NAMED = re.compile(
    r"^(Abstract|Introduction|Related Work|Background|Method|Methods|Approach|"
    r"Experiment|Experiments|Results|Discussion|Conclusion|Conclusions|"
    r"References|Bibliography|Appendix|Acknowledgements|Acknowledgment)\b.*$",
    re.I,
)


class _HTMLToText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0
        self._head: str | None = None
        self._head_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        cls = " ".join(v or "" for k, v in attrs if k.lower() == "class")
        if tag in _SKIP_TAGS or any(tok in cls for tok in _SKIP_CLASS):
            self._skip += 1
            return
        if self._skip:
            return
        if tag in _HEAD:
            self._head = _HEAD[tag]
            self._head_buf = []
            return
        if tag in {"br", "hr"}:
            self.parts.append("\n")
        elif tag in _BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in _SKIP_TAGS:
            if self._skip:
                self._skip -= 1
            return
        if self._skip:
            return
        if tag in _HEAD and self._head is not None:
            title = " ".join("".join(self._head_buf).split())
            if title:
                self.parts.append("\n" + self._head + title + "\n")
            self._head = None
            self._head_buf = []
            return
        if tag in _BLOCK:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip or not data:
            return
        if self._head is not None:
            self._head_buf.append(data)
            return
        self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _HTMLToText()
    parser.feed(html or "")
    parser.close()
    raw = "".join(parser.parts)
    raw = raw.replace("\xa0", " ")
    raw = re.sub(r"[ \t]+", " ", raw)
    raw = re.sub(r" *\n *", "\n", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip() + "\n"


def looks_like_paper_html(html: str) -> bool:
    low = (html or "").lower()
    if len(html or "") < 400:
        return False
    if "html is not available" in low or "no html" in low:
        return False
    return "abstract" in low and ("<article" in low or "<h1" in low or "<h2" in low)


def outline_from_text(text: str, *, limit: int = 40) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for i, line in enumerate((text or "").splitlines(), start=1):
        t = line.strip()
        if not t:
            continue
        level = 0
        title = ""
        m = _HEADING_LINE.match(t)
        if m:
            level = len(m.group(1))
            title = m.group(2).strip()
        elif _NAMED.match(t):
            level = 2
            title = t
        elif _NUMBERED.match(t) and len(t) < 140:
            level = 2
            title = t
        if not title or title.lower() in seen:
            continue
        # skip running headers / tiny junk
        if len(title) < 3 or title.lower() in {"arxiv", "preprint"}:
            continue
        seen.add(title.lower())
        rows.append({"line": i, "level": level or 2, "title": title[:160]})
        if len(rows) >= limit:
            break
    return rows
