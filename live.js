// Live numbers of the Haulnet network from our own server monitor (ADR 0023). The page is complete without
// this script; it only fills in the four numbers. No cookies, no storage, nothing from other sites.
(() => {
  "use strict";
  const box = document.getElementById("live");
  if (!box || !window.fetch) return;
  const stat = (name) => box.querySelector(`[data-stat="${name}"]`);
  let cities = {};
  try { cities = JSON.parse(box.dataset.cities || "{}"); } catch (e) { cities = {}; }
  const list = '<a href="https://servers.haulnet.cc/">servers.haulnet.cc</a>';

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

  const load = () => fetch(box.dataset.statusUrl, { cache: "no-store" })
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
    .then((doc) => {
      if (doc.schema_version !== 1 || !Array.isArray(doc.servers)) throw new Error("unknown format");
      show(doc);
    })
    .catch(fail);

  load();
  setInterval(() => { if (!document.hidden) load(); }, 60000);
})();
