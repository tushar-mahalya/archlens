/* Archlens site: interactive examples and in-view motion. No dependencies.
   Every verdict and query result below is recorded output of archlens.py 0.5.0. */
(function () {
  "use strict";
  var doc = document;
  var reduceMQ = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
  function reduced() { return !!(reduceMQ && reduceMQ.matches); }
  function $(sel, ctx) { return (ctx || doc).querySelector(sel); }
  function $$(sel, ctx) { return Array.prototype.slice.call((ctx || doc).querySelectorAll(sel)); }
  function el(tag, cls, text) { var n = doc.createElement(tag); if (cls) n.className = cls; if (text != null) n.textContent = text; return n; }

  /* ---------- play illustrations only while they are on screen ---------- */
  (function initViz() {
    var items = $$(".viz");
    if (!items.length) return;
    if (!("IntersectionObserver" in window)) { items.forEach(function (v) { v.classList.add("is-live"); }); return; }
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) { e.target.classList.toggle("is-live", e.isIntersecting); });
    }, { threshold: 0.35 });
    items.forEach(function (v) { io.observe(v); });
  })();

  /* ---------- generic tabs ---------- */
  $$("[data-tabs]").forEach(function (wrap) {
    var tabs = $$('[role="tab"]', wrap);
    function select(tab, focus) {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.setAttribute("aria-selected", on ? "true" : "false");
        t.tabIndex = on ? 0 : -1;
        doc.getElementById(t.getAttribute("aria-controls")).hidden = !on;
      });
      if (focus) tab.focus();
      wrap.dispatchEvent(new CustomEvent("tabchange", { detail: tab.getAttribute("aria-controls") }));
    }
    tabs.forEach(function (t, n) {
      t.addEventListener("click", function () { select(t, false); });
      t.addEventListener("keydown", function (e) {
        var k = { ArrowRight: n + 1, ArrowLeft: n - 1, Home: 0, End: tabs.length - 1 }[e.key];
        if (k === undefined) return;
        e.preventDefault();
        select(tabs[(k + tabs.length) % tabs.length], true);
      });
    });
    if (tabs.length) select(tabs[0], false);
  });

  /* ---------- cover demo: open the page map when the edit happens ---------- */
  (function () {
    var panel = $("#map-panel");
    if (!panel) return;
    ["#btn-edit", "#hot"].forEach(function (sel) {
      var t = $(sel);
      if (t) t.addEventListener("click", function () { panel.open = true; });
    });
  })();

  /* ---------- lab 1: judge an edit ---------- */
  (function initDrift() {
    var code = $("#drift-code"), verdict = $("#drift-verdict"), term = $("#drift-term"), range = $("#drift-range");
    if (!code || !verdict || !term) return;
    var K = function (t) { return '<span class="k">' + t + "</span>"; };
    var S = function (t) { return '<span class="s">' + t + "</span>"; };
    var C = function (t) { return '<span class="c">' + t + "</span>"; };
    var base = [
      [20, K("def") + ' <span class="f">submit_order</span>(connection, request_key, sku, quantity):'],
      [21, "    " + K("if not") + " isinstance(request_key, str) " + K("or not") + " request_key.strip():"],
      [22, "        " + K("raise") + " ValueError(" + S('"request_key must be a non-empty string"') + ")"],
      [25, "    " + K("if") + " type(quantity) " + K("is not") + " int " + K("or") + ' quantity &lt;= <span class="n">0</span>:'],
      [26, "        " + K("raise") + " ValueError(" + S('"quantity must be a positive integer"') + ")"],
      [27, "    " + K("with") + " connection:"]
    ];
    var PAGE = "docs/architecture/runtime/submit-order.md";
    function stale(text) { return '<span class="t-stale">STALE</span> ' + text; }
    var edits = {
      reset: {
        lines: base, cited: "cited: L20–L38", state: "fresh", word: "Fresh", why: "The page matches its baseline.",
        out: ["6 fresh, 0 stale, 0 review, 0 unsynced."]
      },
      comment: {
        lines: base.slice(0, 3).concat([[25, "    " + C("# quantity must be a whole number"), "is-new"]], base.slice(3).map(function (l) { return [l[0] + 1, l[1]]; })),
        cited: "cited: L20–L39", state: "moved", word: "Not a change",
        why: "A comment is not code. The range grew by one line, and the link was rewritten.",
        out: ['<span class="t-dim">evidence-moved</span> order_service.py#L20-L38 (submit_order) -&gt; #L20-L39',
              '<span class="t-ok">FIXED</span> ' + PAGE + ": order_service.py#L20-L38 -&gt; #L20-L39"]
      },
      inline: {
        lines: base.slice(0, 5).concat([[27, "    " + K("with") + " connection:  " + C("# one transaction"), "is-new"]]),
        cited: "cited: L20–L38", state: "fresh", word: "Not stale",
        why: "The file changed, the cited code did not. The page is only marked for a quick look.",
        out: ['<span class="t-dim">REVIEW</span> ' + PAGE + " [FLOW-001] review: modified order_service.py"]
      },
      move: {
        lines: [[20, C('"""Order service."""'), "is-new"], [21, "", "is-new"], [22, "", "is-new"]].concat(base.map(function (l) { return [l[0] + 3, l[1]]; })),
        cited: "cited: L23–L41", state: "moved", word: "Moved",
        why: "Same code, new lines. The link follows it. No model, no tokens.",
        out: ['<span class="t-dim">evidence-moved</span> order_service.py#L20-L38 (submit_order) -&gt; #L23-L41',
              '<span class="t-ok">FIXED</span> ' + PAGE + ": order_service.py#L20-L38 -&gt; #L23-L41"]
      },
      rule: {
        lines: base.slice(0, 3).concat([
          [25, "    " + K("if") + " type(quantity) " + K("is not") + " int " + K("or not") + ' <span class="n">1</span> &lt;= quantity &lt;= <span class="n">100</span>:', "is-hit"]
        ], base.slice(4)),
        cited: "cited: L20–L38", state: "stale", word: "Stale",
        why: "The rule changed. The page that describes it needs a look before the commit.",
        out: [stale(PAGE + " [FLOW-001] evidence-changed order_service.py#L20-L38 (submit_order)")]
      },
      rename: {
        lines: [[20, K("def") + ' <span class="f">place_order</span>(connection, request_key, sku, quantity):', "is-hit"]].concat(base.slice(1)),
        cited: "cited: L20–L38", state: "stale", word: "Stale",
        why: "The cited function is gone. The checker suggests where it went.",
        out: [stale(PAGE + " [FLOW-001] symbol-removed order_service.py#L20-L38 (submit_order) now `place_order`?")]
      }
    };
    var buttons = $$(".lab-act"), timer;
    function show(name, animate) {
      var edit = edits[name];
      if (!edit) return;
      code.innerHTML = edit.lines.map(function (l) {
        return '<span class="l' + (l[2] ? " " + l[2] : "") + '" data-n="' + l[0] + '">' + l[1] + "</span>";
      }).join("\n");
      range.textContent = edit.cited;
      verdict.setAttribute("data-state", edit.state);
      $(".verdict-word", verdict).textContent = edit.word;
      $(".verdict-why", verdict).textContent = edit.why;
      term.innerHTML = edit.out.join("\n");
      buttons.forEach(function (b) { if (b.getAttribute("data-edit") !== "reset") b.setAttribute("aria-pressed", b.getAttribute("data-edit") === name ? "true" : "false"); });
      if (animate && !reduced()) {
        verdict.classList.remove("is-stamped");
        void verdict.offsetWidth;
        verdict.classList.add("is-stamped");
      }
    }
    buttons.forEach(function (b) {
      b.addEventListener("click", function () { clearTimeout(timer); show(b.getAttribute("data-edit"), true); });
    });
    show("reset", false);
  })();

  /* ---------- lab 2: find a section ---------- */
  (function initQuery() {
    var term = $("#query-term"), box = $("#query-bytes"), note = $("#query-note");
    if (!term || !box) return;
    var ALL = 21365;
    var data = {
      adr: {
        cmd: "archlens.py query why json map instead of frontmatter",
        out: ["docs/architecture/decisions/ADR-002.md:12-22  Choice implemented  (510 B)",
              "    Store metadata in one `map.json` file beside the handbook.",
              "docs/architecture/decisions/ADR-002.md:24-30  Consequences  (386 B)",
              "    without editing them. Frontmatter could not do that."],
        sections: 896, page: 1631,
        note: "Two sections answer it: 896 bytes, about a twentieth of the handbook."
      },
      file: {
        cmd: "archlens.py query --file plugins/archlens/hooks/hooks.json",
        out: ["docs/architecture/README.md:11-38  Context and main units  (1842 B)  [flowchart]",
              "Covered without a citation: docs/architecture/runtime.md, docs/architecture/decisions/ADR-003.md"],
        sections: 1842, page: 3748,
        note: "One section cites the file. Two more pages cover it without a link."
      },
      outline: {
        cmd: "archlens.py query --page ARCH-DIST",
        out: ["docs/architecture/distribution.md:1-15  How does one source become a plugin and a portable skill?  (652 B)  [flowchart]",
              "  docs/architecture/distribution.md:17-30  Generation rules  (895 B)",
              "  docs/architecture/distribution.md:32-42  Enforcement and release  (776 B)"],
        sections: 652, page: 2328,
        note: "The outline costs a few lines. Then read the diagram first: 652 bytes."
      }
    };
    var chips = $$("[data-query]"), run = 0;
    function fmt(n) { return n.toLocaleString("en-US") + " B"; }
    function bars(d) {
      [["sections", d.sections], ["page", d.page], ["all", ALL]].forEach(function (pair) {
        $('[data-bar="' + pair[0] + '"]', box).style.setProperty("--p", Math.max(1, pair[1] / ALL * 100).toFixed(2));
        $('[data-v="' + pair[0] + '"]', box).textContent = fmt(pair[1]);
      });
      note.textContent = d.note;
    }
    function show(name, animate) {
      var d = data[name], mine = ++run;
      if (!d) return;
      chips.forEach(function (c) { c.setAttribute("aria-pressed", c.getAttribute("data-query") === name ? "true" : "false"); });
      term.textContent = "";
      var cmd = el("span", "t-cmd");
      term.appendChild(doc.createTextNode("$ "));
      term.appendChild(cmd);
      function finish() {
        if (mine !== run) return;
        cmd.textContent = d.cmd;
        term.appendChild(doc.createTextNode("\n" + d.out.join("\n")));
        bars(d);
      }
      if (!animate || reduced()) { finish(); return; }
      var i = 0;
      (function type() {
        if (mine !== run) return;
        cmd.textContent = d.cmd.slice(0, i);
        if (i >= d.cmd.length) { setTimeout(finish, 160); return; }
        i += 2;
        setTimeout(type, 14);
      })();
    }
    chips.forEach(function (c) { c.addEventListener("click", function () { show(c.getAttribute("data-query"), true); }); });
    show("adr", false);
    var lab = $("[data-tabs].lab");
    if (lab) lab.addEventListener("tabchange", function (e) { if (e.detail === "lab-query") show("adr", true); });
  })();

  /* ---------- proof: 420 harmless edits, before and after ---------- */
  (function initDots() {
    var fig = $("#drift-proof"), grid = $("#dots");
    if (!fig || !grid) return;
    var TOTAL = 420, ALARMS = 52, seed = 11, picked = {};
    function rnd() { seed = (seed * 9301 + 49297) % 233280; return seed / 233280; }
    while (Object.keys(picked).length < ALARMS) picked[Math.floor(rnd() * TOTAL)] = true;
    var frag = doc.createDocumentFragment();
    for (var i = 0; i < TOTAL; i++) {
      var d = el("span", "dot" + (picked[i] ? " is-alarm" : ""));
      d.style.setProperty("--k", String((i % 30) + Math.floor(i / 30) * 2));
      frag.appendChild(d);
    }
    grid.appendChild(frag);
    var alarms = $("#dp-alarms"), caught = $("#dp-caught"), buttons = $$(".seg button", fig);
    function set(version) {
      fig.setAttribute("data-version", version);
      buttons.forEach(function (b) { b.setAttribute("aria-pressed", b.getAttribute("data-v") === version ? "true" : "false"); });
      alarms.textContent = version === "old" ? "52" : "0";
      caught.textContent = version === "old" ? "213 / 217" : "226 / 226";
    }
    buttons.forEach(function (b) { b.addEventListener("click", function () { played = true; set(b.getAttribute("data-v")); }); });
    var played = reduced();
    if (!played && "IntersectionObserver" in window) {
      set("old");
      var io = new IntersectionObserver(function (entries) {
        if (!entries[0].isIntersecting || played) return;
        played = true;
        io.disconnect();
        setTimeout(function () { if (fig.getAttribute("data-version") === "old") set("new"); }, 1700);
      }, { threshold: 0.5 });
      io.observe(fig);
    } else {
      set("new");
    }
  })();
})();

/* ---------- guide: mark the section in view ---------- */
(function () {
  "use strict";
  var links = Array.prototype.slice.call(document.querySelectorAll(".guide-nav a"));
  if (!links.length || !("IntersectionObserver" in window)) return;
  var byId = {};
  links.forEach(function (a) { byId[a.getAttribute("href").slice(1)] = a; });
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      links.forEach(function (a) { a.classList.remove("is-current"); a.removeAttribute("aria-current"); });
      var a = byId[e.target.id];
      if (a) { a.classList.add("is-current"); a.setAttribute("aria-current", "true"); }
    });
  }, { rootMargin: "-20% 0px -65% 0px" });
  document.querySelectorAll(".guide .g").forEach(function (s) { io.observe(s); });
})();
