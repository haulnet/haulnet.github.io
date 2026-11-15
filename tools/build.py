#!/usr/bin/env python3
"""Build haulnet.cc: copy the site and fill in facts known at build time.

Usage:
  python tools/build.py --out _site [--offline]

Facts: latest releases of the mod (haulnet/haulnet-repo) and of haulnet-server from the GitHub API and the city
of every listed server from servers.haulnet.cc. "No release yet" is a normal
state; any other failure stops the build so the last deployed site stays online. `--offline` uses placeholders
instead of network requests (local preview only). Set GITHUB_TOKEN to raise the API rate limit.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MOD_REPO = "haulnet/haulnet-repo"
SERVER_REPO = "haulnet/haulnet-server"
SERVER_LIST = "https://servers.haulnet.cc/v1/servers.json"
TEMPLATES = ("index.html",)
# Files and folders of the repository that are not part of the published site.
EXCLUDE = {".git", ".github", ".gitattributes", ".gitignore", "tools", "README.md", "_site", "CNAME", "_pages",
           "_layout.html"}
PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
FRONT_MATTER = re.compile(r"\A(?:\s*<!--\s*([a-z]+):\s*(.*?)\s*-->\n)+")
FRONT_LINE = re.compile(r"<!--\s*([a-z]+):\s*(.*?)\s*-->")
# Documentation pages: _pages/docs/<name>.html → /docs/<name>/ (index.html → /docs/), in this navigation order.
DOCS_NAV = (("index", "Overview"), ("install", "Install"), ("play", "Play"), ("server", "Run a server"),
            ("troubleshooting", "Troubleshooting"))


def get_json(url: str):
    headers = {"Accept": "application/json", "User-Agent": "haulnet.cc-build"}
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as response:
        return json.load(response)


def latest_release(repo: str) -> dict | None:
    """Latest published release, or None when the repository has none yet."""
    try:
        data = get_json(f"https://api.github.com/repos/{repo}/releases/latest")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    tag = data.get("tag_name")
    if not isinstance(tag, str) or not re.fullmatch(r"v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", tag):
        raise ValueError(f"{repo}: unexpected release tag {tag!r}")
    return {
        "version": tag.removeprefix("v"),
        "date": str(data.get("published_at", ""))[:10],
        "url": data.get("html_url") or f"https://github.com/{repo}/releases/latest",
        "downloads": sum(a.get("download_count", 0) for a in data.get("assets") or []),
    }


def server_list() -> dict:
    data = get_json(SERVER_LIST)
    if data.get("schema_version") != 1:
        raise ValueError("server list: unexpected schema version")
    names = {c["id"]: c["name"] for c in data.get("cities", [])}
    return {
        "cities": {s["id"]: names.get(s["city"], s["city"]) for s in data.get("servers", [])},
    }


def gather(offline: bool) -> dict:
    if offline:
        return {"mod": None, "server": {"version": "0.0.0", "date": "", "url": "#", "downloads": 0},
                "list": {"cities": {}}}
    return {"mod": latest_release(MOD_REPO), "server": latest_release(SERVER_REPO), "list": server_list()}


def values(facts: dict, now: datetime) -> dict[str, str]:
    """Strings for the placeholders; every value is HTML, built from escaped parts."""
    e = html.escape
    mod, server, listing = facts["mod"], facts["server"], facts["list"]
    if mod:
        status = f'Mod <a href="{e(mod["url"])}">v{e(mod["version"])}</a> · released {e(mod["date"])}'
        mod_badge = f'<a class="badge" href="{e(mod["url"])}"><span>mod</span>v{e(mod["version"])}</a>'
        players_steps = (
            "<li>Install <b>BepInExPack</b> for R.E.P.O. (a mod manager such as r2modman or Gale does it for you).</li>"
            f'<li>Download <a href="{e(mod["url"])}">Haulnet v{e(mod["version"])}</a> and put it into '
            "<code>BepInEx/plugins</code>, or install it from your mod manager.</li>"
            "<li>Start the game, open <b>Private game</b> or <b>Public game</b> and pick the <b>HAULNET</b> tab.</li>")
    else:
        status = "Pre-release · the mod has no release yet"
        mod_badge = '<span class="badge"><span>mod</span>not released</span>'
        players_steps = (
            "<li>There is no release yet. Builders can compile the mod from "
            f'<a href="https://github.com/{MOD_REPO}#readme">source</a> (BepInEx 5).</li>'
            "<li>The first release will come to Thunderstore (r2modman, Gale) with BepInExPack as its only "
            "dependency.</li>"
            "<li>In the game: <b>Private game</b> or <b>Public game</b> → the <b>HAULNET</b> tab.</li>")
    if server:
        status += f' · server <a href="{e(server["url"])}">v{e(server["version"])}</a>'
        server_badge = f'<a class="badge" href="{e(server["url"])}"><span>server</span>v{e(server["version"])}</a>'
    else:
        server_badge = '<span class="badge"><span>server</span>not released</span>'
    if mod:
        release_note = (f'The latest release is <a href="{e(mod["url"])}">Haulnet v{e(mod["version"])}</a> '
                        f'({e(mod["date"])}).')
        manual_download = (f'<a class="button" href="https://github.com/{MOD_REPO}/releases/latest/download/Haulnet.zip">'
                           f'Download Haulnet v{e(mod["version"])}</a>')
    else:
        release_note = ("Haulnet has <b>no release yet</b>: the first one is being tested. Until then it is built "
                        "from source (below); this page switches to the release by itself when it is out.")
        manual_download = '<span class="button disabled" aria-disabled="true">No release yet</span>'
    return {
        "release_note": release_note,
        "manual_download": manual_download,
        "status_line": status,
        "mod_badge": mod_badge,
        "server_badge": server_badge,
        "players_steps": players_steps,
        "list_url": e(SERVER_LIST),
        "cities_json": e(json.dumps(listing["cities"], separators=(",", ":"), sort_keys=True)),
        "built_at": e(now.strftime("%Y-%m-%d %H:%M UTC")),
    }


def render(template: str, fields: dict[str, str]) -> str:
    missing = sorted({m for m in PLACEHOLDER.findall(template) if m not in fields})
    if missing:
        raise KeyError(f"unknown placeholder(s): {', '.join(missing)}")
    return PLACEHOLDER.sub(lambda m: fields[m.group(1)], template)


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    match = FRONT_MATTER.match(text)
    if not match:
        return {}, text
    return dict(FRONT_LINE.findall(match.group(0))), text[match.end():]


def docs_nav(current: str) -> str:
    items = []
    for name, label in DOCS_NAV:
        href = "/docs/" if name == "index" else f"/docs/{name}/"
        attr = ' aria-current="page"' if name == current else ""
        items.append(f'<li><a href="{href}"{attr}>{html.escape(label)}</a></li>')
    return "\n".join(items)


def build_pages(out: Path, fields: dict[str, str]) -> None:
    layout = (ROOT / "_layout.html").read_text(encoding="utf-8")
    names = {name for name, _ in DOCS_NAV}
    for source in sorted((ROOT / "_pages" / "docs").glob("*.html")):
        name = source.stem
        if name not in names:
            raise KeyError(f"_pages/docs/{source.name} is not in DOCS_NAV")
        meta, body = split_front_matter(source.read_text(encoding="utf-8"))
        if not meta.get("title") or not meta.get("description"):
            raise KeyError(f"_pages/docs/{source.name}: title and description are required")
        path = "docs/" if name == "index" else f"docs/{name}/"
        page = dict(fields, title=html.escape(meta["title"]), description=html.escape(meta["description"]),
                    canonical=f"https://haulnet.cc/{path}", docs_nav=docs_nav(name), content=render(body, fields))
        target = out / path / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(layout, page), encoding="utf-8", newline="\n")
    missing = names - {p.stem for p in (ROOT / "_pages" / "docs").glob("*.html")}
    if missing:
        raise KeyError(f"missing docs page(s): {', '.join(sorted(missing))}")


def build(out: Path, offline: bool = False, now: datetime | None = None) -> None:
    fields = values(gather(offline), now or datetime.now(timezone.utc))
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for item in sorted(ROOT.iterdir()):
        if item.name in EXCLUDE or item.name.startswith(".wt"):
            continue
        target = out / item.name
        if item.is_dir():
            shutil.copytree(item, target)
        elif item.name in TEMPLATES:
            target.write_text(render(item.read_text(encoding="utf-8"), fields), encoding="utf-8", newline="\n")
        else:
            shutil.copy2(item, target)
    build_pages(out, fields)
    (out / ".nojekyll").write_text("", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--offline", action="store_true", help="no network requests (local preview only)")
    args = parser.parse_args()
    try:
        build(args.out, args.offline)
    except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
        print(f"build failed: {exc}", file=sys.stderr)
        return 1
    print(f"built {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
