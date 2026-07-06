#!/usr/bin/env node
// ─────────────────────────────────────────────────────────────────────────
// build-props.mjs — derive a video props JSON from a practice's practice.json,
// using the SAME approved tokens the website's split-flap hero cycles, and
// re-verify each phrase through Shaula's canonical banned-language gate before
// it is allowed into the props file.
//
// HONESTY BRIDGE (the whole point):
//   • Phrases come ONLY from practice.json fields that the engine already
//     produced and linted: tagline, specialties, populations — joined exactly
//     like templates/private-practice/hero-scramble.js (`a · b · c`).
//   • Each phrase is then re-linted by shelling out to engine/banned.py
//     (`python3 -c "import banned; print(banned.lint(text))"`) — the ONE source
//     of truth shared by generate.py / geo.py / svc/honesty.py. We do not
//     re-implement the rules here; we call them. If ANY phrase trips the gate,
//     this script refuses to write props and exits non-zero.
//
//   ⇒ The video therefore cannot display a phrase the website itself wouldn't
//     ship. It invents nothing.
//
// Usage:
//   node scripts/build-props.mjs [path/to/practice.json] [path/to/out.json]
//   (defaults: ../fixtures/northstar-denver/practice.json  →  props/northstar.json)
//
// Synthetic / public marketing data only. NO PHI.
// ─────────────────────────────────────────────────────────────────────────
import { readFileSync, writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, resolve, join } from "node:path";
import { fileURLToPath } from "node:url";
import { execFileSync } from "node:child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));
const PROJ = resolve(__dirname, ".."); // remotion/
const REPO = resolve(PROJ, ".."); // shaula repo root
const ENGINE = join(REPO, "engine"); // where banned.py lives

const inPath = resolve(
  process.argv[2] ?? join(REPO, "fixtures", "northstar-denver", "practice.json")
);
const outPath = resolve(process.argv[3] ?? join(PROJ, "props", "northstar.json"));

// Default brand accent for the synthetic northstar sample (cosmic cyan, matching
// the 7.0 prism palette). Override per practice via a `--accent #RRGGBB` flag.
let accent = "#5BE3C9";
let background = "#07051C";
for (let i = 4; i < process.argv.length - 1; i++) {
  if (process.argv[i] === "--accent") accent = process.argv[i + 1];
  if (process.argv[i] === "--background") background = process.argv[i + 1];
}

// ── format a comma list the same way hero-scramble.js does ──────────────────
const fmtList = (s) =>
  String(s ?? "")
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean)
    .join(" · ");

// ── the canonical honesty gate: call engine/banned.py (single source of truth) ─
function lintViaEngine(text) {
  // Returns the list of banned patterns AFFIRMATIVELY present (empty == clean).
  const code =
    "import sys, json, banned; " +
    "print(json.dumps(banned.lint(sys.argv[1])))";
  const out = execFileSync("python3", ["-c", code, text], {
    cwd: ENGINE,
    encoding: "utf8",
  });
  return JSON.parse(out.trim());
}

// Fail fast if the engine gate isn't reachable — we will NOT silently skip it.
if (!existsSync(join(ENGINE, "banned.py"))) {
  console.error(
    `✗ canonical honesty gate not found at ${join(ENGINE, "banned.py")} — refusing to emit props without it.`
  );
  process.exit(2);
}

const practice = JSON.parse(readFileSync(inPath, "utf8"));

// Same pool, same order as the website hero: tagline → specialties → populations.
const candidates = [
  String(practice.tagline ?? "").trim(),
  fmtList(practice.specialties),
  fmtList(practice.populations),
].filter(Boolean);

// De-dup (case-insensitive), preserve order — mirrors hero-scramble.js.
const seen = new Set();
const phrases = [];
for (const p of candidates) {
  const k = p.toLowerCase();
  if (!seen.has(k)) {
    seen.add(k);
    phrases.push(p);
  }
}

if (phrases.length < 1) {
  console.error(`✗ no approved phrases found in ${inPath} (need tagline/specialties/populations).`);
  process.exit(1);
}

// Re-lint every phrase through the engine gate. Any hit ⇒ refuse.
let dirty = false;
for (const p of phrases) {
  const hits = lintViaEngine(p);
  if (hits.length) {
    dirty = true;
    console.error(`✗ banned-language gate tripped on phrase: ${JSON.stringify(p)}`);
    console.error(`   patterns: ${hits.join(", ")}`);
  }
}
if (dirty) {
  console.error("Refusing to write props — fix the source practice.json (this is honesty parity with the website).");
  process.exit(1);
}

const practiceName = String(
  practice.business_name ?? practice.owner_name ?? "Private Practice"
).trim();

const props = {
  _comment:
    "Synthetic, engine-linted approved phrases ONLY (tagline/specialties/populations from practice.json), re-verified through engine/banned.py. No PHI. The video renders exactly these phrases and invents nothing.",
  phrases,
  accentColor: accent,
  backgroundColor: background,
  practiceName,
};

mkdirSync(dirname(outPath), { recursive: true });
writeFileSync(outPath, JSON.stringify(props, null, 2) + "\n");

console.log(`✓ honesty gate passed (engine/banned.py) for all ${phrases.length} phrase(s).`);
console.log(`✓ wrote ${outPath}`);
for (const p of phrases) console.log(`   • ${p}`);
