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

  const show = (doc) => {
    const online = doc.servers.filter((s) => s.state === "online");
    const where = new Set(online.map((s) => cities[s.id]).filter(Boolean));
    let players = 0, games = 0;
    for (const s of online) {
      if (s.status) { players += s.status.players; games += s.status.rooms; }
    }
    stat("servers").textContent = `${online.length}/${doc.servers.length}`;
    stat("cities").textContent = String(where.size);
    stat("players").textContent = String(players);
    stat("games").textContent = String(games);
    const age = Math.max(0, Math.round((Date.now() - Date.parse(doc.generated_at)) / 60000));
    stat("note").innerHTML =
      `On community and official servers, checked every minute${doc.monitor.location ? " from " + doc.monitor.location.replace(/[<>&]/g, "") : ""}` +
      ` (last check ${age < 1 ? "under a minute" : age + " min"} ago). Games hosted on players' own PCs are not counted. ` +
      `Full list: ${list}.`;
  };

  const fail = () => {
    for (const name of ["servers", "cities", "players", "games"]) stat(name).textContent = "—";
    stat("note").innerHTML = `Live numbers are unavailable right now. Full list: ${list}.`;
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
