# svc — the hosted office runtime (optional)

A FastAPI runtime that serves the 8 no-PHI office staff to practice-facing
apps. Self-hosters don't need it: the harness (`bin/shaula*`) and the workflow
board run entirely locally — see `docs/GETTING_STARTED.md`. The svc exists for
operators who want to host the office for many practices; every knob is an
environment variable (see `svc/config.py`).
