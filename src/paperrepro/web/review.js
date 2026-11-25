/* Stage 5, Review: upload a draft -> exact checks + a structured peer review. */
(function () {
  "use strict";
  var el = PR.el, STAGE = PR.STAGES[4];
  var REC = { ready: ["Ready to submit", "--ok"], minor_revision: ["Minor revision", "--ok"], major_revision: ["Major revision", "--warn"], not_ready: ["Not ready yet", "--bad"] };

  PR.pages.reviews = function (main, D) {
    document.title = "PaperRepro: review";
    PR.head(main, STAGE, "Is it", "ready?",
      "Upload your draft for a structured peer review: scores on six criteria, the strengths, and every major and minor issue tied to the sentences that cause it, with a concrete fix. Plus exact checks on structure, length and citations.");
    var two = el("div", { class: "two" }, main), left = el("div", {}, two), tray = el("div", { class: "tray" }, two);
    el("div", { class: "sh s1" }, tray); el("div", { class: "sh s2" }, tray);
    var drop = el("div", { class: "drop" }, tray);
    PR.icon(drop, PR.ICONS.review, "icon");
    el("div", { class: "big" }, drop, "Drop the draft to review");
    el("div", { class: "small" }, drop, "PDF · Word (.docx) · text");
    var file = el("input", { type: "file", accept: ".pdf,.docx,.txt,.md,.markdown,.tex", hidden: true }, drop);
    var choose = el("button", { class: "btn", type: "button", disabled: !!D.can_run }, drop, "Choose a file");
    var msg = el("div", { class: "msg", role: "status" }, drop);
    el("div", { class: "or" }, drop, "or");
    var pb = el("button", { class: "pastebtn", type: "button" }, drop, "paste your text instead");
    var paste = el("div", { class: "paste", hidden: true }, drop);
    var ta = el("textarea", { class: "big", rows: 7, placeholder: "Paste the draft…" }, paste);
    var go = el("button", { class: "btn", type: "button", disabled: !!D.can_run, style: "margin-top:12px" }, paste, "Review it");
    function fail(t) { msg.className = "msg err"; msg.textContent = t; choose.disabled = false; go.disabled = false; }
    function up(f) {
      if (!f) return;
      if (!/\.(pdf|docx|txt|md|markdown|tex)$/i.test(f.name)) return fail("Use a PDF, a Word file (.docx) or a text file.");
      choose.disabled = true; msg.className = "msg"; msg.textContent = "Uploading " + f.name + "…";
      fetch("/api/review/upload", { method: "POST", headers: { "X-PaperRepro": "1", "X-Research": PR.R.id, "X-Filename": encodeURIComponent(f.name), "Content-Type": "application/octet-stream" }, body: f })
        .then(function (r) { return r.json().then(function (x) { if (!r.ok) throw new Error(x.error); return x; }); })
        .then(function (x) { location.href = PR.link("/review/" + x.id); }).catch(function (e) { fail(e.message); });
    }
    choose.addEventListener("click", function () { file.click(); });
    file.addEventListener("change", function () { up(file.files[0]); });
    ["dragenter", "dragover"].forEach(function (ev) { drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("over"); }); });
    ["dragleave", "drop"].forEach(function (ev) { drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove("over"); }); });
    drop.addEventListener("drop", function (e) { if (!D.can_run) up(e.dataTransfer.files[0]); });
    pb.addEventListener("click", function () { paste.hidden = !paste.hidden; });
    go.addEventListener("click", function () {
      if (ta.value.trim().length < 40) return fail("Paste at least a few sentences.");
      go.disabled = true;
      PR.api("/api/review/paste", { research_id: PR.R.id, text: ta.value, title: ta.value.trim().split("\n")[0].slice(0, 60) }).then(function (x) { location.href = PR.link("/review/" + x.id); }).catch(function (e) { fail(e.message); });
    });
    el("p", { class: "lab", style: "margin:0 0 14px" }, left, "What you get");
    [["Six scores", "originality, clarity, methods, evidence, structure and significance, each explained"],
     ["Issues you can act on", "major problems first, pointed at the exact sentences, each with a concrete fix"],
     ["Exact checks", "missing sections, length, very long sentences and uncited text, counted by code, not guessed"]].forEach(function (x, i) {
      var r = el("div", { style: "display:grid;grid-template-columns:34px 1fr;gap:12px;margin-bottom:18px" }, left);
      el("span", { style: "width:30px;height:30px;border-radius:50%;background:var(--ink);color:var(--paper);display:grid;place-items:center;font-family:var(--mono);font-size:12px" }, r, String(i + 1));
      var t = el("div", {}, r); el("div", { style: "font-family:var(--display);font-size:20px;font-weight:430" }, t, x[0]);
      el("div", { style: "color:var(--muted);font-size:16px;line-height:1.5" }, t, x[1]);
    });
    el("h2", { style: "font-family:var(--display);font-weight:390;font-size:27px;margin:56px 0 16px" }, main, "Your reviews");
    PR.ledger(main, D.reviews || [], {
      empty: "No reviews yet.", icon: "review", href: function (r) { return PR.link("/review/" + r.id); }, title: function (r) { return r.title; },
      sub: function (r) { return r.recommendation ? REC[r.recommendation][0] : r.progress; },
    });
  };

  var R;
  PR.pages.review = function (main, D) {
    R = D.review;
    draw(main);
    if (PR.WORKING[R.status] || R.busy) PR.poll("/api/review/" + R.id, function (x) { return PR.WORKING[x.status] || x.busy; }, function (x) { R = x; draw(main); });
  };

  function sentenceText(id) { var t = ""; R.draft.paragraphs.forEach(function (p) { p.sentences.forEach(function (s) { if (s.id === id) t = s.text; }); }); return t; }
  function ring(parent, avg, color) {
    var s = el("svg:svg", { viewBox: "0 0 120 120", class: "ring", "aria-label": "average score " + avg.toFixed(1) + " of 5" }, parent);
    var C = 2 * Math.PI * 50;
    el("svg:circle", { cx: 60, cy: 60, r: 50, fill: "none", stroke: "var(--paper-2)", "stroke-width": 12 }, s);
    el("svg:circle", { cx: 60, cy: 60, r: 50, fill: "none", stroke: "var(" + color + ")", "stroke-width": 12, "stroke-linecap": "round",
                       "stroke-dasharray": C * avg / 5 + " " + C, transform: "rotate(-90 60 60)" }, s);
    el("svg:text", { x: 60, y: 66, "text-anchor": "middle", "font-family": "Fraunces, Georgia, serif", "font-size": 30, fill: "var(--ink)" }, s, avg.toFixed(1));
    el("svg:text", { x: 60, y: 84, "text-anchor": "middle", "font-family": "JetBrains Mono, monospace", "font-size": 9, fill: "var(--muted)" }, s, "OUT OF 5");
  }

  function draw(main) {
    main.textContent = "";
    document.title = "PaperRepro: review of " + (R.draft.title || R.filename);
    var top = el("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:22px;gap:12px" }, main);
    el("a", { class: "ghost", href: PR.link("/review"), style: "text-decoration:none" }, top, "← all reviews");
    el("span", { class: "when" }, top, PR.ago(R.created_at) + (R.tokens_used ? " · " + Math.round(R.tokens_used / 1000) + "k tokens" : ""));
    var h = el("header", { class: "page-head" }, main), l = el("div", {}, h);
    el("span", { class: "stage" }, l, "Stage 5 of 5 · Review");
    el("h1", { style: "font-size:clamp(28px,3.4vw,46px);line-height:1.1" }, l, R.draft.title || R.filename);

    if (PR.WORKING[R.status] || R.status === "error") {
      var idx = !R.measures ? 0 : 1;
      PR.progress(main, { head: R.status === "error" ? "Something went wrong" : ["Reading your draft", "The reviewer is reading closely"][idx],
        eta: R.status === "error" ? "" : R.progress, idx: R.status === "error" ? -1 : idx, pct: [15, 55][idx], error: R.status === "error" ? R.error : "",
        steps: [["Read the draft", "text layer, OCR for scans", R.measures ? R.measures.words.toLocaleString() + " words" : ""],
                ["Exact checks and peer review", "structure counted by code; review by the Reviewer helper", ""],
                ["Report", "scores, strengths, issues with fixes", ""]] });
      if (!R.review) return;
    }
    var rv = R.review, M = R.measures;
    if (rv) {
      var avg = rv.scores.reduce(function (a, s) { return a + s.score; }, 0) / Math.max(1, rv.scores.length), rec = REC[rv.recommendation];
      var vb = el("section", { class: "sheet verdict-big" }, main);
      ring(vb, avg, rec[1]);
      var vt = el("div", {}, vb);
      el("h2", { style: "color:var(" + rec[1] + ")" }, vt, rec[0]);
      el("p", {}, vt, rv.summary);
      var sc = el("div", { class: "scores" }, main);
      rv.scores.forEach(function (s) {
        var c = el("div", { class: "sheet score" }, sc), t = el("div", { class: "top" }, c);
        el("h4", {}, t, s.criterion); el("span", { class: "val" }, t, s.score + "/5");
        var bar = el("div", { class: "bar" }, c);
        el("i", { style: "width:" + s.score * 20 + "%;background:var(" + (s.score >= 4 ? "--ok" : s.score >= 3 ? "--warn" : "--bad") + ")" }, bar);
        el("p", {}, c, s.comment);
      });
    }
    var grid = el("div", { class: "rv-grid" }, main), left = el("div", {}, grid), right = el("div", {}, grid);
    if (rv) {
      el("h2", { style: "font-family:var(--display);font-weight:390;font-size:26px;margin:0 0 14px" }, left, "What to fix");
      if (!rv.issues.length) el("p", { class: "empty" }, left, "The reviewer found nothing to fix.");
      rv.issues.forEach(function (i) {
        var c = el("article", { class: "sheet issue " + i.severity }, left);
        el("span", { class: "sev" }, c, i.severity);
        el("p", {}, c, i.issue);
        i.sentence_ids.slice(0, 3).forEach(function (sid) { var t = sentenceText(sid); if (t) el("div", { class: "where" }, c, "“" + PR.short(t, 220) + "”"); });
        var fx = el("div", { class: "fix" }, c); el("b", {}, fx, "Fix"); fx.appendChild(document.createTextNode(i.fix));
      });
    }
    if (M) {
      el("h2", { style: "font-family:var(--display);font-weight:390;font-size:26px;margin:0 0 14px" }, right, "Exact checks");
      var ck = el("div", { class: "sheet checks" }, right);
      function row(ok, label, v) { var r = el("div", { class: "ck" }, ck); el("span", { style: "color:var(" + (ok ? "--ok" : "--warn") + ");font-weight:700" }, r, ok ? "✓" : "!"); el("span", {}, r, label); el("span", { class: "v" }, r, v); }
      row(!M.sections_missing.length, M.sections_missing.length ? "Missing: " + M.sections_missing.join(", ") : "All core sections present", M.sections_found.length + " found");
      row(true, "Length", M.words.toLocaleString() + " words");
      row(M.avg_sentence_words <= 25, "Average sentence", M.avg_sentence_words + " words");
      row(M.long_sentences <= 2, "Sentences over 40 words", String(M.long_sentences));
      row(M.citation_markers > 0, "Citations in the text", String(M.citation_markers));
      row(M.has_references, "Reference list", M.has_references ? "yes" : "no");
      row(M.passive_ratio < 0.4, "Sentences in the passive voice", Math.round(M.passive_ratio * 100) + "%");
      var nx = el("div", { style: "display:flex;gap:10px;flex-wrap:wrap;margin:16px 0 26px" }, right);
      if (M.citation_markers < 5 || !M.has_references) el("a", { class: "btn sm", href: PR.link("/cite") }, nx, "Find sources for it →");
      if (M.sections_missing.length) el("a", { class: "btn line sm", href: PR.link("/plan") }, nx, "See the section guide →");
    }
    if (rv && rv.strengths.length) {
      el("h2", { style: "font-family:var(--display);font-weight:390;font-size:26px;margin:0 0 14px" }, right, "What works");
      var st = el("ul", { class: "sheet pad strengths", style: "margin:0;padding-left:44px;font-size:16.5px;line-height:1.5" }, right);
      rv.strengths.forEach(function (s) { el("li", {}, st, s); });
    }
    el("p", { class: "fine" }, main, "This review is an AI reading of your draft, meant to catch problems early. It cannot check facts against sources it hasn't seen, and it is no substitute for a colleague or the venue's own reviewers.");
  }
})();
