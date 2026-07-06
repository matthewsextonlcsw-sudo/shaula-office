/* Headless RENDER DUMP for a filled SPA — the provenance gate's companion.

   render_check.mjs ASSERTS the rendered SPA is structurally sound; this script
   DUMPS the same rendered HTML so a downstream gate (engine/provenance.py) can
   prove every visible claim traces to approved content. They share one execution
   model on purpose: app.js renders all content client-side via route template
   functions + a `posts` array, so the only honest way to see the claims the
   site actually shows is to EXECUTE app.js, invoke every route, and collect the
   produced HTML — exactly what the provenance gate must scan (the static
   index.html shell carries only the title/nav/footer, never the body claims).

   This file deliberately MIRRORS render_check.mjs's DOM/host shim rather than
   importing a shared module: render_check.mjs is the proven CI gate and is left
   untouched. The shim is small, pure Node (no packages), and identical by
   construction; the two cannot drift in any way that matters because both only
   need enough of a DOM to let app.js's pure render functions run.

   Pure Node, no packages. Reads ONLY <out>/app.js — no practice.json needed
   (we dump what the site renders; the gate supplies the approved corpus).

   USAGE
     node render_dump.mjs --out <built-site-dir>
   Prints the concatenated rendered HTML (all routes) to stdout; exits non-zero
   if app.js cannot be executed or a route throws.
*/

import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';

// --- argv ------------------------------------------------------------------
function argOf(flag, fallback) {
  const i = process.argv.indexOf(flag);
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback;
}
const HERE = import.meta.dirname;
const OUT = path.resolve(argOf('--out', path.join(HERE, '..', 'sites', 'cedar-sage')));

let appSrc;
try {
  appSrc = readFileSync(path.join(OUT, 'app.js'), 'utf8');
} catch (e) {
  console.error(`render_dump: cannot read ${path.join(OUT, 'app.js')}: ${e.message}`);
  process.exit(2);
}

// --- minimal DOM/host shim (mirrors render_check.mjs) -----------------------
function makeEl(id = '') {
  return {
    id, hidden: false, innerHTML: '', className: '', dataset: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } },
    style: {},
    addEventListener() {}, removeEventListener() {},
    querySelectorAll() { return []; }, querySelector() { return null; },
    appendChild() {}, removeChild() {}, replaceWith() {}, remove() {},
    setAttribute() {}, getAttribute() { return null; }, closest() { return null; },
    parentElement: null,
  };
}
const routeEls = {};
const ids = ['home', 'about', 'approach', 'method', 'journey', 'who', 'fees', 'writing', 'contact', 'privacy'];
ids.forEach(id => { routeEls['route-' + id] = makeEl('route-' + id); });

const documentShim = {
  getElementById: id => routeEls[id] || null,
  querySelectorAll: () => [],
  querySelector: () => null,
  createElement: () => makeEl(),
  addEventListener() {},
  body: makeEl(),
};
const windowShim = {
  scrollTo() {}, IntersectionObserver: undefined,
  addEventListener() {}, setTimeout: (fn) => { try { fn(); } catch (_) {} return 0; },
};
const context = {
  document: documentShim,
  window: windowShim,
  location: { hash: '', href: '' },
  history: { replaceState() {} },
  setTimeout: (fn) => { try { fn(); } catch (_) {} return 0; },
  clearTimeout() {}, fetch: async () => { throw new Error('no fetch in shim'); },
  URL: { createObjectURL: () => 'blob:stub' },
  console: { log() {}, warn() {}, error() {}, info() {} }, // mute app.js chatter on stdout
};
context.globalThis = context;
context.self = context;

vm.createContext(context);
try {
  vm.runInContext(appSrc, context, { filename: 'app.js' });
} catch (e) {
  console.error(`render_dump: app.js failed to execute: ${e.message}`);
  process.exit(1);
}

// app.js defines `routes` (route -> render fn) and `posts` as top-level
// const/let — pull them out the same way render_check.mjs does.
let routes;
try {
  routes = vm.runInContext('routes', context);
} catch (e) {
  console.error(`render_dump: app.js exposed no \`routes\` map: ${e.message}`);
  process.exit(1);
}
if (!routes || typeof routes !== 'object') {
  console.error('render_dump: `routes` is not a render map');
  process.exit(1);
}

// Invoke every route and concatenate the produced HTML. A route comment marks
// each section so an offender's location stays legible in the gate output.
const parts = [];
let failed = null;
for (const name of Object.keys(routes)) {
  try {
    parts.push(`\n<!-- route: ${name} -->\n`);
    parts.push(String(routes[name]()));
  } catch (e) {
    failed = `route ${name} threw: ${e.message}`;
    break;
  }
}
if (failed) {
  console.error(`render_dump: ${failed}`);
  process.exit(1);
}

// Wrap in a minimal document so the gate's HTML parser sees well-formed input.
process.stdout.write(`<!doctype html>\n<html><body>\n${parts.join('')}\n</body></html>\n`);
