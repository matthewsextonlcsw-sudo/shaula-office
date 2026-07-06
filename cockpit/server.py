#!/usr/bin/env python3
"""server — Shaula cockpit. A branded control panel over the harness: chat with the agent, place
slash-commands, build sites. Pure-stdlib ThreadingHTTPServer (v1 ethos, zero new deps). The model
work goes through router.py (the "what LLM for what" decision); the deterministic site build goes
through the ported honesty engine.

Run:  python3 cockpit/server.py            # http://127.0.0.1:8770
NO PHI — synthetic/marketing text only.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / "engine"))
import router  # noqa: E402
import svc_client  # noqa: E402  — server-side bridge to shaula-svc authoring
import local_runner  # noqa: E402 — the built-in office (no svc needed)

# With no hosted svc wired (the desktop app, any offline box), the office runs
# HERE: same routes, same shapes, local execution + the same honesty gate.
LOCAL_OFFICE = not svc_client.configured()

PORT = 8770

SHAULA_SYSTEM = (
    "You are Shaula — the AI partner that runs a therapist's whole back office: admin, website, "
    "blog, marketing, content, and research. You are capable, proactive, and genuinely helpful — "
    "you draft, research, write, organize, and get things done. Honesty is HOW you work, never a "
    "reason to refuse: you may absolutely write clinical and educational content and cite sources. "
    "The one rule is accuracy — cite only REAL sources you actually have, and never fabricate "
    "statistics, citations, testimonials, credentials, or outcomes. When you lack a verified source "
    "or aren't sure, say so plainly and offer to look it up — do NOT refuse the task. You run inside "
    "the therapist's own Google Workspace. Be warm, specific, and useful. Handy commands: /build a "
    "site, /humanize <text>, /staff."
)


def _build_demo_site() -> dict:
    """Run the deterministic honesty engine on the demo survey; return where it landed."""
    import build_practice as BP
    import pipeline as P
    # Writable outside the app bundle (packaged builds are read-only mounts).
    res = P.build_site(BP.DEMO_SURVEY, sites_dir=str(local_runner._sites_dir()))
    return {"slug": res["slug"], "dir": str(res["dir"]), "business": res.get("business_name")}


def _create_task(capability: str, topic: str, *, idempotency_key: str = "") -> dict:
    """Queue a task (run) on the svc → it lands on the live board. website-launch
    needs a practice profile, so on the demo box we idempotently seed the
    deterministic demo intake first; if that fails, create_run returns the honest 409."""
    if LOCAL_OFFICE:
        return local_runner.create_run(capability, topic, idempotency_key=idempotency_key)
    if capability == "website-launch":
        try:
            import build_practice as BP
            svc_client.upsert_intake(BP.DEMO_SURVEY)
        except Exception:
            pass
    return svc_client.create_run(capability, topic, idempotency_key=idempotency_key)


def _render_clip(slug: str = "demo") -> dict:
    """Render a split-flap social-clip MP4 for the demo practice via the merged
    Remotion project. Phrases come ONLY through remotion/scripts/build-props.mjs,
    which re-lints each phrase through engine/banned.py — so the video can never
    show a phrase the website itself would refuse. Local render: no svc, no cloud
    cost (matches the house-nothing ethos). Synthetic/marketing only — NO PHI."""
    import shutil
    import subprocess
    import tempfile
    import build_practice as BP

    remotion = REPO / "remotion"
    if not (remotion / "node_modules").is_dir():
        return {"ok": False, "error": "Remotion deps not installed — run: npm --prefix remotion install"}
    node = shutil.which("node")
    npx = shutil.which("npx")
    if not node or not npx:
        return {"ok": False, "error": "node/npx not found on PATH"}
    if not re.match(r"^[a-z0-9_-]{1,40}$", slug):
        slug = "demo"

    practice = BP.build_practice(BP.DEMO_SURVEY)
    (remotion / "props").mkdir(exist_ok=True)
    (remotion / "out").mkdir(exist_ok=True)
    props_path = remotion / "props" / f"{slug}.json"
    out_rel = f"out/{slug}.mp4"
    out_path = remotion / out_rel
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
        json.dump(practice, tf)
        practice_path = tf.name
    try:
        # 1) honesty bridge → props (exits non-zero + writes nothing on a banned phrase)
        bp = subprocess.run(
            [node, str(remotion / "scripts" / "build-props.mjs"), practice_path, str(props_path)],
            capture_output=True, text=True, timeout=120,
        )
        if bp.returncode != 0:
            return {"ok": False, "error": "honesty gate refused: " + (bp.stderr or bp.stdout).strip()[-400:]}
        # 2) deterministic Remotion render → mp4
        r = subprocess.run(
            [npx, "remotion", "render", "SplitFlapHeadline", out_rel, "--codec=h264",
             f"--props=props/{slug}.json"],
            cwd=str(remotion), capture_output=True, text=True, timeout=600,
        )
    finally:
        try:
            pathlib.Path(practice_path).unlink()
        except OSError:
            pass
    if r.returncode != 0 or not out_path.exists():
        return {"ok": False, "error": "render failed: " + (r.stderr or r.stdout).strip()[-400:]}
    return {"ok": True, "file": f"{slug}.mp4", "bytes": out_path.stat().st_size,
            "download": f"/api/clip/{slug}.mp4", "business": practice.get("business_name", "")}


def _command(cmd: str) -> dict:
    c = cmd.strip()
    low = c.lower()
    if low in ("/help", "help"):
        return {"output": "Commands:\n  /build — build the demo practice site (honesty-verified)\n"
                          "  /clip — render a split-flap social-clip MP4 (honesty-gated)\n"
                          "  /humanize <text> — strip AI-writing patterns\n  /staff — show the roster\n"
                          "  anything else — chat with the agent"}
    if low.startswith("/build"):
        try:
            s = _build_demo_site()
            return {"output": f"Built {s['business']} → {s['dir']} (0-leak, honesty-verified)."}
        except Exception as e:
            return {"output": f"build failed: {type(e).__name__}: {e}"}
    if low.startswith("/clip") or low.startswith("/video"):
        res = _render_clip()
        if res.get("ok"):
            return {"output": f"Rendered social clip for {res['business']} "
                              f"({res['bytes'] // 1024} KB, honesty-gated) → download {res['download']}"}
        return {"output": f"clip failed: {res.get('error')}"}
    if low.startswith("/humanize"):
        text = c[len("/humanize"):].strip()
        if not text:
            return {"output": "usage: /humanize <text>"}
        r = router.humanize(text)
        return {"output": r["text"], "model": r.get("model"), "backend": r.get("backend")}
    if low in ("/staff", "staff"):
        return {"output": "Staff: ✅ website-builder · ✅ blog-scaffolder · 🗓️ front-desk · "
                          "🗓️ customer-service · 🗓️ marketer · 🗓️ analytics · 🗓️ workspace-backend"}
    # not a known command → treat as chat
    r = router.route("chat", c)
    return {"output": r["text"], "model": r.get("model"), "backend": r.get("backend")}


def _providers_state() -> dict:
    """The provider registry + each provider's consent/attestation state for the UI.
    NEVER includes a key — only a has_key boolean, so this is log-safe."""
    out = []
    for p in router.providers.all():
        rec = router._BYO.get(p.id)
        out.append({
            "id": p.id, "label": p.label, "phi_ok": p.phi_ok,
            "needs_attestation": p.needs_attestation, "needs_key": p.needs_key,
            "billed_by": p.billed_by, "rate": p.rate, "note": p.note,
            "consent": rec["consent"], "baa_attested": rec["baa_attested"],
            "has_key": router._BYO.key(p.id) is not None,
        })
    return {"providers": out,
            "planes": {"marketing": router.providers.PLANE_MARKETING,
                       "phi": router.providers.PLANE_PHI}}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj: dict):
        self._send(code, json.dumps(obj).encode(), "application/json")

    def _read(self) -> dict:
        n = int(self.headers.get("Content-Length", 0) or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, (HERE / "index.html").read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/shaula-logo.png":
            p = HERE / "shaula-logo.png"
            if p.exists():
                self._send(200, p.read_bytes(), "image/png")
            else:
                self._json(404, {"error": "no logo"})
        elif self.path == "/api/health":
            self._json(200, {"ok": True, "routes": router._ROUTES})
        elif self.path == "/api/providers":
            # The BYO-model picker reads this: who's available, who's BAA-covered,
            # and each provider's current consent/attestation state. No keys, ever.
            self._json(200, _providers_state())
        elif self.path == "/api/authoring/config":
            # The surface hides the authoring panel unless a svc is wired —
            # never offer a button that can only fail.
            self._json(200, {"configured": svc_client.configured(),
                             "practice": svc_client._pid()})
        elif self.path == "/api/roster":
            # The staff roster, driven straight from the manifest so it never
            # drifts — every workflow the office can run is reachable from here.
            self._json(200, local_runner.roster() if LOCAL_OFFICE else svc_client.roster())
        elif self.path == "/api/stats":
            # The Analyst surface — real counts only (no estimates).
            if LOCAL_OFFICE:
                runs = local_runner.list_runs()["runs"]
                self._json(200, {"ok": True, "local": True, "counts": {
                    "runsFinished": sum(1 for r in runs if r["status"] == "approved"),
                    "essaysLive": 0, "inquiries": 0}})
            else:
                self._json(200, svc_client.stats())
        elif self.path == "/api/inquiries":
            # The Office Manager surface — consult inquiries from the live site.
            self._json(200, {"ok": True, "inquiries": [], "local": True}
                       if LOCAL_OFFICE else svc_client.inquiries())
        elif self.path == "/api/runs":
            # The live task board polls this — runs queued/working/awaiting-approval,
            # newest first, each with progress (stepsDone/total, current step).
            self._json(200, local_runner.list_runs() if LOCAL_OFFICE else svc_client.list_runs())
        elif self.path.startswith("/api/run/"):
            # One full run — every step's OUTPUT (the deliverable). "where are the outputs"
            rid = self.path[len("/api/run/"):].split("?")[0]
            self._json(200, local_runner.get_run(rid) if LOCAL_OFFICE else svc_client.get_run(rid))
        elif self.path.startswith("/sites/"):
            # The generated site preview. Local office: serve straight from the
            # writable sites dir (path-confined). Hosted: proxy the svc.
            if LOCAL_OFFICE:
                base = local_runner._sites_dir().resolve()
                rel = self.path[len("/sites/"):].split("?")[0]
                target = (base / rel).resolve()
                if base not in target.parents and target != base:
                    return self._json(400, {"error": "bad path"})
                if target.is_dir():
                    target = target / "index.html"
                if target.is_file():
                    ctype = ("text/html; charset=utf-8" if target.suffix in (".html", ".htm")
                             else "text/css" if target.suffix == ".css"
                             else "application/javascript" if target.suffix == ".js"
                             else "application/octet-stream")
                    return self._send(200, target.read_bytes(), ctype)
                return self._json(404, {"error": "no such site file"})
            import urllib.request as _u
            try:
                with _u.urlopen(svc_client._svc_url() + self.path, timeout=10) as r:
                    body, ctype = r.read(), r.headers.get("Content-Type", "text/html; charset=utf-8")
                self._send(200, body, ctype)
            except Exception:
                self._json(502, {"error": "preview unavailable"})
        elif self.path.startswith("/api/clip/"):
            # Download a rendered social-clip MP4 from remotion/out/ (name-sanitized).
            name = self.path[len("/api/clip/"):].split("?")[0]
            if not re.match(r"^[a-z0-9_-]+\.mp4$", name):
                return self._json(400, {"error": "bad clip name"})
            f = REPO / "remotion" / "out" / name
            if f.is_file():
                body = f.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Disposition", f'attachment; filename="{name}"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                self._json(404, {"error": "no such clip"})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        try:
            data = self._read()
        except Exception:
            return self._json(400, {"error": "bad json"})
        if self.path == "/api/byo":
            # Set a provider's billing-consent / BAA attestation (+ optional BYO key).
            # The key goes only to the 0600 store; the response carries no key.
            provider = (data.get("provider") or "").strip()
            if not router.providers.get(provider):
                return self._json(400, {"error": "unknown provider"})
            router._BYO.set(
                provider,
                consent=bool(data.get("consent")),
                baa_attested=bool(data.get("baa_attested")),
                key=(data.get("key") or None),
            )
            return self._json(200, {"ok": True, "state": _providers_state()})
        if self.path == "/api/chat":
            msg = (data.get("message") or "").strip()
            if not msg:
                return self._json(400, {"error": "empty message"})
            # Optional BYO/registered brain, gated by the two-plane rule in router.
            provider = (data.get("provider") or "").strip() or None
            plane = data.get("plane") or router.providers.PLANE_MARKETING
            r = router.route("chat", msg, system=SHAULA_SYSTEM, provider=provider, plane=plane)
            if data.get("humanize"):
                h = router.humanize(r["text"])
                r = {"text": h["text"], "backend": h["backend"], "model": h["model"], "humanized": True}
            self._json(200, {"reply": r["text"], "backend": r["backend"], "model": r["model"],
                             "humanized": bool(data.get("humanize"))})
        elif self.path == "/api/command":
            self._json(200, _command(data.get("command", "")))
        elif self.path == "/api/authoring/draft":
            # Plain-language request -> vetted, honesty-gated workflow PREVIEW
            # (the svc validates every byte; the secret stays on this server).
            self._json(200, svc_client.draft(
                data.get("description", ""), with_skill=bool(data.get("withSkill")),
            ))
        elif self.path == "/api/authoring/create":
            # Therapist-approved template -> the svc's honesty-gated runner.
            self._json(200, svc_client.create(
                data.get("template", {}) or {},
                idempotency_key=str(data.get("idempotencyKey", "")),
            ))
        elif self.path == "/api/runs":
            # Run a staff task — it lands on the live board and stays there.
            self._json(200, _create_task(
                str(data.get("capability", "")), str(data.get("topic", "")),
                idempotency_key=str(data.get("idempotencyKey", "")),
            ))
        elif self.path == "/api/runs/approve":
            fn = local_runner.approve_run if LOCAL_OFFICE else svc_client.approve_run
            self._json(200, fn(str(data.get("runId", "")), note=str(data.get("note", ""))))
        elif self.path == "/api/runs/reject":
            fn = local_runner.reject_run if LOCAL_OFFICE else svc_client.reject_run
            self._json(200, fn(str(data.get("runId", "")), note=str(data.get("note", ""))))
        else:
            self._json(404, {"error": "not found"})


def main():
    port = PORT
    if "--port" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1])
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print(f"Shaula cockpit → http://127.0.0.1:{port}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
