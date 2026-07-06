# Shaula — Social Video (Remotion)

The **video** half of Shaula's kinetic headline. It renders a "Solari" / Penn-Station
**split-flap board** as an MP4 from a therapy practice's **approved phrases** — the social/
marketing twin of the website hero (`templates/private-practice/hero-scramble.js`). Letters flip
in alphabetical order, in a left→right wave, dimmed while flipping — calm and legible, never a
strobe.

This is a **real Remotion project** (the repo's `skills/remotion-video/SKILL.md` is the
instructions; this is the working code). It is **additive** — it does not touch the live engine,
templates, or `shaula-svc`.

---

## Honesty (the important part)

The composition renders **only the phrases it is handed** and has **zero marketing copy of its
own** — no stats, no claims ("proven / evidence-based / #1"), no testimonials.

Those phrases come from a practice's **already-linted tokens**: the same `tagline`,
`specialties`, and `populations` that `engine/build_practice.py` ran through the canonical
banned-language gate (`engine/banned.py` → `G.lint`) before the website could ship, and the exact
strings the website's split-flap hero cycles.

`scripts/build-props.mjs` is the bridge: it pulls those fields from a `practice.json`, joins lists
the same way the website does (`a · b · c`), then **re-runs `engine/banned.py` over every phrase**
(by shelling to Python — one source of truth, not a re-implementation). If any phrase trips the
gate it **refuses to write props and exits non-zero**. So the video can never display a phrase the
website itself wouldn't ship. **It invents nothing — honesty parity with the website.**

> **Public marketing content only. No PHI, ever.** Synthetic / operator-supplied data only.
> Rendering is fine; **publishing/posting needs the practitioner's approval** (same as the skill).

---

## Setup

Remotion is free for individuals and small practices; a company license applies to larger
for-profit orgs — that's the practitioner's call (see `skills/remotion-video/SKILL.md`).

```bash
cd remotion
npm install        # installs Remotion 4.x + a headless Chromium for rendering
```

Requirements: Node 18+ (built/verified on Node 22) and `ffmpeg` on PATH.

---

## Render the synthetic sample (North Star Counseling)

One command — (re)builds the props from the fixture (running the honesty gate) **and** renders:

```bash
npm run render:northstar
# → out/northstar.mp4   (1080×1080, h264, ~16s, duration auto-sized to the phrases)
```

Or the two steps separately:

```bash
npm run build-props          # writes props/northstar.json from fixtures/northstar-denver/practice.json
                             # (fails loudly if any phrase trips engine/banned.py)
npm run render               # renders out/headline.mp4 from props/northstar.json
```

Preview interactively in the browser:

```bash
npm run studio               # opens Remotion Studio; edit props live in the right rail
```

---

## Render for another practice

Point the props builder at that practice's `practice.json` (its fields must already be
engine-linted — the builder re-checks them):

```bash
node scripts/build-props.mjs /path/to/practice.json props/acme.json --accent "#5BE3C9"
npx remotion render SplitFlapHeadline out/acme.mp4 --codec=h264 --props=props/acme.json
```

Optional flags: `--accent "#RRGGBB"` (brand accent, default `#5BE3C9`), `--background "#RRGGBB"`
(board field, default `#07051C`).

---

## Props contract (`src/schema.ts`, zod-validated)

| field             | type        | notes                                                            |
| ----------------- | ----------- | ---------------------------------------------------------------- |
| `phrases`         | `string[]`  | 1–8 **approved, pre-linted** phrases to cycle. The only text shown. |
| `accentColor`     | hex string  | brand accent — cell underglow + footer rule.                     |
| `practiceName`    | string      | quiet footer plate (also an approved token).                     |
| `backgroundColor` | hex string? | optional board field; defaults to `#07051C`.                     |

The composition's **duration is computed from the phrases** (`calculateMetadata` in `Root.tsx`):
a 2-phrase clip and a 4-phrase clip each get exactly the runtime they need — no dead air, no
cutoff. The render is **deterministic** (a pure function of the frame number — no `Math.random`,
no timers), so the same props always produce the same frames.

---

## Layout

```
remotion/
  package.json              # Remotion 4.x + React 19 + render scripts
  remotion.config.ts        # render config (CRF, image format)
  tsconfig.json
  src/
    index.ts                # registerRoot
    Root.tsx                # <Composition> + zod schema + calculateMetadata (duration from props)
    SplitFlapHeadline.tsx   # the split-flap board (mirrors hero-scramble.js)
    schema.ts               # zod props contract + the honesty header note
  scripts/
    build-props.mjs         # honesty bridge: practice.json → props, re-linted via engine/banned.py
  props/
    northstar.json          # sample props (synthetic North Star Counseling)
  out/                      # rendered MP4s land here (gitignored)
```
