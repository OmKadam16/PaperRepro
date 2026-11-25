/* Stage 3, Figures: CSV -> publication-styled SVG charts (line, bar, scatter, error bars).
   Sizes are physical (inches, points) so a "single column" figure is really 3.5 in wide. */
(function () {
  "use strict";
  var el = PR.el, STAGE = PR.STAGES[2];
  var PRESETS = {
    single: { name: "Journal, single column", w: 3.5, h: 2.6, pt: 8 },
    double: { name: "Journal, two columns", w: 7.2, h: 3.4, pt: 8 },
    thesis: { name: "Thesis or report page", w: 6.0, h: 4.0, pt: 10 },
    slide: { name: "Slide (16:9)", w: 10, h: 5.625, pt: 18 },
  };
  var PALETTES = {
    okabe_ito: ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#000000", "#F0E442"],
    viridis: ["#440154", "#3b528b", "#21918c", "#5ec962", "#b5a800", "#7a0177"],
    grayscale: ["#000000", "#555555", "#888888", "#aaaaaa", "#333333", "#777777"],
  };
  var DASH = ["", "5 3", "2 2", "7 2 2 2", "1 3", "9 3"];
  var MARK = ["circle", "square", "triangle", "diamond", "circle", "square"];
  var FONTS = { sans: "Helvetica, Arial, sans-serif", serif: "'Times New Roman', Times, serif" };
  var SAMPLE = "epoch,baseline,baseline_sd,ensemble,ensemble_sd\n1,0.62,0.04,0.66,0.03\n2,0.71,0.03,0.75,0.02\n5,0.79,0.03,0.83,0.02\n10,0.83,0.02,0.87,0.01\n20,0.85,0.02,0.89,0.01\n40,0.86,0.02,0.90,0.01\n";

  // ---------------------------------------------------------------- data
  function parseCSV(text) {
    text = (text || "").replace(/\r\n?/g, "\n").trim();
    if (!text) return { head: [], rows: [] };
    var first = text.split("\n")[0], delim = [",", ";", "\t"].sort(function (a, b) { return first.split(b).length - first.split(a).length; })[0];
    var rows = [], row = [], cell = "", q = false;
    for (var i = 0; i < text.length; i++) {
      var ch = text[i];
      if (q) { if (ch === '"' && text[i + 1] === '"') { cell += '"'; i++; } else if (ch === '"') q = false; else cell += ch; }
      else if (ch === '"') q = true;
      else if (ch === delim) { row.push(cell); cell = ""; }
      else if (ch === "\n") { row.push(cell); rows.push(row); row = []; cell = ""; }
      else cell += ch;
    }
    row.push(cell); rows.push(row);
    var head = rows.shift().map(function (h, i) { return h.trim() || "column " + (i + 1); });
    return { head: head, rows: rows.filter(function (r) { return r.some(function (c) { return c.trim(); }); }) };
  }
  function num(v) { if (v == null) return null; var x = parseFloat(String(v).replace(/,/g, "")); return isFinite(x) ? x : null; }
  function isNumCol(d, c) { var i = d.head.indexOf(c); return i >= 0 && d.rows.length && d.rows.every(function (r) { return num(r[i]) !== null; }); }

  // ---------------------------------------------------------------- scales
  function niceTicks(lo, hi, n) {
    if (lo === hi) { lo -= 1; hi += 1; }
    var raw = (hi - lo) / n, p = Math.pow(10, Math.floor(Math.log10(raw))), m = raw / p;
    var step = (m < 1.5 ? 1 : m < 3 ? 2 : m < 7 ? 5 : 10) * p, t0 = Math.floor(lo / step) * step, out = [];
    for (var t = t0; t <= hi + step * 0.5; t += step) out.push(+t.toFixed(10));
    return out;
  }
  function logTicks(lo, hi) { var out = []; for (var e = Math.floor(Math.log10(lo)); e <= Math.ceil(Math.log10(hi)); e++) out.push(Math.pow(10, e)); return out; }
  function fmt(v) { var a = Math.abs(v); if (a !== 0 && (a >= 1e5 || a < 1e-3)) return v.toExponential(0).replace("e+", "e"); return String(+v.toPrecision(6)); }

  // ---------------------------------------------------------------- the chart
  function chart(d, sp) {
    var P = PRESETS[sp.preset] || PRESETS.single, pt = P.pt, W = P.w * 72, H = P.h * 72;
    var pal = PALETTES[sp.palette] || PALETTES.okabe_ito, font = FONTS[sp.font] || FONTS.sans, gray = sp.palette === "grayscale";
    var xi = d.head.indexOf(sp.x), ys = sp.ys.filter(function (y) { return d.head.indexOf(y) >= 0; });
    var svg = el("svg:svg", { xmlns: "http://www.w3.org/2000/svg", width: P.w + "in", height: P.h + "in", viewBox: "0 0 " + W + " " + H,
                              "font-family": font, "font-size": pt, role: "img" });
    el("svg:rect", { x: 0, y: 0, width: W, height: H, fill: "#fff" }, svg);
    if (xi < 0 || !ys.length || !d.rows.length) {
      el("svg:text", { x: W / 2, y: H / 2, "text-anchor": "middle", fill: "#888" }, svg, "Choose an x column and at least one y column");
      return svg;
    }
    var catX = sp.chart === "bar" || !isNumCol(d, sp.x);
    var series = ys.map(function (y, k) {
      var yi = d.head.indexOf(y), ei = sp.errors && sp.errors[y] ? d.head.indexOf(sp.errors[y]) : -1;
      var pts = d.rows.map(function (r, j) { return { x: catX ? j : num(r[xi]), label: r[xi], y: num(r[yi]), e: ei >= 0 ? num(r[ei]) : null }; })
        .filter(function (p) { return p.y !== null && (catX || p.x !== null) && (!sp.log_y || p.y > 0); });
      return { name: y, pts: pts, color: pal[k % pal.length], dash: gray ? DASH[k % DASH.length] : "", mark: MARK[k % MARK.length] };
    });
    var all = []; series.forEach(function (s) { s.pts.forEach(function (p) { all.push(p.y - (p.e || 0), p.y + (p.e || 0)); }); });
    if (!all.length) { el("svg:text", { x: W / 2, y: H / 2, "text-anchor": "middle", fill: "#888" }, svg, "No numeric values in the chosen columns"); return svg; }
    var lo = Math.min.apply(null, all), hi = Math.max.apply(null, all);
    if (sp.chart === "bar" && !sp.log_y) lo = Math.min(0, lo);
    var yt = sp.log_y ? logTicks(Math.max(lo, 1e-12), hi) : niceTicks(lo, hi, P.h > 3 ? 6 : 5);
    var y0 = yt[0], y1 = yt[yt.length - 1];
    var tickW = Math.max.apply(null, yt.map(function (t) { return fmt(t).length; })) * pt * 0.56;
    var legendH = sp.legend && series.length > 1 ? pt * 1.9 : 0;
    var L = tickW + pt * (sp.ylabel ? 2.6 : 1.2), R = pt * 1.2, T = pt * 0.9 + legendH, B = pt * (sp.xlabel ? 3.4 : 2.2);
    var pw = W - L - R, ph = H - T - B;
    function Y(v) { return sp.log_y ? T + ph - (Math.log10(v) - Math.log10(y0)) / (Math.log10(y1) - Math.log10(y0)) * ph : T + ph - (v - y0) / (y1 - y0) * ph; }
    var cats = d.rows.map(function (r) { return r[xi]; }), X, xt = [], band = 0;
    if (catX) { band = pw / cats.length; X = function (j) { return L + band * (j + 0.5); }; }
    else {
      var xs = []; series.forEach(function (s) { s.pts.forEach(function (p) { xs.push(p.x); }); });
      xt = niceTicks(Math.min.apply(null, xs), Math.max.apply(null, xs), P.w > 5 ? 8 : 5);
      var x0 = xt[0], x1 = xt[xt.length - 1]; X = function (v) { return L + (v - x0) / (x1 - x0) * pw; };
    }
    var ax = el("svg:g", { stroke: "#000", "stroke-width": 0.75, fill: "none" }, svg);
    el("svg:path", { d: "M" + L + " " + T + "V" + (T + ph) + "H" + (L + pw) }, ax);
    var tk = pt * 0.35;
    yt.forEach(function (t) { var y = Y(t); el("svg:path", { d: "M" + L + " " + y + "h" + (-tk) }, ax);
      el("svg:text", { x: L - tk * 1.8, y: y + pt * 0.35, "text-anchor": "end", fill: "#000", stroke: "none" }, svg, fmt(t)); });
    if (catX) cats.forEach(function (c, j) { el("svg:path", { d: "M" + X(j) + " " + (T + ph) + "v" + tk }, ax);
      el("svg:text", { x: X(j), y: T + ph + tk + pt * 1.05, "text-anchor": "middle", fill: "#000" }, svg, PR.short(String(c), Math.max(4, Math.floor(band / (pt * 0.55))))); });
    else xt.forEach(function (t) { el("svg:path", { d: "M" + X(t) + " " + (T + ph) + "v" + tk }, ax);
      el("svg:text", { x: X(t), y: T + ph + tk + pt * 1.05, "text-anchor": "middle", fill: "#000" }, svg, fmt(t)); });
    if (sp.xlabel) el("svg:text", { x: L + pw / 2, y: H - pt * 0.55, "text-anchor": "middle", fill: "#000" }, svg, sp.xlabel);
    if (sp.ylabel) el("svg:text", { transform: "translate(" + pt * 1.05 + " " + (T + ph / 2) + ") rotate(-90)", "text-anchor": "middle", fill: "#000" }, svg, sp.ylabel);

    var ms = pt * 0.32;
    function marker(g, s, x, y) {
      if (s.mark === "square") el("svg:rect", { x: x - ms, y: y - ms, width: ms * 2, height: ms * 2, fill: s.color }, g);
      else if (s.mark === "triangle") el("svg:path", { d: "M" + x + " " + (y - ms * 1.2) + "l" + ms * 1.1 + " " + ms * 2 + "h" + (-ms * 2.2) + "z", fill: s.color }, g);
      else if (s.mark === "diamond") el("svg:path", { d: "M" + x + " " + (y - ms * 1.3) + "l" + ms * 1.3 + " " + ms * 1.3 + "l" + (-ms * 1.3) + " " + ms * 1.3 + "l" + (-ms * 1.3) + " " + (-ms * 1.3) + "z", fill: s.color }, g);
      else el("svg:circle", { cx: x, cy: y, r: ms * 1.05, fill: s.color }, g);
    }
    function errbar(g, s, x, p) {
      if (p.e == null) return;
      var a = Y(Math.max(p.y - p.e, sp.log_y ? y0 : -Infinity)), b = Y(p.y + p.e), cap = pt * 0.3;
      el("svg:path", { d: "M" + x + " " + a + "V" + b + "M" + (x - cap) + " " + a + "h" + cap * 2 + "M" + (x - cap) + " " + b + "h" + cap * 2, stroke: s.color, "stroke-width": 0.75, fill: "none" }, g);
    }
    series.forEach(function (s, k) {
      var g = el("svg:g", {}, svg);
      if (sp.chart === "bar") {
        var gw = band * 0.76, bw = gw / series.length, base = Y(sp.log_y ? y0 : Math.max(0, y0));
        s.pts.forEach(function (p) {
          var x = X(p.x) - gw / 2 + bw * k, y = Y(p.y);
          el("svg:rect", { x: x + bw * 0.06, y: Math.min(y, base), width: bw * 0.88, height: Math.abs(base - y), fill: s.color,
                           stroke: gray ? "#000" : "none", "stroke-width": 0.5, "fill-opacity": gray ? 0.2 + 0.6 * (k / Math.max(1, series.length - 1)) : 1 }, g);
          errbar(g, { color: "#000" }, x + bw / 2, p);
        });
        return;
      }
      if (sp.chart === "line" && s.pts.length > 1) {
        el("svg:path", { d: s.pts.map(function (p, i) { return (i ? "L" : "M") + X(p.x) + " " + Y(p.y); }).join(""), stroke: s.color, "stroke-width": 1.1, fill: "none", "stroke-dasharray": s.dash || null }, g);
      }
      s.pts.forEach(function (p) { errbar(g, s, X(p.x), p); marker(g, s, X(p.x), Y(p.y)); });
      if (sp.chart === "scatter" && sp.fit && !catX && s.pts.length > 2) {
        var n = s.pts.length, sx = 0, sy = 0, sxx = 0, sxy = 0, syy = 0;
        s.pts.forEach(function (p) { sx += p.x; sy += p.y; sxx += p.x * p.x; sxy += p.x * p.y; syy += p.y * p.y; });
        var slope = (n * sxy - sx * sy) / (n * sxx - sx * sx), icpt = (sy - slope * sx) / n;
        var r2 = Math.pow(n * sxy - sx * sy, 2) / ((n * sxx - sx * sx) * (n * syy - sy * sy));
        var xa = xt[0], xb = xt[xt.length - 1];
        el("svg:path", { d: "M" + X(xa) + " " + Y(slope * xa + icpt) + "L" + X(xb) + " " + Y(slope * xb + icpt), stroke: s.color, "stroke-width": 0.9, "stroke-dasharray": "4 2", fill: "none", "clip-path": "url(#plotclip)" }, g);
        s.r2 = r2;
      }
    });
    var cp = el("svg:clipPath", { id: "plotclip" }, el("svg:defs", {}, svg)); el("svg:rect", { x: L, y: T, width: pw, height: ph }, cp);
    if (legendH) {
      var lx = L, lg = el("svg:g", {}, svg);
      series.forEach(function (s) {
        var label = s.name + (s.r2 != null ? " (R² = " + s.r2.toFixed(2) + ")" : "");
        if (sp.chart === "bar") el("svg:rect", { x: lx, y: pt * 0.55, width: pt * 0.9, height: pt * 0.9, fill: s.color, stroke: gray ? "#000" : "none", "stroke-width": 0.5 }, lg);
        else { if (sp.chart === "line") el("svg:path", { d: "M" + lx + " " + pt + "h" + pt * 1.8, stroke: s.color, "stroke-width": 1.1, "stroke-dasharray": s.dash || null }, lg); marker(lg, s, lx + pt * 0.9, pt); }
        el("svg:text", { x: lx + pt * 2.3, y: pt * 1.35, fill: "#000" }, lg, label);
        lx += pt * 3 + label.length * pt * 0.55;
      });
    } else if (sp.chart === "scatter" && sp.fit && series[0] && series[0].r2 != null) {
      el("svg:text", { x: L + pw, y: T + pt, "text-anchor": "end", fill: "#000" }, svg, "R² = " + series[0].r2.toFixed(2));
    }
    return svg;
  }
  PR.chart = chart;  // exposed for tests in the browser

  // ---------------------------------------------------------------- pages
  PR.pages.figures = function (main, D) {
    document.title = "PaperRepro: figures";
    var right = el("div", {});
    var nb = el("button", { class: "btn", type: "button" }, right, "+ New figure");
    PR.head(main, STAGE, "Figures", "that pass review.",
      "Paste your data and get a chart sized for your venue, in colorblind-safe or grayscale palettes, with clean axes and real error bars. Export SVG for the journal or PNG at 300 dpi.", right);
    nb.addEventListener("click", function () {
      nb.disabled = true;
      PR.api("/api/figures", { research_id: PR.R.id, title: "Accuracy over training", csv: SAMPLE, spec: { chart: "line", x: "epoch", ys: ["baseline", "ensemble"], errors: { baseline: "baseline_sd", ensemble: "ensemble_sd" }, xlabel: "Epoch", ylabel: "Test accuracy" } })
        .then(function (f) { location.href = PR.link("/figures/" + f.id); }).catch(function (e) { PR.toast(e.message); nb.disabled = false; });
    });
    PR.ledger(main, D.figures || [], {
      empty: "No figures yet. Start one with “New figure”; it opens with sample data you can replace.", icon: "figures",
      href: function (f) { return PR.link("/figures/" + f.id); }, title: function (f) { return f.title; }, sub: function (f) { return f.chart + " chart"; },
    });
  };

  PR.pages.figure = function (main, D) {
    var F = D.figure, sp = JSON.parse(JSON.stringify(F.spec)), data = parseCSV(F.csv), saveT;
    document.title = "PaperRepro: " + F.title;
    var top = el("div", { style: "display:flex;justify-content:space-between;align-items:center;margin-bottom:18px;gap:12px;flex-wrap:wrap" }, main);
    el("a", { class: "ghost", href: PR.link("/figures"), style: "text-decoration:none" }, top, "← all figures");
    var saved = el("span", { class: "msg", style: "margin:0" }, top, "saved");
    var grid = el("div", { class: "fig-grid" }, main);
    var side = el("aside", { class: "sheet fig-side" }, grid), stageCol = el("div", {}, grid);
    var stage = el("div", { class: "fig-stage" }, stageCol), note = el("div", { class: "size-note" }, stageCol);
    var acts = el("div", { style: "display:flex;gap:10px;margin-top:14px;flex-wrap:wrap" }, stageCol);
    var meta = el("section", { class: "sheet fig-meta" }, stageCol);

    function field(label, node) { var w = el("div", {}, side); el("label", { class: "f" }, w, label); w.appendChild(node); return w; }
    var title = el("input", { class: "field", value: F.title }); field("Figure name (for you)", title);
    var csvBox = el("textarea", { class: "big", spellcheck: "false" }); csvBox.value = F.csv;
    var csvW = field("Data (CSV: first row is column names)", csvBox);
    var fileIn = el("input", { type: "file", accept: ".csv,.tsv,.txt", hidden: true }, csvW);
    var lf = el("button", { class: "more", type: "button", style: "margin-top:6px" }, csvW, "load a CSV file");
    lf.addEventListener("click", function () { fileIn.click(); });
    fileIn.addEventListener("change", function () { var f = fileIn.files[0]; if (!f) return; var rd = new FileReader(); rd.onload = function () { csvBox.value = rd.result; onData(); }; rd.readAsText(f); });
    var info = el("div", { class: "msg", style: "margin-top:4px" }, csvW);
    var typeSeg = el("div", { class: "seg" }); field("Chart", typeSeg);
    var xSel = el("select", { class: "field" }); field("X axis column", xSel);
    var yBox = el("div", { class: "cols" }); field("Y series (one or more)", yBox);
    var errBox = el("div", { style: "display:grid;gap:8px" }); var errW = field("Error bars (optional, per series)", errBox);
    var preset = el("select", { class: "field" }); field("Size", preset);
    Object.keys(PRESETS).forEach(function (k) { el("option", { value: k, selected: sp.preset === k }, preset, PRESETS[k].name + " · " + PRESETS[k].w + " in"); });
    var palSeg = el("div", { class: "seg" }); field("Colours", palSeg);
    var fontSeg = el("div", { class: "seg" }); field("Font", fontSeg);
    var r2 = el("div", { class: "row2" }, side);
    var xl = el("input", { class: "field", value: sp.xlabel, placeholder: "e.g. Epoch" }), yl = el("input", { class: "field", value: sp.ylabel, placeholder: "e.g. Accuracy (%)" });
    var a = el("div", {}, r2); el("label", { class: "f" }, a, "X label"); a.appendChild(xl);
    var b = el("div", {}, r2); el("label", { class: "f" }, b, "Y label (with units)"); b.appendChild(yl);
    var togs = el("div", { class: "tog" }, side);
    function tog(key, label) { var l = el("label", {}, togs); var c = el("input", { type: "checkbox" }, l); c.checked = !!sp[key]; l.appendChild(document.createTextNode(label)); c.addEventListener("change", function () { sp[key] = c.checked; render(); save(); }); return l; }
    tog("legend", "legend"); tog("log_y", "log y axis"); var fitT = tog("fit", "fit line (scatter)");

    function seg(node, opts, key) {
      node.textContent = "";
      opts.forEach(function (o) {
        var bt = el("button", { type: "button", "aria-pressed": sp[key] === o[0] ? "true" : "false" }, node, o[1]);
        bt.addEventListener("click", function () { sp[key] = o[0]; seg(node, opts, key); syncControls(); render(); save(); });
      });
    }
    seg(typeSeg, [["line", "line"], ["bar", "bar"], ["scatter", "scatter"], ["errorbar", "points ± error"]], "chart");
    seg(palSeg, [["okabe_ito", "colourblind-safe"], ["viridis", "viridis"], ["grayscale", "grayscale"]], "palette");
    seg(fontSeg, [["sans", "Helvetica"], ["serif", "Times"]], "font");

    function syncControls() {
      xSel.textContent = "";
      data.head.forEach(function (h) { el("option", { value: h, selected: h === sp.x }, xSel, h); });
      if (data.head.indexOf(sp.x) < 0) sp.x = data.head[0] || "";
      sp.ys = sp.ys.filter(function (y) { return data.head.indexOf(y) >= 0 && y !== sp.x; });
      yBox.textContent = "";
      data.head.forEach(function (h) {
        if (h === sp.x) return;
        var l = el("label", {}, yBox), c = el("input", { type: "checkbox" }, l); c.checked = sp.ys.indexOf(h) >= 0;
        l.appendChild(document.createTextNode(h));
        c.addEventListener("change", function () { sp.ys = c.checked ? sp.ys.concat([h]) : sp.ys.filter(function (y) { return y !== h; }); syncControls(); render(); save(); });
      });
      errBox.textContent = "";
      errW.hidden = sp.chart === "scatter" || !sp.ys.length;
      sp.ys.forEach(function (y) {
        var r = el("div", { style: "display:grid;grid-template-columns:1fr 1fr;gap:8px;align-items:center" }, errBox);
        el("span", { class: "msg", style: "margin:0" }, r, y + " ±");
        var s = el("select", { class: "field" }, r); el("option", { value: "" }, s, "none");
        data.head.forEach(function (h) { if (h !== y && h !== sp.x) el("option", { value: h, selected: sp.errors[y] === h }, s, h); });
        s.addEventListener("change", function () { if (s.value) sp.errors[y] = s.value; else delete sp.errors[y]; render(); save(); });
      });
      fitT.hidden = sp.chart !== "scatter";
      info.textContent = data.rows.length + " rows · " + data.head.length + " columns";
    }
    function onData() { data = parseCSV(csvBox.value); syncControls(); render(); save(); }
    var svgNode;
    function render() {
      stage.textContent = "";
      svgNode = chart(data, sp); stage.appendChild(svgNode);
      var P = PRESETS[sp.preset];
      note.textContent = P.name + " · " + P.w + " × " + P.h + " in (" + Math.round(P.w * 25.4) + " × " + Math.round(P.h * 25.4) + " mm) · text " + P.pt + " pt at 100%";
    }
    function save() {
      clearTimeout(saveT); saved.textContent = "saving…";
      saveT = setTimeout(function () {
        PR.api("/api/figures", { id: F.id, title: title.value, csv: csvBox.value, spec: sp }).then(function (x) { F = x; saved.textContent = "saved"; })
          .catch(function (e) { saved.textContent = "not saved: " + e.message; });
      }, 700);
    }
    csvBox.addEventListener("input", function () { clearTimeout(csvBox._t); csvBox._t = setTimeout(onData, 350); });
    title.addEventListener("input", save);
    xSel.addEventListener("change", function () { sp.x = xSel.value; syncControls(); render(); save(); });
    preset.addEventListener("change", function () { sp.preset = preset.value; render(); save(); });
    xl.addEventListener("input", function () { sp.xlabel = xl.value; render(); save(); });
    yl.addEventListener("input", function () { sp.ylabel = yl.value; render(); save(); });

    function svgText() { return '<?xml version="1.0" encoding="UTF-8"?>\n' + new XMLSerializer().serializeToString(svgNode); }
    var fname = function (ext) { return (title.value || "figure").replace(/[^\w\- ]+/g, "").trim() + "." + ext; };
    el("button", { class: "btn", type: "button" }, acts, "Download SVG").addEventListener("click", function () { PR.download(fname("svg"), new Blob([svgText()], { type: "image/svg+xml" })); });
    el("button", { class: "btn line", type: "button" }, acts, "Download PNG · 300 dpi").addEventListener("click", function () {
      var P = PRESETS[sp.preset], c = document.createElement("canvas"); c.width = Math.round(P.w * 300); c.height = Math.round(P.h * 300);
      var img = new Image();
      img.onload = function () { var g = c.getContext("2d"); g.fillStyle = "#fff"; g.fillRect(0, 0, c.width, c.height); g.drawImage(img, 0, 0, c.width, c.height); c.toBlob(function (b) { PR.download(fname("png"), b); }, "image/png"); };
      img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svgText());
    });

    function drawMeta() {
      meta.textContent = "";
      var h = el("div", { style: "display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap" }, meta);
      el("div", { class: "lab" }, h, "Caption and alt text");
      var cb = el("button", { class: "btn line sm", type: "button", disabled: !!D.can_run }, h, F.caption ? "Rewrite with AI" : "Write with AI");
      cb.addEventListener("click", function () {
        cb.disabled = true; cb.textContent = "writing…";
        clearTimeout(saveT);
        PR.api("/api/figures", { id: F.id, title: title.value, csv: csvBox.value, spec: sp })
          .then(function () { return PR.api("/api/figures/" + F.id + "/caption", {}); })
          .then(function (x) { F = x; drawMeta(); }).catch(function (e) { PR.toast(e.message); cb.disabled = false; cb.textContent = "Write with AI"; });
      });
      var cap = el("textarea", { class: "big", rows: 3, placeholder: "Figure 1. What is shown, units, n, and what the error bars mean.", style: "margin-top:12px;font-size:16px" }, meta);
      cap.value = F.caption || "";
      cap.addEventListener("input", function () { clearTimeout(cap._t); cap._t = setTimeout(function () { PR.api("/api/figures", { id: F.id, title: title.value, csv: csvBox.value, spec: sp, caption: cap.value }).then(function (x) { F = x; }); }, 700); });
      if (F.alt_text) { el("div", { class: "lab", style: "margin-top:14px" }, meta, "Alt text"); el("p", { class: "cap" }, meta, F.alt_text); }
      el("p", { class: "msg" }, meta, "The AI sees only column names and summary numbers, never asserts what the error bars mean, and you can edit everything.");
    }
    syncControls(); render(); drawMeta();
  };
})();
