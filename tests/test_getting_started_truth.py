"""test_getting_started_truth — the onboarding docs may not drift from reality.

docs/GETTING_STARTED.md and bin/shaula-setup are the front door: the first
commands a stranger runs. A guide that cites a file that moved, a port that
changed, or a capability count that's stale is worse than no guide — it burns
the one shot at trust. These tests pin every load-bearing claim in the guide
to the artifact it describes, the same way test_banned.py pins the linter and
ManifestIntegrity pins the capability surface.

Stdlib only, zero network, safe for the prove.sh gate.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_GUIDE = os.path.join(_ROOT, "docs", "GETTING_STARTED.md")
_SETUP = os.path.join(_ROOT, "bin", "shaula-setup")


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


class GuideExists(unittest.TestCase):
    def test_guide_and_walkthrough_exist(self):
        self.assertTrue(os.path.isfile(_GUIDE), "docs/GETTING_STARTED.md missing")
        self.assertTrue(os.path.isfile(_SETUP), "bin/shaula-setup missing")
        self.assertTrue(os.access(_SETUP, os.X_OK), "bin/shaula-setup not executable")

    def test_walkthrough_parses(self):
        # bash -n: syntax-checks without executing anything.
        proc = subprocess.run(["bash", "-n", _SETUP], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, f"bash -n failed: {proc.stderr}")

    def test_readme_points_at_the_guide(self):
        self.assertIn("GETTING_STARTED", _read(os.path.join(_ROOT, "README.md")),
                      "README must link the getting-started guide")


class GuideCitesRealFiles(unittest.TestCase):
    """Every repo path the guide names must exist. Parse conservatively:
    backticked tokens that look like repo-relative paths."""

    _PATH_RE = re.compile(r"`((?:bin|docs|config|scripts|workflows|vendor)/[^`*]+?)`")

    def test_cited_paths_exist(self):
        guide = _read(_GUIDE)
        cited = set(self._PATH_RE.findall(guide))
        self.assertTrue(cited, "guide cites no repo paths — parser broken?")
        for p in cited:
            p = p.strip().rstrip("/")
            if "*" in p or "$" in p or "<" in p:
                continue  # globs / variables are illustrative, not paths
            if ".venv-shaula" in p:
                continue  # created BY the walkthrough — absent in a fresh clone by design
            self.assertTrue(os.path.exists(os.path.join(_ROOT, p)),
                            f"guide cites {p!r} which does not exist")

    def test_setup_cites_real_files(self):
        setup = _read(_SETUP)
        for rel in ("config/constraints-shaula.txt", "config/shaula-harden.yaml",
                    "scripts/install_profiles.py", "scripts/install_skills.sh",
                    "scripts/install-hub-skills.sh", "scripts/verify-harden.sh"):
            self.assertIn(rel.split("/")[-1], setup, f"setup no longer references {rel}")
            self.assertTrue(os.path.isfile(os.path.join(_ROOT, rel)), f"{rel} missing")


class GuideNumbersMatchReality(unittest.TestCase):
    def test_capability_count_matches_manifest(self):
        manifest = json.loads(_read(os.path.join(_ROOT, "workflows", "CAPABILITY_MANIFEST.json")))
        n = len(manifest["capabilities"])
        guide = _read(_GUIDE)
        self.assertIn(f"{n} ", guide.replace("**", ""),
                      f"guide's capability count is stale (manifest has {n})")
        # The walkthrough's closing banner names the count too.
        self.assertIn(str(n), _read(_SETUP), "setup banner capability count stale")

    def test_ports_match_the_launchers(self):
        guide = _read(_GUIDE)
        board = _read(os.path.join(_ROOT, "bin", "shaula-board"))
        office = _read(os.path.join(_ROOT, "bin", "shaula-office"))
        # The board launcher's default port, as documented in the guide.
        self.assertIn("9121", board, "board launcher no longer defaults to 9121")
        self.assertIn("9121", guide, "guide's board port is stale")
        self.assertIn('"8800"', office, "office launcher no longer defaults to 8800")
        self.assertIn("8800", guide, "guide's office port is stale")

    def test_local_model_matches_the_hardened_floor(self):
        # The setup default model must be the documented offline floor in the
        # hardened config template (they drift → doctor passes, chat 404s).
        harden = _read(os.path.join(_ROOT, "config", "shaula-harden.yaml"))
        setup = _read(_SETUP)
        m = re.search(r'LOCAL_MODEL="\$\{SHAULA_OLLAMA_MODEL:-([^}"]+)\}"', setup)
        self.assertIsNotNone(m, "setup lost its LOCAL_MODEL default")
        self.assertIn(m.group(1), harden,
                      "setup's local model is not the floor documented in shaula-harden.yaml")

    def test_python_window_matches_hermes(self):
        # Guide + setup promise 3.11–3.13; the vendored pyproject is the truth.
        pyproject = _read(os.path.join(_ROOT, "vendor", "hermes", "pyproject.toml"))
        self.assertIn('requires-python = ">=3.11,<3.14"', pyproject,
                      "hermes python window changed — update bin/shaula-setup + the guide")


class GuideIsHonest(unittest.TestCase):
    def test_guide_passes_the_house_linter(self):
        # The onboarding doc obeys the same banned-language gate as everything
        # the office ships. (Negation-aware: 'no invented statistics' is fine.)
        from engine.generate import lint
        hits = lint(_read(_GUIDE))
        self.assertEqual(hits, [], f"GETTING_STARTED.md carries banned language: {hits}")


if __name__ == "__main__":
    unittest.main()
