"""Hash-router anchors must be real links (WCAG 4.1.2 + 2.1.1 regression guard).

The private-practice SPA routes via a ``data-route`` attribute + JS click
delegation. A bare ``<a data-route="x">`` with no ``href`` exposes as plain
text in the accessibility tree (no link role) and does NOT activate on Enter —
locking out keyboard and screen-reader users (WCAG 4.1.2 Name/Role/Value and
2.1.1 Keyboard). The fix adds ``href="#<route>"`` to every router anchor, which
restores the implicit link role + native keyboard activation; the existing
click handler calls ``preventDefault()`` first, so SPA routing is byte-identical.

This test pins that root-cause fix at the source so the anti-pattern cannot
regress: the template (source of truth) AND the golden fixture (kept in
lockstep) must each carry a matching href on every ``data-route`` anchor —
in the static ``index.html`` AND in the anchors ``app.js`` renders at runtime
(the original fix caught the former and missed five of the latter).

Stdlib only (unittest). NO PHI — operates on neutral template/fixture markup.
"""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]

TARGETS = [
    ROOT / "templates" / "private-practice" / "index.html",
    ROOT / "fixtures" / "cedar-sage" / "expected-output" / "index.html",
    # app.js emits router anchors at runtime too — same dead-anchor risk as the
    # static HTML, and the original ISSUE-001 fix missed every one of them.
    ROOT / "templates" / "private-practice" / "app.js",
    ROOT / "fixtures" / "cedar-sage" / "expected-output" / "app.js",
]

_A_TAG = re.compile(r"<a\b([^>]*)>", re.IGNORECASE)
_DATA_ROUTE = re.compile(r'\bdata-route="([^"]+)"')
_HREF = re.compile(r'\bhref="([^"]*)"')


class NavAnchorsAreReachable(unittest.TestCase):
    def test_every_data_route_anchor_has_matching_href(self):
        for path in TARGETS:
            html = path.read_text(encoding="utf-8")
            offenders = []
            for m in _A_TAG.finditer(html):
                attrs = m.group(1)
                dr = _DATA_ROUTE.search(attrs)
                if not dr:
                    continue  # not a router anchor
                route = dr.group(1)
                href = _HREF.search(attrs)
                if not href:
                    offenders.append(f'<a data-route="{route}"> has NO href')
                elif href.group(1) != f"#{route}":
                    offenders.append(
                        f'<a data-route="{route}"> href is "{href.group(1)}", '
                        f'expected "#{route}"'
                    )
            self.assertEqual(
                offenders,
                [],
                f"{path.relative_to(ROOT)}: router anchors missing/mismatched "
                f"href (keyboard + screen-reader users locked out):\n  "
                + "\n  ".join(offenders),
            )

    def test_guard_actually_sees_router_anchors(self):
        # Sanity: the lint must find anchors in BOTH file kinds, else a markup or
        # renderer change could make the scan vacuously pass. The template ships
        # >=7 static router anchors (6 nav + CTA) in index.html and >=5
        # JS-rendered router anchors in app.js.
        for path, minimum in (
            (ROOT / "templates" / "private-practice" / "index.html", 7),
            (ROOT / "templates" / "private-practice" / "app.js", 5),
        ):
            text = path.read_text(encoding="utf-8")
            count = sum(
                1 for m in _A_TAG.finditer(text) if _DATA_ROUTE.search(m.group(1))
            )
            self.assertGreaterEqual(
                count,
                minimum,
                f"{path.relative_to(ROOT)}: expected >={minimum} router anchors, "
                f"found {count}",
            )


if __name__ == "__main__":
    unittest.main()
