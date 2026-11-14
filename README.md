# haulnet.cc

Source of [haulnet.cc](https://haulnet.cc/), the home page of Haulnet, served by GitHub Pages from `main`.

Plain HTML and CSS with a small build step ([`tools/build.py`](tools/build.py), Python standard library): it fills
in the latest releases of the mod and of `haulnet-server` from the GitHub API and the server cities from
`servers.haulnet.cc`. [`.github/workflows/pages.yml`](.github/workflows/pages.yml) builds and deploys on every push to
`main`, every hour and by hand. Documentation pages are fragments in [`_pages/docs/`](_pages/docs/) wrapped in [`_layout.html`](_layout.html) and
published as `/docs/<page>/`. One script, [`live.js`](live.js), shows live numbers from our own server monitor
`monitor.haulnet.cc`; the page is complete without it. No cookies, no analytics, nothing from other sites. Logo,
icons and artwork follow the Haulnet brand (original SVG, no game art).

Preview locally:

```bash
python tools/build.py --out _site            # set GITHUB_TOKEN to avoid API rate limits; --offline for no network
python -m http.server 8000 --directory _site
python -m unittest discover -s tools
```

The server list is a separate site: [servers.haulnet.cc](https://servers.haulnet.cc/)
([haulnet-servers](https://github.com/haulnet/haulnet-servers)).

Haulnet is an independent fan project. It is not affiliated with or endorsed by semiwork (developers of
R.E.P.O.) or Exit Games GmbH. "R.E.P.O." and "Photon" are trademarks of their respective owners and are used
only to describe compatibility.

## License

[MIT](LICENSE).
