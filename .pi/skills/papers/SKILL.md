---
name: papers
description: Download an arXiv paper and read it in slices (outline, grep, capped read). Load when you need the full text of a paper, not just the abstract from search_papers.
---

# Skill: papers

`search_papers` only returns title + short abstract. Full text is this pack. **You do not download PDFs yourself** — the tools fetch from arXiv.

If the user wants a random paper / 随便看一篇: `random_paper` (optional `query` / `category`). It picks and downloads. Then `read_paper(section="Abstract")`.

Otherwise:

1. `fetch_paper(paper_id)` once. Writes `<lab>/papers/<id>/paper.txt`, returns **outline + line count**, never the body.
2. `search_paper(paper_id, query)` to jump to a method / equation / dataset.
3. `read_paper(paper_id, start_line=..., n_lines<=80)` or `section="Abstract"`. If `truncated`, continue with `start_line=next_line`.

Do **not** ingest `paper.txt` with Pi `read`/`grep` end-to-end. Do **not** ask `read_paper` for the whole file. Cap is 80 lines / 6000 chars on purpose.
