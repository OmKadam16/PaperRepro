# Architecture

## Goal
A research workbench that follows the research process: find a gap (stage 1), plan the paper (2), make figures (3), cite sources (4), review the draft (5). Never invent a source.

## Stages and modules
| Stage | Pipeline | Helpers (`agents/*.md` + `agents/*.py`) | Deterministic parts |
|---|---|---|---|
| 1 Find a gap | `gapfinder.py` | idea_framer, gap_analyst, novelty_checker | `tools/literature.py` (OpenAlex) |
| 2 Plan | — | — | `templates.py` (guide + .docx outline) |
| 3 Figures | `figures.py` (describe) | caption_writer | `web/figures.js` (SVG charts) |
| 4 Cite | `pipeline.py` | ocr, claim_finder, source_judge | `cite.py`, `tools/reader.py`, `tools/segment.py` |
| 5 Review | `reviewing.py` | reviewer | `measures.py` |

Gap study honesty: papers are numbered P1..Pn for the model; code maps ids back, drops unknown ids, drops gaps with no valid evidence, and turns an "addressed" verdict that names no paper into "partly_addressed".

## Stage 4 (Cite) flow
```
upload (.pdf .docx .txt .md, or pasted text)
  -> reader       tools/reader.py     text layer; scanned PDF pages -> PNG
  -> OCR          agents/ocr.py       LLM transcribes scanned pages verbatim
  -> segment      tools/segment.py    paragraphs -> sentences (conservative splitter)
  -> claim finder agents/claim_finder.py  which sentences need a source, + 2-3 search queries
  -> literature   tools/literature.py OpenAlex (+ Semantic Scholar with a key); real records only
  -> source judge agents/source_judge.py  supports / related / unrelated per candidate
  -> person picks sources in the web app
  -> cite         cite.py             markers + reference list (Numbered, IEEE, APA); .docx / text export
```
`pipeline.py` runs these steps, saving `projects/<id>/project.json` after each sentence so the page can show progress live. Searching and judging run 4 sentences at a time.

## Honesty rules (enforced in code, not just prompts)
- A `Source` is built only from an API record. The judge sees candidates and may only return their ids; unknown ids are dropped.
- A `supports` verdict needs an abstract **and** a quote that appears verbatim in it; otherwise it is downgraded to `related`, and quotes not found in the abstract are erased.
- Only sources that survived judging are stored with the project.
- The server refuses to cite a source for a sentence it was not found for.
- References are formatted by `cite.py` from the stored metadata.

## State
`Project` (pydantic, `state.py`): `draft` (paragraphs -> sentences with stable ids like `p3s2`), `claims`, `sources`, `matches`, `chosen` (sentence id -> source ids), `style`. Persisted atomically.

## Web app
`server.py` (stdlib `http.server`, one background AI worker) serves `web/shell.html` with one script per page (`web/dashboard.js`, `gap.js`, `plan.js`, `figures.js`, `cite.js`, `review.js`) on top of `web/core.js` (helpers, the process rail, the progress card) and `web/app.css`. Records: `projects/<id>/project.json` (drafts), `projects/gap|review|figure/<id>/*.json`.

Safety: binds 127.0.0.1; checks Host and Origin; writes need the `X-PaperRepro: 1` header; ids, sizes, file types and styles are validated; all page text is rendered with `textContent`.

## Privacy
The draft's text goes to the LLM provider (reading, finding claims, judging). Only short keyword queries go to OpenAlex / Semantic Scholar. Drafts are stored in `projects/` (gitignored).

## LLM layer
`llm.py`: one `structured()` call (optional page image for OCR), OpenAI Responses API or Anthropic, one schema-validation retry, per-helper model via `PAPERREPRO_MODEL_<AGENT>`.
