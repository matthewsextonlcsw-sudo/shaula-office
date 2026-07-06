"""Cloud Run deploy-context generator contract (concierge-beta stream 7).

`scripts/render_run_context.py` is the missing piece of the proven publish runbook
(`docs/WEBSITE_PUBLISH_RUNBOOK.md` §2): the "tiny nginx Dockerfile" the Cloud Run leg
needs, which was DESCRIBED but generated nowhere. These tests pin that contract:

  * the rendered context carries a real nginx Dockerfile + vhost with the exact port
    + SPA fallback the runbook specifies;
  * the built site is copied in VERBATIM (bytes preserved, nested assets included) and
    the served sites/<slug>/ is never moved;
  * a directory with no index.html is refused (build the site first);
  * re-rendering into the same context dir is idempotent (clean overwrite).

Everything runs in a temp dir — no repo tree is touched. Stdlib unittest only,
deterministic, NO network, NO gcloud, NO PHI (synthetic site fixture).
"""
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import render_run_context as RC  # noqa: E402


def _make_site(root: pathlib.Path) -> pathlib.Path:
    """A minimal but realistic built site: index.html + app.js + a nested asset."""
    site = root / "sites" / "demo-slug"
    (site / "assets").mkdir(parents=True)
    (site / "index.html").write_text("<!doctype html><title>demo</title>\n", encoding="utf-8")
    (site / "app.js").write_text("export const x = 1;\n", encoding="utf-8")
    (site / "assets" / "logo.svg").write_text("<svg/>\n", encoding="utf-8")
    return site


class RendersContext(unittest.TestCase):
    def test_context_has_dockerfile_and_nginx_conf(self):
        with tempfile.TemporaryDirectory() as td:
            site = _make_site(pathlib.Path(td))
            ctx = RC.render_context(site)
            dockerfile = (ctx / "Dockerfile").read_text(encoding="utf-8")
            nginx = (ctx / "nginx.conf").read_text(encoding="utf-8")
            # The Dockerfile is a self-contained nginx image rooted at the copied site.
            self.assertIn("FROM nginx", dockerfile)
            self.assertIn("EXPOSE 8080", dockerfile)
            self.assertIn("COPY site/", dockerfile)
            # The vhost listens on Cloud Run's port and falls back to the SPA router.
            self.assertIn("listen       8080", nginx)
            self.assertIn("try_files $uri $uri/ /index.html", nginx)

    def test_site_files_copied_verbatim(self):
        with tempfile.TemporaryDirectory() as td:
            site = _make_site(pathlib.Path(td))
            original = (site / "index.html").read_bytes()
            ctx = RC.render_context(site)
            copied = ctx / "site"
            # index.html is byte-identical, and nested + sibling assets came along.
            self.assertEqual((copied / "index.html").read_bytes(), original)
            self.assertTrue((copied / "app.js").is_file())
            self.assertTrue((copied / "assets" / "logo.svg").is_file())
            # The served site itself is untouched (copied, never moved).
            self.assertTrue((site / "index.html").is_file())

    def test_missing_index_raises(self):
        with tempfile.TemporaryDirectory() as td:
            empty = pathlib.Path(td) / "not-a-site"
            empty.mkdir()
            with self.assertRaises(FileNotFoundError):
                RC.render_context(empty)

    def test_explicit_out_dir_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            tmp = pathlib.Path(td)
            site = _make_site(tmp)
            out = tmp / "ctx"
            first = RC.render_context(site, out)
            # A stale file under the prior site copy must not survive a re-render.
            (first / "site" / "STALE.txt").write_text("old", encoding="utf-8")
            second = RC.render_context(site, out)
            self.assertEqual(first, second)
            self.assertFalse((second / "site" / "STALE.txt").exists())
            self.assertTrue((second / "site" / "index.html").is_file())


if __name__ == "__main__":
    unittest.main()
