/* Stage 1, Find a gap: describe an idea -> framing, field map, checked gaps. */
(function () {
  "use strict";
  var el = PR.el, STAGE = PR.STAGES[0];
  var EXAMPLES = [
    "Does short-form video use before bed affect sleep quality in teenagers?",
    "Can large language models grade programming assignments as reliably as teaching assistants?",
    "How do urban green spaces change personal air-pollution exposure in South Asian cities?",
    "I want to improve uncertainty estimates of neural networks on tabular medical data.",
  ];
  var NOVELTY = { open: "OPEN", partly_addressed: "PARTLY ADDRESSED", addressed: "ADDRESSED", unchecked: "NOT CHECKED" };
  var KIND = { unstudied: "not yet studied", contradictory: "findings conflict", narrow_evidence: "thin evidence", method: "needs a better method", population: "untested setting", replication: "needs replication" };

  PR.pages.gaps = function (main, D) {
    document.title = "PaperRepro: find a research gap";
    PR.head(main, STAGE, "Find the gap", "worth filling.",
      "Describe what you want to research, however rough. We sharpen it into questions, read the published literature on it, map what's been done, and propose the open gaps, each checked against a fresh search.");
    var box = el("section", { class: "sheet idea-box" }, main);
    el("label", { class: "f", for: "idea" }, box, "Your research idea");
    var ta = el("textarea", { id: "idea", class: "big", maxlength: 4000, placeholder: "e.g. I'm interested in whether… / I want to build… / Why does…" }, box);
    var chips = el("div", { class: "chips" }, box);
    EXAMPLES.forEach(function (x) { var c = el("button", { class: "chip", type: "button" }, chips, x); c.addEventListener("click", function () { ta.value = x; ta.focus(); }); });
    var row = el("div", { style: "display:flex;justify-content:space-between;align-items:center;gap:16px;margin-top:20px;flex-wrap:wrap" }, box);
    var msg = el("div", { class: "msg", role: "status", style: "margin:0" }, row, "Takes 1–3 minutes. Reads around 45 papers.");
    var go = el("button", { class: "btn", type: "button", disabled: !!D.can_run }, row, "Find the gaps →");
    go.addEventListener("click", function () {
      if (ta.value.trim().length < 15) { msg.className = "msg err"; msg.textContent = "Describe the idea in at least a sentence."; return; }
      go.disabled = true; msg.className = "msg"; msg.textContent = "Starting…";
      PR.api("/api/gap", { idea: ta.value }).then(function (x) { location.href = "/gap/" + x.id; })
        .catch(function (e) { msg.className = "msg err"; msg.textContent = e.message; go.disabled = false; });
    });
    el("h2", { style: "font-family:var(--display);font-weight:390;font-size:27px;margin:56px 0 16px" }, main, "Your gap studies");
    PR.ledger(main, D.studies || [], {
      empty: "No studies yet. Describe an idea above to start one.", icon: "gap",
      href: function (s) { return "/gap/" + s.id; }, title: function (s) { return s.idea; },
      sub: function (s) { return s.status === "ready" ? s.gaps + " gaps from " + s.papers + " papers" : s.progress; },
    });
  };

  var S;
  PR.pages.gap = function (main, D) {
    S = D.study;
    document.title = "PaperRepro: gaps in " + PR.short(S.idea, 60);
    draw(main);
    if (PR.WORKING[S.status] || S.busy) PR.poll("/api/gap/" + S.id, function (x) { return PR.WORKING[x.status] || x.busy; }, function (x) { S = x; draw(main); });
  };

  function paperRefs(parent, text) {
    String(text || "").split(/«([^»]+)»/).forEach(function (part, i) {
      if (i % 2 === 0) { parent.appendChild(document.createTextNode(part)); return; }
      var p = S.papers[part];
      if (!p) { parent.appendChild(document.createTextNode("a paper")); return; }
      var u = PR.safeUrl(p.url), label = (p.authors[0] ? p.authors[0].split(" ").slice(-1)[0] + (p.authors.length > 1 ? " et al." : "") : PR.short(p.title, 30)) + " " + (p.year || "");
      if (u) el("a", { href: u, target: "_blank", rel: "noopener noreferrer", title: p.title, style: "color:var(--accent)" }, parent, label);
      else el("span", { title: p.title }, parent, label);
    });
  }
  function paperLine(parent, id) {
    var p = S.papers[id]; if (!p) return;
    var r = el("div", { class: "paperline" }, parent);
    el("span", { class: "y" }, r, String(p.year || "n.d."));
    var t = el("span", {}, r), u = PR.safeUrl(p.url);
    if (u) el("a", { href: u, target: "_blank", rel: "noopener noreferrer" }, t, p.title); else t.textContent = p.title;
    t.appendChild(document.createTextNode("  · " + PR.authors(p.authors)));
  }

  function draw(main) {
    main.textContent = "";
    var top = el("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:22px;gap:12px" }, main);
    el("a", { class: "ghost", href: "/gap", style: "text-decoration:none" }, top, "← all studies");
    el("span", { class: "when" }, top, PR.ago(S.created_at) + (S.tokens_used ? " · " + Math.round(S.tokens_used / 1000) + "k tokens" : ""));
    var h = el("header", { class: "page-head" }, main), l = el("div", {}, h);
    el("span", { class: "stage" }, l, "Stage 1 of 5 · Find a gap");
    el("h1", { style: "font-size:clamp(28px,3.4vw,44px);line-height:1.12" }, l, S.idea);

    var working = PR.WORKING[S.status];
    if (working || S.status === "error") {
      var checked = S.gaps.filter(function (g) { return g.novelty !== "unchecked"; }).length;
      var idx = !S.framing ? 0 : !Object.keys(S.papers).length ? 1 : !S.gaps.length ? 2 : 3;
      PR.progress(main, {
        head: S.status === "error" ? "Something went wrong" : ["Framing your idea", "Searching the literature", "Reading the papers and mapping the field", "Checking each gap is still open"][idx],
        eta: S.status === "error" ? "" : S.progress, idx: S.status === "error" ? -1 : idx, error: S.status === "error" ? S.error : "",
        pct: [8, 22, 45, 60 + 38 * (S.gaps.length ? checked / S.gaps.length : 0)][idx],
        steps: [["Frame the idea", "research questions and search terms", S.framing ? S.framing.questions.length + " questions" : ""],
                ["Search the literature", "OpenAlex, several angles at once", Object.keys(S.papers).length ? Object.keys(S.papers).length + " papers" : ""],
                ["Map the field", "themes, then gaps backed by the papers", S.gaps.length ? S.gaps.length + " gaps" : ""],
                ["Check novelty", "a fresh search per gap, to catch work that already fills it", S.gaps.length ? checked + " / " + S.gaps.length : ""]],
      });
    }

    if (S.framing) {
      var fr = el("section", { class: "sheet framing" }, main);
      el("div", { class: "lab" }, fr, S.framing.field);
      el("p", { style: "font-size:19px;line-height:1.55;margin:8px 0 14px" }, fr, S.framing.summary);
      el("h3", {}, fr, "Candidate research questions");
      var ol = el("ol", {}, fr);
      S.framing.questions.forEach(function (q) {
        var li = el("li", {}, ol); li.appendChild(document.createTextNode(q + "  "));
        el("a", { href: "/plan?q=" + encodeURIComponent(q), class: "more", style: "font-size:11.5px" }, li, "plan a paper →");
      });
      if (S.framing.assumptions.length) el("p", { class: "msg", style: "margin-top:14px" }, fr, "Assumed: " + S.framing.assumptions.join("; "));
    }

    if (S.themes.length) {
      el("h2", { style: "font-family:var(--display);font-weight:390;font-size:27px;margin:8px 0 14px" }, main, "What the field has done");
      var th = el("div", { class: "themes" }, main);
      S.themes.forEach(function (t) {
        var c = el("div", { class: "sheet theme" }, th);
        el("h4", {}, c, t.name); el("p", {}, c, t.summary);
        el("div", { class: "n" }, c, t.paper_ids.length + " paper" + (t.paper_ids.length === 1 ? "" : "s"));
      });
    }

    if (S.gaps.length) {
      var gh = el("div", { style: "display:flex;justify-content:space-between;align-items:baseline;margin:10px 0 14px;gap:12px;flex-wrap:wrap" }, main);
      el("h2", { style: "font-family:var(--display);font-weight:390;font-size:27px;margin:0" }, gh, "Gaps you could fill");
      el("span", { class: "msg", style: "margin:0" }, gh, "open ones first · based on the " + Object.keys(S.papers).length + " papers retrieved, not the whole literature");
      S.gaps.forEach(function (g) {
        var c = el("article", { class: "sheet gapcard", style: g.novelty === "addressed" ? "opacity:.72;border-left-color:var(--rule-2)" : "" }, main);
        var tr = el("div", { style: "display:flex;gap:12px;align-items:center;flex-wrap:wrap" }, c);
        el("span", { class: "stamp " + g.novelty }, tr, NOVELTY[g.novelty]);
        el("span", { class: "kind" }, tr, KIND[g.kind] || g.kind);
        el("h3", {}, c, g.title);
        el("p", { class: "desc" }, c, g.description);
        el("div", { class: "rq" }, c, g.question);
        var meta = el("div", { class: "meta" }, c);
        var a = el("div", {}, meta); el("b", {}, a, "Why it's open"); paperRefs(a, g.why_open);
        var b = el("div", {}, meta); el("b", {}, b, "How you could study it"); b.appendChild(document.createTextNode(g.approach));
        if (g.novelty_reason) { var nv = el("div", { style: "margin-top:14px;font-size:15.5px;color:var(--muted);line-height:1.5" }, c); el("b", { style: "font-family:var(--ui);font-size:12px;color:var(--ink);display:block;margin-bottom:4px" }, nv, "Novelty check"); paperRefs(nv, g.novelty_reason); }
        var ps = el("div", { class: "papers" }, c);
        el("div", { class: "lab", style: "margin-bottom:4px" }, ps, "Evidence from the literature");
        g.evidence_ids.forEach(function (id) { paperLine(ps, id); });
        if (g.addressing_ids.length) { el("div", { class: "lab", style: "margin:10px 0 4px;color:var(--rel)" }, ps, "Already working on it"); g.addressing_ids.forEach(function (id) { paperLine(ps, id); }); }
        var act = el("div", { class: "gap-actions" }, c);
        el("a", { class: "btn sm", href: "/plan?q=" + encodeURIComponent(g.question) }, act, "Plan a paper on this →");
        var cp = el("button", { class: "btn line sm", type: "button" }, act, "Copy question");
        cp.addEventListener("click", function () { navigator.clipboard.writeText(g.question).then(function () { PR.toast("Question copied"); }); });
      });
    }

    var ids = Object.keys(S.papers);
    if (ids.length && S.status === "ready") {
      var det = el("details", { class: "sheet pad", style: "margin-top:26px" }, main);
      el("summary", { style: "cursor:pointer;font-family:var(--ui);font-weight:600" }, det, "All " + ids.length + " papers read");
      var list = el("div", { class: "papers", style: "margin-top:14px" }, det);
      ids.sort(function (a, b) { return (S.papers[b].year || 0) - (S.papers[a].year || 0); }).forEach(function (id) { paperLine(list, id); });
    }
  }
})();
