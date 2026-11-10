/* Archlens site. Vanilla JS, no dependencies. Every feature degrades to static content. */
(function () {
  "use strict";

  var doc = document;
  var root = doc.documentElement;
  var REPO = "https://github.com/tushar-mahalya/archlens/blob/main/";
  var EX = REPO + "examples/order-service/";
  var reduceMQ = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
  function reduced() { return !!(reduceMQ && reduceMQ.matches); }
  function $(sel, ctx) { return (ctx || doc).querySelector(sel); }
  function $$(sel, ctx) { return Array.prototype.slice.call((ctx || doc).querySelectorAll(sel)); }
  function wait(ms) { return new Promise(function (r) { setTimeout(r, reduced() ? 0 : ms); }); }
  function fmt(n) { return n.toLocaleString("en-US"); }

  /* ---------- motion: one set of tokens, read from the CSS custom properties ---------- */
  var css = getComputedStyle(root);
  function token(name, fallback) { var v = parseFloat(css.getPropertyValue(name)); return isNaN(v) ? fallback : v; }
  var D1 = token("--d-1", 140), D2 = token("--d-2", 260), D3 = token("--d-3", 520), D4 = token("--d-4", 1100), STAGGER = token("--stagger", 70);
  function tween(ms, step, alive) {
    var start = null;
    requestAnimationFrame(function frame(t) {
      if (alive && !alive()) return;
      if (start === null) start = t;
      var k = Math.min(1, (t - start) / ms);
      step(1 - Math.pow(1 - k, 3));
      if (k < 1) requestAnimationFrame(frame);
    });
  }
  function typeText(el, text, alive, speed) {
    return new Promise(function (resolve) {
      if (reduced()) { el.textContent = text; resolve(); return; }
      var i = 0;
      el.classList.add("is-typing");
      (function next() {
        if (alive && !alive()) { el.classList.remove("is-typing"); resolve(); return; }
        el.textContent = text.slice(0, ++i);
        if (i < text.length) setTimeout(next, speed || 34);
        else { el.classList.remove("is-typing"); resolve(); }
      })();
    });
  }
  /* Run callbacks once, the first time an element scrolls into view; one shared observer. */
  var seenIO = "IntersectionObserver" in window ? new IntersectionObserver(function (entries) {
    entries.filter(function (e) { return e.isIntersecting; })
      .map(function (e) { return e.target; })
      .sort(function (a, b) { return a.compareDocumentPosition(b) & 4 ? -1 : 1; })
      .forEach(function (el, k) {
        seenIO.unobserve(el);
        var fns = el.__seen || [];
        el.__seen = null;
        fns.forEach(function (fn) { fn(el, k); });
      });
  }, { rootMargin: "0px 0px -8% 0px" }) : null;
  function onSeen(el, fn) {
    if (!seenIO) { fn(el, 0); return; }
    (el.__seen = el.__seen || []).push(fn);
    seenIO.observe(el);
  }
  var motionOK = !reduced() && !!seenIO;
  var vh = window.innerHeight;
  function belowFold(el) { return el.getBoundingClientRect().top >= vh; }

  /* ---------- theme ---------- */
  function store(key, value) {
    try { if (value === undefined) return localStorage.getItem(key); localStorage.setItem(key, value); } catch (e) { return null; }
    return null;
  }
  var darkMQ = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  function currentTheme() {
    var t = root.getAttribute("data-theme");
    if (t === "light" || t === "dark") return t;
    return darkMQ && darkMQ.matches ? "dark" : "light";
  }
  function syncThemeUI() {
    var btn = $("#theme-toggle");
    var t = currentTheme();
    if (btn) {
      var next = t === "dark" ? "paper" : "blueprint";
      $(".theme-label", btn).textContent = t === "dark" ? "Paper" : "Blueprint";
      btn.setAttribute("aria-label", "Switch to " + next + " theme (" + (t === "dark" ? "light" : "dark") + ")");
    }
    var color = getComputedStyle(root).getPropertyValue("--paper").trim();
    if (root.hasAttribute("data-theme")) $$('meta[name="theme-color"]').forEach(function (m) { m.setAttribute("content", color); });
  }
  (function initTheme() {
    var btn = $("#theme-toggle");
    if (!btn) return;
    btn.hidden = false;
    btn.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      function apply() { root.setAttribute("data-theme", next); store("archlens-theme", next); syncThemeUI(); }
      if (reduced() || !doc.startViewTransition) { apply(); return; }
      var r = btn.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
      root.style.setProperty("--vt-x", x.toFixed(0) + "px");
      root.style.setProperty("--vt-y", y.toFixed(0) + "px");
      root.style.setProperty("--vt-r", Math.ceil(Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y))) + "px");
      doc.startViewTransition(apply);
    });
    if (darkMQ && darkMQ.addEventListener) darkMQ.addEventListener("change", syncThemeUI);
    syncThemeUI();
  })();

  /* ---------- active sheet in the index ---------- */
  (function initNav() {
    var links = $$(".sheet-nav a");
    if (!("IntersectionObserver" in window) || !links.length) return;
    var byId = {};
    links.forEach(function (a) { byId[a.getAttribute("href").slice(1)] = a; });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        links.forEach(function (a) { a.removeAttribute("aria-current"); });
        var a = byId[e.target.id];
        if (a) {
          a.setAttribute("aria-current", "location");
          var nav = a.closest(".sheet-nav");
          if (nav && nav.scrollWidth > nav.clientWidth) {
            var ar = a.getBoundingClientRect(), nr = nav.getBoundingClientRect();
            var left = nav.scrollLeft + (ar.left - nr.left) - (nav.clientWidth - ar.width) / 2;
            nav.scrollTo({ left: left, behavior: reduced() ? "auto" : "smooth" });
          }
        }
      });
    }, { rootMargin: "-40% 0px -55% 0px" });
    $$("main .sheet").forEach(function (s) { io.observe(s); });
  })();

  /* ---------- revision clouds ---------- */
  var NS = "http://www.w3.org/2000/svg";
  function seeded(seed) { var s = seed || 7; return function () { s = (s * 9301 + 49297) % 233280; return s / 233280; }; }
  function cloudPath(w, h, gap, rnd) {
    var x0 = -gap, y0 = -gap, x1 = w + gap, y1 = h + gap;
    var r = Math.max(8, Math.min(15, (y1 - y0) / 3));
    var step = r * 1.6, pts = [];
    function edge(ax, ay, bx, by) {
      var n = Math.max(1, Math.round(Math.hypot(bx - ax, by - ay) / step));
      for (var i = 1; i <= n; i++) pts.push([ax + (bx - ax) * i / n, ay + (by - ay) * i / n]);
    }
    edge(x0, y0, x1, y0); edge(x1, y0, x1, y1); edge(x1, y1, x0, y1); edge(x0, y1, x0, y0);
    var d = "M" + x0.toFixed(1) + " " + y0.toFixed(1), px = x0, py = y0;
    pts.forEach(function (p) {
      var rr = (Math.hypot(p[0] - px, p[1] - py) / 2) * (1.06 + rnd() * 0.22);
      d += " A" + rr.toFixed(1) + " " + rr.toFixed(1) + " 0 0 1 " + p[0].toFixed(1) + " " + p[1].toFixed(1);
      px = p[0]; py = p[1];
    });
    return d;
  }
  function drawCloud(el, opts) {
    opts = opts || {};
    var host = opts.host || el;
    var old = host.__cloud;
    if (old) old.remove();
    var hostBox = host.getBoundingClientRect(), box = el.getBoundingClientRect();
    var left = box.left - hostBox.left + (opts.left || 0), top = box.top - hostBox.top;
    var w = box.width - (opts.left || 0), h = box.height, pad = 16, gap = opts.gap == null ? 5 : opts.gap;
    if (w < 4 || h < 4) return null;
    var svg = doc.createElementNS(NS, "svg");
    svg.setAttribute("class", "cloud" + (opts.blue ? " is-blue" : ""));
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    svg.setAttribute("viewBox", [-pad, -pad, w + pad * 2, h + pad * 2].join(" "));
    svg.style.left = (left - pad) + "px";
    svg.style.top = (top - pad) + "px";
    svg.style.width = (w + pad * 2) + "px";
    svg.style.height = (h + pad * 2) + "px";
    var path = doc.createElementNS(NS, "path");
    path.setAttribute("d", cloudPath(w, h, gap, seeded(opts.seed)));
    path.setAttribute("pathLength", "1");
    svg.appendChild(path);
    host.appendChild(svg);
    host.__cloud = svg;
    if (opts.animate && !reduced()) {
      path.style.strokeDasharray = "1";
      path.style.strokeDashoffset = "1";
      path.getBoundingClientRect();
      path.style.transition = "stroke-dashoffset var(--d-4) var(--ease-io)";
      requestAnimationFrame(function () { path.style.strokeDashoffset = "0"; });
    }
    return svg;
  }
  function removeCloud(host) { if (host && host.__cloud) { host.__cloud.remove(); host.__cloud = null; } }

  var heroCloud = $("[data-cloud]");
  function heroCloudDraw(animate) { if (heroCloud) drawCloud(heroCloud, { gap: 7, seed: 3, animate: animate }); }
  if (heroCloud) {
    var fontsReady = doc.fonts && doc.fonts.ready ? doc.fonts.ready : Promise.resolve();
    fontsReady.then(function () { heroCloudDraw(true); });
  }

  /* ---------- A-000 coupling demo ---------- */
  (function initCoupling() {
    var fig = $("#coupling");
    if (!fig) return;
    var controls = $("#coupling-controls");
    var btnEdit = $("#btn-edit"), btnUpdate = $("#btn-update"), btnReset = $("#btn-reset");
    var hot = $("#hot"), hotNew = $(".hot-new", hot);
    var stamp = $("#stamp"), stampWord = $(".stamp-word", stamp), stampSub = $(".stamp-sub", stamp);
    var docPanel = $(".panel-doc", fig);
    var redline = $("#redline"), redOld = $(".redline-old", redline), redNew = $(".redline-new", redline);
    var cell = redline.parentNode;
    var mapEl = $("#map-text"), count = $("#map-count"), flags = $$("[data-flag]", mapEl);
    var bytesEl = $("#map-bytes"), bytesDim = $("#map-bytes-dim"), dim = $("#map-dim");
    var log = $("#coupling-log");
    var NEW_RULE = "Quantity is not an integer from 1 to 100";
    var OLD_RULE = "Quantity is not a positive integer";
    var state = "synced", runId = 0, shownBytes = 0;

    controls.hidden = false;
    var tag = doc.createElement("span");
    tag.className = "hot-tag";
    tag.setAttribute("aria-hidden", "true");
    tag.textContent = "click to edit";
    hot.appendChild(tag);
    hot.setAttribute("role", "button");
    hot.setAttribute("tabindex", "0");
    hot.setAttribute("aria-label", "Edit lines 25 and 26: limit quantity to 1 to 100");

    function mapBytes() { return new TextEncoder().encode(mapEl.textContent + "\n").length; }
    function setBytes(n, animate) {
      var from = shownBytes, my = runId;
      shownBytes = n;
      dim.style.setProperty("--used", n);
      if (!animate || reduced() || from === n) { bytesEl.textContent = fmt(n); bytesDim.textContent = fmt(n); return; }
      tween(D3 + D2, function (k) {
        var v = Math.round(from + (n - from) * k);
        bytesEl.textContent = fmt(v); bytesDim.textContent = fmt(v);
      }, function () { return my === runId; });
    }
    function say(kind, html) {
      log.className = "log" + (kind === "stale" ? " is-stale" : kind === "synced" ? " is-synced" : "");
      log.innerHTML = html;
    }
    function setStamp(kind, sub) {
      stamp.setAttribute("data-state", kind);
      stampWord.textContent = kind === "stale" ? "Stale" : "Synced";
      stampSub.textContent = sub;
      stamp.classList.remove("is-slam");
      docPanel.classList.remove("is-hit");
      void stamp.offsetWidth;
      if (!reduced()) { stamp.classList.add("is-slam"); docPanel.classList.add("is-hit"); }
    }
    function moveFocus(from, to) {
      var a = doc.activeElement;
      if (a === from || a === hot || a === doc.body || (a && a.disabled)) to.focus({ preventScroll: true });
    }

    function edit() {
      if (state !== "synced") return;
      state = "busy";
      var my = ++runId;
      hot.classList.add("is-edited", "is-done");
      hot.removeAttribute("role");
      hot.removeAttribute("aria-label");
      hot.setAttribute("tabindex", "-1");
      hotNew.hidden = false;
      drawCloud(hotNew, { host: hot, left: 48, gap: 2, seed: 11, animate: true });
      btnEdit.disabled = true;
      say("", '<span class="log-k">edit</span> order_service.py lines 25–26: quantity must be an integer from 1 to 100.');
      wait(650).then(function () {
        if (my !== runId) return;
        fig.setAttribute("data-state", "stale");
        setStamp("stale", "Evidence changed · L20–L38");
        count.textContent = "4 stale";
        count.classList.add("is-stale");
        flags.forEach(function (f, i) {
          setTimeout(function () {
            if (my !== runId) return;
            f.textContent = f.getAttribute("data-flag");
            f.classList.remove("is-new"); void f.offsetWidth; f.classList.add("is-new");
            if (i === flags.length - 1) setBytes(mapBytes(), true);
          }, reduced() ? 0 : i * STAGGER);
        });
        if (reduced()) setBytes(mapBytes(), false);
        say("stale", '<span class="log-k">Stop hook</span>Archlens: 4 handbook page(s) cite code you changed (README.md, context.md, runtime/submit-order.md, data.md). They update when Claude commits, or run /archlens:update to refresh them.<span class="log-sub"><span class="log-k">status</span>STALE docs/architecture/runtime/submit-order.md [FLOW-001] evidence-changed order_service.py#L20-L38 (submit_order); review: modified order_service.py<br>REVIEW docs/architecture/decisions/ADR-001.md [ADR-001] review: modified order_service.py</span>');
        state = "stale";
        btnUpdate.disabled = false;
        moveFocus(btnEdit, btnUpdate);
      });
    }

    function update() {
      if (state !== "stale") return;
      state = "busy";
      var my = ++runId, alive = function () { return my === runId; };
      btnUpdate.disabled = true;
      say("stale", '<span class="log-k">commit gate</span>Archlens: this commit would leave handbook pages stale: README.md, context.md, runtime/submit-order.md, data.md. Before committing, invoke the archlens:update skill with pages INDEX CONTEXT FLOW-001 DATA; it runs in an isolated task. Then stage the updated pages and the handbook\'s .archlens-state.json, and run the commit again. …');
      wait(1400).then(function () {
        if (!alive()) return;
        say("", '<span class="log-k">update</span>Isolated task: reads the diff of order_service.py and the 4 stale pages, then edits only the prose the change made wrong.');
        return wait(700);
      }).then(function () {
        if (!alive()) return;
        redline.classList.add("is-struck");
        return wait(500);
      }).then(function () {
        if (my !== runId) return;
        return typeText(redNew, NEW_RULE, alive);
      }).then(function () {
        if (my !== runId) return;
        redNew.removeAttribute("aria-hidden");
        redOld.setAttribute("aria-hidden", "true");
        cell.style.position = "relative";
        drawCloud(redline, { host: cell, gap: 4, seed: 5, blue: true, animate: true });
        return wait(600);
      }).then(function () {
        if (my !== runId) return;
        fig.setAttribute("data-state", "updated");
        setStamp("synced", "FLOW-001 · new baseline");
        flags.forEach(function (f) { f.textContent = ""; f.classList.remove("is-new"); });
        count.textContent = "0 stale";
        count.classList.remove("is-stale");
        setBytes(mapBytes(), true);
        say("synced", '<span class="log-k">commit</span>Rule 3 rewritten in runtime/submit-order.md, and the 4 reviewed pages synced with <code>sync --page</code>. The commit runs again: order_service.py, the page, and .archlens-state.json land together. The map is back to 6 pages, 0 stale.');
        state = "updated";
        moveFocus(btnUpdate, btnReset);
      });
    }

    function reset() {
      runId++;
      state = "synced";
      fig.setAttribute("data-state", "synced");
      hot.classList.remove("is-edited", "is-done");
      hot.setAttribute("role", "button");
      hot.setAttribute("tabindex", "0");
      hot.setAttribute("aria-label", "Edit lines 25 and 26: limit quantity to 1 to 100");
      hotNew.hidden = true;
      removeCloud(hot);
      removeCloud(cell);
      redline.classList.remove("is-struck");
      redOld.textContent = OLD_RULE;
      redOld.removeAttribute("aria-hidden");
      redNew.textContent = "";
      redNew.classList.remove("is-typing");
      redNew.setAttribute("aria-hidden", "true");
      stamp.classList.remove("is-slam");
      stamp.setAttribute("data-state", "synced");
      stampWord.textContent = "Synced";
      stampSub.textContent = "FLOW-001 · baseline recorded";
      flags.forEach(function (f) { f.textContent = ""; f.classList.remove("is-new"); });
      count.textContent = "0 stale";
      count.classList.remove("is-stale");
      setBytes(mapBytes(), false);
      btnEdit.disabled = false;
      btnUpdate.disabled = true;
      say("", '<span class="log-k">status</span> 6 pages, 0 stale. Click <em>Edit the code</em> or the marked lines 25–26.');
    }

    btnEdit.addEventListener("click", edit);
    btnUpdate.addEventListener("click", update);
    btnReset.addEventListener("click", function () { reset(); btnEdit.focus({ preventScroll: true }); });
    hot.addEventListener("click", edit);
    hot.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); edit(); }
    });
    setBytes(mapBytes(), false);
    window.__archlensMapBytes = mapBytes;

    /* leader line from the edited code to the rule it documents */
    var coupler = $(".coupler", fig), rowHot = $(".row-hot", fig);
    var wideMQ = window.matchMedia("(min-width: 901px)");
    var leader = null;
    function drawLeader() {
      if (!coupler || !rowHot) return;
      if (!wideMQ.matches) {
        if (leader) { coupler.removeChild(leader); leader = null; }
        coupler.classList.remove("has-leader");
        return;
      }
      var cb = coupler.getBoundingClientRect();
      var hb = (hot.classList.contains("is-edited") ? hotNew : hot).getBoundingClientRect();
      var rb = rowHot.getBoundingClientRect();
      var w = cb.width, y1 = hb.top + hb.height / 2 - cb.top, y2 = rb.top + rb.height / 2 - cb.top, mid = Math.round(w / 2);
      if (!leader) {
        leader = doc.createElementNS(NS, "svg");
        leader.setAttribute("class", "coupler-svg");
        leader.setAttribute("aria-hidden", "true");
        leader.appendChild(doc.createElementNS(NS, "path"));
        for (var c = 0; c < 2; c++) { var dot = doc.createElementNS(NS, "circle"); dot.setAttribute("r", "3.5"); leader.appendChild(dot); }
        coupler.appendChild(leader);
      }
      leader.setAttribute("width", w);
      leader.setAttribute("height", Math.max(cb.height, y1, y2) + 8);
      $("path", leader).setAttribute("d", "M0 " + y1.toFixed(1) + "H" + mid + "V" + y2.toFixed(1) + "H" + w);
      var dots = $$("circle", leader);
      dots[0].setAttribute("cx", 0); dots[0].setAttribute("cy", y1.toFixed(1));
      dots[1].setAttribute("cx", w); dots[1].setAttribute("cy", y2.toFixed(1));
      coupler.style.setProperty("--label-y", ((y1 + y2) / 2).toFixed(1) + "px");
      coupler.style.setProperty("--label-x", mid + "px");
      coupler.classList.add("has-leader");
    }
    drawLeader();
    if (doc.fonts && doc.fonts.ready) doc.fonts.ready.then(drawLeader);
    if ("ResizeObserver" in window) {
      var ro = new ResizeObserver(function () { drawLeader(); });
      $$(".panel-code, .panel-doc", fig).forEach(function (p) { ro.observe(p); });
      ro.observe(hot);
    } else {
      window.addEventListener("resize", drawLeader);
    }
    if (wideMQ.addEventListener) wideMQ.addEventListener("change", drawLeader);
  })();

  /* ---------- A-201 loop ---------- */
  (function initLoop() {
    var loop = $("#loop");
    if (!loop) return;
    function activate(step) {
      $$("[data-step]", loop).forEach(function (el) {
        el.classList.toggle("is-active", step != null && el.getAttribute("data-step") === String(step));
      });
    }
    $$(".bubble-svg, .keyed-notes li", loop).forEach(function (el) {
      var step = el.getAttribute("data-step");
      el.addEventListener("mouseenter", function () { activate(step); });
      el.addEventListener("mouseleave", function () { activate(null); });
      el.addEventListener("focus", function () { activate(step); });
      el.addEventListener("blur", function () { activate(null); });
      el.addEventListener("click", function () { activate(step); });
      el.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); activate(step); }
      });
    });
    if (!motionOK) return;
    var drawn = Promise.resolve();
    if (belowFold(loop)) {
      loop.classList.add("is-armed");
      drawn = new Promise(function (done) {
        onSeen($(".loop-figure", loop), function () { loop.classList.add("is-drawn"); setTimeout(done, D4 * 1.6); });
      });
    }
    if (Element.prototype.animate) drawn.then(pulse);

    /* After the drawing, a pulse travels the loop edge by edge at one speed; it pauses off screen. */
    function edgeLength(d) {
      var x = 0, y = 0, len = 0, m, re = /([MHV])\s*(-?[\d.]+)(?:[ ,](-?[\d.]+))?/g;
      while ((m = re.exec(d))) {
        if (m[1] === "M") { x = +m[2]; y = +m[3]; }
        else if (m[1] === "H") { len += Math.abs(m[2] - x); x = +m[2]; }
        else { len += Math.abs(m[2] - y); y = +m[2]; }
      }
      return len;
    }
    function pulse() {
      if (reduced()) return;
      var SPEED = 0.3, GAP = 240, DASH = 26, all = [];
      var vis = new IntersectionObserver(function (entries) {
        entries.forEach(function (e) { (e.target.__anims || []).forEach(function (a) { if (e.isIntersecting) a.play(); else a.pause(); }); });
      });
      $$(".loop-svg", loop).forEach(function (svg) {
        var edges = $$(".edges .ln", svg), lens = edges.map(function (p) { return edgeLength(p.getAttribute("d")); });
        var total = lens.reduce(function (sum, l) { return sum + l / SPEED + GAP; }, 0) + D4, at = 0;
        var g = doc.createElementNS(NS, "g");
        g.setAttribute("class", "pulse");
        g.setAttribute("aria-hidden", "true");
        svg.__anims = edges.map(function (edge, i) {
          var c = doc.createElementNS(NS, "path"), L = lens[i], dur = L / SPEED;
          c.setAttribute("d", edge.getAttribute("d"));
          c.style.strokeDasharray = DASH + " " + (L + DASH);
          c.style.strokeDashoffset = String(DASH);
          c.style.opacity = "1";
          g.appendChild(c);
          var a = c.animate([
            { strokeDashoffset: String(DASH), offset: 0 },
            { strokeDashoffset: String(-L), offset: dur / total },
            { strokeDashoffset: String(-L), offset: 1 }
          ], { duration: total, delay: at, iterations: Infinity, easing: "linear" });
          at += dur + GAP;
          return a;
        });
        all = all.concat(svg.__anims);
        svg.insertBefore(g, $(".bubbles", svg));
        vis.observe(svg);
      });
      if (reduceMQ && reduceMQ.addEventListener) reduceMQ.addEventListener("change", function () {
        if (reduced()) { all.forEach(function (a) { a.cancel(); }); vis.disconnect(); }
      });
    }
  })();

  /* ---------- A-101 terminal replay ---------- */
  (function initTerm() {
    if (!motionOK) return;
    $$("[data-term]").forEach(function (term) {
      var pre = $(".term-body", term), lines = $$(".t-ln", term), run = 0;
      lines.forEach(function (ln) { var tx = $(".t-tx", ln); if (tx) tx.__full = tx.textContent; });
      function play() {
        var my = ++run, alive = function () { return my === run; }, chain = Promise.resolve();
        term.classList.add("is-armed");
        pre.setAttribute("aria-busy", "true");
        lines.forEach(function (ln) { ln.classList.toggle("is-on", false); var tx = $(".t-tx", ln); if (tx) tx.textContent = ""; });
        lines.forEach(function (ln) {
          chain = chain.then(function () {
            if (!alive()) return;
            ln.classList.add("is-on");
            var tx = $(".t-tx", ln);
            return tx ? typeText(tx, tx.__full, alive, 22).then(function () { return wait(D2); }) : wait(STAGGER);
          });
        });
        chain.then(function () { if (alive()) pre.removeAttribute("aria-busy"); });
      }
      var btn = doc.createElement("button");
      btn.type = "button";
      btn.className = "term-replay";
      btn.textContent = "Replay";
      btn.setAttribute("aria-label", "Replay the terminal session");
      btn.addEventListener("click", play);
      $(".term-bar", term).appendChild(btn);
      if (belowFold(term)) { term.classList.add("is-armed"); onSeen(term, play); }
    });
  })();

  /* ---------- scroll reveals and counters (content below the fold only) ---------- */
  function countUp(el) {
    var node = el.firstChild, text = node && node.nodeType === 3 ? node.nodeValue : "";
    var m = /^(\D*)(\d[\d,]*(?:\.\d+)?)([\s\S]*)$/.exec(text);
    if (!m) return;
    var target = parseFloat(m[2].replace(/,/g, "")), dec = (m[2].split(".")[1] || "").length;
    function show(k) {
      var v = (target * k).toFixed(dec);
      node.nodeValue = m[1] + (m[2].indexOf(",") >= 0 ? Number(v).toLocaleString("en-US", { minimumFractionDigits: dec }) : v) + m[3];
    }
    show(0);
    tween(D4, function (k) { if (k < 1) show(k); else node.nodeValue = text; });
  }
  (function initReveal() {
    if (!motionOK) return;
    var blocks = [];
    $$("main .frame").forEach(function (f) {
      Array.prototype.forEach.call(f.children, function (c) { if (!c.classList.contains("zones")) blocks.push(c); });
    });
    var below = blocks.map(belowFold);
    blocks.forEach(function (b, n) {
      if (!below[n]) return;
      b.classList.add("rv");
      $$("[data-stagger]", b).forEach(function (g) {
        Array.prototype.forEach.call(g.children, function (k, i) { k.style.setProperty("--i", Math.min(i, 9)); });
      });
      onSeen(b, function (el, k) {
        k = Math.min(k, 4);
        el.style.setProperty("--d", k);
        el.classList.add("is-in");
        $$("[data-count]", el).forEach(function (c, i) { setTimeout(function () { countUp(c); }, (k + i) * STAGGER); });
        setTimeout(function () { el.classList.toggle("rv", false); el.classList.toggle("is-in", false); el.style.removeProperty("--d"); }, D4 * 2.5);
      });
    });
    root.classList.add("motion");
  })();

  /* ---------- A-501 quiz ---------- */
  (function initQuiz() {
    var body = $("#quiz-body");
    if (!body) return;
    var FLOW = EX + "docs/architecture/runtime/submit-order.md";
    var DATA = EX + "docs/architecture/data.md";
    var ADR = EX + "docs/architecture/decisions/ADR-001.md";
    var SRC = EX + "order_service.py";
    var QUIZ = [
      {
        q: "A caller submits request key <code>request-1</code> twice, both times with SKU <code>BOOK</code> and quantity 2. What does the second call return?",
        choices: ["A new order ID", "The same order ID as the first call", "It raises <code>RequestConflict</code>", "It raises <code>ValueError</code>"],
        answer: 1,
        right: "The insert uses <code>ON CONFLICT(request_key) DO NOTHING</code>, then reads the row for that key. The stored SKU and quantity match, so the function returns the existing ID. The demo prints exactly this.",
        gap: "The unique request key and the conflict clause stop a second row. The insert does nothing, and the read returns the first order’s ID because the data matches.",
        cite: [["runtime/submit-order.md, rule 5", FLOW], ["order_service.py L28–38", SRC + "#L28-L38"]]
      },
      {
        q: "Same key <code>request-1</code>, same SKU, but quantity 3. What happens?",
        choices: ["A second order is stored", "The first order changes to quantity 3", "It raises <code>RequestConflict</code>, and the transaction rolls back", "It returns the first order ID and ignores the new quantity"],
        answer: 2,
        right: "The read finds the stored row, and its SKU and quantity differ from the request. The function raises <code>RequestConflict</code> inside the connection context, so the transaction rolls back.",
        gap: "Reusing a key with different data is a conflict: not an update, and not a silent success. ADR-001 proposes rejecting reuse rather than silently accepting it.",
        cite: [["runtime/submit-order.md, rule 4", FLOW], ["ADR-001", ADR], ["order_service.py L36–37", SRC + "#L36-L37"]]
      },
      {
        q: "What does <code>submit_order(db, \"request-2\", \"BOOK\", True)</code> do?",
        choices: ["Stores quantity 1, because <code>True == 1</code> in Python", "It raises <code>ValueError</code>", "SQLite rejects it with its CHECK constraint", "It raises <code>RequestConflict</code>"],
        answer: 1,
        right: "The check is <code>type(quantity) is not int</code>, and the type of <code>True</code> is <code>bool</code>. A boolean quantity is not an integer for this API, so validation raises <code>ValueError</code> before any write.",
        gap: "<code>True == 1</code> in Python, but the check uses <code>type(quantity) is not int</code>, which rejects <code>bool</code>. Validation runs before the write, so SQLite never sees the value.",
        cite: [["runtime/submit-order.md, rule 3", FLOW], ["data.md, Quantity", DATA], ["order_service.py L25–26", SRC + "#L25-L26"]]
      }
    ];
    var i = 0, score = 0;
    function render() {
      var item = QUIZ[i];
      body.innerHTML = '<p class="q-count">Question ' + (i + 1) + " of " + QUIZ.length + '</p><p class="q">' + item.q + '</p>' +
        '<ul class="choices" role="list">' + item.choices.map(function (c, k) {
          return '<li><button type="button" class="choice" data-k="' + k + '"><span class="choice-key" aria-hidden="true">' +
            "ABCD"[k] + '</span><span><span class="vh">' + "ABCD"[k] + ". </span>" + c + "</span></button></li>";
        }).join("") + '</ul><div class="grade-slot" aria-live="polite"></div>';
      $$(".choice", body).forEach(function (b) { b.addEventListener("click", function () { grade(+b.getAttribute("data-k")); }); });
    }
    function grade(k) {
      var item = QUIZ[i], ok = k === item.answer;
      if (ok) score++;
      $$(".choice", body).forEach(function (b) {
        var bk = +b.getAttribute("data-k");
        b.disabled = true;
        if (bk === item.answer) b.classList.add("is-right");
        else if (bk === k) b.classList.add("is-wrong");
      });
      var last = i === QUIZ.length - 1;
      var html = '<div class="grade' + (ok ? "" : " is-wrong") + '"><p><span class="grade-mark">' + (ok ? "Correct" : "Gap") + "</span>" +
        (ok ? item.right : "The answer is " + "ABCD"[item.answer] + ". " + item.gap) + '</p><p class="cite">Evidence: ' +
        item.cite.map(function (c) { return '<a href="' + c[1] + '">' + c[0] + "</a>"; }).join(" · ") + "</p></div>" +
        '<button type="button" class="btn" id="quiz-next">' + (last ? "See score" : "Next question") + "</button>";
      $(".grade-slot", body).innerHTML = html;
      var next = $("#quiz-next");
      next.addEventListener("click", function () { if (last) done(); else { i++; render(); focusFirst(); } });
      next.focus({ preventScroll: true });
    }
    function focusFirst() { var c = $(".choice", body); if (c) c.focus({ preventScroll: true }); }
    function done() {
      body.innerHTML = '<p class="q-count">Score</p><p class="q">' + score + " of " + QUIZ.length + ". " +
        (score === QUIZ.length ? "Well traced." : "Worth another look.") + '</p><div class="grade"><p>Pages to reread: <a href="' + FLOW +
        '">runtime/submit-order.md</a> and <a href="' + DATA + '">data.md</a>.</p><p class="cite">The real quiz asks five questions, one at a time, and grades each against evidence in your repository.</p></div>' +
        '<button type="button" class="btn btn-ghost" id="quiz-again">Start again</button>';
      var again = $("#quiz-again");
      again.addEventListener("click", function () { i = 0; score = 0; render(); focusFirst(); });
      again.focus({ preventScroll: true });
    }
    render();
  })();

  /* ---------- I-601 tabs ---------- */
  (function initTabs() {
    var wrap = $("#install-tabs");
    if (!wrap) return;
    var list = $('[role="tablist"]', wrap), tabs = $$('[role="tab"]', wrap);
    list.hidden = false;
    function select(tab, focus) {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.setAttribute("aria-selected", on ? "true" : "false");
        t.tabIndex = on ? 0 : -1;
        doc.getElementById(t.getAttribute("aria-controls")).hidden = !on;
      });
      if (focus) tab.focus();
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
    select(tabs[0], false);
  })();

  /* ---------- copy buttons ---------- */
  (function initCopy() {
    function fallbackCopy(text) {
      var ta = doc.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed"; ta.style.top = "-1000px"; ta.style.opacity = "0";
      doc.body.appendChild(ta);
      ta.select();
      var ok = false;
      try { ok = doc.execCommand("copy"); } catch (e) { ok = false; }
      ta.remove();
      return ok;
    }
    function copy(text) {
      if (navigator.clipboard && window.isSecureContext) {
        return navigator.clipboard.writeText(text).then(function () { return true; }, function () { return fallbackCopy(text); });
      }
      return Promise.resolve(fallbackCopy(text));
    }
    $$(".code-block").forEach(function (block) {
      var code = $("code", block);
      if (!code) return;
      var first = code.textContent.split("\n")[0].trim();
      var btn = doc.createElement("button");
      btn.type = "button";
      btn.className = "copy";
      btn.textContent = "Copy";
      btn.setAttribute("aria-label", "Copy: " + (first.length > 48 ? first.slice(0, 48) + "…" : first));
      var live = doc.createElement("span");
      live.className = "vh";
      live.setAttribute("aria-live", "polite");
      btn.addEventListener("click", function () {
        copy(code.textContent).then(function (ok) {
          btn.textContent = ok ? "Copied" : "Press Ctrl+C";
          live.textContent = ok ? "Copied to clipboard" : "Copy failed; select the text and copy it manually";
          btn.classList.toggle("is-done", ok);
          setTimeout(function () { btn.textContent = "Copy"; btn.classList.remove("is-done"); live.textContent = ""; }, 1800);
        });
      });
      block.appendChild(btn);
      block.appendChild(live);
    });
  })();

  /* ---------- keep clouds aligned ---------- */
  var resizeTimer;
  window.addEventListener("resize", function () {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(function () {
      heroCloudDraw(false);
      var hot = $("#hot");
      if (hot && hot.__cloud) drawCloud($(".hot-new", hot), { host: hot, left: 48, gap: 2, seed: 11 });
      var red = $("#redline");
      if (red && red.parentNode.__cloud) drawCloud(red, { host: red.parentNode, gap: 4, seed: 5, blue: true });
    }, 120);
  });
})();
