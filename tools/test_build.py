"""Tests for tools/build.py without network access. Run: python -m unittest discover -s tools -v"""

from __future__ import annotations

import sys
import tempfile
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build  # noqa: E402

NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
LIST = {"luxon": ["v1.5"], "cities": {"europe-moscow-1": "Moscow"}}
SERVER = {"version": "0.1.1", "date": "2026-11-14", "url": "https://github.com/haulnet/haulnet-server/releases/tag/v0.1.1",
          "downloads": 3}


class ValuesTests(unittest.TestCase):
    def test_no_mod_release(self):
        v = build.values({"mod": None, "server": SERVER, "list": LIST}, NOW)
        self.assertIn("no release yet", v["status_line"])
        self.assertIn("server <a", v["status_line"])
        self.assertIn("not released", v["mod_badge"])
        self.assertIn("source", v["players_steps"])
        self.assertEqual(v["built_at"], "2026-11-14 12:00 UTC")
        self.assertIn("&quot;europe-moscow-1&quot;:&quot;Moscow&quot;", v["cities_json"])

    def test_mod_release(self):
        mod = {"version": "0.4.0", "date": "2026-12-01", "url": "https://github.com/haulnet/haulnet-repo/releases/tag/v0.4.0",
               "downloads": 0}
        v = build.values({"mod": mod, "server": SERVER, "list": LIST}, NOW)
        self.assertIn("v0.4.0", v["status_line"])
        self.assertIn("released 2026-12-01", v["status_line"])
        self.assertIn("v0.4.0", v["mod_badge"])
        self.assertIn("BepInEx/plugins", v["players_steps"])

    def test_values_are_escaped(self):
        listing = {"luxon": ["<b>"], "cities": {"x": "<script>"}}
        v = build.values({"mod": None, "server": None, "list": listing}, NOW)
        self.assertNotIn("<b>", v["luxon_badge"])
        self.assertNotIn("<script>", v["cities_json"])


class RenderTests(unittest.TestCase):
    def test_unknown_placeholder_fails(self):
        with self.assertRaises(KeyError):
            build.render("{{ nope }}", {})

    def test_placeholders_replaced(self):
        self.assertEqual(build.render("a {{x}} b {{ x }}", {"x": "1"}), "a 1 b 1")

    def test_index_has_only_known_placeholders(self):
        fields = build.values({"mod": None, "server": SERVER, "list": LIST}, NOW)
        html = build.render((build.ROOT / "index.html").read_text(encoding="utf-8"), fields)
        self.assertNotIn("{{", html)


class ReleaseTests(unittest.TestCase):
    def test_missing_release_is_none(self):
        error = urllib.error.HTTPError("u", 404, "Not Found", {}, None)
        with mock.patch.object(build, "get_json", side_effect=error):
            self.assertIsNone(build.latest_release("haulnet/x"))

    def test_other_errors_fail_the_build(self):
        error = urllib.error.HTTPError("u", 500, "Error", {}, None)
        with mock.patch.object(build, "get_json", side_effect=error):
            with self.assertRaises(urllib.error.HTTPError):
                build.latest_release("haulnet/x")

    def test_bad_tag_fails(self):
        with mock.patch.object(build, "get_json", return_value={"tag_name": "<oops>"}):
            with self.assertRaises(ValueError):
                build.latest_release("haulnet/x")

    def test_release_fields(self):
        data = {"tag_name": "v0.1.1", "published_at": "2026-11-14T10:18:06Z", "html_url": "https://e/x",
                "assets": [{"download_count": 2}, {"download_count": 5}]}
        with mock.patch.object(build, "get_json", return_value=data):
            self.assertEqual(build.latest_release("haulnet/x"),
                             {"version": "0.1.1", "date": "2026-11-14", "url": "https://e/x", "downloads": 7})


class BuildTests(unittest.TestCase):
    def test_offline_build_publishes_site_files_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "site"
            build.build(out, offline=True, now=NOW)
            names = {p.name for p in out.iterdir()}
            self.assertTrue({"index.html", "style.css", "live.js", "404.html", ".nojekyll", "assets"} <= names)
            self.assertFalse(names & {"tools", ".github", "README.md", ".git"})
            self.assertNotIn("{{", (out / "index.html").read_text(encoding="utf-8"))


class PagesTests(unittest.TestCase):
    def test_front_matter(self):
        meta, body = build.split_front_matter("<!-- title: A -->\n<!-- description: B c -->\n<h1>x</h1>\n")
        self.assertEqual(meta, {"title": "A", "description": "B c"})
        self.assertEqual(body, "<h1>x</h1>\n")

    def test_docs_pages_and_internal_links(self):
        import re as _re
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "site"
            build.build(out, offline=True, now=NOW)
            pages = {}
            for name, label in build.DOCS_NAV:
                path = "docs/" if name == "index" else f"docs/{name}/"
                text = (out / path / "index.html").read_text(encoding="utf-8")
                self.assertNotIn("{{", text, path)
                self.assertIn(f'aria-current="page">{label}<', text, path)
                pages["/" + path] = text
            pages["/"] = (out / "index.html").read_text(encoding="utf-8")
            for source, text in pages.items():
                for href in _re.findall(r'href="(/[^"]*)"', text):
                    path, _, anchor = href.partition("#")
                    target = out / path.lstrip("/")
                    if path.endswith("/") or path == "":
                        target = target / "index.html"
                    self.assertTrue(target.exists(), f"{source}: broken link {href}")
                    if anchor and path in pages:
                        self.assertIn(f'id="{anchor}"', pages[path], f"{source}: missing anchor {href}")


if __name__ == "__main__":
    unittest.main()
