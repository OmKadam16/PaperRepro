/* Research tab, tool 1: the gap this project started from, its question, and the path ahead. */
(function () {
  "use strict";
  var el = PR.el;

  PR.pages.research = function (main, D) {
    var R = PR.R;
    document.title = "PaperRepro: " + R.title;
    var grid = el("div", { class: "ov-grid" }, main), left = el("div", {}, grid), right = el("div", {}, grid);

    el("span", { class: "lab", style: "display:block;margin-bottom:8px;color:var(--accent)" }, left, "Research project · started " + PR.ago(R.created_at));
    var title = el("input", { class: "titlefield", value: R.title, "aria-label": "Project title" }, left);
    el("label", { class: "f", for: "q", style: "margin-top:22px" }, left, "Research question");
    var q = el("textarea", { id: "q", class: "qfield", rows: 2 }, left); q.value = R.question || "";
    var saved = el("div", { class: "msg" }, left, " ");
    var t;
    function save() {
      clearTimeout(t); saved.textContent = "saving…";
      t = setTimeout(function () {
        PR.api("/api/r/" + R.id, { title: title.value, question: q.value }).then(function (x) {
          PR.R = x; saved.textContent = "saved";
          var tab = document.querySelector('.tab[aria-current="page"] .ti'); if (tab) tab.textContent = x.title;
          var rt = document.querySelector(".toolnav .rtitle"); if (rt) rt.textContent = x.title;
        }).catch(function (e) { saved.textContent = e.message; });
      }, 600);
    }
    title.addEventListener("input", save); q.addEventListener("input", save);

    var g = R.gap;
    if (g) {
      var c = el("article", { class: "sheet gapcard", style: "margin-top:20px" }, left);
      var tr = el("div", { style: "display:flex;gap:12px;align-items:center;flex-wrap:wrap" }, c);
      el("span", { class: "lab" }, tr, "The gap");
      el("span", { class: "stamp " + g.novelty }, tr, PR.NOVELTY[g.novelty]);
      el("span", { class: "kind" }, tr, PR.KIND[g.kind] || g.kind);
      el("h3", {}, c, g.title);
      el("p", { class: "desc" }, c, g.description);
      var meta = el("div", { class: "meta" }, c);
      var a = el("div", {}, meta); el("b", {}, a, "Why it's open"); PR.paperRefs(a, g.why_open, R.papers);
      var b = el("div", {}, meta); el("b", {}, b, "How you could study it"); b.appendChild(document.createTextNode(g.approach));
      if (g.novelty_reason) { var nv = el("div", { style: "margin-top:14px;font-size:15.5px;color:var(--muted);line-height:1.5" }, c); el("b", { style: "font-family:var(--ui);font-size:12px;color:var(--ink);display:block;margin-bottom:4px" }, nv, "Novelty check"); PR.paperRefs(nv, g.novelty_reason, R.papers); }
      var ps = el("div", { class: "papers" }, c);
      el("div", { class: "lab", style: "margin-bottom:4px" }, ps, "Evidence from the literature");
      g.evidence_ids.forEach(function (id) { PR.paperLine(ps, R.papers[id]); });
      if (g.addressing_ids.length) { el("div", { class: "lab", style: "margin:10px 0 4px;color:var(--rel)" }, ps, "Already working on it"); g.addressing_ids.forEach(function (id) { PR.paperLine(ps, R.papers[id]); }); }
      if (R.chat_id) el("a", { class: "more", href: "/chat/" + R.chat_id, style: "display:inline-block;margin-top:14px" }, c, "← back to the conversation this came from");
    } else {
      el("p", { class: "empty", style: "padding:20px 0" }, left, "This project wasn't started from a gap search. Set the question above, or start a new conversation to find a gap.");
    }

    el("h2", { style: "font-family:var(--display);font-weight:390;font-size:24px;margin:0 0 12px" }, right, "Your path");
    var path = el("ol", { class: "sheet pad path", style: "padding:14px" }, right);
    var done = { plan: !!R.template, figures: R.figures, cite: R.drafts, review: R.reviews };
    var next = !R.figures ? "figures" : !R.drafts ? "cite" : !R.reviews ? "review" : null;
    var DESC = { plan: "pick a template, follow the guide, get an outline", figures: "turn your data into journal-ready charts",
                 cite: "upload the draft; find and cite sources", review: "get a peer review before you submit" };
    PR.TOOLS.slice(1).forEach(function (tl) {
      var li = el("li", {}, path), a = el("a", { href: PR.link(tl.path), class: (done[tl.key] && tl.key !== "plan" ? "has" : "") + (tl.key === next ? " next" : "") }, li);
      el("span", { class: "n" }, a, done[tl.key] && tl.key !== "plan" ? "✓" : String(tl.n));
      var mid = el("span", {}, a); el("div", { class: "t" }, mid, tl.name); el("div", { class: "d" }, mid, DESC[tl.key]);
      el("span", { class: "c" }, a, tl.key === "figures" ? R.figures + " made" : tl.key === "cite" ? R.drafts + " draft" + (R.drafts === 1 ? "" : "s") + (R.citations ? ", " + R.citations + " cited" : "") : tl.key === "review" ? R.reviews + " done" : "→");
    });
    el("p", { class: "fine", style: "margin-top:20px" }, right, "Everything in this tab belongs to this project only. Open more projects from the chat; each gets its own tab.");
  };
})();
