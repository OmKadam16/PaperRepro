# Build Plan

The paper-reproduction pipeline (Phase 0/1) is preserved at git tag `reproduction-v1`.

## v1: citation finder (this build)
- [x] Read PDF (text layer), Word (.docx), text/Markdown, pasted text; OCR for scanned PDF pages
- [x] Conservative sentence splitter; References section excluded from searching
- [x] Claim finder helper (which sentences need a source, search queries)
- [x] Literature search: OpenAlex; Semantic Scholar when a key is set
- [x] Source judge with code-enforced honesty rules (verbatim quotes, no abstract -> not "supports")
- [x] Citation styles: Numbered, IEEE, APA 7; first-appearance numbering, ranges; Word + text export
- [x] Web app: upload, live progress, manuscript + source cards, tick to cite, find sources for any sentence
- [x] Live test in the browser: 5/5 claim sentences sourced on a sample essay, ~3 cents; landmark papers ranked first

## Next
- [ ] Insert citations into the person's original .docx, keeping their formatting (today the export is a clean re-typeset)
- [ ] More styles (Chicago, Harvard, MLA) and BibTeX export
- [ ] Open-access full text (Unpaywall / arXiv) so the judge can check beyond the abstract
- [ ] Flag sentences where a found paper contradicts the claim
- [ ] Judge is still a little generous with "supports" on broad method sentences; try a second-pass check or full-text evidence
- [ ] Remember rejected sources; "more like this"
- [ ] Hosting for other people: accounts, per-user spending cap, storage limits

## Small fixes
For any agent; see AGENTS.md. Each is one file or less.
- [ ] `env.py`: `scrubbed_env` is unused since the sandbox was removed; delete it and its test.
- [ ] `tests/fixtures/synthetic_paper.pdf` text is about the old tool; replace with a short essay-like fixture.
