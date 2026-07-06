// Shaula Desktop — the free, house-nothing AI office, in a window.
//
// What it does: launches the proven cockpit (cockpit/server.py) wired to a LOCAL
// model (Ollama), and shows it in a window. Nothing leaves the machine — the only
// network call is to the user's own local Ollama at 127.0.0.1:11434. NO telemetry,
// NO phone-home, NO accounts required. This is the mission build: free, local, ours.
//
// First run: if Ollama (the free local AI engine) isn't installed, we show the
// onboarding page (firstrun.html) instead of failing. Once it's there, we boot.
//
// Dev vs packaged: in dev, the repo is one dir up and we use the system python3.
// Packaged, cockpit/ + engine/ ride in resources/ and a bundled python-env runs
// them (TODO: the bundling step — see the plan). Kept explicit so a maintainer can
// read the whole lifecycle in one file.
'use strict';

const { app, BrowserWindow, Menu, dialog, shell, ipcMain } = require('electron');
const { spawn } = require('child_process');
const http = require('http');
const path = require('path');
const fs = require('fs');
const { modelInstalled, pullPercent, MODELS, DEFAULT_MODEL_KEY, modelById, bundledPythonRelPath } = require('./model-util');

const COCKPIT_PORT = Number(process.env.SHAULA_COCKPIT_PORT || 8770);
const OLLAMA = process.env.SHAULA_OLLAMA_URL_BASE || 'http://127.0.0.1:11434';

// Which brain to run. Priority: env override (power users / tests) > saved choice > Fast-brain default.
// The choice persists in userData/config.json so a user's "smarter brain" upgrade survives restarts.
function configPath() { return path.join(app.getPath('userData'), 'config.json'); }
function readConfig() {
  try { return JSON.parse(fs.readFileSync(configPath(), 'utf8')); } catch { return {}; }
}
function writeConfig(patch) {
  const next = { ...readConfig(), ...patch };
  try {
    fs.mkdirSync(path.dirname(configPath()), { recursive: true });
    fs.writeFileSync(configPath(), JSON.stringify(next, null, 2));
  } catch (e) { console.error('[shaula] config write:', e.message); }
  return next;
}
function chosenModel() {
  if (process.env.SHAULA_OLLAMA_MODEL) return process.env.SHAULA_OLLAMA_MODEL;
  return readConfig().model || MODELS[DEFAULT_MODEL_KEY].id;
}

// Repo root: dev = parent of desktop/. Packaged = process.resourcesPath (cockpit/ + engine/ staged there).
const RESOURCES = app.isPackaged ? process.resourcesPath : path.resolve(__dirname, '..');

let cockpitProc = null;
let activeWindow = null;

// Resolve true if an HTTP endpoint answers within the timeout (used to detect Ollama + the cockpit).
function ping(url) {
  return new Promise((resolve) => {
    const req = http.get(url, (res) => { res.resume(); resolve(true); });
    req.on('error', () => resolve(false));
    req.setTimeout(1500, () => { req.destroy(); resolve(false); });
  });
}

function ollamaReady() { return ping(OLLAMA + '/api/version'); }

// GET a JSON endpoint; resolve the parsed object or null (down / bad JSON / timeout).
function getJSON(url) {
  return new Promise((resolve) => {
    const req = http.get(url, (res) => {
      let buf = '';
      res.on('data', (d) => (buf += d));
      res.on('end', () => { try { resolve(JSON.parse(buf)); } catch { resolve(null); } });
    });
    req.on('error', () => resolve(null));
    req.setTimeout(2500, () => { req.destroy(); resolve(null); });
  });
}

// Is the chosen model actually pulled into the local Ollama? (Ollama up != model present.)
async function modelReady() {
  return modelInstalled(await getJSON(OLLAMA + '/api/tags'), chosenModel());
}

// Pull `name` via the LOCAL Ollama (POST /api/pull, streamed). onProgress gets each chunk.
// House-nothing holds: the app only ever talks to 127.0.0.1; Ollama itself fetches the weights.
// No client timeout — pulls are GB-scale and Ollama drives the stream to completion.
function pullModel(name, onProgress) {
  return new Promise((resolve) => {
    let done = false;
    const finish = (r) => { if (!done) { done = true; resolve(r); } };
    const u = new URL(OLLAMA + '/api/pull');
    const body = JSON.stringify({ name, stream: true });
    const req = http.request({
      hostname: u.hostname, port: u.port, path: u.pathname, method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(body) },
    }, (res) => {
      let buf = '';
      res.on('data', (d) => {
        buf += d;
        let nl;
        while ((nl = buf.indexOf('\n')) >= 0) {
          const line = buf.slice(0, nl).trim();
          buf = buf.slice(nl + 1);
          if (!line) continue;
          try {
            const chunk = JSON.parse(line);
            onProgress(chunk);
            if (chunk.error) finish({ ok: false, error: String(chunk.error) });
          } catch { /* partial line — wait for more */ }
        }
      });
      res.on('end', () => finish({ ok: true }));
    });
    req.on('error', (e) => finish({ ok: false, error: e.message }));
    req.write(body);
    req.end();
  });
}

// Which python runs the cockpit. Priority: env override > bundled runtime (packaged) > system python3 (dev).
// Packaged builds ship a relocatable CPython in resources/python (see scripts/fetch-python.mjs), so the
// app needs no system Python.
function resolvePython() {
  if (process.env.SHAULA_PY) return process.env.SHAULA_PY;
  if (app.isPackaged) {
    return path.join(process.resourcesPath, ...bundledPythonRelPath(process.platform).split('/'));
  }
  return 'python3';
}

function startCockpit() {
  if (cockpitProc) return;
  const py = resolvePython();
  const model = chosenModel();
  cockpitProc = spawn(py, [path.join(RESOURCES, 'cockpit', 'server.py'), '--port', String(COCKPIT_PORT)], {
    cwd: RESOURCES,
    env: {
      ...process.env,
      // Point every model route at the LOCAL Ollama — house-nothing by construction.
      SHAULA_OLLAMA_URL: OLLAMA + '/v1',
      SHAULA_OLLAMA_MODEL: model,
      SHAULA_ROUTE_CHAT: 'ollama:' + model,
      SHAULA_ROUTE_CONTENT: 'ollama:' + model,
      SHAULA_ROUTE_HUMANIZE: 'ollama:' + model,
    },
    stdio: 'inherit',
  });
  cockpitProc.on('exit', (code) => {
    console.error('[shaula] cockpit exited with code', code);
    cockpitProc = null;
  });
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function waitForCockpit(tries = 40) {
  for (let i = 0; i < tries; i++) {
    if (await ping('http://127.0.0.1:' + COCKPIT_PORT + '/')) return true;
    await sleep(250);
  }
  return false;
}

// Stop the cockpit and wait for the port to actually free, so a restart on a new
// model can rebind :COCKPIT_PORT cleanly (used when switching brains).
async function stopCockpit() {
  if (!cockpitProc) return;
  cockpitProc.kill();
  cockpitProc = null;
  for (let i = 0; i < 40; i++) {
    if (!(await ping('http://127.0.0.1:' + COCKPIT_PORT + '/'))) return;
    await sleep(150);
  }
}

function showWindow(url) {
  if (!activeWindow || activeWindow.isDestroyed()) {
    activeWindow = new BrowserWindow({
      width: 1120, height: 780, minWidth: 720, minHeight: 560, title: 'Shaula',
      backgroundColor: '#0e0f1a',
      webPreferences: {
        contextIsolation: true,
        nodeIntegration: false,
        preload: path.join(__dirname, 'preload.js'),
      },
    });
  }
  activeWindow.loadURL(url);
  return activeWindow;
}

function onboardingURL() { return 'file://' + path.join(__dirname, 'firstrun.html'); }

// The boot decision, three states:
//   Ollama down        -> onboarding (install-engine panel)
//   Ollama up, no model -> onboarding (download-brain panel; firstrun.html reads getStatus)
//   all present        -> launch the cockpit
async function boot() {
  if (!(await ollamaReady())) { showWindow(onboardingURL()); return; }
  if (!(await modelReady())) { showWindow(onboardingURL()); return; }
  startCockpit();
  if (await waitForCockpit()) {
    showWindow('http://127.0.0.1:' + COCKPIT_PORT + '/');
  } else {
    dialog.showErrorBox('Shaula', 'The local office did not start. Is Python available on this machine?');
  }
}

// firstrun.html reads this on load to pick which panel to show (install engine vs download brain).
ipcMain.handle('shaula:status', async () => ({
  ollamaUp: await ollamaReady(),
  model: chosenModel(),
  modelPresent: await modelReady(),
}));
// "I've installed it — continue": re-run the boot decision (advances to model panel or cockpit).
ipcMain.handle('shaula:recheck', async () => { boot(); return { ok: true }; });
// "Download the brain": pull the chosen model with live progress; on success, boot() loads the cockpit.
ipcMain.handle('shaula:pull-model', async (e) => {
  const r = await pullModel(chosenModel(), (chunk) => {
    if (!e.sender.isDestroyed()) {
      e.sender.send('shaula:pull-progress', {
        status: chunk.status, percent: pullPercent(chunk),
        completed: chunk.completed, total: chunk.total, error: chunk.error || null,
      });
    }
  });
  if (r.ok) boot();
  return r;
});
ipcMain.handle('shaula:open-external', (_e, url) => {
  if (/^https:\/\/(ollama\.com|github\.com\/ollama)/.test(url)) shell.openExternal(url);
});

// --- Brain switching (Fast brain <-> Smarter brain) ---

// Persist the chosen brain, stop the old cockpit, and re-boot. boot() downloads the model
// first (via the firstrun download panel) if it isn't pulled yet, then starts the cockpit on it.
async function switchModel(key) {
  const m = MODELS[key];
  if (!m) return;
  if (process.env.SHAULA_OLLAMA_MODEL) {
    dialog.showMessageBox({ message: 'A model is pinned via SHAULA_OLLAMA_MODEL — unset it to switch brains from the menu.' });
    return;
  }
  if (chosenModel() === m.id && cockpitProc) { buildMenu(); return; } // already on it
  writeConfig({ model: m.id });
  buildMenu();
  await stopCockpit();
  boot();
}

// Confirm the big download, then switch. The download itself runs in the firstrun panel (progress bar).
function getSmarterBrain() {
  const m = MODELS.smart;
  const choice = dialog.showMessageBoxSync({
    type: 'question', buttons: ['Download', 'Cancel'], defaultId: 0, cancelId: 1,
    message: 'Get the smarter brain (Gemma 4)?',
    detail: `One-time ~${m.approxGB} GB download; needs a fairly powerful Mac. It stays on your machine — nothing leaves your computer. You can switch back to the Fast brain any time.`,
  });
  if (choice === 0) switchModel('smart');
}

function buildMenu() {
  const cur = chosenModel();
  const template = [
    ...(process.platform === 'darwin'
      ? [{ label: app.name, submenu: [{ role: 'about' }, { type: 'separator' }, { role: 'hide' }, { role: 'quit' }] }]
      : []),
    { label: 'Brain', submenu: [
      { label: `Fast brain — ${MODELS.light.id} (runs anywhere)`, type: 'checkbox', checked: cur === MODELS.light.id, click: () => switchModel('light') },
      { label: `Smarter brain — Gemma 4 (~${MODELS.smart.approxGB} GB)`, type: 'checkbox', checked: cur === MODELS.smart.id, click: () => getSmarterBrain() },
      { type: 'separator' },
      { label: `Current: ${(modelById(cur) && modelById(cur).label) || cur}`, enabled: false },
    ] },
    { role: 'editMenu' },
    { role: 'viewMenu' },
    { role: 'windowMenu' },
  ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// Auto-update via electron-updater + GitHub Releases (publish config in package.json).
// No-ops in dev/unsigned; activates once the app is signed + a release is published.
function initAutoUpdate() {
  if (!app.isPackaged) return;
  try {
    const { autoUpdater } = require('electron-updater');
    autoUpdater.checkForUpdatesAndNotify().catch((e) => console.error('[shaula] update check:', e.message));
  } catch (_) { /* electron-updater absent — skip */ }
}

app.whenReady().then(() => { buildMenu(); boot(); initAutoUpdate(); });
app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) boot(); });
app.on('window-all-closed', () => { app.quit(); });
app.on('before-quit', () => { if (cockpitProc) { cockpitProc.kill(); cockpitProc = null; } });
