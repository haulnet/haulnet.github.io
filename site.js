// Live numbers of the Haulnet network (ADR 0023). The page is complete without this script; it only fills in the
// four numbers. It reads the server list itself, so a server or city added to the list shows up here without a new
// build of this site; the copy baked in at build time is only the fallback. No cookies, no storage, nothing from
// other sites.
(() => {
  "use strict";
  const box = document.getElementById("live");
  if (!box || !window.fetch) return;
  const stat = (name) => box.querySelector(`[data-stat="${name}"]`);
  const list = '<a href="https://servers.haulnet.cc/">servers.haulnet.cc</a>';
  // The list is served with max-age=600; reading it more often only returns the cached copy.
  const LIST_MS = 600000;

  // Server id → city name. Starts with the copy from the build, replaced by the live list once it loads.
  let cities = {};
  try { cities = JSON.parse(box.dataset.cities || "{}"); } catch (e) { cities = {}; }
  let statusUrl = box.dataset.statusUrl;
  let listAt = 0;

  // A number that changed since the last round gets a short highlight (CSS, only without reduced motion).
  const put = (name, text) => {
    const el = stat(name);
    if (el.textContent === text) return;
    const had = el.textContent !== "—";
    el.textContent = text;
    if (had) { el.classList.remove("changed"); void el.offsetWidth; el.classList.add("changed"); }
  };
  const live = (on) => { const dot = stat("dot"); if (dot) dot.classList.toggle("idle", !on); };

  const getJson = (url, options) => fetch(url, options)
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))));

  const useList = (doc) => {
    if (doc.schema_version !== 1 || !Array.isArray(doc.servers)) throw new Error("unknown list format");
    const names = {};
    for (const c of Array.isArray(doc.cities) ? doc.cities : []) {
      if (c && typeof c.id === "string") names[c.id] = typeof c.name === "string" ? c.name : c.id;
    }
    const map = {};
    for (const s of doc.servers) {
      if (s && typeof s.id === "string" && typeof s.city === "string") map[s.id] = names[s.city] || s.city;
    }
    cities = map;
    // The list names the monitor (status_url), as the mod reads it; the address in the page is the fallback.
    if (typeof doc.status_url === "string" && doc.status_url.startsWith("https://")) statusUrl = doc.status_url;
    listAt = Date.now();
  };

  // A failed list keeps the last good one (or the build's copy) and is tried again on the next round.
  const refreshList = () => (!box.dataset.listUrl || Date.now() - listAt < LIST_MS)
    ? Promise.resolve()
    : getJson(box.dataset.listUrl).then(useList).catch(() => {});

  const every = (s) => (!s || s === 60 ? "every minute" : s < 60 ? `every ${s} s` : `every ${Math.round(s / 60)} min`);

  const show = (doc) => {
    const online = doc.servers.filter((s) => s.state === "online");
    const where = new Set(online.map((s) => cities[s.id]).filter(Boolean));
    let players = 0, games = 0;
    for (const s of online) {
      if (s.status) { players += s.status.players; games += s.status.rooms; }
    }
    put("servers", `${online.length}/${doc.servers.length}`);
    put("cities", String(where.size));
    put("players", String(players));
    put("games", String(games));
    live(true);
    const age = Math.max(0, Math.round((Date.now() - Date.parse(doc.generated_at)) / 60000));
    stat("note").innerHTML =
      `On Haulnet servers (official and community), checked ${every(doc.monitor.interval_s)}${doc.monitor.location ? " from " + doc.monitor.location.replace(/[<>&]/g, "") : ""}` +
      ` (last check ${age < 1 ? "under a minute" : age + " min"} ago). Games hosted on players' own PCs are not counted. ` +
      `Full list: ${list}.`;
  };

  const fail = () => {
    for (const name of ["servers", "cities", "players", "games"]) stat(name).textContent = "—";
    stat("note").innerHTML = `Live numbers are unavailable right now. Full list: ${list}.`;
    live(false);
  };

  const load = () => refreshList()
    .then(() => getJson(statusUrl, { cache: "no-store" }))
    .then((doc) => {
      if (doc.schema_version !== 1 || !Array.isArray(doc.servers)) throw new Error("unknown format");
      show(doc);
    })
    .catch(fail);

  load();
  setInterval(() => { if (!document.hidden) load(); }, 60000);
})();

// Keep the controls outside the <pre> so they stay visible when a long line scrolls.
(() => {
  "use strict";

  for (const code of document.querySelectorAll(".doc pre > code:only-child")) {
    const pre = code.parentElement;
    const block = document.createElement("div");
    block.className = "code-block";

    const toolbar = document.createElement("div");
    toolbar.className = "code-toolbar";
    const status = document.createElement("span");
    status.className = "code-copy-status";
    status.setAttribute("role", "status");

    const button = document.createElement("button");
    button.className = "code-copy";
    button.type = "button";
    button.setAttribute("aria-label", "Copy code");
    button.textContent = "Copy";

    let resetStatus;
    button.addEventListener("click", async () => {
      clearTimeout(resetStatus);
      status.textContent = "";
      try {
        await navigator.clipboard.writeText(code.textContent);
      } catch {
        status.textContent = "Select the code to copy it manually.";
        return;
      }
      status.textContent = "Copied to clipboard";
      resetStatus = setTimeout(() => { status.textContent = ""; }, 2500);
    });

    toolbar.append(status, button);
    pre.before(block);
    block.append(toolbar, pre);
  }
})();
