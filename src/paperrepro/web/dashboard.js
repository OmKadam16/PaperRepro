/* Dashboard: the research journey, what exists at each stage, what to do next. */
(function () {
  "use strict";
  var el = PR.el;
  var BLURB = {
    gap: "Describe your idea. Get research questions and the gaps in the literature.",
    plan: "Pick a paper template and follow a section-by-section writing guide.",
    figures: "Turn your data into charts sized and styled for your venue.",
    cite: "Find published papers that back each claim, and cite them.",
    review: "Get a structured peer review before you submit.",
  };

  PR.pages.dashboard = function (main, D) {
    document.title = "PaperRepro: your research desk";
    var c = D.counts || {}, recent = D.recent || [];
    var h = el("h1", { class: "welcome" }, main);
    h.appendChild(document.createTextNode("From a rough idea to a paper "));
    el("em", {}, h, "you can stand behind.");

    var next = !c.gap ? "gap" : !c.plan_visited ? "plan" : !c.figures ? "figures" : !c.cite ? "cite" : !c.review ? "review" : null;
    var ns = el("div", { class: "nextstep" }, main);
    if (next) {
      var st = PR.STAGES.filter(function (s) { return s.key === next; })[0];
      ns.appendChild(document.createTextNode(next === "gap" ? "Start where research starts: what are you curious about?" : "Next on your path: " + st.name.toLowerCase() + "."));
      el("a", { class: "btn", href: st.href }, ns, next === "gap" ? "Describe your idea →" : "Go to " + st.name + " →");
    } else ns.appendChild(document.createTextNode("You've used every stage. Pick up wherever you left off."));

    var j = el("section", { class: "journey", "aria-label": "The research process" }, main);
    PR.STAGES.forEach(function (st) {
      var n = st.key === "plan" ? (c.plan_visited ? 1 : 0) : (c[st.key] || 0);
      var a = el("a", { class: "station" + (n ? " has" : "") + (st.key === next ? " next" : ""), href: st.href }, j);
      var disc = el("div", { class: "disc" }, a); PR.icon(disc, PR.ICONS[st.key]); el("span", { class: "num" }, disc, String(st.n));
      el("h3", {}, a, st.name);
      el("p", {}, a, BLURB[st.key]);
      var label = { gap: ["study", "studies"], plan: ["visit", "visits"], figures: ["figure", "figures"], cite: ["draft", "drafts"], review: ["review", "reviews"] }[st.key];
      var t = el("div", { class: "tally" }, a);
      if (st.key === "plan") t.textContent = c.plan_visited ? "templates ready" : "5 templates";
      else { el("b", {}, t, String(n)); t.appendChild(document.createTextNode(" " + label[n === 1 ? 0 : 1])); }
    });

    var g = el("div", { class: "dash-grid" }, main);
    var l = el("section", {}, g), r = el("section", {}, g);
    el("h2", {}, l, "Recent work");
    var ICON = { gap: "gap", review: "review", figure: "figures", draft: "cite" };
    PR.ledger(l, recent, {
      empty: "Nothing yet. Your gap studies, drafts, figures and reviews will collect here.",
      icon: "plan",
      href: function (d) { return d.href; }, title: function (d) { return d.title; },
      sub: function (d) { return d.kind_label + " · " + d.sub; },
    });
    // per-row icons by kind
    Array.prototype.forEach.call(l.querySelectorAll(".row-d"), function (row, i) {
      var ic = row.querySelector(".ico"); ic.textContent = ""; PR.icon(ic, PR.ICONS[ICON[recent[i].kind]]);
    });
    el("h2", {}, r, "So far");
    var tot = el("div", { class: "totals" }, r);
    [[D.totals.papers, "papers read for gaps"], [D.totals.gaps, "research gaps found"], [D.totals.citations, "citations added"],
     [D.totals.figures, "figures made"], [D.totals.reviews, "drafts reviewed"], [D.totals.tokens_k + "k", "AI tokens used"]].forEach(function (x) {
      var d = el("div", {}, tot); el("b", {}, d, String(x[0])); el("span", {}, d, x[1]);
    });
    el("p", { class: "fine" }, main, "Everything runs on this computer. Your text goes to the AI provider for the helpers that need it; only short keyword searches go to the scholarly index (OpenAlex). Every paper shown anywhere in the app is a real database record.");
  };
})();
