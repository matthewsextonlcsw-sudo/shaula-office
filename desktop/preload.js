// Preload — the ONLY bridge between the renderer (firstrun.html / the cockpit) and the
// main process. Context-isolated, minimal surface: read boot status, re-check, pull the
// local model (with progress), and open the two allowed external links. Nothing else is
// exposed — house-nothing extends to the IPC surface.
'use strict';

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('shaula', {
  // { ollamaUp, model, modelPresent } — firstrun.html uses this to pick its panel.
  getStatus: () => ipcRenderer.invoke('shaula:status'),
  // Re-run the boot decision (after the user installs/starts Ollama).
  recheck: () => ipcRenderer.invoke('shaula:recheck'),
  // Pull the configured model into local Ollama; resolves { ok, error? }.
  pullModel: () => ipcRenderer.invoke('shaula:pull-model'),
  // Subscribe to pull progress; returns an unsubscribe fn.
  onPullProgress: (cb) => {
    const fn = (_e, data) => cb(data);
    ipcRenderer.on('shaula:pull-progress', fn);
    return () => ipcRenderer.removeListener('shaula:pull-progress', fn);
  },
  openExternal: (url) => ipcRenderer.invoke('shaula:open-external', url),
});
