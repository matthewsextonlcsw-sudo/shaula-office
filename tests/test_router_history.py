"""Hash router must support Back/Forward + deep-links (navigation regression guard).

The private-practice SPA renders sections behind a hash route. Two history-API
facts make Back/Forward behave the way users expect:
  1. user navigation uses ``history.pushState`` — each click is a real history
     entry, so Back can step through the sections just visited; and
  2. a ``hashchange`` listener re-renders the view whenever the URL changes
     (Back, Forward, or a hand-edited hash) — without it the URL and the visible
     section desync.

Both regressed silently at one point (every nav used ``replaceState`` and there
was no listener), so Back left the page showing the wrong section. This test
pins the fix at the source template. The route DOM toggling itself is exercised
live in QA; here we guard the load-bearing history wiring statically.

Stdlib only (unittest). NO PHI — operates on neutral framework JS.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_JS = ROOT / "templates" / "private-practice" / "app.js"


class RouterSupportsHistory(unittest.TestCase):
    def setUp(self):
        self.src = APP_JS.read_text(encoding="utf-8")

    def test_navigate_accepts_push_flag(self):
        # The flag is what lets initial-load / hashchange replay a route WITHOUT
        # pushing a duplicate entry, while a click pushes a real one.
        self.assertRegex(
            self.src,
            r"function\s+navigate\(\s*name\s*,\s*push\s*\)",
            "navigate() must accept a push flag (user nav pushes, replay replaces)",
        )

    def test_user_navigation_pushes_history(self):
        self.assertIn(
            "history.pushState",
            self.src,
            "user navigation must pushState so Back/Forward can step through sections",
        )

    def test_back_forward_listener_present(self):
        self.assertTrue(
            re.search(r"addEventListener\(\s*['\"]hashchange['\"]", self.src)
            or re.search(r"addEventListener\(\s*['\"]popstate['\"]", self.src),
            "a hashchange/popstate listener must re-render the view on Back/Forward",
        )

    def test_hashchange_leaves_in_page_anchors_native(self):
        # R-1 regression guard (WCAG 2.4.1). The hashchange listener must NOT
        # route every hash. In-page anchors are not routes: the "Skip to
        # content" link points at #main, and #main is an element id, not a
        # route. A listener that navigates on every hashchange sends that click
        # to routes['main'] (undefined) -> falls back to home, scrolls to top,
        # and rewrites the URL to #home -- the exact opposite of "skip to
        # content". The fix checks route membership and returns early for any
        # non-route hash, leaving the browser's native in-page jump intact.
        m = re.search(
            r"addEventListener\(\s*['\"]hashchange['\"]\s*,\s*\(\s*\)\s*=>\s*\{"
            r"(.*?)\n\s*\}\s*\)",
            self.src,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "hashchange listener body not found")
        body = m.group(1)
        self.assertIn(
            "routes[",
            body,
            "hashchange handler must check route membership before navigating",
        )
        self.assertRegex(
            body,
            r"\breturn\b",
            "hashchange handler must return early on non-route (in-page) hashes "
            "so the #main skip link stays native -- otherwise it bounces the "
            "user to home (R-1 regression).",
        )


if __name__ == "__main__":
    unittest.main()
