"""Stage 2: paper templates and a section-by-section writing guide. Deterministic content.

Word counts are typical ranges, not rules: always check the target venue's author guide.
"""
from __future__ import annotations

from pydantic import BaseModel

from paperrepro.cite import docx_bytes


class Section(BaseModel):
    name: str
    words: str  # typical length
    purpose: str
    include: list[str]
    avoid: list[str]
    starter: str  # a sentence frame to get going


class Template(BaseModel):
    key: str
    name: str
    blurb: str
    total: str
    sections: list[Section]


ABSTRACT = Section(
    name="Abstract", words="150–250",
    purpose="Let a busy reader decide in 30 seconds whether to read on. It is a miniature of the whole paper, not an introduction.",
    include=["One sentence of context and the problem", "What you did (data, method) in concrete terms",
             "The main result, with a number", "What it means and for whom"],
    avoid=["Citations and abbreviations you define later", "Vague promises like “results are discussed”",
           "Claims the paper does not back up"],
    starter="[Problem] limits [field/application]. We [method] on [data], and find that [main result, with a number], suggesting [implication].",
)
INTRO = Section(
    name="Introduction", words="500–900",
    purpose="Move the reader from the general area to your specific question, then show why the question matters and how you answer it.",
    include=["Context: what is known, with citations", "The gap: what is not known, and why it matters",
             "Your research question or hypothesis, stated plainly", "Your contributions as a short list",
             "A one-line roadmap of the paper (optional)"],
    avoid=["A history lesson that starts too far from the question", "Hiding the research question in paragraph five",
           "Claiming “no one has ever studied this” without checking"],
    starter="Although [what is known] [citations], it remains unclear whether [gap]. This matters because [consequence]. We ask: [research question].",
)
RELATED = Section(
    name="Related work", words="400–800",
    purpose="Position your work against the closest prior work, organised by idea rather than by paper.",
    include=["Two to four themes, each with the key papers", "For each theme: what they did and what they leave open",
             "How your work differs, in one clear sentence per theme"],
    avoid=["A list of one-paragraph summaries, one per paper", "Dismissing prior work unfairly",
           "Leaving out the paper reviewers will expect"],
    starter="Prior work on [theme] has [approach] [citations]; these studies [limitation]. In contrast, we [your difference].",
)
METHODS = Section(
    name="Methods", words="800–1,500",
    purpose="Let another researcher repeat what you did. Precision matters more than elegance here.",
    include=["Data: source, size, collection, inclusion and exclusion criteria", "Procedure or model, with every parameter that matters",
             "How you measured outcomes, and the metrics' definitions", "Statistical analysis: tests, number of runs or seeds, significance threshold",
             "Ethics approval or data licence, where relevant"],
    avoid=["“Standard settings” without saying which", "Results or interpretation (save them for later)",
           "Choices you made after seeing the results, unless you say so"],
    starter="We collected [n] [units] from [source] between [dates]. [Method] was applied with [key parameters]. We report [metric], averaged over [k] runs.",
)
RESULTS = Section(
    name="Results", words="800–1,500",
    purpose="Report what you found, in the order of your questions, with the evidence for each finding.",
    include=["One subsection or paragraph per question or hypothesis", "Numbers with uncertainty (SD, CI or SE, and say which)",
             "Figures and tables that each make one point, referenced in the text", "Negative and unexpected results"],
    avoid=["Repeating every number from a table in the prose", "Interpreting or speculating (save it for the Discussion)",
           "Error bars without saying what they show"],
    starter="[Condition] improved [metric] from [a] to [b] ([uncertainty]; Figure [n]), whereas [other condition] did not ([numbers]).",
)
DISCUSSION = Section(
    name="Discussion", words="600–1,200",
    purpose="Say what the results mean, how they fit with prior work, and where they stop.",
    include=["The main finding restated in one or two sentences", "How it agrees or disagrees with prior work, and possible reasons",
             "Limitations, stated honestly, with their likely effect", "Implications for practice or theory", "Concrete future work"],
    avoid=["Claiming more than the data show (“proves”, “always”)", "New results that were not in the Results",
           "A limitations paragraph that is only a list of excuses"],
    starter="Our results suggest that [finding], consistent with [prior work] but in contrast to [other work], possibly because [reason]. A key limitation is [limitation].",
)
CONCLUSION = Section(
    name="Conclusion", words="150–300",
    purpose="Close the loop: answer the question from the introduction, in plain words.",
    include=["The answer to your research question", "The single most important implication", "One forward-looking sentence"],
    avoid=["Repeating the abstract word for word", "New claims or citations"],
    starter="We asked whether [question]. We found [answer], which means [implication].",
)
REFERENCES = Section(
    name="References", words="—",
    purpose="Every claim that relies on someone else's work points here, in the venue's style.",
    include=["Every source cited in the text, and only those", "DOIs where available", "Consistent formatting in one style"],
    avoid=["Citing papers you have not read", "Mixing citation styles"],
    starter="Use the Cite stage to find and format these automatically.",
)

TEMPLATES = [
    Template(key="article", name="Research article", blurb="The classic empirical paper: introduction, methods, results and discussion (IMRaD).",
             total="4,000–8,000 words", sections=[ABSTRACT, INTRO, RELATED, METHODS, RESULTS, DISCUSSION, CONCLUSION, REFERENCES]),
    Template(key="conference", name="Conference paper", blurb="Compact and contribution-first, common in computer science and engineering.",
             total="4–9 pages", sections=[ABSTRACT, INTRO.model_copy(update={"words": "400–700"}), RELATED.model_copy(update={"words": "300–500"}),
                                          METHODS.model_copy(update={"name": "Method", "words": "700–1,200"}),
                                          RESULTS.model_copy(update={"name": "Experiments", "words": "700–1,200"}),
                                          CONCLUSION.model_copy(update={"name": "Conclusion and limitations"}), REFERENCES]),
    Template(key="review", name="Review article", blurb="Synthesises a body of literature to show what is known, what conflicts and what is missing.",
             total="6,000–10,000 words",
             sections=[ABSTRACT, INTRO.model_copy(update={"include": ["Why this topic needs a review now", "Scope and the questions the review answers", "How it differs from earlier reviews"]}),
                       Section(name="Search and selection", words="300–600", purpose="Show how you found and chose the literature, so readers can judge coverage.",
                               include=["Databases and search terms", "Inclusion and exclusion criteria", "How many papers were screened and kept"],
                               avoid=["“We reviewed the relevant literature” with no method"],
                               starter="We searched [databases] for [terms] published between [years], and kept [n] of [m] papers that [criteria]."),
                       Section(name="Thematic synthesis", words="3,000–6,000", purpose="The body of the review: organise findings by theme, compare them and weigh the evidence.",
                               include=["One subsection per theme", "Where studies agree, disagree, and why", "Strength of evidence (size, design) for each conclusion"],
                               avoid=["Paper-by-paper summaries", "Treating a single small study as settled"],
                               starter="Across [n] studies of [theme], [finding] held when [condition] but not when [other condition]."),
                       Section(name="Gaps and future directions", words="500–900", purpose="Turn the synthesis into a research agenda.",
                               include=["Specific open questions", "Methods that would answer them"], avoid=["Generic calls for more research"],
                               starter="No study we found has [gap]; a [design] comparing [x] and [y] would settle it."),
                       CONCLUSION, REFERENCES]),
    Template(key="short", name="Short communication", blurb="One focused finding, reported quickly. Often called a letter or brief report.",
             total="1,500–3,000 words", sections=[ABSTRACT.model_copy(update={"words": "100–150"}), INTRO.model_copy(update={"words": "250–400"}),
                                                  METHODS.model_copy(update={"words": "400–700"}), RESULTS.model_copy(update={"name": "Results and discussion", "words": "600–1,000"}),
                                                  REFERENCES]),
    Template(key="thesis", name="Thesis chapter", blurb="A self-contained chapter that still connects to the thesis as a whole.",
             total="8,000–15,000 words",
             sections=[Section(name="Chapter overview", words="200–400", purpose="Tell the examiner what this chapter does and how it fits the thesis.",
                               include=["The chapter's question", "Its link to earlier and later chapters"], avoid=["Repeating the thesis introduction"],
                               starter="Chapter [n] showed [x]; this chapter asks [question], which Chapter [n+1] builds on by [y]."),
                       INTRO.model_copy(update={"name": "Background"}), METHODS, RESULTS, DISCUSSION,
                       CONCLUSION.model_copy(update={"name": "Chapter summary"}), REFERENCES]),
]
BY_KEY = {t.key: t for t in TEMPLATES}


def outline_docx(key: str, title: str, question: str) -> bytes:
    """A ready-to-fill outline: headings, the guidance as notes, the question in place."""
    t = BY_KEY[key]
    out: list[tuple[str, str]] = [("heading", title or "Working title"),
                                  ("note", f"{t.name} · typical length {t.total}. Check your target venue's author guide.")]
    for s in t.sections:
        out.append(("heading", s.name))
        out.append(("note", f"Aim for {s.words} words. {s.purpose}"))
        for item in s.include:
            out.append(("bullet", f"☐ {item}"))
        if s.name in ("Introduction", "Background") and question:
            out.append(("body", f"Research question: {question}"))
        out.append(("body", s.starter))
    return docx_bytes(out)
