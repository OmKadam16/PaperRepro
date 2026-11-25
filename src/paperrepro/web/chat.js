/* Home: chat with the Research Guide; searches show as cards; "Start research" opens a tab. */
(function () {
  "use strict";
  var el = PR.el;
  var IDEAS = [
    "I'm curious whether short-form video before bed affects teenagers' sleep",
    "Can LLMs grade programming assignments as reliably as teaching assistants?",
    "Something about green spaces and air pollution in South Asian cities",
    "Better uncertainty estimates for neural networks on medical tabular data",
  ];
  var C = null, main, thread, input, send, pollT, sending = false;

  PR.pages.chat = function (m, D) {
    main = m; C = D.chat;
    document.title = C ? "PaperRepro: " + C.title : "PaperRepro: find your research";
    PR.side(C && C.id);
    draw();
    watch();
  };

  function busy() {
    if (!C) return false;
    if (C.busy || C.status === "queued" || C.status === "working") return true;
    return Object.keys(C.studies || {}).some(function (k) { var s = C.studies[k]; return PR.WORKING[s.status] || s.busy; });
  }
  function watch() {
    clearTimeout(pollT);
    if (!busy()) return;
    pollT = setTimeout(function () {
      PR.get("/api/chat/" + C.id).then(function (x) { var changed = JSON.stringify(x) !== JSON.stringify(C); C = x; if (changed) drawThread(); watch(); }).catch(watch);
    }, 1800);
  }

  function draw() {
    main.textContent = "";
    main.style.padding = "0";
    main.style.maxWidth = "none";
    var wrap = el("div", { class: "chatwrap" }, main);
    if (!C || !C.messages.length) {
      var e = el("div", { class: "chat-empty" }, wrap);
      var h = el("h1", {}, e); h.appendChild(document.createTextNode("What do you want to ")); el("em", {}, h, "research?");
      el("p", {}, e, "Tell me the idea however rough it is. I'll ask what I need, search the published literature, and show you the gaps worth filling. Pick one and press Start research to open it as a project.");
      composer(e);
      var chips = el("div", { class: "chips", style: "margin-top:16px" }, e);
      IDEAS.forEach(function (x) { var c = el("button", { class: "chip", type: "button" }, chips, x); c.addEventListener("click", function () { input.value = x; input.focus(); grow(); }); });
      thread = null;
      setTimeout(function () { input.focus(); }, 30);
      return;
    }
    thread = el("div", { class: "thread", "aria-live": "polite" }, wrap);
    composer(wrap);
    drawThread();
  }

  function composer(parent) {
    var c = el("div", { class: "composer" }, parent), box = el("div", { class: "box" }, c);
    input = el("textarea", { rows: 1, placeholder: C ? "Reply, narrow it down, or ask for a different angle…" : "e.g. I want to study whether…", "aria-label": "Message", maxlength: 4000 }, box);
    send = el("button", { class: "send", type: "button", "aria-label": "Send", disabled: !!PR.D.can_run }, box);
    PR.icon(send, PR.ICONS.send);
    el("div", { class: "hint" }, c, "Enter to send · Shift+Enter for a new line · searches read about 45 papers and take 1–3 minutes");
    input.addEventListener("input", grow);
    input.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); } });
    send.addEventListener("click", submit);
  }
  function grow() { input.style.height = "auto"; input.style.height = Math.min(220, input.scrollHeight) + "px"; }

  function submit() {
    var text = input.value.trim();
    if (!text || sending || busy()) return;
    sending = true; send.disabled = true;
    var wasNew = !C;
    PR.api("/api/chat", { chat_id: C ? C.id : "", text: text }).then(function (x) {
      C = x; input.value = ""; sending = false;
      if (wasNew) { history.replaceState(null, "", "/chat/" + C.id); draw(); } else drawThread();
      watch();
    }).catch(function (e) { PR.toast(e.message); sending = false; send.disabled = false; });
  }

  function drawThread() {
    if (!thread) return draw();
    var atBottom = window.innerHeight + window.scrollY >= document.body.scrollHeight - 80;
    thread.textContent = "";
    C.messages.forEach(function (m) {
      if (m.role === "user") { el("div", { class: "msg-u" }, thread, m.text); return; }
      var a = el("div", { class: "msg-a" }, thread), av = el("div", { class: "av", "aria-hidden": "true" }, a);
      PR.icon(av, PR.ICONS.gap);
      var body = el("div", {}, a);
      if (m.study_id) study(body, C.studies[m.study_id]);
      else prose(el("div", { class: "tx" }, body), m.text);
    });
    var searching = Object.keys(C.studies || {}).some(function (k) { return PR.WORKING[C.studies[k].status]; });
    if ((C.busy || C.status === "queued" || C.status === "working") && !searching) {  // the search card shows its own progress
      var a = el("div", { class: "msg-a" }, thread), av = el("div", { class: "av" }, a); PR.icon(av, PR.ICONS.gap);
      var t = el("div", { class: "typing", "aria-label": "thinking" }, a); el("i", {}, t); el("i", {}, t); el("i", {}, t);
    }
    if (send) send.disabled = busy() || !!PR.D.can_run;
    if (atBottom || sending) window.scrollTo(0, document.body.scrollHeight);
  }

  function prose(node, text) {  // **bold** only; everything else stays plain text
    String(text || "").split(/\*\*([^*]+)\*\*/).forEach(function (part, i) {
      if (i % 2) el("b", {}, node, part); else node.appendChild(document.createTextNode(part));
    });
  }

  function study(parent, S) {
    var card = el("div", { class: "study" }, parent);
    if (!S) { el("div", { class: "live" }, card, "This search is no longer available."); return; }
    var sh = el("div", { class: "sh" }, card);
    el("b", {}, sh, PR.WORKING[S.status] ? "Searching the literature" : S.status === "error" ? "The search stopped" : S.gaps.length + " gaps from " + Object.keys(S.papers).length + " papers");
    el("span", { class: "msg", style: "margin:0" }, sh, PR.short(S.idea, 90));
    if (PR.WORKING[S.status]) {
      var idx = !S.framing ? 0 : !Object.keys(S.papers).length ? 1 : !S.gaps.length ? 2 : 3;
      var live = el("div", { class: "live" }, card); el("span", { class: "spin" }, live); live.appendChild(document.createTextNode(S.progress || "Starting…"));
      var ms = el("div", { class: "mini-steps", "aria-hidden": "true" }, card);
      for (var i = 0; i < 4; i++) el("i", { class: i < idx ? "d" : i === idx ? "n" : "" }, ms);
      return;
    }
    if (S.status === "error") { el("div", { class: "msg err" }, card, S.error); return; }
    if (S.themes.length) {
      var th = el("div", { class: "themes-inline" }, card);
      S.themes.forEach(function (t) { el("span", { title: t.summary }, th, t.name + " · " + t.paper_ids.length); });
    }
    S.gaps.forEach(function (g, i) { gapmini(card, S, g, i); });
  }

  function gapmini(parent, S, g, i) {
    var c = el("div", { class: "gapmini " + g.novelty }, parent);
    var top = el("div", { style: "display:flex;gap:10px;align-items:center;flex-wrap:wrap" }, c);
    el("span", { class: "gn" }, top, "Gap " + (i + 1));
    el("span", { class: "stamp " + g.novelty }, top, PR.NOVELTY[g.novelty]);
    el("span", { class: "kind" }, top, PR.KIND[g.kind] || g.kind);
    el("h4", {}, c, g.title);
    el("p", {}, c, g.description);
    el("div", { class: "rq" }, c, g.question);
    var det = el("details", {}, c);
    el("summary", {}, det, "why it's open · evidence (" + g.evidence_ids.length + " papers)");
    var w = el("p", { style: "margin-top:8px" }, det); PR.paperRefs(w, g.why_open, S.papers);
    if (g.novelty_reason) { var nv = el("p", { style: "margin-top:8px" }, det); el("b", { style: "font-family:var(--ui);font-size:12px;color:var(--ink)" }, nv, "Novelty check: "); PR.paperRefs(nv, g.novelty_reason, S.papers); }
    var ps = el("div", { class: "papers", style: "margin-top:8px" }, det);
    g.evidence_ids.forEach(function (id) { PR.paperLine(ps, S.papers[id]); });
    var acts = el("div", { class: "acts" }, c);
    var existing = (C.started || {})[S.id + ":" + g.title];
    if (existing) { el("a", { class: "btn sm line", href: "/r/" + existing }, acts, "Open project →"); return; }
    var go = el("button", { class: "btn sm go", type: "button" }, acts, "Start research →");
    go.addEventListener("click", function () {
      go.disabled = true; go.textContent = "Creating project…";
      PR.api("/api/research", { study_id: S.id, gap: i, chat_id: C.id }).then(function (x) { location.href = "/r/" + x.id; })
        .catch(function (e) { PR.toast(e.message); go.disabled = false; go.textContent = "Start research →"; });
    });
    el("span", { class: "msg", style: "margin:0" }, acts, "opens a new tab with plan, figures, cite and review for this gap");
  }
})();
