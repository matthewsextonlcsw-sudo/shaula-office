"""engine/render_dump.mjs — execute the built SPA headless and DUMP the rendered
HTML (all routes) for the claim-provenance gate.

WHY: the built site is a single-page app. The static index.html is a SHELL — its
<main> is empty route divs; the body claims (hero, about, approach, method, fees)
are rendered client-side by app.js. So the only honest target for a claim scan is
the EXECUTED output, exactly what render_check.mjs already proves renders. This
dumper is its companion: same VM execution model, but it emits the HTML instead of
asserting it.

unittest; builds the synthetic northstar site, renders it, and asserts the dump is
real, filled (0 {{tokens}} / 0 AI-GENERATE markers), and carries the practice's own
data. Node-dependent → skips when node is absent (CI + prove.sh always have it).
NO PHI: synthetic fixture only.
"""
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import pipeline  # noqa: E402

SURVEY = json.loads(
    (ROOT / "fixtures" / "northstar-denver" / "survey.json").read_text(encoding="utf-8")
)
HAS_NODE = shutil.which("node") is not None

_TMP = tempfile.mkdtemp(prefix="renderdump-test-")
BUILT = pipeline.build_site(
    SURVEY, sites_dir=pathlib.Path(_TMP) / "sites", slug="rd-northstar"
)


def tearDownModule():
    shutil.rmtree(_TMP, ignore_errors=True)


@unittest.skipUnless(HAS_NODE, "node required to execute the SPA")
class RenderDump(unittest.TestCase):
    def _dump(self, out_dir):
        return subprocess.run(
            ["node", str(ROOT / "engine" / "render_dump.mjs"), "--out", str(out_dir)],
            capture_output=True, text=True, timeout=60,
        )

    def test_dumps_real_filled_html(self):
        p = self._dump(BUILT["dir"])
        self.assertEqual(p.returncode, 0, p.stderr)
        html = p.stdout
        self.assertGreater(len(html), 2000, "rendered dump should be substantial")
        self.assertNotIn("{{", html, "no unfilled tokens may survive into the dump")
        self.assertNotIn("AI-GENERATE", html, "no generate markers may survive")
        self.assertIn("Maya Restrepo", html, "the practice's own data must render")

    def test_missing_app_js_is_a_hard_error(self):
        # A directory with no app.js must FAIL loudly, never emit an empty pass
        # that a downstream gate would read as "nothing to flag".
        empty = pathlib.Path(tempfile.mkdtemp(prefix="rd-empty-"))
        self.addCleanup(shutil.rmtree, empty, ignore_errors=True)
        p = self._dump(empty)
        self.assertNotEqual(p.returncode, 0)


if __name__ == "__main__":
    unittest.main()
