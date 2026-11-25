# PaperRepro

**Find the published sources behind every claim in your draft.**

Upload an essay or paper (PDF, Word, text; scans are read with OCR). PaperRepro marks the sentences that need a source, searches the published literature for each, and checks every match against its abstract. You see your draft on the left and the sources on the right; tick the ones you want and the citations and reference list are written for you, in Numbered, IEEE or APA style. Export to Word or copy the text.

```
uv pip install -e ".[dev,pdf,openai]"
echo 'OPENAI_API_KEY=sk-...' > .env      # gitignored
paperrepro serve                         # then open http://127.0.0.1:8765
```

Optional: `SEMANTIC_SCHOLAR_API_KEY=...` in `.env` adds Semantic Scholar to the search (its keyless pool is usually rate-limited).

## What it will not do
- Invent a paper. Every source is a real database record with a DOI or link.
- Show a quote that is not in the paper's abstract.
- Mark a paper as "supports" without an abstract to check it against.

Verdicts are an assistant's reading of abstracts. Open the paper before you rely on it.

## Cost
Helpers run on `gpt-6.1-terra` ($1 / $5 per million tokens). A 10-page draft is typically a few cents to about $0.20. Change models per helper in `.env`, e.g. `PAPERREPRO_MODEL_SOURCE_JUDGE=gpt-6.2-sol`.

See [ARCHITECTURE.md](ARCHITECTURE.md) for how it works and [PLAN.md](PLAN.md) for what is next.
