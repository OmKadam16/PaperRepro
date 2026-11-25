/* PaperRepro core: helpers, the process rail, the progress card, page boot.
   All text from the server or the AI is rendered with textContent, never innerHTML. */
(function () {
  "use strict";
  var NS = "http://www.w3.org/2000/svg";
  var PR = window.PR = { pages: {} };
  PR.D = JSON.parse(document.getElementById("app-data").textContent);

  PR.el = function (tag, attrs, parent, text) {
    var n = tag.indexOf("svg:") === 0 ? document.createElementNS(NS, tag.slice(4)) : document.createElement(tag);
    for (var k in (attrs || {})) {
      var v = attrs[k];
      if (v == null || v === false) continue;
      n.setAttribute(k, v === true ? "" : v);
    }
    if (text != null) n.textContent = text;
    if (parent) parent.appendChild(n);
    return n;
  };
  var el = PR.el;
  PR.icon = function (parent, paths, cls) {
    var s = el("svg:svg", { viewBox: "0 0 24 24", class: cls || "", "aria-hidden": "true", fill: "none", stroke: "currentColor",
                            "stroke-width": 1.5, "stroke-linecap": "round", "stroke-linejoin": "round" }, parent);
    paths.forEach(function (d) { el("svg:path", { d: d }, s); });
    return s;
  };
  PR.ICONS = {
    home: ["M3.5 11 12 4l8.5 7", "M5.5 9.5V20h13V9.5", "M10 20v-5h4v5"],
    gap: ["M10.5 17a6.5 6.5 0 1 0 0-13 6.5 6.5 0 0 0 0 13z", "M15.5 15.5 21 21", "M8 10.5h5"],
    plan: ["M6 3.5h9l3.5 3.5V20.5H6z", "M14.5 3.5V7.5H18.5", "M9 11h6M9 14h6M9 17h4"],
    figures: ["M4 20V4", "M4 20h16", "M7.5 16l3.5-5 3 3 4.5-7"],
    cite: ["M5 7.5c3-1.6 6.6-1.6 10 .5v12c-3.4-2.1-7-2.1-10-.5z", "M19 7.5v12", "M8 11h4M8 14h4"],
    review: ["M4.5 12.5 9 17 19.5 6.5", "M4 4.5h7M4 8h4"],
    upload: ["M7 17.5h-.5a4 4 0 0 1-.6-7.96 6 6 0 0 1 11.7-1.5A4.5 4.5 0 0 1 17.5 17.5H17", "M12 12v8.5", "M9 15l3-3 3 3"],
  };
  PR.STAGES = [
    { key: "gap", n: 1, name: "Find a gap", ds: "your idea → open questions", href: "/gap" },
    { key: "plan", n: 2, name: "Plan", ds: "templates & writing guide", href: "/plan" },
    { key: "figures", n: 3, name: "Figures", ds: "your data → journal charts", href: "/figures" },
    { key: "cite", n: 4, name: "Cite", ds: "sources for every claim", href: "/cite" },
    { key: "review", n: 5, name: "Review", ds: "is the paper ready?", href: "/review" },
  ];

  PR.api = function (path, body) {
    return fetch(path, { method: "POST", headers: { "Content-Type": "application/json", "X-PaperRepro": "1" }, body: JSON.stringify(body || {}) })
      .then(function (r) { return r.json().then(function (x) { if (!r.ok) throw new Error(x.error || "request failed"); return x; }); });
  };
  PR.get = function (path) { return fetch(path).then(function (r) { return r.json(); }); };
  var toastEl = document.getElementById("toast"), toastT;
  PR.toast = function (t) { toastEl.textContent = t; toastEl.classList.add("on"); clearTimeout(toastT); toastT = setTimeout(function () { toastEl.classList.remove("on"); }, 2800); };
  PR.safeUrl = function (u) { return /^https?:\/\//i.test(u || "") ? u : null; };
  PR.ago = function (ts) {
    var s = Date.now() / 1000 - ts;
    if (s < 60) return "just now"; if (s < 3600) return Math.round(s / 60) + " min ago";
    if (s < 86400) return Math.round(s / 3600) + " h ago";
    return new Date(ts * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short" });
  };
  PR.mins = function (s) { return s < 60 ? "under a minute" : "about " + Math.round(s / 60) + " min"; };
  PR.authors = function (a) { if (!a || !a.length) return "Unknown authors"; return a.length > 3 ? a.slice(0, 3).join(", ") + " et al." : a.join(", "); };
  PR.short = function (t, n) { t = t || ""; return t.length > n ? t.slice(0, n - 1).replace(/\s+\S*$/, "") + "…" : t; };
  PR.WORKING = { queued: 1, reading: 1, finding_claims: 1, searching: 1, checking: 1, working: 1 };
  PR.download = function (name, blob) {
    var a = el("a", { href: URL.createObjectURL(blob), download: name }, document.body);
    a.click(); setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
  };

  /* page header: stage number, big title, one-line purpose */
  PR.head = function (parent, stage, title, em, lede, right) {
    var h = el("header", { class: "page-head" }, parent), l = el("div", {}, h);
    if (stage) el("span", { class: "stage" }, l, "Stage " + stage.n + " of 5 · " + stage.name);
    var h1 = el("h1", {}, l, title);
    if (em) { h1.appendChild(document.createTextNode(" ")); el("em", {}, h1, em); }
    if (lede) el("p", {}, l, lede);
    if (right) h.appendChild(right);
    return h;
  };

  /* a list of saved items (drafts, studies, reviews, figures) */
  PR.ledger = function (parent, items, opts) {
    var led = el("div", { class: "ledger" }, parent);
    if (!items.length) { el("div", { class: "empty" }, led, opts.empty); return led; }
    items.forEach(function (d) {
      var a = el("a", { class: "row-d", href: opts.href(d) }, led);
      var ic = el("span", { class: "ico", "aria-hidden": "true" }, a); PR.icon(ic, PR.ICONS[opts.icon]);
      var mid = el("div", { style: "min-width:0" }, a);
      el("div", { class: "nm" }, mid, opts.title(d));
      el("div", { class: "sub" }, mid, opts.sub(d));
      var st = d.status === "ready" ? "ready" : d.status === "error" ? "error" : "work";
      el("span", { class: "pill " + st }, a, st === "work" ? "working" : d.status);
      el("span", { class: "when" }, a, PR.ago(d.created_at));
    });
    return led;
  };

  /* the progress clipboard: steps = [[title, detail, right]], idx = active step, pct */
  PR.progress = function (parent, o) {
    var clip = el("section", { class: "clip", "aria-live": "polite" }, parent);
    el("p", { class: "now" }, clip, o.head);
    el("div", { class: "eta" }, clip, o.eta || "");
    var tr = el("div", { class: "track", role: "progressbar", "aria-valuenow": Math.round(o.pct), "aria-valuemin": 0, "aria-valuemax": 100 }, clip);
    el("i", { style: "width:" + Math.max(0, Math.min(100, o.pct)) + "%" }, tr);
    var steps = el("ol", { class: "steps" }, clip);
    o.steps.forEach(function (x, i) {
      var cls = o.idx < 0 ? "todo" : i < o.idx ? "done" : i === o.idx ? (o.done ? "done" : "now") : "todo";
      var li = el("li", { class: cls }, steps);
      el("span", { class: "dot" }, li, cls === "done" ? "✓" : cls === "now" ? "" : String(i + 1));
      var mid = el("div", {}, li); el("div", { class: "t" }, mid, x[0]); el("div", { class: "d" }, mid, x[1]);
      el("span", { class: "r" }, li, x[2] || "");
    });
    if (o.error) el("div", { class: "err" }, clip, o.error);
    return clip;
  };

  /* poll an endpoint while `busy(x)` is true; calls onData(x) whenever it changes */
  PR.poll = function (url, busy, onData, ms) {
    var last = "";
    (function tick() {
      setTimeout(function () {
        PR.get(url).then(function (x) {
          var sig = JSON.stringify(x); if (sig !== last) { last = sig; onData(x); }
          if (busy(x)) tick();
        }).catch(tick);
      }, ms || 2000);
    })();
  };

  function rail() {
    var r = document.getElementById("rail"), D = PR.D, counts = D.counts || {};
    var b = el("a", { class: "brand", href: "/", "aria-label": "PaperRepro dashboard" }, r);
    var s = el("svg:svg", { viewBox: "0 0 32 32", "aria-hidden": "true" }, b);
    el("svg:path", { d: "M5 7.5c3-1.6 6.6-1.6 10 .5v18c-3.4-2.1-7-2.1-10-.5z", fill: "none", stroke: "currentColor", "stroke-width": 1.6, "stroke-linejoin": "round" }, s);
    el("svg:path", { d: "M27 7.5c-3-1.6-6.6-1.6-10 .5v18c3.4-2.1 7-2.1 10-.5z", fill: "none", stroke: "currentColor", "stroke-width": 1.6, "stroke-linejoin": "round" }, s);
    el("svg:path", { d: "M20 12.5h-1.5v8H20M24 12.5h1.5v8H24M22 14.5v4", fill: "none", stroke: "var(--accent)", "stroke-width": 1.6 }, s);
    el("b", {}, b, "PaperRepro");
    var home = el("a", { class: "r-home", href: "/", "aria-current": D.section === "home" ? "page" : null }, r);
    PR.icon(home, PR.ICONS.home); el("span", {}, home, "Dashboard");
    el("div", { class: "r-label" }, r, "The research process");
    var ol = el("ol", { class: "line" }, r);
    PR.STAGES.forEach(function (st) {
      var li = el("li", {}, ol);
      var a = el("a", { href: st.href, class: counts[st.key] ? "has" : null, "aria-current": D.section === st.key ? "page" : null }, li);
      el("span", { class: "stn" }, a, counts[st.key] ? "✓" : String(st.n));
      var t = el("span", {}, a); el("div", { class: "nm" }, t, st.name); el("div", { class: "ds" }, t, st.ds);
    });
    var f = el("div", { class: "rail-foot" }, r);
    el("span", {}, f, "runs on this computer");
    var th = el("button", { class: "ghost", type: "button", "aria-label": "Switch light or dark" }, f, "◐ theme");
    th.addEventListener("click", function () {
      var cur = document.documentElement.getAttribute("data-theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
      var next = cur === "dark" ? "light" : "dark";
      document.documentElement.setAttribute("data-theme", next);
      try { localStorage.setItem("pr-theme", next); } catch (e) {}
    });
  }

  PR.boot = function () {
    try { var saved = localStorage.getItem("pr-theme"); if (saved) document.documentElement.setAttribute("data-theme", saved); } catch (e) {}
    rail();
    var main = document.getElementById("main");
    if (PR.D.can_run) el("div", { class: "banner" }, main, "AI helpers are off: " + PR.D.can_run);
    var fn = PR.pages[PR.D.page];
    if (fn) fn(main, PR.D); else el("p", { class: "empty" }, main, "Page not found.");
  };
})();
