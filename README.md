# PaperRepro

**A research workbench: from a rough idea to a paper you can stand behind.**

Open the app and you're in a **chat** with the Research Guide. Describe what you want to study; it asks what it needs, searches the published literature, and shows the gaps worth filling as cards in the conversation. Press **Start research** on one and it opens as a **project tab**, like a browser tab. Work on several at once; each tab has its own tools, holding only that project's work:

| Stage | What you do | AI helpers |
|---|---|---|
| 1 **Gap & question** | Found in the chat: sharp research questions, a map of the literature, open gaps backed by real papers and re-checked for novelty. The tab keeps the gap, its evidence and your question. | Research Guide, Idea Framer, Gap Analyst, Novelty Checker |
| 2 **Plan** | Pick a template (research article, conference paper, review, short communication, thesis chapter); follow a section-by-section guide; download a filled outline. | none (deterministic) |
| 3 **Figures** | Paste data; get line, bar, scatter or error-bar charts at real journal sizes, colourblind-safe or grayscale; export SVG or 300 dpi PNG. | Caption Writer (optional) |
| 4 **Cite** | Upload your draft; see which published papers back each sentence; tick to cite in Numbered, IEEE or APA; export Word or text. | OCR, Claim Finder, Source Judge |
| 5 **Review** | Get a structured peer review: six scored criteria, strengths, and issues tied to sentences with concrete fixes, plus exact checks by code. | Reviewer |

```
uv pip install -e ".[dev,pdf,openai]"
echo 'OPENAI_API_KEY=sk-...' > .env      # gitignored
paperrepro serve                         # then open http://127.0.0.1:8765
```

## Keys and limits
Put keys in `.env` only: `OPENAI_API_KEY` for the AI helpers, plus `OPENROUTER_API_KEY` and/or `ZAI_API_KEY` for the chat panel in each project tab. The browser never receives them. Each user gets **15 AI calls a day** (each chat message, citation run, review or caption is one call), and the counter resets at midnight UTC. The panel is text-only: requests for code are refused.

## What it will not do
- Invent a paper. Every paper shown anywhere is a real OpenAlex record with a DOI or link; helpers can only refer to papers they were shown, and code drops anything else.
- Show a quote that is not in the paper's abstract, or call a source "supports" without one.
- Propose a gap that does not point at retrieved papers, or say a gap is filled without naming the paper.
- Invent what your error bars mean in a caption.

Every AI output is an assistant's reading of abstracts or of your draft. Check before you rely on it.

## Cost
Mechanical helpers run on `gpt-6.1-terra`; the Gap Analyst and Reviewer on `gpt-6.2-sol`. In testing: a gap study about $0.10, a review or a draft's citations a few cents. Change models per helper in `.env`, e.g. `PAPERREPRO_MODEL_REVIEWER=gpt-6.1-terra`.

See [ARCHITECTURE.md](ARCHITECTURE.md) and [PLAN.md](PLAN.md).
