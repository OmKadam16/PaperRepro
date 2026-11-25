/* Project assistant: a text-only chat on the right of every research tab.
   Replies come from the server; no key and no model name ever reaches this page.
   Everything is rendered with textContent. */
(function () {
  "use strict";
  var el = PR.el;

  PR.panel = function () {
    var R = PR.R, body = document.getElementById("body");
    var collapsed = false;
    try { collapsed = localStorage.getItem("pr-panel") === "closed"; } catch (e) {}
    body.classList.add("with-panel");
    var side = el("aside", { class: "panel", "aria-label": "Project assistant" }, body);
    var open = el("button", { class: "panel-open", type: "button", "aria-label": "Open the project assistant" }, body);
    PR.icon(open, PR.ICONS.chat); el("span", {}, open, "Ask");

    var head = el("div", { class: "p-head" }, side);
    var hl = el("div", {}, head);
    el("b", {}, hl, "Project assistant");
    el("span", { class: "p-model" }, hl, "Research help for this project");
    var close = el("button", { class: "ghost p-close", type: "button", "aria-label": "Hide the project assistant" }, head, "→");

    var thread = el("div", { class: "p-thread", "aria-live": "polite" }, side);
    var foot = el("div", { class: "p-foot" }, side);
    var box = el("div", { class: "p-box" }, foot);
    var ta = el("textarea", { rows: 2, maxlength: 2000, placeholder: "Ask about your question, method or writing…", "aria-label": "Message the project assistant" }, box);
    var send = el("button", { class: "send", type: "button", "aria-label": "Send" }, box); PR.icon(send, PR.ICONS.send);
    var note = el("div", { class: "p-note" }, foot);
    el("span", {}, note, "Text only · no code");
    var left = el("span", { class: "p-left" }, note);

    var msgs = [], sending = false;
    function setOpen(on) {
      body.classList.toggle("panel-closed", !on);
      try { localStorage.setItem("pr-panel", on ? "open" : "closed"); } catch (e) {}
      if (on) setTimeout(function () { ta.focus(); }, 50);
    }
    close.addEventListener("click", function () { setOpen(false); });
    open.addEventListener("click", function () { setOpen(true); });
    if (collapsed || matchMedia("(max-width: 900px)").matches) body.classList.add("panel-closed");

    function draw() {
      thread.textContent = "";
      if (!msgs.length) {
        var e = el("div", { class: "p-empty" }, thread);
        el("p", {}, e, "Talk through this project in plain words.");
        ["How could I sharpen this research question?", "What are the biggest threats to validity here?", "What should my methods section cover?"].forEach(function (q) {
          var b = el("button", { class: "p-sugg", type: "button" }, e, q);
          b.addEventListener("click", function () { ta.value = q; go(); });
        });
      }
      msgs.forEach(function (m) {
        if (m.role === "user") { el("div", { class: "p-u" }, thread, m.text); return; }
        var d = el("div", { class: "p-a" }, thread);  // **bold** only; everything else stays plain text
        String(m.text || "").split(/\*\*([^*\n]+)\*\*/).forEach(function (part, i) {
          if (i % 2) el("b", {}, d, part); else d.appendChild(document.createTextNode(part));
        });
      });
      if (sending) { var t = el("div", { class: "typing p-typing" }, thread); el("i", {}, t); el("i", {}, t); el("i", {}, t); }
      thread.scrollTop = thread.scrollHeight;
    }
    function go() {
      var text = ta.value.trim();
      if (!text || sending) return;
      sending = true; send.disabled = true;
      msgs.push({ role: "user", text: text }); ta.value = ""; draw();
      PR.api("/api/r/" + R.id + "/chat", { text: text }).then(function (x) {
        msgs = x.messages;
        PR.setQuota(x.quota);
      }).catch(function (e) {
        msgs.pop(); ta.value = text; PR.toast(e.message);
      }).then(function () { sending = false; send.disabled = false; draw(); });
    }
    send.addEventListener("click", go);
    ta.addEventListener("keydown", function (e) { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); go(); } });

    PR.onQuota = function (q) { left.textContent = q.left + " of " + q.limit + " calls left today"; left.classList.toggle("out", q.left === 0); };
    if (PR.D.quota) PR.onQuota(PR.D.quota);
    PR.get("/api/r/" + R.id + "/chat").then(function (x) {
      msgs = x.messages || [];
      if (!x.ready) { ta.disabled = send.disabled = true; ta.placeholder = "The project chat isn't set up on the server yet."; }
      draw();
    });
    draw();
  };
})();
