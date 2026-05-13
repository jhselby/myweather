// birds.js — eBird sightings card rendering

function escapeHtml(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function renderBirds(birds) {
  const primaryEl   = document.getElementById("birdsPrimaryCollapsed");
  const secondaryEl = document.getElementById("birdsSecondaryCollapsed");
  const contentEl   = document.getElementById("birdsContent");
  if (!primaryEl || !contentEl) return;

  if (!birds || !Array.isArray(birds.species) || birds.species.length === 0) {
    primaryEl.textContent = "No recent sightings";
    secondaryEl.textContent = "";
    const days = birds?.back_days ?? 2;
    const km   = birds?.radius_km ?? 5;
    contentEl.innerHTML = `<div style="padding:20px;text-align:center;color:var(--text-secondary);font-size:0.9rem;">No eBird sightings in the last ${days} day${days === 1 ? "" : "s"} within ${km} km.</div>`;
    return;
  }

  const species       = birds.species;
  const speciesCount  = birds.species_count ?? species.length;
  const notables      = species.filter(s => s.notable);
  const totalBirds    = species.reduce((sum, s) => sum + (s.count || 0), 0);

  // --- Collapsed tile ---
  if (notables.length > 0) {
    const topNotable = [...notables].sort((a, b) =>
      (b.last_seen || "").localeCompare(a.last_seen || "")
    )[0];
    primaryEl.textContent = topNotable.name;
    const extra = notables.length - 1;
    secondaryEl.textContent = extra > 0
      ? `+ ${extra} other notable${extra === 1 ? "" : "s"}`
      : "Notable sighting";
  } else {
    primaryEl.textContent = `${speciesCount} species`;
    secondaryEl.textContent = `${totalBirds} bird${totalBirds === 1 ? "" : "s"} · ${birds.radius_km ?? 5} km`;
  }

  // --- Expanded view: theme-aware colors ---
  const light     = isLight();
  const textFaint = light ? "rgba(0,0,0,0.40)"      : "rgba(255,255,255,0.4)";
  const textSub   = light ? "rgba(0,0,0,0.55)"      : "rgba(255,255,255,0.55)";
  const textHead  = light ? "rgba(0,0,0,0.75)"      : "rgba(255,255,255,0.85)";
  const border    = light ? "rgba(0,0,0,0.08)"      : "rgba(255,255,255,0.08)";
  const rowBg     = light ? "rgba(0,0,0,0.02)"      : "rgba(255,255,255,0.03)";
  const notableBg = light ? "rgba(255,140,60,0.15)" : "rgba(255,180,90,0.18)";
  const notableFg = light ? "rgba(200,90,10,0.95)"  : "rgba(255,200,120,0.95)";
  const linkCol   = light ? "rgba(20,80,200,0.9)"   : "rgba(120,190,255,0.9)";

  // Group species by location, then aggregate duplicate species within each location
  const byLocation = new Map();
  species.forEach(s => {
    const key = s.location || "Unknown location";
    if (!byLocation.has(key)) {
      byLocation.set(key, {
        name: key,
        loc_id: s.loc_id,
        loc_private: s.loc_private,
        lat: s.lat,
        lng: s.lng,
        distance_km: s.distance_km,
        last_seen: s.last_seen,
        species: []
      });
    }
    const loc = byLocation.get(key);
    loc.species.push(s);
    if ((s.last_seen || "") > (loc.last_seen || "")) loc.last_seen = s.last_seen;
  });

  const locations = [...byLocation.values()].map(loc => {
    const speciesMap = new Map();

    loc.species.forEach(s => {
      const speciesKey = s.code || s.name || "unknown-species";
      if (!speciesMap.has(speciesKey)) {
        speciesMap.set(speciesKey, { ...s });
        return;
      }
      const existing = speciesMap.get(speciesKey);
      if (existing.count != null || s.count != null) {
        existing.count = (existing.count || 0) + (s.count || 0);
      }
      existing.notable = !!(existing.notable || s.notable);
      if ((s.last_seen || "") > (existing.last_seen || "")) {
        existing.last_seen = s.last_seen;
      }
      speciesMap.set(speciesKey, existing);
    });

    loc.species = [...speciesMap.values()];
    loc.species.sort((a, b) => {
      if (a.notable !== b.notable) return a.notable ? -1 : 1;
      const countDiff = (b.count || 0) - (a.count || 0);
      if (countDiff !== 0) return countDiff;
      return (a.name || "").localeCompare(b.name || "");
    });

    loc.hasNotable = loc.species.some(s => s.notable);
    return loc;
  });

  locations.sort((a, b) => {
    if (a.hasNotable !== b.hasNotable) return a.hasNotable ? -1 : 1;
    return (a.distance_km ?? 99) - (b.distance_km ?? 99);
  });

  // Format "2026-04-23 18:49" -> "Apr 23, 6:49 PM"
  const fmtBirdTime = (ts) => {
    if (!ts) return "";
    const [datePart, timePart] = ts.split(" ");
    if (!datePart || !timePart) return ts;
    const [y, mo, d] = datePart.split("-").map(Number);
    const [h, mi]    = timePart.split(":").map(Number);
    const dt = new Date(y, mo - 1, d, h, mi);
    return dt.toLocaleDateString("en-US", { month: "short", day: "numeric" }) +
           ", " +
           dt.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  };

  const fetchedAt = birds.fetched_at
    ? new Date(birds.fetched_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
    : null;

  const notableBadge = notables.length > 0
    ? `<span style="background:${notableBg};color:${notableFg};padding:2px 8px;border-radius:999px;font-size:0.72rem;font-weight:700;margin-left:8px;">${notables.length} notable</span>`
    : "";

  let html = `
    <div style="padding:12px 0 14px;border-bottom:1px solid ${border};margin-bottom:12px;">
      <div style="font-size:1.1rem;font-weight:700;color:${textHead};">
        ${speciesCount} species · ${totalBirds} bird${totalBirds === 1 ? "" : "s"}${notableBadge}
      </div>
      <div style="font-size:0.78rem;color:${textFaint};margin-top:4px;">
        eBird · ${Math.round((birds.radius_km ?? 5) * 0.621371)} miles radius · last ${birds.back_days ?? 2} day${(birds.back_days ?? 2) === 1 ? "" : "s"}${fetchedAt ? ` · updated ${fetchedAt}` : ""}
      </div>
    </div>
  `;

  locations.forEach((loc, idx) => {
    const groupId = `birdLoc_${idx}`;
    const locNotables = loc.species.filter(s => s.notable).length;
    const locSpeciesCount = loc.species.length;
    const locBirdCount = loc.species.reduce((sum, s) => sum + (s.count || 0), 0);
    const distStr = loc.distance_km != null
      ? `${(loc.distance_km * 0.621371).toFixed(1)} mi`
      : "";

    html += `
      <div style="border:1px solid ${border};border-radius:10px;margin-bottom:8px;overflow:hidden;background:${rowBg};">
        <div onclick="document.getElementById('${groupId}').style.display = document.getElementById('${groupId}').style.display === 'none' ? 'block' : 'none'; this.querySelector('.bird-chev').textContent = document.getElementById('${groupId}').style.display === 'none' ? '▾' : '▴';"
             style="padding:10px 12px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:8px;">
          <div style="min-width:0;flex:1;">
            <div style="font-weight:700;font-size:0.9rem;color:${textHead};overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
              ${loc.loc_id && !loc.loc_private ? `<a href="https://ebird.org/hotspots?hs=${loc.loc_id}" target="_blank" rel="noopener" onclick="event.stopPropagation(); event.preventDefault(); window.__externalLinkOpen = true; window.open('https://ebird.org/hotspots?hs=${loc.loc_id}', '_blank');" style="color:${textHead};text-decoration:none;border-bottom:1px dotted ${textFaint};">${escapeHtml(loc.name)}</a>` : loc.loc_private && loc.lat && loc.lng ? `<a href="https://www.openstreetmap.org/?mlat=${loc.lat}&mlon=${loc.lng}#map=15/${loc.lat}/${loc.lng}" target="_blank" rel="noopener" onclick="event.stopPropagation(); event.preventDefault(); window.__externalLinkOpen = true; window.location.href = 'https://www.openstreetmap.org/?mlat=${loc.lat}&mlon=${loc.lng}#map=15/${loc.lat}/${loc.lng}';" style="color:${textHead};text-decoration:none;border-bottom:1px dotted ${textFaint};">${escapeHtml(loc.name)}</a>` : escapeHtml(loc.name)}
            </div>
            ${locNotables > 0 ? `<div style="margin-top:2px;"><span style="background:${notableBg};color:${notableFg};padding:1px 6px;border-radius:999px;font-size:0.7rem;font-weight:700;">${locNotables} notable★</span></div>` : ""}
            <div style="font-size:0.75rem;color:${textFaint};margin-top:2px;">
              ${distStr} · ${locSpeciesCount} species · ${locBirdCount} bird${locBirdCount === 1 ? "" : "s"} · ${fmtBirdTime(loc.last_seen)}
            </div>
          </div>
          <span class="bird-chev" style="color:${textFaint};font-size:0.9rem;flex-shrink:0;">▾</span>
        </div>
        <div id="${groupId}" style="display:none;padding:0 12px 10px;border-top:1px solid ${border};">
          ${loc.species.map(s => {
            const ebirdUrl = `https://ebird.org/species/${s.code}`;
            const isNotable = s.notable;
            const nameStyle = isNotable
              ? `background:${notableBg};color:${notableFg};padding:1px 6px;border-radius:4px;font-weight:700;`
              : "";
            return `
              <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid ${border};font-size:0.85rem;">
                <a href="${ebirdUrl}" target="_blank" rel="noopener" onclick="event.stopPropagation(); event.preventDefault(); window.__externalLinkOpen = true; window.open('${ebirdUrl}', '_blank');" style="color:${linkCol};text-decoration:none;flex:1;min-width:0;">
                  <span style="${nameStyle}">${escapeHtml(s.name)}</span>
                </a>
                <span style="color:${textSub};margin-left:10px;font-variant-numeric:tabular-nums;flex-shrink:0;">
                  ${s.count > 1 ? `×${s.count}` : "·"}
                </span>
              </div>
            `;
          }).join("")}
        </div>
      </div>
    `;
  });

  contentEl.innerHTML = html;
}
