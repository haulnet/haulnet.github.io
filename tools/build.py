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
SITE = "https://haulnet.cc"
# The mod's English text table: the one source of every message the troubleshooting page quotes (ADR 0025).
# Read from the latest mod release, or from main while there is none.
MOD_STRINGS = "https://raw.githubusercontent.com/" + MOD_REPO + "/{ref}/mod/Haulnet/Localization/{lang}.tsv"
# Players see message titles in the game's language: the page also shows these translations, so a player can find a
# message by the title they saw. (code, English name of the language)
TITLE_LANGUAGES = (("ru", "Russian"), ("uk", "Ukrainian"))
# Headers of text-input popups: the game does not show them, so the page does not explain them (en.tsv comment).
HIDDEN_HEADERS = {"ADDRESS.HEADER", "PORT.HEADER"}
MSG = re.compile(r"<!--\s*msg:\s*([A-Z_]+)((?:\s+[a-z]+=[^\s>]+)*)\s*-->(.*?)<!--\s*/msg\s*-->", re.S)
MSG_LIST = re.compile(r"<!--\s*msg-list:\s*([A-Z_]+\.)\s*-->")
TEMPLATES = ("index.html", "404.html")
# Files and folders of the repository that are not part of the published site.
EXCLUDE = {".git", ".github", ".gitattributes", ".gitignore", "tools", "README.md", "_site", "CNAME", "_pages",
           "_layout.html", "_partials"}
PLACEHOLDER = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
FRONT_MATTER = re.compile(r"\A(?:\s*<!--\s*([a-z]+):\s*(.*?)\s*-->\n)+")
FRONT_LINE = re.compile(r"<!--\s*([a-z]+):\s*(.*?)\s*-->")
# Main navigation: (key, href, label). The docs pages mark "docs" (or "server" on /docs/server/) as current.
SITE_NAV = (("docs", "/docs/", "Docs"), ("servers", "https://servers.haulnet.cc/", "Servers"),
            ("server", "/docs/server/", "Run a server"), ("github", "https://github.com/haulnet", "GitHub"))
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


def get_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "haulnet.cc-build"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read().decode("utf-8")


def parse_strings(text: str) -> dict[str, str]:
    """KEY<TAB>text lines of a mod text table; \\n is a line break, # starts a comment."""
    strings = {}
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        key, sep, value = line.partition("\t")
        if not sep or not re.fullmatch(r"[A-Z0-9_.]+", key):
            raise ValueError(f"mod strings: unexpected line {line[:40]!r}")
        strings[key] = value.replace("\\n", "\n")
    if "NO_SERVER.HEADER" not in strings:
        raise ValueError("mod strings: NO_SERVER.HEADER missing")
    return strings


def mod_strings(mod: dict | None) -> dict:
    ref = f'v{mod["version"]}' if mod else "main"
    titles = {code: parse_strings(get_text(MOD_STRINGS.format(ref=ref, lang=code))) for code, _ in TITLE_LANGUAGES}
    return {"ref": ref, "strings": parse_strings(get_text(MOD_STRINGS.format(ref=ref, lang="en"))), "titles": titles}


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
                "list": {"cities": {}}, "text": None}
    mod = latest_release(MOD_REPO)
    return {"mod": mod, "server": latest_release(SERVER_REPO), "list": server_list(), "text": mod_strings(mod)}


def values(facts: dict, now: datetime) -> dict[str, str]:
    """Strings for the placeholders; every value is HTML, built from escaped parts."""
    e = html.escape
    mod, server, listing = facts["mod"], facts["server"], facts["list"]
    releases = f"https://github.com/{MOD_REPO}/releases"
    if mod:
        status = f'Mod <a href="{e(mod["url"])}">v{e(mod["version"])}</a> · released {e(mod["date"])}'
        mod_badge = f'<a class="badge" href="{e(mod["url"])}"><span>mod</span>v{e(mod["version"])}</a>'
        players_steps = (
            "<li>Install <b>BepInExPack</b> (BepInEx 5) for R.E.P.O.</li>"
            f'<li>Download <a href="https://github.com/{MOD_REPO}/releases/latest/download/Haulnet.zip">Haulnet '
            f'v{e(mod["version"])}</a> and extract it into <code>BepInEx/plugins</code>.</li>'
            "<li>Start the game, open <b>Private game</b> or <b>Public game</b> and pick the <b>HAULNET</b> tab.</li>")
        release_note = (f'The latest release is <a href="{e(mod["url"])}">Haulnet v{e(mod["version"])}</a> '
                        f'({e(mod["date"])}).')
        release_note_short = release_note
        manual_download = (f'<a class="button" href="https://github.com/{MOD_REPO}/releases/latest/download/Haulnet.zip">'
                           f'Download Haulnet v{e(mod["version"])}</a>')
    else:
        status = "Free and open source"
        mod_badge = '<span class="badge"><span>mod</span>from source</span>'
        players_steps = (
            f'<li>Packaged downloads are published on <a href="{releases}">GitHub</a> (<i>Watch → Custom → '
            'Releases</i> tells you when); until the first one, build Haulnet <a href="/docs/install/#source">from '
            "source</a>.</li>"
            "<li>Install it with <b>BepInExPack</b> (BepInEx 5), its only dependency: "
            '<a href="/docs/install/">Install</a>.</li>'
            "<li>In the game: <b>Private game</b> or <b>Public game</b> → the <b>HAULNET</b> tab.</li>")
        release_note = ('Until the first packaged download is published, Haulnet is built <a href="#source">from '
                        "source</a>; this page shows the download by itself as soon as it is out.")
        release_note_short = ("Releases are published on GitHub; until the first one, Haulnet is built from source "
                              '(<a href="/docs/install/">Install</a>).')
        manual_download = '<span class="button disabled" aria-disabled="true">Download not published yet</span>'
    if server:
        status += f' · server <a href="{e(server["url"])}">v{e(server["version"])}</a>'
        server_badge = f'<a class="badge" href="{e(server["url"])}"><span>server</span>v{e(server["version"])}</a>'
    else:
        server_badge = '<span class="badge"><span>server</span>not released</span>'
    text = facts.get("text")
    strings = text["strings"] if text else {}
    if text:
        ref = text["ref"]
        source = (f'<a href="https://github.com/{MOD_REPO}/blob/{e(ref)}/mod/Haulnet/Localization/en.tsv">'
                  + (f"Haulnet {e(ref)}" if ref != "main" else "the current source on main") + "</a>")
    else:
        source = "offline preview: keys instead of texts"
    return {
        "release_note": release_note,
        "release_note_short": release_note_short,
        "messages_source": source,
        "row_full": e(strings.get("ROW.FULL", "ROW.FULL")),
        "row_updating": e(strings.get("ROW.UPDATING", "ROW.UPDATING")),
        "row_checking": e(strings.get("ROW.CHECKING", "ROW.CHECKING")),
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


def message_html(text: str) -> str:
    """A mod text as HTML: escaped, {placeholders} in italics, line breaks kept."""
    out = html.escape(text, quote=False)
    out = re.sub(r"\{([a-z]+)\}", r"<i>\1</i>", out)
    return out.replace("\n", "<br>")


def render_messages(page: str, strings: dict[str, str] | None, titles: dict[str, dict[str, str]] | None = None) -> str:
    """Fills <!-- msg: KEY id=… body=A,B --> explanation <!-- /msg --> blocks from the mod's text table.

    With the table (every real build) it fails when a message the game shows has no block, or a block names a key the
    table does not have. Without it (offline preview) the keys are shown instead of the texts."""
    used = set()

    def text(key: str) -> str:
        if strings is None:
            return f"<code>{html.escape(key)}</code>"
        if key not in strings:
            raise KeyError(f"troubleshooting: {key} is not in the mod's en.tsv")
        return message_html(strings[key])

    def block(match: re.Match) -> str:
        key, attrs, explanation = match.group(1), dict(a.split("=", 1) for a in match.group(2).split()), match.group(3)
        header = f"{key}.HEADER"
        if header in used:
            raise KeyError(f"troubleshooting: {header} explained twice")
        used.add(header)
        anchor = attrs.get("id", key.lower().replace("_", "-"))
        quotes = "".join(f'\n  <p class="msg">{text(b)}</p>' for b in attrs.get("body", f"{key}.BODY").split(","))
        other = [f'in {name}: <b lang="{code}">{html.escape(titles[code][header])}</b>'
                 for code, name in TITLE_LANGUAGES if titles and header in titles.get(code, {})]
        if other:
            quotes = f'\n  <p class="msg-alt">Title {" · ".join(other)}</p>' + quotes
        return f'<dt id="{html.escape(anchor)}">{text(header)}</dt>\n<dd>{quotes}\n{explanation.strip(chr(10))}\n</dd>'

    def listing(match: re.Match) -> str:
        if strings is None:
            return f"<p><code>{html.escape(match.group(1))}*</code></p>"
        keys = [k for k in strings if k.startswith(match.group(1))]
        if not keys:
            raise KeyError(f"troubleshooting: no keys start with {match.group(1)}")
        return '<ul class="msg-list">' + "".join(f"<li>{message_html(strings[k])}</li>" for k in keys) + "</ul>"

    page = MSG_LIST.sub(listing, MSG.sub(block, page))
    if strings is not None:
        shown = {k for k in strings if k.endswith(".HEADER")} - HIDDEN_HEADERS
        if shown - used:
            raise KeyError(f"troubleshooting: no explanation for {', '.join(sorted(shown - used))}")
    return page


def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    match = FRONT_MATTER.match(text)
    if not match:
        return {}, text
    return dict(FRONT_LINE.findall(match.group(0))), text[match.end():]


def partial(name: str) -> str:
    return (ROOT / "_partials" / name).read_text(encoding="utf-8").rstrip(chr(10))


def header(current: str | None) -> str:
    links = []
    for key, href, label in SITE_NAV:
        attr = ' aria-current="page"' if key == current else ""
        links.append(f'      <a href="{href}"{attr}>{html.escape(label)}</a>')
    lines = ['<header class="top">', '  <div class="wrap">',
             f'    <a class="brand" href="/" aria-label="Haulnet home">{partial("logo.svg")}</a>',
             '    <nav aria-label="Main">', *links, '    </nav>', '  </div>', '</header>']
    return chr(10).join(lines)


def chrome(fields: dict[str, str], current: str | None = None) -> dict[str, str]:
    """Fields plus the shared header and footer of every page."""
    return dict(fields, header=header(current), footer=render(partial("footer.html"), dict(fields, logo=partial("logo.svg"))))


def wrap_tables(text: str) -> str:
    """Wide tables scroll inside their own box on narrow screens instead of widening the page."""
    return text.replace("<table>", '<div class="table-wrap"><table>').replace("</table>", "</table></div>")


def docs_nav(current: str) -> str:
    items = []
    for name, label in DOCS_NAV:
        href = "/docs/" if name == "index" else f"/docs/{name}/"
        attr = ' aria-current="page"' if name == current else ""
        items.append(f'<li><a href="{href}"{attr}>{html.escape(label)}</a></li>')
    return "\n".join(items)


def build_pages(out: Path, fields: dict[str, str], strings: dict[str, str] | None = None,
                titles: dict[str, dict[str, str]] | None = None) -> None:
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
        if name == "troubleshooting":
            body = render_messages(body, strings, titles)
        page = dict(chrome(fields, "server" if name == "server" else "docs"), title=html.escape(meta["title"]), description=html.escape(meta["description"]),
                    canonical=f"https://haulnet.cc/{path}", docs_nav=docs_nav(name), content=wrap_tables(render(body, fields)))
        target = out / path / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(layout, page), encoding="utf-8", newline="\n")
    missing = names - {p.stem for p in (ROOT / "_pages" / "docs").glob("*.html")}
    if missing:
        raise KeyError(f"missing docs page(s): {', '.join(sorted(missing))}")


def seo_files(out: Path, pages: list[str], now: datetime) -> None:
    """robots.txt and sitemap.xml: every published page, nothing else."""
    (out / "robots.txt").write_text(f"User-agent: *\nAllow: /\n\nSitemap: {SITE}/sitemap.xml\n",
                                    encoding="utf-8", newline="\n")
    day = now.strftime("%Y-%m-%d")
    urls = "".join(f"  <url><loc>{SITE}/{p}</loc><lastmod>{day}</lastmod></url>\n" for p in pages)
    (out / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n'
                                     '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
                                     f"{urls}</urlset>\n", encoding="utf-8", newline="\n")


def build(out: Path, offline: bool = False, now: datetime | None = None) -> None:
    now = now or datetime.now(timezone.utc)
    facts = gather(offline)
    fields = chrome(values(facts, now))
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
    text = facts["text"]
    build_pages(out, fields, text["strings"] if text else None, text.get("titles") if text else None)
    seo_files(out, [""] + [("docs/" if n == "index" else f"docs/{n}/") for n, _ in DOCS_NAV], now)
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
