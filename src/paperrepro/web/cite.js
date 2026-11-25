/* Stage 4, Cite: upload a draft, then the two-pane editor (manuscript + source cards). */
(function () {
  "use strict";
  var el = PR.el, STAGE = PR.STAGES[3];

  // ================================================================ upload + list
  PR.pages.cite = function (main, D) {
    document.title = "PaperRepro: cite";
    PR.head(main, STAGE, "Every claim deserves", "its source.",
      "Drop in your draft. We mark the sentences that need a source, search the published literature for each, check every match against its abstract, and write the citations you pick.");
    var two = el("div", { class: "two" }, main);
    var left = el("div", {}, two), tray = el("div", { class: "tray" }, two);
    el("div", { class: "sh s1" }, tray); el("div", { class: "sh s2" }, tray);
    var drop = el("div", { class: "drop" }, tray);
    PR.icon(drop, PR.ICONS.upload, "icon");
    el("div", { class: "big" }, drop, "Drop your draft here");
    el("div", { class: "small" }, drop, "PDF · Word (.docx) · text  —  scanned pages welcome");
    var file = el("input", { type: "file", accept: ".pdf,.docx,.txt,.md,.markdown,.tex", hidden: true, "aria-label": "Choose your draft" }, drop);
    var choose = el("button", { class: "btn", type: "button" }, drop, "Choose a file");
    var msg = el("div", { class: "msg", role: "status" }, drop);
    el("div", { class: "or" }, drop, "or");
    var pb = el("button", { class: "pastebtn", type: "button" }, drop, "paste your text instead");
    var paste = el("div", { class: "paste", hidden: true }, drop);
    var ta = el("textarea", { class: "big", rows: 7, placeholder: "Paste a few paragraphs (or the whole thing)…", "aria-label": "Your text" }, paste);
    var prow = el("div", { class: "row" }, paste);
    el("span", { class: "small" }, prow, "");
    var go = el("button", { class: "btn", type: "button" }, prow, "Find sources");
    if (D.can_run) { choose.disabled = true; go.disabled = true; }
    function busy(t) { msg.className = "msg"; msg.textContent = ""; el("span", { class: "spin" }, msg); msg.appendChild(document.createTextNode("  " + t)); }
    function fail(t) { msg.className = "msg err"; msg.textContent = t; choose.disabled = false; go.disabled = false; }
    PR.uploadFile = function (f, endpoint, onId) {
      if (!f) return;
      if (!/\.(pdf|docx|txt|md|markdown|tex)$/i.test(f.name)) return fail("Use a PDF, a Word file (.docx) or a text file.");
      if (f.size > 25 * 1024 * 1024) return fail("That file is over 25 MB.");
      busy("Uploading " + f.name + "…");
      fetch(endpoint, { method: "POST", headers: { "X-PaperRepro": "1", "X-Filename": encodeURIComponent(f.name), "Content-Type": "application/octet-stream" }, body: f })
        .then(function (r) { return r.json().then(function (x) { if (!r.ok) throw new Error(x.error); return x; }); })
        .then(function (x) { onId(x.id); }).catch(function (e) { fail(e.message || "Upload failed."); });
    };
    function up(f) { choose.disabled = true; PR.uploadFile(f, "/api/upload", function (id) { location.href = "/d/" + id; }); }
    choose.addEventListener("click", function () { file.click(); });
    file.addEventListener("change", function () { up(file.files[0]); });
    ["dragenter", "dragover"].forEach(function (ev) { drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.add("over"); }); });
    ["dragleave", "drop"].forEach(function (ev) { drop.addEventListener(ev, function (e) { e.preventDefault(); drop.classList.remove("over"); }); });
    drop.addEventListener("drop", function (e) { if (!D.can_run) up(e.dataTransfer.files[0]); });
    pb.addEventListener("click", function () { paste.hidden = !paste.hidden; if (!paste.hidden) ta.focus(); });
    go.addEventListener("click", function () {
      if (ta.value.trim().length < 40) return fail("Paste at least a few sentences.");
      go.disabled = true; busy("Sending…");
      PR.api("/api/paste", { text: ta.value, title: ta.value.trim().split("\n")[0].slice(0, 60) })
        .then(function (x) { location.href = "/d/" + x.id; }).catch(function (e) { fail(e.message); });
    });

    el("p", { class: "lab", style: "margin:0 0 14px" }, left, "How it works");
    [["We read it", "Text straight from your file; scanned pages by OCR, word for word."],
     ["We search and check", "Each claim is searched in OpenAlex, and each match is checked against its abstract."],
     ["You tick, we cite", "Citations go into your text in Numbered, IEEE or APA style; the reference list builds itself."]].forEach(function (x, i) {
      var r = el("div", { style: "display:grid;grid-template-columns:34px 1fr;gap:12px;margin-bottom:18px" }, left);
      el("span", { class: "stn", style: "width:30px;height:30px;border-radius:50%;background:var(--ink);color:var(--paper);display:grid;place-items:center;font-family:var(--mono);font-size:12px" }, r, String(i + 1));
      var t = el("div", {}, r); el("div", { style: "font-family:var(--display);font-size:20px;font-weight:430" }, t, x[0]);
      el("div", { style: "color:var(--muted);font-size:16px;line-height:1.5" }, t, x[1]);
    });
    el("h2", { style: "font-family:var(--display);font-weight:390;font-size:27px;margin:60px 0 16px" }, main, "Your drafts");
    PR.ledger(main, D.drafts || [], {
      empty: "Nothing here yet. Your first draft will appear here.", icon: "cite",
      href: function (d) { return "/d/" + d.id; }, title: function (d) { return d.title || d.filename; },
      sub: function (d) { return d.status === "ready" ? d.with_sources + " of " + d.claims + " claims have sources · " + d.cited + " cited" : d.status === "error" ? "stopped" : d.progress; },
    });
  };

  // ================================================================ editor
  var P, sel = null, pane, redraw;
  function matchesFor(sid) { return P.matches.filter(function (m) { return m.sentence_id === sid; }); }
  function claimFor(sid) { return P.claims.filter(function (c) { return c.sentence_id === sid; })[0]; }
  function claimOrder() {
    var ids = {}; P.claims.forEach(function (c) { ids[c.sentence_id] = 1; });
    var out = []; P.draft.paragraphs.forEach(function (p) { p.sentences.forEach(function (s) { if (ids[s.id]) out.push(s.id); }); });
    return out;
  }
  function checkedIds() { var d = {}; P.matches.forEach(function (m) { d[m.sentence_id] = 1; }); return d; }
  function select(sid) {
    sel = sid; redraw();
    if (sid) { var n = document.querySelector('[data-sid="' + sid + '"]'); if (n) n.scrollIntoView({ block: "center", behavior: "smooth" }); pane.classList.add("open"); pane.scrollTop = 0; }
    else pane.classList.remove("open");
  }
  function refresh(x) { P = x; redraw(); }

  PR.pages.editor = function (main, D) {
    P = D.project;
    document.title = "PaperRepro: " + (P.draft.title || P.filename);
    var bar = el("div", { class: "bar2" }, main);
    var desk = el("div", { class: "desk" }, main), left = el("div", {}, desk);
    pane = el("aside", { class: "pane", "aria-label": "Sources" }, desk);
    redraw = function () { drawBar(bar); drawLeft(left); drawPane(); };
    redraw();
    document.addEventListener("keydown", function (e) {
      if (/TEXTAREA|INPUT|SELECT/.test(e.target.tagName)) return;
      var order = claimOrder(), i = order.indexOf(sel);
      if (e.key === "j") { select(order[Math.min(order.length - 1, i + 1)] || order[0]); e.preventDefault(); }
      if (e.key === "k") { select(order[Math.max(0, i - 1)] || order[0]); e.preventDefault(); }
      if (e.key === "Escape") select(null);
    });
    watch();
  };
  function watch() {
    if (!(PR.WORKING[P.status] || P.busy)) return;
    PR.poll("/api/d/" + P.id, function (x) { return PR.WORKING[x.status] || x.busy; }, function (x) { refresh(x); });
  }

  function drawBar(bi) {
    bi.textContent = "";
    el("a", { class: "ghost", href: "/cite", style: "text-decoration:none" }, bi, "← drafts");
    el("div", { class: "docname", title: P.filename }, bi, P.draft.title || P.filename);
    var meter = el("div", { class: "meter" }, bi);
    function m(n, t) { var s = el("span", {}, meter); el("b", {}, s, String(n)); s.appendChild(document.createTextNode(" " + t)); }
    m(P.claims.length, "claims"); m(Object.keys(checkedIds()).length, "with sources"); m(Object.keys(P.chosen).length, "cited");
    var seg = el("div", { class: "seg", role: "group", "aria-label": "Citation style" }, bi);
    ["numbered", "ieee", "apa"].forEach(function (s) {
      var b = el("button", { type: "button", "aria-pressed": P.style === s ? "true" : "false" }, seg, P.style_names[s]);
      b.addEventListener("click", function () { if (P.style !== s) PR.api("/api/d/" + P.id + "/style", { style: s }).then(refresh).catch(function (e) { PR.toast(e.message); }); });
    });
    var copy = el("button", { class: "btn line sm", type: "button" }, bi, "Copy text");
    copy.addEventListener("click", function () {
      fetch("/api/d/" + P.id + "/export.txt").then(function (r) { return r.text(); }).then(function (t) {
        return navigator.clipboard.writeText(t).then(function () { PR.toast("Copied, with " + P.references.length + " reference" + (P.references.length === 1 ? "" : "s")); });
      }).catch(function () { PR.toast("Could not copy. Use Download instead."); });
    });
    el("a", { class: "btn sm", href: "/api/d/" + P.id + "/export.docx" }, bi, "Download .docx");
  }

  function drawLeft(left) {
    left.textContent = "";
    if (PR.WORKING[P.status] || P.status === "error" || P.busy) progress(left);
    var ms = el("article", { class: "manuscript" }, left);
    if (!P.draft.paragraphs.length) { el("p", { class: "para", style: "color:var(--faint);font-style:italic" }, ms, "Your draft will appear here as soon as it has been read."); return; }
    var checked = checkedIds(), claims = {};
    P.claims.forEach(function (c) { claims[c.sentence_id] = 1; });
    P.draft.paragraphs.forEach(function (p, pi) {
      if (p.kind === "heading") { var t = p.sentences[0].text; el(pi === 0 && t === P.draft.title ? "h2" : "div", { class: pi === 0 && t === P.draft.title ? "ttl" : "hd" }, ms, t); return; }
      var para = el("p", { class: p.kind === "references" ? "refs" : "para" }, ms);
      p.sentences.forEach(function (s, i) {
        if (i) para.appendChild(document.createTextNode(" "));
        if (p.kind === "references") { para.appendChild(document.createTextNode(s.text)); return; }
        var ms_ = matchesFor(s.id), cls = "s";
        if (P.chosen[s.id]) cls += " cited claim";
        else if (ms_.length) cls += " claim" + (ms_.some(function (m) { return m.verdict === "supports"; }) ? "" : " rel-only");
        else if (claims[s.id]) cls += checked[s.id] || P.status === "ready" ? " nosrc" : " waiting";
        else cls += " plain";
        if (sel === s.id) cls += " sel";
        var span = el("span", { class: cls, "data-sid": s.id, tabindex: claims[s.id] ? "0" : null, role: "button" }, para);
        var mk = P.markers[s.id], m = mk ? s.text.match(/([.!?;:]+["'”’)\]]*)\s*$/) : null;
        if (mk && m) { span.appendChild(document.createTextNode(s.text.slice(0, m.index))); el("span", { class: "mk" }, span, " " + mk); span.appendChild(document.createTextNode(m[1])); }
        else { span.appendChild(document.createTextNode(s.text)); if (mk) el("span", { class: "mk" }, span, " " + mk); }
        span.addEventListener("click", function () { select(sel === s.id ? null : s.id); });
        span.addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(s.id); } });
      });
    });
    if (P.references.length) {
      var rb = el("section", { class: "refblock" }, ms);
      el("h3", {}, rb, P.draft.paragraphs.some(function (p) { return p.kind === "references"; }) ? "Added references" : "References");
      var ol = el("ol", {}, rb); P.references.forEach(function (r) { el("li", {}, ol, r); });
    }
  }

  var startedChecking = null;
  function progress(left) {
    var order = ["reading", "finding_claims", "searching", "ready"];
    var stage = P.status === "checking" ? "searching" : P.status === "queued" ? "reading" : P.status;
    var idx = P.status === "error" ? -1 : order.indexOf(stage), total = P.claims.length, done = Object.keys(checkedIds()).length;
    var eta = P.progress || "Starting…";
    if (stage === "searching" && total) {
      if (!startedChecking) startedChecking = { t: Date.now(), d: done };
      var rate = (Date.now() - startedChecking.t) / 1000 / Math.max(1, done - startedChecking.d);
      eta = done + " of " + total + " sentences checked · " + PR.mins(done > startedChecking.d ? rate * (total - done) : total * 2) + " left";
    }
    PR.progress(left, {
      head: P.status === "error" ? "Something went wrong" : P.busy && P.busy.indexOf("find:") === 0 ? "Searching for one more sentence" :
        { reading: "Reading your draft", finding_claims: "Finding the sentences that need sources", searching: "Searching and checking sources", ready: "Ready" }[stage],
      eta: P.status === "error" ? "" : eta, idx: idx, done: stage === "ready", error: P.status === "error" ? P.error : "",
      pct: P.status === "error" ? 0 : { reading: 8, finding_claims: 20, ready: 100 }[stage] || 22 + 76 * (total ? done / total : 0),
      steps: [["Read the draft", "text layer first; OCR for scanned pages", P.draft.ocr_pages.length ? P.draft.ocr_pages.length + " page(s) by OCR" : ""],
              ["Find sentences that need a source", "facts, findings and prior work, not your own results", total ? total + " found" : ""],
              ["Search the literature and check each match", "OpenAlex index; abstracts read and judged", total ? done + " / " + total : ""],
              ["Ready to cite", "tick the papers you want", ""]],
    });
  }

  function drawPane() {
    var keep = pane.scrollTop;
    pane.textContent = "";
    var x = el("button", { class: "ghost sheet-close", type: "button" }, pane, "close ✕");
    x.addEventListener("click", function () { select(null); });
    var sentence = null;
    P.draft.paragraphs.forEach(function (p) { p.sentences.forEach(function (s) { if (s.id === sel) sentence = s; }); });
    if (!sel || !sentence) return overview();
    var order = claimOrder(), i = order.indexOf(sel), c = claimFor(sel), ms = matchesFor(sel), busyHere = P.busy === "find:" + sel;
    var head = el("div", { class: "head" }, pane);
    el("div", { class: "lab" }, head, c ? "Sources for this sentence" : "This sentence");
    el("div", { class: "quote" }, head, sentence.text);
    if (c) el("div", { class: "claimline" }, head, "claim: " + c.claim + "   ·   searched: " + c.queries.join(" / "));
    if (i >= 0) {
      var nav = el("div", { class: "navp" }, head);
      var pv = el("button", { type: "button", disabled: i <= 0 }, nav, "‹ prev"); pv.addEventListener("click", function () { select(order[i - 1]); });
      el("span", {}, nav, (i + 1) + " / " + order.length);
      var nx = el("button", { type: "button", disabled: i >= order.length - 1 }, nav, "next ›"); nx.addEventListener("click", function () { select(order[i + 1]); });
      el("span", { style: "margin-left:auto;color:var(--faint)" }, nav, "j / k");
    }
    function findMore(btn) { btn.disabled = true; PR.api("/api/d/" + P.id + "/find", { sentence_id: sel }).then(function (x) { refresh(x); watch(); }).catch(function (e) { PR.toast(e.message); btn.disabled = false; }); }
    if (!ms.length) {
      var none = el("div", { class: "none" }, pane);
      if (busyHere) { var pp = el("p", {}, none); el("span", { class: "spin" }, pp); pp.appendChild(document.createTextNode("  Searching the literature for this sentence…")); }
      else if (PR.WORKING[P.status] && c) el("p", {}, none, "Still searching for this one.");
      else {
        el("p", {}, none, c ? "No published paper we found clearly backs this sentence. It may be your own point, or the wording is unusual." : "This sentence was not flagged as needing a source.");
        var b = el("button", { class: "btn line", type: "button", disabled: !!P.busy || PR.WORKING[P.status] }, none, c ? "Search again" : "Find sources anyway");
        b.addEventListener("click", function () { findMore(b); });
      }
      return;
    }
    var chosen = P.chosen[sel] || [];
    ms.forEach(function (m) {
      var s = P.sources[m.source_id]; if (!s) return;
      var on = chosen.indexOf(s.id) >= 0;
      var card = el("article", { class: "card" + (on ? " on" : "") }, pane);
      var tr = el("div", { class: "top-r" }, card);
      el("span", { class: "stamp " + m.verdict }, tr, m.verdict === "supports" ? "SUPPORTS" : "RELATED");
      el("span", {}, tr, String(s.year || "n.d.")); if (s.cited_by != null) el("span", {}, tr, "cited " + s.cited_by.toLocaleString() + "×");
      var h = el("h4", {}, card), u = PR.safeUrl(s.url);
      if (u) el("a", { href: u, target: "_blank", rel: "noopener noreferrer" }, h, s.title); else h.textContent = s.title;
      el("div", { class: "by" }, card, PR.authors(s.authors) + (s.venue ? "  ·  " + s.venue : ""));
      el("p", { class: "why" }, card, m.reason);
      if (m.evidence) el("blockquote", {}, card, "“" + m.evidence + "”");
      var f = el("div", { class: "foot" }, card);
      el("span", { class: "found" }, f, s.doi ? "doi:" + s.doi : (s.found_by || []).join(" + "));
      var t = el("button", { class: "tick" + (on ? " on" : ""), type: "button", "aria-pressed": on ? "true" : "false" }, f);
      el("span", { class: "box", "aria-hidden": "true" }, t);
      t.appendChild(document.createTextNode(on ? "Cited " + (P.style === "apa" ? "" : "[" + P.numbers[s.id] + "]") : "Cite this"));
      t.addEventListener("click", function () {
        var cur = (P.chosen[sel] || []).filter(function (x) { return x !== s.id; });
        P.chosen[sel] = !on ? cur.concat([s.id]) : cur; redraw();  // optimistic; the server renders markers
        PR.api("/api/d/" + P.id + "/choose", { sentence_id: sel, source_id: s.id, on: !on }).then(refresh).catch(function (e) { PR.toast(e.message); });
      });
      el("span", { class: "hole", "aria-hidden": "true" }, card);
    });
    var again = el("button", { class: "more", type: "button", disabled: !!P.busy || PR.WORKING[P.status], style: "margin:6px 0 0" }, pane, busyHere ? "searching…" : "Not right? Search again for this sentence");
    again.addEventListener("click", function () { findMore(again); });
    pane.scrollTop = keep;
  }

  function overview() {
    el("div", { class: "lab", style: "margin-bottom:6px" }, pane, "How to read the highlights");
    var lg = el("div", { class: "legend" }, pane);
    [["linear-gradient(transparent 50%, var(--hi) 50%, var(--hi) 94%, transparent 94%)", "sources found; at least one directly supports it"],
     ["linear-gradient(transparent 50%, var(--hi-soft) 50%, var(--hi-soft) 94%, transparent 94%)", "only related papers found"],
     ["none", "needs a source, none found yet"]].forEach(function (x) {
      var r = el("div", {}, lg), sw = el("span", { class: "sw", style: "background:" + x[0] }, r, "text");
      if (x[0] === "none") { sw.style.color = "var(--ink)"; sw.style.textDecoration = "underline dotted var(--faint)"; }
      r.appendChild(document.createTextNode(x[1]));
    });
    el("p", { style: "font-size:16px;line-height:1.5;color:var(--muted);margin:0 0 26px" }, pane, "Click a highlighted sentence to see its sources, or any other sentence to search for one. Keys: j and k move between claims.");
    var ov = el("div", { class: "overview" }, pane);
    el("h3", {}, ov, P.references.length ? "Your references so far" : "No sources cited yet");
    if (!P.references.length) el("p", { style: "margin:4px 0 0;color:var(--muted);font-size:15.5px" }, ov, "Tick “Cite this” on a source card and it appears here.");
    P.references.forEach(function (r) {
      var row = el("div", { class: "ov-row" }, ov), mm = r.match(/^\[(\d+)\]\s*(.*)$/);
      el("span", { class: "n" }, row, mm ? mm[1] : "•"); el("span", {}, row, mm ? mm[2] : r);
    });
  }
})();
