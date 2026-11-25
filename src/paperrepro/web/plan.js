/* Stage 2, Plan: pick a template, read the section guide, download a filled outline. */
(function () {
  "use strict";
  var el = PR.el, STAGE = PR.STAGES[1];

  PR.pages.plan = function (main, D) {
    document.title = "PaperRepro: plan your paper";
    var T = D.templates, cur = T[0], question = D.question || "";
    PR.head(main, STAGE, "Plan the paper", "before you write it.",
      "Pick the kind of paper you're writing. Each section below says what it is for, what to put in, what reviewers punish, and a sentence frame to get you started.");

    var tp = el("div", { class: "tpls", role: "group", "aria-label": "Paper templates" }, main);
    var form = el("section", { class: "sheet pad", style: "margin-bottom:30px" }, main);
    var grid = el("div", { class: "plan-grid" }, main);

    T.forEach(function (t) {
      var b = el("button", { class: "tpl", type: "button", "aria-pressed": t === cur ? "true" : "false" }, tp);
      var mini = el("div", { class: "mini", "aria-hidden": "true" }, b);
      t.sections.slice(0, 7).forEach(function (s, i) { el("i", { class: i % 2 === 0 ? "h" : "", style: "width:" + (i % 2 === 0 ? 40 + (i * 7) % 30 : 70 + (i * 13) % 30) + "%" }, mini); });
      el("h4", {}, b, t.name); el("p", {}, b, t.blurb);
      el("p", { style: "margin-top:8px;font-family:var(--mono);font-size:11px;color:var(--accent)" }, b, t.total);
      b.addEventListener("click", function () { cur = t; Array.prototype.forEach.call(tp.children, function (x) { x.setAttribute("aria-pressed", x === b ? "true" : "false"); }); drawGuide(); });
    });

    var r2 = el("div", { class: "row2" }, form);
    var a = el("div", {}, r2); el("label", { class: "f", for: "ttl" }, a, "Working title");
    var title = el("input", { id: "ttl", class: "field", placeholder: "e.g. Calibrated uncertainty for tabular clinical models" }, a);
    var b2 = el("div", {}, r2); el("label", { class: "f", for: "rq" }, b2, "Research question");
    var rq = el("input", { id: "rq", class: "field", placeholder: "From your gap study, or your own", value: question }, b2);
    var row = el("div", { style: "display:flex;gap:12px;margin-top:16px;flex-wrap:wrap;align-items:center" }, form);
    var dl = el("a", { class: "btn" }, row, "Download outline (.docx)");
    el("span", { class: "msg", style: "margin:0" }, row, "Headings, a checklist for each section, and your question in place.");
    function link() { dl.href = "/api/plan/outline.docx?t=" + cur.key + "&title=" + encodeURIComponent(title.value) + "&q=" + encodeURIComponent(rq.value); }
    title.addEventListener("input", link); rq.addEventListener("input", link);

    var toc = el("nav", { class: "sheet toc", "aria-label": "Sections" }, grid), body = el("div", {}, grid);
    function drawGuide() {
      link(); toc.textContent = ""; body.textContent = "";
      el("div", { class: "lab", style: "padding:0 8px 8px" }, toc, cur.name);
      cur.sections.forEach(function (s, i) {
        var id = "sec-" + i;
        var a = el("a", { href: "#" + id }, toc); el("span", { class: "i" }, a, String(i + 1)); el("span", {}, a, s.name); el("span", { class: "w" }, a, s.words);
        var sec = el("section", { class: "sheet guide-sec", id: id }, body);
        el("h3", {}, sec, s.name); el("div", { class: "len" }, sec, "typical length: " + s.words + (s.words === "—" ? "" : " words"));
        el("p", { class: "purpose" }, sec, s.purpose);
        el("h5", {}, sec, "Put in");
        var ul = el("ul", { class: "do" }, sec); s.include.forEach(function (x) { el("li", {}, ul, x); });
        el("h5", {}, sec, "Avoid");
        var ul2 = el("ul", { class: "avoid" }, sec); s.avoid.forEach(function (x) { el("li", {}, ul2, x); });
        var st = el("div", { class: "starter" }, sec); el("b", {}, st, "Sentence frame"); st.appendChild(document.createTextNode(s.starter));
        if (s.name === "References") el("a", { class: "btn line sm", href: "/cite", style: "margin-top:14px" }, sec, "Go to Cite →");
        if (/Results|Experiments/.test(s.name)) el("a", { class: "btn line sm", href: "/figures", style: "margin-top:14px" }, sec, "Make the figures →");
      });
      var fin = el("section", { class: "sheet guide-sec" }, body);
      el("h3", {}, fin, "Before you submit");
      var ul3 = el("ul", { class: "do" }, fin);
      ["Every claim that relies on others' work has a citation", "Every figure is referenced in the text and has a full caption",
       "Numbers in the abstract match the results", "Limitations are stated, not hidden", "You've read the target venue's author guide, including the length limit"].forEach(function (x) { el("li", {}, ul3, x); });
      el("a", { class: "btn sm", href: "/review", style: "margin-top:16px" }, fin, "Get a review →");
    }
    drawGuide();
  };
})();
