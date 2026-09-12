"""Best-effort TeX source → readable text (sections kept as markdown headings)."""

from __future__ import annotations

import re

_SECTION = re.compile(r"\\(part|chapter|section|subsection|subsubsection)\*?\{([^{}]*)\}")
_LEVEL = {"part": "# ", "chapter": "# ", "section": "## ", "subsection": "### ", "subsubsection": "#### "}
_MACRO = re.compile(r"\\[a-zA-Z]+\*?")
_BRACE = re.compile(r"[{}]")


def tex_to_text(src: str) -> str:
    lines_out: list[str] = []
    for raw in (src or "").splitlines():
        line = raw.split("%", 1)[0]
        if not line.strip():
            lines_out.append("")
            continue
        chunks: list[str] = []
        pos = 0
        for m in _SECTION.finditer(line):
            chunks.append(_strip_tex(line[pos : m.start()]))
            chunks.append("\n" + _LEVEL.get(m.group(1), "## ") + m.group(2).strip() + "\n")
            pos = m.end()
        chunks.append(_strip_tex(line[pos:]))
        lines_out.append("".join(chunks))
    text = "\n".join(lines_out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def _strip_tex(s: str) -> str:
    s = s.replace("~", " ").replace("\\&", "&").replace("\\%", "%")
    s = _MACRO.sub(" ", s)
    s = _BRACE.sub("", s)
    return re.sub(r"[ \t]+", " ", s).strip()
