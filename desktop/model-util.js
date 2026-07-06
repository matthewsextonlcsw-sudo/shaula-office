// Pure model helpers — NO electron / network deps so they're unit-testable in plain node.
// Used by main.js (the boot decision) and exercised by model-util.test.js.
'use strict';

// Does the Ollama /api/tags payload contain the wanted model?
// Exact tag match; if `wanted` has no ':tag', also accept ':latest' (Ollama's default tag).
function modelInstalled(tags, wanted) {
  if (!wanted) return false;
  const list = tags && Array.isArray(tags.models) ? tags.models : [];
  const names = list.map((m) => (m && (m.name || m.model)) || '').filter(Boolean);
  if (names.includes(wanted)) return true;
  if (!wanted.includes(':')) return names.includes(wanted + ':latest');
  return false;
}

// Whole-number percent from an Ollama pull-stream chunk ({total, completed}); null when not yet measurable.
function pullPercent(chunk) {
  if (!chunk || typeof chunk.total !== 'number' || typeof chunk.completed !== 'number' || chunk.total <= 0) {
    return null;
  }
  const p = Math.round((chunk.completed / chunk.total) * 100);
  return Math.max(0, Math.min(100, p));
}

// The two shipped brains. Default is the Fast brain so the app opens with no download wall;
// the Smarter brain is an opt-in upgrade (big download, needs a stronger Mac). approxGB are the
// real Ollama pull sizes (verified from the registry manifest), used in the menu/dialog copy.
const MODELS = {
  light: { key: 'light', id: 'gemma3:1b',  label: 'Fast brain',               approxGB: 0.8 },
  smart: { key: 'smart', id: 'gemma4:e4b', label: 'Smarter brain — Gemma 4',  approxGB: 9.6 },
};
const DEFAULT_MODEL_KEY = 'light';

// Map a model id back to its catalog entry (or null if it's neither shipped brain).
function modelById(id) { return Object.values(MODELS).find((m) => m.id === id) || null; }

// Relative path (under resourcesPath) to the bundled CPython for a given OS platform.
// python-build-standalone install_only layout: `python/bin/python3` (mac/linux), `python/python.exe` (win).
function bundledPythonRelPath(platform) {
  return platform === 'win32' ? 'python/python.exe' : 'python/bin/python3';
}

module.exports = { modelInstalled, pullPercent, MODELS, DEFAULT_MODEL_KEY, modelById, bundledPythonRelPath };
