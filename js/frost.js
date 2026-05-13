// frost.js — Frost tracker card

function renderFrostTracker(frost) {
  const el = document.getElementById("frostTracker");
  if (!el || !frost) return;
  const light = isLight();
  const textFaint  = light ? "rgba(0,0,0,0.40)" : "rgba(255,255,255,0.4)";
  const textMid    = light ? "rgba(0,0,0,0.55)" : "rgba(255,255,255,0.5)";
  const textSub    = light ? "rgba(0,0,0,0.38)" : "rgba(255,255,255,0.35)";
  const textHead   = light ? "rgba(0,0,0,0.65)" : "rgba(255,255,255,0.55)";
  const tile1bg    = light ? "rgba(30,120,255,0.06)"  : "rgba(100,180,255,0.08)";
  const tile1bd    = light ? "rgba(30,120,255,0.20)"  : "rgba(100,180,255,0.18)";
  const tile1num   = light ? "rgba(20,80,200,0.90)"   : "rgba(180,220,255,0.9)";
  const tile2bg    = light ? "rgba(30,80,220,0.06)"   : "rgba(60,120,255,0.08)";
  const tile2bd    = light ? "rgba(30,80,220,0.20)"   : "rgba(60,120,255,0.18)";
  const tile2num   = light ? "rgba(20,60,200,0.90)"   : "rgba(140,180,255,0.9)";
  const tile3bg    = light ? "rgba(10,30,160,0.06)"   : "rgba(20,60,180,0.08)";
  const tile3bd    = light ? "rgba(10,30,160,0.22)"   : "rgba(20,60,180,0.25)";
  const tile3num   = light ? "rgba(10,40,180,0.90)"   : "rgba(100,140,255,0.9)";
  const upcomingColor = light ? "rgba(20,70,200,0.85)" : "rgba(180,210,255,0.8)";

  // Check if we have any meaningful frost data this season
  const hasFrostData = frost.season_start && (
    (frost.freeze_days ?? 0) > 0 ||
    (frost.hard_freeze_days ?? 0) > 0 ||
    (frost.severe_days ?? 0) > 0
  );

  if (!frost.season_start) {
    el.innerHTML = `<div style="color:${textFaint};font-size:0.85rem;">No frost data yet — will populate after first overnight run.</div>`;
    return;
  }

  if (!hasFrostData) {
    const upcoming = frost.upcoming_freeze_days || [];
    const upcomingHtml = upcoming.length === 0
      ? `<span style="color:${textFaint};">None in 10-day forecast</span>`
      : upcoming.map(u => {
          const label = u.min_f <= 20 ? "Hard freeze" : u.min_f <= 28 ? "Frost" : "Cool night";
          const d = new Date(u.date).toLocaleDateString("en-US", { weekday:"short", month:"short", day:"numeric" });
          return `<span style="margin-right:12px;">${label} ${d} (${u.min_f}°F)</span>`;
        }).join("");
    el.innerHTML = `
      <div style="text-align:center;padding:12px 0 8px;">
        <div style="font-size:1.8rem;margin-bottom:6px;">❄️</div>
        <div style="font-size:0.92rem;font-weight:600;color:${textFaint};margin-bottom:4px;">No frost events this season</div>
        <div style="font-size:0.78rem;color:${textFaint};margin-bottom:14px;">Season started ${new Date(frost.season_start).toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric"})}</div>
      </div>
      <div style="font-size:0.82rem;font-weight:800;color:${textHead};margin-bottom:6px;">Upcoming freeze nights (10-day):</div>
      <div style="font-size:0.82rem;color:${upcomingColor};line-height:1.8;">${upcomingHtml}</div>
    `;
    return;
  }

  const [sy, sm, sd] = frost.season_start.split("-").map(Number);
  const seasonStart = new Date(sy, sm-1, sd).toLocaleDateString("en-US", { month:"short", day:"numeric", year:"numeric" });
  const fmt = d => d ? new Date(d).toLocaleDateString("en-US", { month:"short", day:"numeric" }) : "None this season";

  const upcoming = frost.upcoming_freeze_days || [];
  const upcomingHtml = upcoming.length === 0
    ? `<span style="color:${textFaint};">None in 10-day forecast</span>`
    : upcoming.map(u => {
        const label = u.min_f <= 20 ? "Hard freeze" : u.min_f <= 28 ? "Frost" : "Cool";
        const d = new Date(u.date).toLocaleDateString("en-US", { weekday:"short", month:"short", day:"numeric" });
        return `<span style="margin-right:12px;">${label} ${d} (${u.min_f}°F)</span>`;
      }).join("");

  el.innerHTML = `
    <div style="font-size:0.78rem;color:${textFaint};margin-bottom:10px;">Season from ${seasonStart}</div>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px;" class="mobile-3col">
      <div style="background:${tile1bg};border:1px solid ${tile1bd};border-radius:10px;padding:10px;text-align:center;">
        <div style="font-size:1.8rem;font-weight:900;color:${tile1num};">${frost.freeze_days ?? 0}</div>
        <div style="font-size:0.78rem;color:${textMid};margin-top:2px;">Freeze days</div>
        <div style="font-size:0.72rem;color:${textSub};margin-top:3px;">min ≤ 32°F</div>
        <div style="font-size:0.72rem;color:${textFaint};margin-top:4px;">Last: ${fmt(frost.last_freeze)}</div>
      </div>
      <div style="background:${tile2bg};border:1px solid ${tile2bd};border-radius:10px;padding:10px;text-align:center;">
        <div style="font-size:1.8rem;font-weight:900;color:${tile2num};">${frost.hard_freeze_days ?? 0}</div>
        <div style="font-size:0.78rem;color:${textMid};margin-top:2px;">Hard freeze days</div>
        <div style="font-size:0.72rem;color:${textSub};margin-top:3px;">min ≤ 28°F</div>
        <div style="font-size:0.72rem;color:${textFaint};margin-top:4px;">Last: ${fmt(frost.last_hard)}</div>
      </div>
      <div style="background:${tile3bg};border:1px solid ${tile3bd};border-radius:10px;padding:10px;text-align:center;">
        <div style="font-size:1.8rem;font-weight:900;color:${tile3num};">${frost.severe_days ?? 0}</div>
        <div style="font-size:0.78rem;color:${textMid};margin-top:2px;">Severe freeze days</div>
        <div style="font-size:0.72rem;color:${textSub};margin-top:3px;">min ≤ 20°F</div>
        <div style="font-size:0.72rem;color:${textFaint};margin-top:4px;">Last: ${fmt(frost.last_severe)}</div>
      </div>
    </div>
    <div style="font-size:0.82rem;font-weight:800;color:${textHead};margin-bottom:6px;">Upcoming freeze nights (10-day forecast):</div>
    <div style="font-size:0.82rem;color:${upcomingColor};line-height:1.8;">${upcomingHtml}</div>
  `;
}
