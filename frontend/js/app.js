/* Gap frontend. Plain script (no build, no modules) so index.html also works when double-clicked. */
(function () {
  "use strict";
  var CFG = window.GAP_CONFIG || {};
  var BUNDLE = window.GAP_BUNDLE || { companies: [] };
  var COS = BUNDLE.companies || [];
  var app = document.getElementById("app");

  /* ---------- helpers ---------- */
  var V = {
    consistent: { label: "Consistent", icon: "✓", color: "#1f9d8c", gapw: "10px" },
    watch: { label: "Watch", icon: "◐", color: "#d99a1f", gapw: "44px" },
    gap: { label: "Gap", icon: "●", color: "#e5532b", gapw: "92px" },
    insufficient_evidence: { label: "Not enough evidence", icon: "–", color: "#8a96a8", gapw: "26px" }
  };
  var ORDER = ["gap", "watch", "consistent", "insufficient_evidence"];
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); }
  function safeUrl(u) { return typeof u === "string" && /^https?:\/\//i.test(u) ? u : null; }
  function a(u, t, cls) { var s = safeUrl(u); return s ? '<a href="' + esc(s) + '" target="_blank" rel="noopener noreferrer"' + (cls ? ' class="' + cls + '"' : "") + ">" + esc(t) + "</a>" : esc(t); }
  function num(n, d) { return n == null || isNaN(n) ? "–" : Number(n).toFixed(d || 0); }
  function fdate(s) {
    if (!s) return "";
    var m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
    var d = m ? new Date(+m[1], +m[2] - 1, +m[3]) : new Date(s);
    return isNaN(d) ? String(s) : d.toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" });
  }
  function fdt(s) { var d = new Date(s); return isNaN(d) ? "" : d.toLocaleString("en-IN", { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" }); }
  function short(n) { return /^Billionbrains/i.test(n || "") ? "Groww" : String(n || "").replace(/\s+(Limited|Ltd\.?)$/i, ""); }
  function clip(t, n) { t = String(t || ""); if (t.length <= n) return t; var cut = t.slice(0, n); var i = Math.max(cut.lastIndexOf(". "), cut.lastIndexOf("; ")); return (i > n * 0.5 ? cut.slice(0, i + 1) : cut.replace(/\s+\S*$/, "") + "…"); }
  function co(slug) { return COS.filter(function (c) { return c.slug === slug; })[0]; }
  function claimsOf(c) { return (c.findings && c.findings.findings) || []; }
  function allClaims() { var out = []; COS.forEach(function (c) { claimsOf(c).forEach(function (f) { out.push({ co: c, f: f }); }); }); return out; }
  function counts(c) { var k = { gap: 0, watch: 0, consistent: 0, insufficient_evidence: 0 }; claimsOf(c).forEach(function (f) { k[f.verdict] = (k[f.verdict] || 0) + 1; }); return k; }
  /* Gap Score: the same method as backend/score.py. consistent 0, watch 0.5, gap 1; claims backed by more evidence count more;
     the score is the mean of a Beta posterior and comes with a 90% range, because only some claims could be judged. */
  function gapStats(c) {
    var M = { consistent: 0, watch: 0.5, gap: 1 }, S = 0, W = 0, n = 0, total = claimsOf(c).length;
    claimsOf(c).forEach(function (f) {
      if (M[f.verdict] == null) return;
      var ids = {}; (f.evidence || []).forEach(function (e) { ids[e.item_id] = 1; });
      var w = 1 - Math.pow(0.5, Math.max(1, Math.min(5, Object.keys(ids).length)));
      S += w * M[f.verdict]; W += w; n++;
    });
    if (!n) return null;
    var a = 1 + S, b = 1 + W - S, G = 2000, xs = [], lp = [], mx = -Infinity, i, x;
    for (i = 0; i < G; i++) { x = (i + 0.5) / G; xs.push(x); lp.push((a - 1) * Math.log(x) + (b - 1) * Math.log(1 - x)); if (lp[i] > mx) mx = lp[i]; }
    var pdf = lp.map(function (v) { return Math.exp(v - mx); }), tot = pdf.reduce(function (p, q) { return p + q; }, 0), acc = 0, lo = null, hi = null;
    for (i = 0; i < G; i++) { acc += pdf[i] / tot; if (lo === null && acc >= 0.05) lo = xs[i]; if (hi === null && acc >= 0.95) { hi = xs[i]; break; } }
    if (hi === null) hi = 1; if (lo === null) lo = 0;
    var width = (hi - lo) * 100;
    return { score: Math.floor(100 * a / (a + b) + 0.5), low: Math.floor(100 * lo + 0.5), high: Math.floor(100 * hi + 0.5), judged: n, total: total,
             conf: width <= 30 ? "high" : width <= 50 ? "medium" : "low" };
  }
  function gapScore(c) { var g = gapStats(c); return g ? g.score : null; }
  function band(score) {
    if (score == null) return { t: "Not enough evidence", c: "#8a96a8" };
    if (score <= 30) return { t: "Mostly consistent", c: "#1f9d8c" };
    if (score <= 60) return { t: "Mixed picture", c: "#d99a1f" };
    return { t: "Gaps worth reviewing", c: "#e5532b" };
  }
  function pill(v) { var x = V[v] || { label: v, icon: "" }; return '<span class="pill ' + esc(v) + '">' + x.icon + " " + esc(x.label) + "</span>"; }
  function ring(score, size) {
    var b = band(score), C = 2 * Math.PI * 52, off = score == null ? C : C * (1 - score / 100);
    return '<div class="ring" style="' + (size ? "width:" + size + "px;height:" + size + "px" : "") + '"><svg viewBox="0 0 120 120" aria-hidden="true"><circle class="tr" cx="60" cy="60" r="52" fill="none" stroke-width="10"/><circle class="pg" cx="60" cy="60" r="52" fill="none" stroke-width="10" stroke-linecap="round" stroke="' + b.c + '" stroke-dasharray="' + C.toFixed(1) + '" stroke-dashoffset="' + off.toFixed(1) + '"/></svg><div class="n"><b>' + (score == null ? "–" : score) + "</b><i>Gap Score</i></div></div>";
  }
  function vbar(k) {
    var total = ORDER.reduce(function (s, x) { return s + (k[x] || 0); }, 0) || 1;
    return '<div class="vbar" role="img" aria-label="' + ORDER.map(function (x) { return k[x] + " " + V[x].label; }).join(", ") + '">' + ORDER.map(function (x) { return k[x] ? '<span style="width:' + (k[x] / total) * 100 + "%;background:" + V[x].color + '"></span>' : ""; }).join("") + "</div>";
  }
  function vkey(k) { return '<div class="vk">' + ORDER.map(function (x) { return '<span><i class="dot" style="background:' + V[x].color + '"></i><b>' + k[x] + "</b> " + V[x].label + "</span>"; }).join("") + "</div>"; }
  function sum(arr, fn) { return arr.reduce(function (s, x) { return s + (fn(x) || 0); }, 0); }
  function sig(c) { return (c.findings && c.findings.signal_summary) || {}; }

  /* ---------- router ---------- */
  var cleanup = null;
  function parse() {
    var h = location.hash.replace(/^#\/?/, ""), q = {}, qi = h.indexOf("?");
    if (qi >= 0) { h.slice(qi + 1).split("&").forEach(function (p) { var kv = p.split("="); if (kv[0]) q[decodeURIComponent(kv[0])] = decodeURIComponent(kv[1] || ""); }); h = h.slice(0, qi); }
    var parts = h.split("/").filter(Boolean);
    return { page: parts[0] || "home", arg: parts[1] ? decodeURIComponent(parts[1]) : null, q: q };
  }
  function route() {
    if (cleanup) { cleanup(); cleanup = null; }
    var r = parse();
    var page = ["home", "results", "claims", "how", "ask"].indexOf(r.page) >= 0 ? r.page : "notfound";
    document.querySelectorAll("[data-nav]").forEach(function (l) { if (l.dataset.nav === page) l.setAttribute("aria-current", "page"); else l.removeAttribute("aria-current"); });
    if (!COS.length) { app.innerHTML = '<div class="notfound"><h1>No data yet</h1><p class="muted">Run <code>python scripts/build_frontend_data.py</code> from the repo root, then refresh.</p></div>'; return; }
    var R = { home: pHome, results: pResults, claims: pClaims, how: pHow, ask: pAsk, notfound: function () { app.innerHTML = '<div class="notfound"><h1>Page not found</h1><p><a href="#/">Back to home</a></p></div>'; } };
    R[page](r);
    if (!(page === "claims" && r.q.id)) window.scrollTo(0, 0);
    document.title = (page === "home" ? "Gap: what companies say vs. what the web shows" : ({ results: "Results", claims: "Claims", how: "How it works", ask: "Ask Gap" }[page] || "Gap") + " · Gap");
  }

  /* ---------- HOME ---------- */
  function pHome() {
    var cl = allClaims(), tf = COS.map(function (c) { return c.tinyfish || { runs: [] }; });
    var stats = [
      [COS.length, "companies tracked"],
      [cl.length, "management claims checked"],
      [sum(COS, function (c) { return (sig(c).news || {}).articles_collected; }), "news articles read"],
      [sum(COS, function (c) { return sum(sig(c).reviews || [], function (r) { return (r.recent || {}).n; }); }), "recent app reviews sampled"],
      [sum(COS, function (c) { return (sig(c).reddit || {}).posts_used; }), "Reddit posts used"]
    ];
    var runs = sum(tf, function (t) { return t.runs.length; }), arts = sum(tf, function (t) { return sum(t.runs, function (r) { return r.articles; }); });
    var names = COS.map(function (c) { return short(c.company); });

    app.innerHTML =
      '<section class="hero"><canvas id="net" aria-hidden="true"></canvas><div class="hero-in">' +
      '<div><h1>Companies tell their own story. <em>Gap</em> checks it against the web.</h1>' +
      '<p class="lede">We take what management said on the earnings call, collect what app reviews, job pages, Reddit and the news show, and flag where the two disagree.</p>' +
      '<div class="cta"><a class="btn" href="#/results/' + esc(COS[0].slug) + '">Explore the results</a><a class="btn ghost" href="#/how">How it works</a></div>' +
      '<p class="by">Web evidence collected by <b>TinyFish</b> agents for ' + esc(names.join(" and ")) + ".</p></div>" +
      '<div class="ss" id="ss" aria-live="off"></div></div></section>' +

      '<div class="stats"><div class="stats-in">' + stats.map(function (s) { return '<div class="stat"><b>' + s[0] + "</b><span>" + s[1] + "</span></div>"; }).join("") + "</div></div>" +

      '<section class="band"><div class="wrap"><div class="sec-head"><h2>Investors hear one side of the story</h2><p>Earnings calls are prepared and positive. The truth tends to show up first in places nobody tracks together.</p></div>' +
      '<div class="cols3"><div><h3>The story is curated</h3><p>Management picks the words. Results, calls and releases all come from the company.</p></div>' +
      '<div><h3>The evidence is scattered</h3><p>Reviews, hiring, news and Reddit live on different sites, and most have no API.</p></div>' +
      '<div><h3>Nobody connects them</h3><p>Retail investors can’t read every source against every claim, so mismatches surface late.</p></div></div></div></section>' +

      '<section class="band" style="padding-top:0"><div class="wrap"><div class="sec-head"><h2>See how each company held up</h2><p>The Gap Score runs from 0 to 100: consistent counts 0, watch 0.5 and gap 1, and claims backed by more evidence count more. Lower means the web agrees with management.</p></div>' +
      '<div class="co-cards">' + COS.map(function (c) { var k = counts(c), s = gapScore(c), b = band(s);
        return '<a class="co" href="#/results/' + esc(c.slug) + '">' + ring(s) + "<div><h3>" + esc(short(c.company)) + '</h3><p class="q">' + esc(c.quarter) + " earnings call. " + esc(b.t) + "</p>" + vbar(k) + vkey(k) + "</div></a>"; }).join("") + "</div></div></section>" +

      '<section class="band" style="padding-top:0"><div class="wrap"><div class="sec-head"><h2>From transcript to a verdict you can check</h2></div>' + flowHTML() +
      '<p style="margin-top:22px"><a href="#/how">Read the full method</a></p></div></section>' +

      '<section class="band" style="padding-top:0"><div class="wrap"><div class="tf-band"><div><h2>The live web, collected by TinyFish</h2><p>Most of these sources have no API. TinyFish agents browse them like a person would and save what they find, so every number on this site can be traced to a page.</p><p style="margin-top:18px"><a class="btn" href="#/results/' + esc(COS[0].slug) + '#tinyfish" data-tf="1">See the collection log</a></p></div>' +
      '<div class="tf-nums"><div><b>' + runs + '</b><span>news search runs</span></div><div><b>' + arts + '</b><span>articles found</span></div><div><b>4</b><span>signal types</span></div></div></div></div></section>';

    var tfLink = app.querySelector("[data-tf]");
    if (tfLink) tfLink.addEventListener("click", function (e) { e.preventDefault(); location.hash = "#/results/" + COS[0].slug; setTimeout(function () { var el = document.getElementById("tinyfish"); if (el) el.scrollIntoView({ behavior: "smooth" }); }, 60); });
    var stop = heroRotator(cl), stopNet = network(document.getElementById("net"));
    cleanup = function () { stop(); stopNet(); };
  }

  function flowHTML() {
    return '<div class="flow"><div><h3>Claims</h3><p>Eight checkable statements are taken from each earnings-call transcript. Every quote is matched word for word.</p></div>' +
      '<div><h3>Collect with TinyFish</h3><p>TinyFish agents gather app reviews, careers pages, Reddit posts and news, and find the transcript link.</p></div>' +
      '<div><h3>Count, then judge</h3><p>Python counts the numbers. Gemini labels the news and judges each claim against that evidence only.</p></div>' +
      '<div><h3>Validate</h3><p>Python re-checks every verdict. A “gap” needs two different signal types, or it drops to “watch”.</p></div></div>';
  }

  /* the memorable bit: the gap between "said" and "showed" is drawn to scale */
  function heroRotator(cl) {
    var box = document.getElementById("ss"), i = 0, timer = null, hold = false;
    var order = []; var maxLen = Math.max.apply(null, COS.map(function (c) { return claimsOf(c).length; }));
    for (var j = 0; j < maxLen; j++) COS.forEach(function (c) { if (claimsOf(c)[j]) order.push({ co: c, f: claimsOf(c)[j] }); });
    // start on the first non-"insufficient" claim so the first thing shown has a real verdict
    for (var s = 0; s < order.length; s++) if (order[s].f.verdict !== "insufficient_evidence") { i = s; break; }
    box.innerHTML = '<div class="ss-top"><span id="ss-co"></span><span id="ss-topic"></span></div>' +
      '<div class="ss-grid" id="ss-grid"><div class="ss-col ss-say"><h4>Management said</h4><div class="ss-fade" id="ss-say"></div></div><div class="ss-ch" id="ss-ch"></div><div class="ss-col ss-show"><h4>The web showed</h4><div class="ss-fade" id="ss-show"></div></div></div>' +
      '<div class="ss-foot"><span id="ss-pill"></span><span class="scale">The channel between the two columns is drawn to scale: wider means a bigger gap.</span></div>' +
      '<div class="dots" role="group" aria-label="Choose a claim">' + order.map(function (o, n) { return '<button type="button" data-i="' + n + '" style="--dc:' + V[o.f.verdict].color + '" aria-label="' + esc(short(o.co.company) + ": " + o.f.topic) + '"></button>'; }).join("") + "</div>";
    function show(n, instant) {
      i = (n + order.length) % order.length;
      var o = order[i], f = o.f, v = V[f.verdict] || V.insufficient_evidence;
      var fades = box.querySelectorAll(".ss-fade");
      function paint() {
        document.getElementById("ss-co").innerHTML = "<b>" + esc(short(o.co.company)) + "</b> " + esc(o.co.quarter);
        document.getElementById("ss-topic").textContent = f.topic;
        document.getElementById("ss-say").innerHTML = "<blockquote>“" + esc(clip(f.quote, 170)) + '”</blockquote><div class="who">' + esc(f.speaker) + (f.role ? ", " + esc(f.role) : "") + "</div>";
        document.getElementById("ss-show").innerHTML = "<p>" + esc(clip(f.explanation, 250)) + "</p>";
        document.getElementById("ss-pill").innerHTML = pill(f.verdict);
        var g = document.getElementById("ss-grid"), ch = document.getElementById("ss-ch");
        g.style.setProperty("--gapw", v.gapw);
        ch.className = "ss-ch" + (f.verdict === "insufficient_evidence" ? " dashed" : "");
        ch.style.setProperty("--c1", v.color); ch.style.setProperty("--c2", v.color); ch.style.setProperty("--glow", v.color);
        box.querySelectorAll(".dots button").forEach(function (b, k) { if (k === i) b.setAttribute("aria-current", "true"); else b.removeAttribute("aria-current"); });
        fades.forEach(function (x) { x.classList.remove("out"); });
      }
      if (instant) paint(); else { fades.forEach(function (x) { x.classList.add("out"); }); setTimeout(paint, 280); }
    }
    box.querySelectorAll(".dots button").forEach(function (b) { b.addEventListener("click", function () { show(+b.dataset.i); restart(); }); });
    box.addEventListener("mouseenter", function () { hold = true; }); box.addEventListener("mouseleave", function () { hold = false; });
    box.addEventListener("focusin", function () { hold = true; }); box.addEventListener("focusout", function () { hold = false; });
    var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
    function restart() { clearInterval(timer); if (!reduce) timer = setInterval(function () { if (!hold && !document.hidden) show(i + 1); }, 8000); }
    show(i, true); restart();
    return function () { clearInterval(timer); };
  }

  /* drifting network behind the hero */
  function network(cv) {
    if (!cv || !cv.getContext) return function () {};
    var ctx = cv.getContext("2d"), W = 0, H = 0, N = [], raf = 0, dpr = Math.min(window.devicePixelRatio || 1, 2);
    var reduce = window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches;
    function size() { var r = cv.getBoundingClientRect(); W = r.width; H = r.height; cv.width = W * dpr; cv.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); var n = Math.round(Math.min(70, W * H / 15000)); N = []; for (var i = 0; i < n; i++) N.push({ x: Math.random() * W, y: Math.random() * H, vx: (Math.random() - .5) * .22, vy: (Math.random() - .5) * .22, c: Math.random() < .3 ? "229,83,43" : "63,190,172" }); }
    function frame() {
      ctx.clearRect(0, 0, W, H);
      for (var i = 0; i < N.length; i++) {
        var p = N[i]; if (!reduce) { p.x += p.vx; p.y += p.vy; if (p.x < 0 || p.x > W) p.vx *= -1; if (p.y < 0 || p.y > H) p.vy *= -1; }
        for (var j = i + 1; j < N.length; j++) { var q = N[j], dx = p.x - q.x, dy = p.y - q.y, d = Math.sqrt(dx * dx + dy * dy); if (d < 150) { ctx.strokeStyle = "rgba(" + p.c + "," + (0.2 * (1 - d / 150)).toFixed(3) + ")"; ctx.lineWidth = 1; ctx.beginPath(); ctx.moveTo(p.x, p.y); ctx.lineTo(q.x, q.y); ctx.stroke(); } }
        ctx.fillStyle = "rgba(" + p.c + ",.75)"; ctx.beginPath(); ctx.arc(p.x, p.y, 2.2, 0, 6.283); ctx.fill();
      }
      if (!reduce && !document.hidden) raf = requestAnimationFrame(frame); else if (!reduce) raf = setTimeout(function () { raf = requestAnimationFrame(frame); }, 400);
    }
    size(); frame(); window.addEventListener("resize", size);
    return function () { cancelAnimationFrame(raf); clearTimeout(raf); window.removeEventListener("resize", size); };
  }

  /* ---------- RESULTS ---------- */
  function seg(active, base) { return '<div class="seg" role="group" aria-label="Company">' + COS.map(function (c) { return '<button type="button" data-co="' + esc(c.slug) + '" aria-pressed="' + (c.slug === active) + '">' + esc(short(c.company)) + "</button>"; }).join("") + "</div>"; }
  function pResults(r) {
    var c = co(r.arg) || COS[0];
    if (!r.arg || !co(r.arg)) { history.replaceState(null, "", "#/results/" + c.slug); }
    var f = c.findings, k = counts(c), gs = gapStats(c), s = gs ? gs.score : null, b = band(s), n = k.gap + k.watch + k.consistent, tot = claimsOf(c).length, S = sig(c), I = c.inspect || {};
    var parts = []; parts.push(k.gap ? k.gap + " clearly contradicted" : "None clearly contradicted"); parts.push(k.watch + " worth watching"); parts.push(k.insufficient_evidence + " could not be checked with the data collected");
    var flags = S.flags || [];
    var rv = S.reviews || [], jb = (S.jobs || [])[0], nw = S.news || {}, rd = S.reddit || {};
    var r0 = rv[0] || {}, mainRec = r0.recent || {};

    app.innerHTML =
      '<div class="ph"><div class="ph-in"><div><h1>Results</h1><p>' + esc(f.company) + ", " + esc(f.quarter) + " earnings call</p></div>" + seg(c.slug) + "</div></div>" +
      '<div class="body">' +
      '<section class="block"><div class="card sum">' + ring(s) +
      '<div><span class="pill" style="background:' + b.c + ';color:#fff">' + esc(b.t) + "</span><h3>" + esc(f.company) + '</h3><p class="d">' + n + " of " + tot + " management claims had enough public evidence to judge. " + esc(parts.join(". ")) + ".</p>" +
      '<div class="chips"><span class="chip">Analysed ' + esc(fdate(f.generated_at)) + '</span><span class="chip">Model ' + esc(f.model || "n/a") + "</span>" + (f.stale ? '<span class="chip" style="color:#9a6a07">Data changed since this analysis</span>' : "") + "</div></div>" +
      '<div class="sum-bars"><h4>How the ' + tot + " claims came out</h4>" + vbar(k) + vkey(k) + '<p class="note">' + (gs ? "Gap Score " + gs.score + " (likely range " + gs.low + " to " + gs.high + ", confidence " + gs.conf + ", based on " + gs.judged + " of " + gs.total + " claims). " : "") + 'Consistent counts 0, watch 0.5, gap 1, and claims with more evidence count more. “Not enough evidence” is never counted as a pass or a fail.</p></div></div>' +
      (flags.length ? '<ul class="flags">' + flags.map(function (x) { return "<li>⚑ " + esc(x) + "</li>"; }).join("") + "</ul>" : "") + "</section>" +

      '<section class="block"><h2>Claims at a glance</h2><p class="sub">' + tot + ' claims from the call. Select one to read the quote and the evidence.</p><div class="card glance">' +
      claimsOf(c).map(function (x) { return '<a class="row" href="#/claims?co=' + esc(c.slug) + "&id=" + esc(x.claim_id) + '">' + pill(x.verdict) + '<span class="tt">' + esc(x.topic) + '</span><span class="ex">' + esc(x.explanation) + "</span></a>"; }).join("") + "</div></section>" +

      '<section class="block"><h2>Signals</h2><p class="sub">What the web looked like when TinyFish collected it.</p>' +
      '<div class="tiles">' +
      tile(num(mainRec.avg, 1) + " ★", "Recent average rating", "#d99a1f", mainRec.n ? "from " + mainRec.n + " reviews in the last 14 days" + (rv.length > 1 ? " (" + esc(r0.app) + ")" : "") : "") +
      tile(num(mainRec.one_star_pct, 1) + "%", "1-star share", "#e5532b", "") +
      tile(jb ? num(jb.open_roles) : "–", "Open roles counted", "#2a4f8a", jb && I.jobs_total && I.jobs_total !== jb.open_roles ? "The saved careers file lists " + I.jobs_total + " (job-board search). See Inspect." : "shown on the careers page") +
      tile(num(nw.negative_facts) + " / " + num(nw.positive_facts), "Negative / positive news facts", "#1f9d8c", "from " + num(nw.relevant_reported_facts) + " relevant facts") +
      "</div>" +
      '<div class="two"><div class="card"><h3>App reviews</h3>' + (rv.length ? rv.map(appBlock).join("") : '<p class="muted">No review data in this analysis.</p>') + "</div>" +
      '<div class="card"><h3>News and Reddit</h3><p style="font-size:18px"><b>' + num(nw.articles_collected) + "</b> articles read, <b>" + num(nw.relevant_reported_facts) + "</b> relevant facts</p>" +
      vbar({ gap: nw.negative_facts || 0, watch: 0, consistent: nw.positive_facts || 0, insufficient_evidence: Math.max(0, (nw.relevant_reported_facts || 0) - (nw.negative_facts || 0) - (nw.positive_facts || 0)) }) +
      '<div class="vk"><span><i class="dot" style="background:#e5532b"></i><b>' + num(nw.negative_facts) + '</b> negative</span><span><i class="dot" style="background:#1f9d8c"></i><b>' + num(nw.positive_facts) + '</b> positive</span><span><i class="dot" style="background:#8a96a8"></i><b>' + Math.max(0, (nw.relevant_reported_facts || 0) - (nw.negative_facts || 0) - (nw.positive_facts || 0)) + "</b> neutral</span></div>" +
      '<p class="fine">' + num(rd.posts_used) + " of " + num(rd.posts_collected) + " Reddit posts were relevant enough to use.</p></div></div></section>" +

      '<section class="block"><h2>Inspect</h2><p class="sub">What sits behind the numbers.</p><div class="three">' + careersCard(I, jb) + lowStarCard(I) + redditCard(I) + "</div></section>" +

      tinyfishCard(c) +

      ((f.risk_context || []).length ? '<section class="block"><h2>Risk context</h2><p class="sub">Background that matters but does not test a specific claim.</p><div class="card risk">' + f.risk_context.map(function (x) {
        var inner = "<b>" + esc(x.headline) + "</b><span>" + esc([x.publisher, fdate(x.date), (x.type || "").replace(/_/g, " "), x.direction].filter(Boolean).join(", ")) + "</span>" + (x.why_relevant ? "<span>" + esc(x.why_relevant) + "</span>" : "");
        var u = safeUrl(x.source_url); return u ? '<a href="' + esc(u) + '" target="_blank" rel="noopener noreferrer">' + inner + "</a>" : '<a style="cursor:default">' + inner + "</a>"; }).join("") + "</div></section>" : "") +
      dq(f) + "</div>";

    document.getElementById("disclaimer").textContent = f.disclaimer || document.getElementById("disclaimer").textContent;
    app.querySelectorAll("[data-co]").forEach(function (bn) { bn.addEventListener("click", function () { location.hash = "#/results/" + bn.dataset.co; }); });
  }
  function tile(big, label, color, small) { return '<div class="tile" style="--tc:' + color + '"><b>' + esc(big) + "</b><span>" + esc(label) + "</span>" + (small ? "<small>" + esc(small) + "</small>" : "") + "</div>"; }
  function metric(label, val, pct, color, suffix) { return '<div class="metric"><span>' + esc(label) + '</span><div class="tr"><i style="width:' + Math.max(1.5, Math.min(100, pct)) + "%;--c:" + color + '"></i></div><em>' + num(val, suffix === "★" ? 2 : 1) + (suffix || "%") + "</em></div>"; }
  function appBlock(r) {
    var rc = r.recent || {};
    return '<div class="app"><h4>' + esc(r.app) + "</h4>" + metric("Avg rating", rc.avg, (rc.avg || 0) / 5 * 100, "#d99a1f", " ★") + metric("1-star share", rc.one_star_pct, rc.one_star_pct || 0, "#e5532b") + metric("Service complaints", rc.service_pct, rc.service_pct || 0, "#2a4f8a") +
      '<p class="fine">' + num(rc.n) + " reviews in the 14 days to " + esc(fdate(r.ref_date)) + (r.comparable ? "" : ". No earlier window, so no trend can be called") + ". Store rating " + num(r.overall_rating, 1) + " from " + num(r.total_reviews_in_file) + " reviews in the file.</p></div>";
  }
  function careersCard(I, jb) {
    var mismatch = I.jobs_total && jb && I.jobs_total !== jb.open_roles;
    var body = (I.jobs || []).slice(0, 6).map(function (j) { return "<li>" + (j.brand ? '<span class="tag">' + esc(j.brand) + "</span>" : "") + esc(j.title) + '<span class="l">' + esc(j.location) + "</span></li>"; }).join("");
    return '<div class="card"><h3>Careers listings</h3>' + (I.jobs_total != null ? '<div class="big">' + esc(I.jobs_total) + '</div><p class="fine" style="margin:4px 0 8px">' + esc(I.jobs_method || "listings in the saved file") + "</p>" : '<p class="muted">No careers data in the saved files.</p>') +
      (mismatch ? '<div class="warn">The analysis used ' + esc(jb.open_roles) + " listings it could read. Treat the hiring signal as a small sample.</div>" : "") +
      '<ul class="list">' + body + "</ul>" + (I.jobs_url ? '<p class="fine">' + a(I.jobs_url, "Open careers page") + "</p>" : "") + "</div>";
  }
  function lowStarCard(I) {
    return '<div class="card"><h3>Low-star reviews, newest first</h3>' + ((I.low_star || []).length ? '<ul class="list">' + I.low_star.map(function (r) { return '<li class="rev"><q>“' + esc(clip(r.text, 200)) + '”</q><div class="l"><span class="s">' + "★".repeat(r.stars) + "</span> " + esc(r.app) + ", " + esc(r.date) + "</div></li>"; }).join("") + "</ul>" : '<p class="muted">No low-star reviews in the saved file.</p>') + "</div>";
  }
  function redditCard(I) {
    return '<div class="card"><h3>Reddit posts used</h3>' + ((I.reddit || []).length ? '<ul class="list">' + I.reddit.map(function (p) { return "<li>" + a(p.url, p.title || "Reddit post") + '<span class="l">' + esc(fdate(p.date)) + "</span></li>"; }).join("") + "</ul>" : '<p class="muted">No Reddit posts in the saved files.</p>') + "</div>";
  }
  function tinyfishCard(c) {
    var t = c.tinyfish || { runs: [] }, m = t.meta, tot = sum(t.runs, function (r) { return r.articles; });
    return '<section class="block" id="tinyfish"><div class="card tfc"><div class="tfh"><span class="tfb">TinyFish</span><h3 style="margin:0">Collected from the live web</h3></div>' +
      '<p class="muted" style="max-width:62ch">TinyFish agents gathered the signals above and found the earnings-call transcript. Below is the news collection log for ' + esc(short(c.company)) + ".</p>" +
      (m ? '<div class="chips"><span class="chip">Source: ' + esc(m.source) + '</span><span class="chip">Collected ' + esc(fdt(m.collected_at)) + '</span><span class="chip">' + esc(m.articles_total) + " articles after removing duplicates</span></div>" : "") +
      (t.runs.length ? '<div class="scroll"><table style="margin-top:14px"><thead><tr><th>Run</th><th>Search query</th><th>Type</th><th class="n">Articles</th></tr></thead><tbody>' + t.runs.map(function (r) { return '<tr><td><span class="tag">' + esc(r.run) + "</span></td><td>" + esc(r.query) + "</td><td>" + esc((r.query_type || "").replace(/_/g, " ")) + '</td><td class="n">' + esc(r.articles) + "</td></tr>"; }).join("") + '<tr><td></td><td><b>Total before removing duplicates</b></td><td></td><td class="n"><b>' + tot + "</b></td></tr></tbody></table></div>" : '<p class="fine">No run log saved for this company.</p>') + "</div></section>";
  }
  function dq(f) {
    var w = []; (f.data_quality || []).forEach(function (q) { (q.warnings || []).forEach(function (x) { w.push(q.signal + ": " + x); }); });
    (f.validation_notes || []).forEach(function (x) { w.push(typeof x === "string" ? x : JSON.stringify(x)); });
    return w.length ? '<section class="block"><details class="card"><summary style="cursor:pointer;font-weight:700">Data quality notes (' + w.length + ')</summary><ul class="list" style="margin-top:12px">' + w.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul></details></section>" : "";
  }

  /* ---------- CLAIMS ---------- */
  function pClaims(r) {
    var st = { co: r.q.co || "all", v: r.q.v || "all", text: "" }, openId = r.q.id ? r.q.co + ":" + r.q.id : null;
    var total = allClaims().length;
    app.innerHTML = '<div class="ph"><div class="ph-in"><div><h1>Claims</h1><p>' + total + " things management said, each checked against the evidence</p></div></div></div>" +
      '<div class="body"><div class="tools"><input class="search" id="q" type="search" placeholder="Search a topic or a quote" aria-label="Search claims" autocomplete="off">' +
      '<div class="fl" id="cf"></div><div class="fl" id="vf"></div></div><div id="list"></div></div>';
    function chips(id, items, key) {
      document.getElementById(id).innerHTML = items.map(function (x) { return '<button type="button" data-v="' + esc(x[0]) + '" aria-pressed="' + (st[key] === x[0]) + '">' + esc(x[1]) + "</button>"; }).join("");
      document.getElementById(id).querySelectorAll("button").forEach(function (b) { b.addEventListener("click", function () { st[key] = b.dataset.v; paint(); }); });
    }
    function paint() {
      chips("cf", [["all", "All companies"]].concat(COS.map(function (c) { return [c.slug, short(c.company)]; })), "co");
      chips("vf", [["all", "Every verdict"]].concat(ORDER.map(function (x) { return [x, V[x].label]; })), "v");
      var t = st.text.toLowerCase();
      var rows = allClaims().filter(function (o) { return (st.co === "all" || o.co.slug === st.co) && (st.v === "all" || o.f.verdict === st.v) && (!t || (o.f.topic + " " + o.f.quote + " " + o.f.explanation).toLowerCase().indexOf(t) >= 0); });
      document.getElementById("list").innerHTML = rows.length ? rows.map(function (o) { return claimHTML(o, openId === o.co.slug + ":" + o.f.claim_id); }).join("") : '<div class="empty">No claims match. Clear the search or pick another verdict.</div>';
    }
    document.getElementById("q").addEventListener("input", function (e) { st.text = e.target.value; paint(); });
    paint();
    if (openId) { var el = document.getElementById("c-" + openId.replace(":", "-")); if (el) setTimeout(function () { el.scrollIntoView({ block: "center" }); el.classList.add("hl"); }, 80); }
  }
  function claimHTML(o, open) {
    var f = o.f, ev = f.evidence || [], v = V[f.verdict] || V.insufficient_evidence;
    return '<details class="claim" id="c-' + esc(o.co.slug) + "-" + esc(f.claim_id) + '" style="--vc:' + v.color + '"' + (open ? " open" : "") + "><summary>" +
      '<span class="m">' + esc(short(o.co.company)) + ", claim " + esc(f.claim_id) + "</span>" + pill(f.verdict) + "<h3>" + esc(f.topic) + "</h3><q>“" + esc(f.quote) + "”</q></summary>" +
      '<div class="cb"><div class="muted" style="font-size:14px">' + esc(f.speaker) + (f.role ? ", " + esc(f.role) : "") + ". " + a(f.source_url, f.source || "Earnings call") + (f.date ? ", " + esc(fdate(f.date)) : "") + "</div>" +
      "<p>" + esc(f.explanation) + "</p>" +
      '<div class="cv"><div><b>The evidence covers</b>' + esc(f.covers || "–") + "</div><div><b>It does not cover</b>" + esc(f.does_not_cover || "–") + "</div></div>" +
      (f.weight_note ? '<p class="muted" style="font-size:15px"><b>Why it matters:</b> ' + esc(f.weight_note) + "</p>" : "") +
      (ev.length ? '<div class="ev"><h4>' + ev.length + " piece" + (ev.length > 1 ? "s" : "") + " of evidence</h4>" + ev.map(function (e) { return '<div class="it"><span class="tag">' + esc(e.signal) + "</span>" + a(e.source_url, e.title || e.item_id) + '<div class="l">' + esc(fdate(e.date)) + "</div>" + (e.what_it_shows ? "<div>" + esc(e.what_it_shows) + "</div>" : "") + "</div>"; }).join("") + "</div>" : '<p class="muted">No evidence was cited for this claim.</p>') + "</div></details>";
  }

  /* ---------- HOW IT WORKS ---------- */
  function pHow() {
    var model = (COS[0].findings || {}).model || "Gemini";
    app.innerHTML = '<div class="ph"><div class="ph-in"><div><h1>How it works</h1><p>From earnings-call transcript to a verdict you can check</p></div></div></div><div class="body narrow" style="max-width:1000px">' +
      '<section class="block"><h2>The pipeline</h2>' + flowHTML() + "</section>" +
      '<section class="block"><h2>What the verdicts mean</h2><div class="card scroll"><table class="vtab"><tbody>' +
      [["consistent", "The evidence supports what management said."], ["watch", "Some evidence points the other way, or the claim is only partly supported."], ["gap", "The evidence contradicts the claim, and it shows up in at least two different kinds of signal."], ["insufficient_evidence", "We did not collect anything that can confirm or contradict it. This is not a pass."]].map(function (x) { return "<tr><td>" + pill(x[0]) + "</td><td>" + x[1] + "</td></tr>"; }).join("") + "</tbody></table></div>" +
      '<p class="fine">Gap Score = a 0 to 100 score where consistent counts 0, watch 0.5 and gap 1, and claims backed by more evidence count more. Because only some claims can be judged, it comes with a likely range. A higher score means a bigger distance between the story and the evidence. Verdicts are judged by ' + esc(model) + " and then re-checked by Python.</p></section>" +
      '<section class="block"><h2>What each signal tells you</h2><div class="card scroll"><table><thead><tr><th>Signal</th><th>Collected from</th><th>What it tells you</th></tr></thead><tbody>' +
      [["App reviews", "Play Store, by a TinyFish agent", "Average rating, share of 1-star reviews and service complaints among the newest reviews."], ["Careers", "Company careers pages or job boards, by a TinyFish agent", "How many roles are open, and in which brand."], ["Reddit", "TinyFish Search and Fetch", "Recent user posts and discussion."], ["News", "TinyFish Search, then a news filter", "Dated, sourced articles, labelled positive, negative or neutral."]].map(function (x) { return "<tr><td><b>" + x[0] + "</b></td><td>" + x[1] + "</td><td>" + x[2] + "</td></tr>"; }).join("") + "</tbody></table></div></section>" +
      '<section class="block"><h2>Limits you should know</h2><div class="limits"><div class="card"><h3>A snapshot, not a trend</h3><p>Most signals are one collection, so “no trend” is often the honest answer.</p></div><div class="card"><h3>Samples are small</h3><p>Review samples are dozens, not thousands. Treat the numbers as indicators.</p></div><div class="card"><h3>Public evidence only</h3><p>Gap cannot see inside a company. It checks claims against what is publicly visible.</p></div></div></section>' +
      '<section class="block"><h2>An example of a gap</h2><div class="card sample"><div class="t">Illustration with a fictional company, not real data</div><p>Management says “customer experience improved a lot this quarter.” App reviews show the 1-star share rising, and Reddit threads about slow support are growing. Two different signals disagree with the claim, so the verdict is ' + pill("gap") + ".</p></div></section>" +
      '<section class="block"><h2>Run it yourself</h2><pre class="code">pip install -r requirements.txt\ncp .env.example .env                   <i># add GEMINI_API_KEY</i>\npython -m backend.cli analyze groww\npython -m backend.cli analyze eternal\npython scripts/build_frontend_data.py  <i># refresh the website data</i>\n<i># open frontend/index.html in your browser</i></pre>' +
      '<p class="fine">To add another company: add its claims and signal files, run <code>analyze</code> and the build script, and it appears on every page.</p></section></div>';
  }

  /* ---------- ASK GAP ---------- */
  var ADVICE = /\b(buy|sell|hold|target price|price target|should i invest|invest in|multibagger|stock tip)\b/i;
  var apiBase = (/\/app\/?/.test(location.pathname) && /^https?:/.test(location.protocol)) ? location.origin : (CFG.API_BASE || "");
  apiBase = apiBase.replace(/\/$/, "");
  /* Wake the backend as soon as the page opens (a sleeping free server needs up to a minute) and show the badge when it answers.
     The chat never waits for this: it always tries the backend itself. */
  function probeApi() {
    if (!apiBase) return;
    var ctl = window.AbortController ? new AbortController() : null, t = setTimeout(function () { ctl && ctl.abort(); }, CFG.API_PROBE_MS || 60000);
    fetch(apiBase + "/companies", ctl ? { signal: ctl.signal } : {}).then(function (r) { if (!r.ok) throw 0; return r.json(); }).then(function () {
      clearTimeout(t); var b = document.getElementById("badge"); if (b) { b.textContent = "live answers"; b.classList.add("live"); }
    }).catch(function () { clearTimeout(t); });
  }
  function askAnswer(slug, q) {
    if (ADVICE.test(q)) return Promise.resolve({ can_answer: false, sources: [], answer: "Gap does not give buy, sell or price advice. It compares what the company said on its earnings call with public evidence. You can ask what the evidence says about any claim." });
    var c = co(slug);
    if (apiBase) {
      var ctl = window.AbortController ? new AbortController() : null, t = setTimeout(function () { ctl && ctl.abort(); }, CFG.ASK_TIMEOUT_MS || 45000);
      return fetch(apiBase + "/ask/" + encodeURIComponent(slug), { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question: q }), signal: ctl ? ctl.signal : undefined })
        .then(function (r) { clearTimeout(t); if (!r.ok) throw new Error("backend"); return r.json(); })
        .then(function (res) { return (res && res.answer) ? res : offline(c, q); })
        .catch(function () { clearTimeout(t); return offline(c, q); });
    }
    return Promise.resolve(offline(c, q));
  }
  function offline(c, q) {
    var f = c.findings, items = {}; (f.items || []).forEach(function (i) { items[i.item_id] = i; });
    var low = q.toLowerCase(), cl = claimsOf(c);
    function srcs(list) { var seen = {}, out = []; list.forEach(function (x) { (x.evidence || []).forEach(function (e) { if (seen[e.item_id]) return; seen[e.item_id] = 1; var it = items[e.item_id] || e; out.push({ signal: it.signal, title: it.title, source_url: it.source_url, date: it.date }); }); }); return out.slice(0, 6); }
    var PROF = { groww: "Groww (run by Billionbrains Garage Ventures) is an Indian investing platform. People use its app and website to invest in stocks and mutual funds, and it offers other products such as futures and options and margin trading. It earns mainly from broking fees and related services.",
                 eternal: "Eternal is the listed Indian company that owns Zomato, the food delivery and dining app, and Blinkit, a quick-commerce app that delivers groceries and other items in minutes. It also runs Hyperpure, which supplies restaurants." };
    var pm = low.replace(/[?.!]+$/, "").match(/^(what is|what's|what does|who is|tell me about|explain|describe)\s+(the\s+)?(groww|billionbrains|eternal|zomato|blinkit)(\s+(do|does|company|business|app))*$/);
    if (pm) { var ps = /groww|billionbrains/.test(pm[3]) ? "groww" : "eternal"; return { can_answer: true, sources: [], answer: PROF[ps] + "\n\n(General background, not from the evidence Gap collected, and it may be out of date.)" }; }
    if (/\b(more|most|fewer|less|higher|lower|worse|better|compare|than|versus|vs|which)\b/.test(low) && /\b(gaps?|watch|score|mismatch)\b/.test(low)) {
      var lines = COS.map(function (x) { var kk = counts(x), g = gapStats(x); return short(x.company) + ": " + kk.gap + " gap, " + kk.watch + " watch, " + kk.consistent + " consistent, " + kk.insufficient_evidence + " not enough evidence" + (g ? ". Gap Score " + g.score + " (likely range " + g.low + " to " + g.high + ")" : "") + "."; });
      return { can_answer: true, sources: [], answer: lines.join("\n") + "\n\nEach score rests on only part of the claims, so treat it as a snapshot." };
    }
    var listy = /\b(which|list|show|how many|what are|any)\b/.test(low);
    var vm = !listy ? null : /\bgaps?\b|contradict/.test(low) ? "gap" : /watch/.test(low) ? "watch" : /\bconsistent\b|supported/.test(low) ? "consistent" : /not enough|insufficient|unclear|unverif|could not be checked/.test(low) ? "insufficient_evidence" : null;
    if (vm) {
      var hit = cl.filter(function (x) { return x.verdict === vm; });
      return { can_answer: true, answer: hit.length ? short(c.company) + " has " + hit.length + " claim" + (hit.length > 1 ? "s" : "") + " marked “" + V[vm].label + "”:\n" + hit.map(function (x) { return "• " + x.topic; }).join("\n") : "No claims for " + short(c.company) + " are marked “" + V[vm].label + "”.", sources: [] };
    }
    if (/tinyfish|collect|scrap|source/.test(low)) {
      var t = c.tinyfish || { runs: [] };
      return { can_answer: true, answer: "TinyFish agents collected the web signals for " + short(c.company) + " (app reviews, careers, Reddit, news). The news log has " + t.runs.length + " search runs and " + sum(t.runs, function (r) { return r.articles; }) + " articles before removing duplicates. See the TinyFish card on the Results page.", sources: [] };
    }
    var stem = function (w) { return w.length > 5 ? w.slice(0, w.length - 3) : w.length > 4 ? w.slice(0, 4) : w; };
    var stop = "the and for what does with about that this claim claims backed evidence say says are was how why any from have has company".split(" ");
    var keys = (low.match(/[a-z0-9]{3,}/g) || []).filter(function (w) { return stop.indexOf(w) < 0; }).map(stem);
    function score(t) { t = t.toLowerCase(); return keys.reduce(function (n, k) { return n + (t.indexOf(k) >= 0 ? 1 : 0); }, 0); }
    var ranked = cl.map(function (x) { return { x: x, s: score(x.topic + " " + x.quote + " " + x.explanation) * 2 + score(x.covers || "") }; }).filter(function (r) { return r.s > 0; }).sort(function (p, q2) { return q2.s - p.s; }).slice(0, 2);
    if (!ranked.length) return { can_answer: false, sources: [], answer: "The AI is busy right now and this question needs it. Please try again in a moment, or ask about a topic from the Claims page." };
    return { can_answer: true, sources: srcs(ranked.map(function (r) { return r.x; })), answer: "The AI is busy for a moment, so here is what Gap's analysis says on this.\n\n" + ranked.map(function (r) { return r.x.topic + ": " + V[r.x.verdict].label + ". " + r.x.explanation; }).join("\n\n") };
  }
  function pAsk(r) {
    var cur = (co(r.q.co) || COS[0]).slug;
    app.innerHTML = '<div class="ph"><div class="ph-in"><div><h1>Ask Gap</h1><p>Questions about what the evidence says. Gap answers from the saved findings and does not give buy or sell advice.</p></div></div></div>' +
      '<div class="body narrow" style="max-width:900px"><div class="askbox"><form class="askrow" id="af"><select id="as" aria-label="Company">' + COS.map(function (c) { return '<option value="' + esc(c.slug) + '"' + (c.slug === cur ? " selected" : "") + ">" + esc(short(c.company)) + "</option>"; }).join("") + '</select><input id="ai" maxlength="500" placeholder="For example: Is the pricing claim backed up?" aria-label="Your question" autocomplete="off"><button class="btn dark" type="submit">Ask</button></form><div class="sug" id="sg"></div></div><div class="qa" id="qa" aria-live="polite"></div></div>';
    function sugg() {
      var c = co(document.getElementById("as").value), cl = claimsOf(c);
      var s = cl.slice(0, 3).map(function (x) { return "Is the “" + x.topic + "” claim backed up?"; }).concat(["Which claims are worth watching?", "How did TinyFish collect the data?"]);
      var sg = document.getElementById("sg"); sg.innerHTML = s.map(function (x) { return '<button type="button">' + esc(x) + "</button>"; }).join("");
      sg.querySelectorAll("button").forEach(function (b) { b.addEventListener("click", function () { document.getElementById("ai").value = b.textContent; ask(b.textContent); }); });
    }
    function ask(q) {
      q = (q || "").trim(); if (!q) return;
      var slug = document.getElementById("as").value, box = document.getElementById("qa"), id = "a" + Date.now();
      box.insertAdjacentHTML("afterbegin", '<div class="a" id="' + id + '"><div class="qq">' + esc(q) + '</div><div class="spin" role="status" aria-label="Working"></div></div>');
      var hint = setTimeout(function () { var sp = document.querySelector("#" + id + " .spin"); if (sp) sp.insertAdjacentHTML("afterend", '<div class="fine" style="margin-top:8px">Still working. The server may be waking up, which can take up to a minute.</div>'); }, 8000);
      askAnswer(slug, q).then(function (res) {
        clearTimeout(hint);
        var el = document.getElementById(id); if (!el) return;
        el.className = "a" + (res.can_answer ? "" : " no");
        el.innerHTML = '<div class="qq">' + esc(q) + '</div><div class="tx">' + esc(res.answer) + "</div>" + ((res.sources || []).length ? '<div class="src"><b>Sources</b>' + res.sources.map(function (s) { return "<div>" + (safeUrl(s.source_url) ? a(s.source_url, (s.signal ? s.signal + ": " : "") + s.title) : esc((s.signal ? s.signal + ": " : "") + s.title)) + (s.date ? ", " + esc(fdate(s.date)) : "") + "</div>"; }).join("") + "</div>" : "");
      });
      document.getElementById("ai").value = "";
    }
    document.getElementById("af").addEventListener("submit", function (e) { e.preventDefault(); ask(document.getElementById("ai").value); });
    document.getElementById("as").addEventListener("change", sugg);
    sugg();
  }

  window.addEventListener("hashchange", route);
  probeApi();
  route();
})();
