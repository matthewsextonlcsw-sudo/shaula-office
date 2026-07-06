"""test_fill_escaping — stored-XSS regression for the engine token-fill path.

A practice-survey value flows: intake -> practice.json -> build_token_map ->
substitute_tokens -> template HTML/JS (attribute contexts). The token path must
HTML-escape values (quote=True) so `"><script>` cannot break out of an attribute
and execute on the published, public, client-facing site. (The AI-GENERATE blocks
are escaped separately; this guards the deterministic token path.)
"""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from engine import fill  # noqa: E402

_PAYLOAD = '"><script>alert(document.cookie)</script>'


class TestBuildTokenMapEscapes(unittest.TestCase):
    def test_dangerous_value_is_escaped(self):
        tokens = fill.build_token_map({"business_name": _PAYLOAD, "_comment": "skip me"})
        bn = tokens["business_name"]
        self.assertNotIn("<script>", bn)
        self.assertIn("&lt;script&gt;", bn)
        self.assertIn("&quot;", bn)            # quote=True -> attribute breakout closed
        self.assertNotIn('"', bn)              # no raw double-quote survives
        self.assertNotIn("_comment", tokens)   # underscore keys still skipped

    def test_normal_value_round_trips_for_display(self):
        # Escaping must be transparent for ordinary names (browser decodes entities).
        tokens = fill.build_token_map({"owner_name": "O'Brien & Sons"})
        self.assertIn("&#x27;", tokens["owner_name"])  # apostrophe escaped
        self.assertIn("&amp;", tokens["owner_name"])   # ampersand escaped
        self.assertNotIn("<", tokens["owner_name"])

    def test_none_becomes_empty(self):
        self.assertEqual(fill.build_token_map({"x": None})["x"], "")


class TestSubstituteTokensNoBreakout(unittest.TestCase):
    def test_attribute_context_cannot_break_out(self):
        d = pathlib.Path(tempfile.mkdtemp())
        page = d / "index.html"
        page.write_text('<img alt="{{business_name}}">', encoding="utf-8")
        tokens = fill.build_token_map({"business_name": _PAYLOAD})
        fill.substitute_tokens(d, {"index.html"}, tokens, lenient=True)
        out = page.read_text(encoding="utf-8")
        self.assertNotIn("<script>", out)
        self.assertNotIn('"><script', out)     # the breakout sequence is gone
        self.assertIn("&lt;script&gt;", out)


if __name__ == "__main__":
    unittest.main()
