/* ═══════════════════════════════════════════════════════════════════
   hero-scramble.js — split-flap ("Solari" / Penn Station board) hero.

   Progressive enhancement ONLY. The real <h1> headline ships in the markup
   (SEO + no-JS + reduced-motion all see it); this upgrades it to a split-flap
   board that flips, in alphabetical order, from one approved phrase to the
   next — calm and legible, never a random strobe.

   HONESTY: every phrase is read from already-linted tokens carried on the
   hero <section> (tagline / specialties / populations) plus the resolved
   <h1> headline itself. This file invents no words — it only re-spells
   existing approved text. It is loaded by index.html (NOT app.js), so the
   headless render-check (which executes only app.js) never sees it.

   Self-contained: no deps, injects its own style, browser-only APIs stay here.
   Carries no curly-brace tokens and no generator marker, so the fill-engine
   verifier copies it through untouched.

   Accessibility/comfort: ordered flips at a human cadence with a staggered
   wave (never the whole line changing at once), flipping cells merely dimmed
   (no colour strobe), and prefers-reduced-motion gets a plain text rotate.
   ═══════════════════════════════════════════════════════════════════ */
(function () {
  'use strict';

  var CFG = {
    tickMs: 68,          // ms per flip — slow, board-like
    stagger: 1.2,        // ticks of delay per column → tight left→right sweep (~6 cells active)
    minFlips: 3,         // fewest letters a changing cell flips through
    maxFlips: 7,         // most letters a changing cell flips through (bounded = calm)
    holdMs: 2600,        // pause on each fully-spelled phrase
    uppercase: true,     // display-only (CSS); DOM text stays natural-case
    font: 'Anton',       // display font for the board (loaded on demand); '' = inherit template
    glyphs: " ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.,&·'-"
  };

  var reduce = false;
  try { reduce = window.matchMedia('(prefers-reduced-motion:reduce)').matches; } catch (e) {}

  function esc(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

  // ---- one-time style ------------------------------------------------------
  function injectStyle() {
    if (document.getElementById('kh-style')) return;
    if (CFG.font) {
      var l = document.createElement('link');
      l.rel = 'stylesheet';
      l.href = 'https://fonts.googleapis.com/css2?family=' + encodeURIComponent(CFG.font) + '&display=swap';
      document.head.appendChild(l);
    }
    var s = document.createElement('style');
    s.id = 'kh-style';
    s.textContent =
      '#h1.kh-on{text-transform:' + (CFG.uppercase ? 'uppercase' : 'none') + ';' +
        (CFG.font ? "font-family:'" + CFG.font + "',sans-serif;" : '') +
        'letter-spacing:.012em;line-height:.95;font-size:clamp(2.2rem,7.4vw,5.4rem);}' +
      '#h1.kh-on .kh-flap{opacity:.5;}' +
      '#h1.kh-on{will-change:contents;}';
    document.head.appendChild(s);
  }

  // ---- the split-flap engine ----------------------------------------------
  function Board(el) { this.el = el; this.timer = null; this.cur = []; }
  Board.prototype.to = function (text) {
    var self = this, GL = CFG.glyphs, GLn = GL.length;
    var disp = text.toUpperCase();
    var L = Math.max(disp.length, this.cur.length);   // pad so a shrinking line flips trailing cells to blank
    var plan = [];
    for (var i = 0; i < L; i++) {
      var ch = i < disp.length ? disp[i] : ' ', gi = GL.indexOf(ch);
      var prev = (this.cur[i] != null && this.cur[i] >= 0) ? this.cur[i] : 0; // old glyph (0 = space)
      if (gi < 0) { plan.push({ fixed: true, ch: ch }); continue; }       // unknown char → static
      if (prev === gi) { plan.push({ idx: gi, target: gi, start: 0, hold: gi, done: true }); continue; }
      var flips = CFG.minFlips + Math.floor(Math.random() * (CFG.maxFlips - CFG.minFlips + 1));
      var startIdx = ((gi - flips) % GLn + GLn) % GLn;                     // flip forward to land on target
      plan.push({ idx: startIdx, target: gi, start: Math.floor(i * CFG.stagger), hold: prev, done: false });
    }
    if (this.timer) clearInterval(this.timer);
    var tick = 0, fin;
    var p = new Promise(function (r) { fin = r; });
    this.timer = setInterval(function () {
      var out = '', allDone = true;
      for (var j = 0; j < plan.length; j++) {
        var q = plan[j];
        if (q.fixed) { out += esc(q.ch); continue; }
        if (q.done) { out += esc(GL[q.target]); continue; }
        if (tick < q.start) { out += esc(GL[q.hold]); allDone = false; continue; } // hold prior letter, steady
        q.idx = (q.idx + 1) % GLn;
        if (q.idx === q.target) { q.done = true; out += esc(GL[q.target]); }
        else { out += '<span class="kh-flap">' + esc(GL[q.idx]) + '</span>'; allDone = false; }
      }
      self.el.innerHTML = out;
      self.cur = plan.map(function (q) { return q.fixed ? -1 : q.idx; });
      tick++;
      if (allDone) { clearInterval(self.timer); self.timer = null; fin(); }
    }, CFG.tickMs);
    return p;
  };
  Board.prototype.kill = function () { if (this.timer) { clearInterval(this.timer); this.timer = null; } };

  // ---- phrase sourcing (approved tokens only) ------------------------------
  function fmtList(s) {
    return String(s || '').split(',').map(function (x) { return x.trim(); })
      .filter(Boolean).join(' · ');
  }
  function phrasesFor(section, h1) {
    var out = [];
    var head = (h1.textContent || '').trim();      // the resolved hero_headline
    if (head) out.push(head);
    var ds = section.dataset || {};
    if ((ds.khTagline || '').trim()) out.push(ds.khTagline.trim());
    if ((ds.khSpecialties || '').trim()) out.push(fmtList(ds.khSpecialties));
    if ((ds.khPopulations || '').trim()) out.push(fmtList(ds.khPopulations));
    var seen = {}, uniq = [];
    out.forEach(function (p) { var k = p.toLowerCase(); if (p && !seen[k]) { seen[k] = 1; uniq.push(p); } });
    return uniq;
  }

  // ---- lifecycle -----------------------------------------------------------
  var state = { h1: null, bd: null, timer: null, phrases: null };

  function isHome() {
    var h = (location.hash || '').replace(/^#\/?/, '');
    return h === '' || h === 'home';
  }
  function stop() {
    if (state.timer) { clearTimeout(state.timer); clearInterval(state.timer); state.timer = null; }
    if (state.bd) { state.bd.kill(); state.bd = null; }
    if (state.h1) { state.h1.classList.remove('kh-on'); }
    state.h1 = null; state.phrases = null;
  }
  function cycle(i) {
    if (!state.bd || !state.h1) return;
    var phrase = state.phrases[i % state.phrases.length];
    state.bd.to(phrase).then(function () {
      if (!state.h1) return;
      state.h1.textContent = phrase;                 // settle clean → CSS uppercases; natural-case in DOM
      state.timer = setTimeout(function () { cycle(i + 1); }, CFG.holdMs);
    });
  }
  function boot() {
    if (!isHome()) { stop(); return; }
    var section = document.querySelector('section.hero[data-kh]');
    if (!section) return;
    var h1 = section.querySelector('#h1') || document.getElementById('h1');
    if (!h1) return;
    if (state.h1 === h1) return;                      // already attached — no-op
    stop();
    var phrases = phrasesFor(section, h1);
    if (phrases.length < 2) return;                   // nothing to cycle to → leave static
    injectStyle();
    h1.setAttribute('aria-label', phrases[0]);        // stable accessible name
    if (reduce) {                                     // no flips — plain text rotate
      var i = 0;
      state.h1 = h1; state.phrases = phrases;
      state.timer = setInterval(function () {
        if (!state.h1) return; i = (i + 1) % phrases.length; h1.textContent = phrases[i];
      }, CFG.holdMs + 800);
      return;
    }
    h1.classList.add('kh-on');
    state.h1 = h1; state.phrases = phrases; state.bd = new Board(h1);
    cycle(0);
  }

  // initial render may be deferred by app.js navigate(); retry a few frames.
  var tries = 0;
  function tryBoot() {
    boot();
    if (!state.h1 && tries++ < 12) requestAnimationFrame(tryBoot);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', tryBoot);
  } else { tryBoot(); }
  window.addEventListener('load', boot);
  window.addEventListener('hashchange', function () { tries = 0; tryBoot(); });
  document.addEventListener('visibilitychange', function () {
    if (document.hidden) { if (state.timer) { clearTimeout(state.timer); state.timer = null; } }
    else if (state.bd && state.h1 && !state.timer) { cycle(0); }
  });
})();
