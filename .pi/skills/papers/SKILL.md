---
name: papers
description: Download an arXiv paper and read it in slices (outline, grep, capped read). Load when you need the full text of a paper, not just the abstract from search_papers.
---

# Skill: papers

`search_papers` only returns title + short abstract. Full text is this pack. **You do not download PDFs yourself** — the tools fetch from arXiv.

Vendor Python **has network**. `search_papers` tries OpenAlex first, then arXiv Atom. Atom 429/timeout does **not** mean fetch is offline (`arxiv.org/html/...` is a different host). Never write `papers_fetch.py` (or scrape `arxiv.org/search` HTML) in the lab.

The **Experiment Designer** may `deep_research` / `fetch_paper` / `search_paper` / `read_paper` when proposing (slices only). The **Reviewer** may slice-check a claimed citation. The Experimenter must not fetch papers. Do not dump `paper.txt` into a packet.

If the user wants a random paper / 随便看一篇: `random_paper` (optional `query` / `category`). It picks and downloads. Then `read_paper(section="Abstract")`.

If `search_papers` / `deep_research` returns empty: **do not invent an arXiv id**, **do not call search_papers again this turn**, and **do not design experiments from textbooks with empty `papers`**. Retry `deep_research` next turn, or `fetch_paper` a known id from DIRECTIONS. `random_paper` still hits Atom and is not a literature substitute. Fetch HTML does not use Atom. Never scrape `arxiv.org/search`.

Otherwise:

1. `fetch_paper(paper_id)` once. Writes `<lab>/papers/<id>/paper.txt`, returns **outline + line count**, never the body.
2. `search_paper(paper_id, query)` to jump to a method / equation / dataset.
3. `read_paper(paper_id, start_line=..., n_lines<=80)` or `section="Abstract"`. If `truncated`, continue with `start_line=next_line`.

Do **not** ingest `paper.txt` with Pi `read`/`grep` end-to-end. Do **not** ask `read_paper` for the whole file. Cap is 80 lines / 6000 chars on purpose.
