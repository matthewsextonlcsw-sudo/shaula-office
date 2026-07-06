# Shaula Desktop — the free, house-nothing AI office

Shaula's marketing/back-office office, as a downloadable desktop app. Runs **entirely on the
user's machine** against a local model (Ollama). No account, no cloud, no fees, **no telemetry** —
the mission build. Free because it's built on the free Nous Hermes harness, and the revenue lives
in the paid clinical products, not here.

## Run (dev)
```
cd desktop && npm install
npm start                                   # defaults to the Fast brain (gemma3:1b)
npm test                                    # unit tests (node:test, zero deps)
```
`main.js` runs a three-state boot: **Ollama missing** → onboarding install panel; **Ollama up but
the chosen model not pulled** → onboarding download panel (live progress, pulls via local Ollama);
**all present** → spawns the cockpit (`../cockpit/server.py`) on the model and opens the window. The
**only** network call is to `127.0.0.1:11434` (the user's own Ollama).

## Brains (model choice)
Two shipped brains, picked from the in-app **Brain** menu (choice persists in `userData/config.json`):
- **Fast brain** — `gemma3:1b` (~0.8 GB). The default: opens with no download wall, runs on modest machines.
- **Smarter brain** — `gemma4:e4b` (Gemma 4, ~9.6 GB). Opt-in upgrade; far better output, needs a stronger Mac.
  Selecting it downloads the model (progress bar) then restarts the cockpit on it.

Override for power users / tests: set `SHAULA_OLLAMA_MODEL=<tag>` to pin a model (this wins over the menu choice).

## Build an installer
```
npm run dist            # current platform (unsigned)
npm run dist:mac        # DMG + zip   (distribution needs Apple signing — see Gates)
npm run dist:win        # NSIS
npm run dist:linux      # AppImage + deb
```

## Architecture
- **Electron shell** (`main.js` + `preload.js`) — process lifecycle, Ollama detection, window.
- **The cockpit** (`../cockpit`, pure-stdlib Python) — the UI + the office, wired to local Ollama.
- **The engine** (`../engine`) — the honesty gate; staged into `resources/` when packaged.
- **Auto-update** — `electron-updater` via GitHub Releases (`package.json` `build.publish`).
  No-ops in dev/unsigned; activates once signed + published.

## Remaining gates (Matthew / identity-bound — cannot be automated)
- **Apple Developer ($99/yr)** — sign + notarize for macOS (Gatekeeper + auto-update need it).
- **Windows code-signing cert** — for the NSIS installer.
- **GitHub Releases** — publish the signed artifacts + the update manifest.
- **Bundle a standalone Python** (e.g. `python-build-standalone`) so the packaged app needs no
  system Python; point `SHAULA_PY` at it. Dev uses system `python3`; the cockpit + engine are
  stdlib-only, so the runtime is all that's needed.

## House-nothing
`scripts/verify-harden.sh` gates the harness config. The desktop layer adds nothing that
egresses — no telemetry, no analytics. The only outbound calls are the user's own local Ollama
and (optional, their choice) their own Google Vertex. That's the whole point.
