# Solo Private-Practice Template

A genericized, AI-fillable website template for a **solo therapist's private practice** — derived from a real, polished psychotherapy site and stripped of every owner-specific detail. It is a self-contained single-page app (one `index.html` shell + `app.js` that renders all nine pages client-side: Home, About, Approach, a signature **Method**, a structured multi-phase **Journey/Program**, Fees & Insurance with FAQ, Writing/blog index, Contact with a working consult form, and a combined Privacy/Terms/Accessibility page). No build step, no framework, no backend — just static files you can host anywhere. Every owner-specific string is a `{{token}}` and every piece of prose is an `<!-- AI-GENERATE -->` block, all catalogued in `FILL_MANIFEST.md`, so an AI can spin up a finished site for any clinician from a short `practice.md` intake.

**Visual style (one line):** warm editorial "bone-white" calm — Fraunces serif display over Inter Tight, a talon-gold accent and dawn-sky palette, glass-card facts, soft sunrise rules, and a full-width ambient hawks-in-flight hero video with a static fallback; understated, literary, and clinical rather than corporate or "wellness-spa."

**Best use-case:** an established or newly-launching individual licensed therapist (LCSW / LPC / LMFT / LMHC / PsyD) who offers out-of-network or private-pay telehealth and wants a credible, content-rich brochure site with room to show a personal clinical philosophy, a named method/program, and writing — not a multi-clinician group practice or an insurance-first/booking-portal site (though it adapts cleanly to in-network and single-state practices via the manifest's fallback notes).

---

### What's in here
- `index.html` — nav + footer shell (tokenized), loads the SPA.
- `app.js` — all page content as route templates + the `posts` data array (tokens + AI-GENERATE blocks live here).
- `styles.css` · `tweaks.js` — pure design + a live hero-tuning dev panel; **no customer content**, do not edit to genericize.
- `assets/` — `hawks-hero.mp4` + `hawks-sky.png` and alternates (keep — visual identity); `placeholder-headshot.svg` + `placeholder-logo.svg` (replace per customer).
- `FILL_MANIFEST.md` — the fill engine: every token and every AI-GENERATE prompt with sources + constraints.

### Quick preview
From this folder: `python3 -m http.server 8731` then open `http://127.0.0.1:8731/index.html`. You'll see the layout intact with `{{tokens}}` visible where copy will go.
