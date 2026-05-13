// dock.js — Swim float / dock day forecast card

// ======================================================
// Beach Day Score
// Dock floats when tide > DOCK_FLOAT_THRESHOLD_FT (above MLLW).
// DOCK_TIDE_OFFSET_FT: correction to apply to predicted heights once
//   empirical observed-vs-predicted data is collected. Default 0.0.
// Dock faces 315° (NW) — open water fetch in that direction.
//   NW winds = directly onshore at dock = choppy.
//   SE winds = offshore from dock = calm.
// ======================================================
const DOCK_FLOAT_THRESHOLD_FT = 1.5;   // ft above MLLW — dock just floats
const DOCK_TIDE_OFFSET_FT     = 0.0;   // empirical correction — update when data available
const DOCK_FACE_DEG           = 315;   // dock faces NW (summer solstice sunset bearing)
const DOCK_USABLE_HOUR_START  =  7;    // before this hour = not usable
const DOCK_USABLE_HOUR_END    = 20;    // after this hour = not usable

function renderDockDay(data) {
  const el = document.getElementById("swimFloatContent");
  if (!el) return;

  const curve   = (data.tide_curve || {});
  const ctimes  = curve.times   || [];
  const cheights= curve.heights || [];
  const hourly  = data.hourly   || {};
  const htimes  = hourly.times  || [];
  const htemps  = hourly.corrected_temperature || hourly.temperature || [];
  const hwind   = hourly.wind_speed  || [];
  const hwinddir= hourly.wind_direction || [];
  const hprecip = hourly.precipitation_probability || [];
  const buoy    = data.buoy     || {};
  const waterTempRaw = data.salem_water_temp_f ?? buoy.water_temp_f;

  if (!ctimes.length) {
    el.innerHTML = `<div style="color:rgba(255,255,255,0.4);font-size:0.85rem;">Tide curve data unavailable</div>`;
    return;
  }

  // Apply tide offset to all heights
  const correctedHeights = cheights.map(h => h + DOCK_TIDE_OFFSET_FT);

  // Helper: nearest hourly value to a given timestamp
  function nearestHourly(arr, targetMs) {
    let best = null, bestDiff = Infinity;
    for (let i = 0; i < htimes.length; i++) {
      const diff = Math.abs(new Date(htimes[i]).getTime() - targetMs);
      if (diff < bestDiff) { bestDiff = diff; best = arr[i]; }
    }
    return best;
  }

  // Build accessible windows for today and tomorrow
  const now   = new Date();
  const days  = [0, 1].map(d => {
    const date = new Date(now);
    date.setDate(date.getDate() + d);
    return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
  });

  const dayCards = [];

  for (const dayStr of days) {
    // Find all 6-min curve points for this day
    const dayPoints = [];
    for (let i = 0; i < ctimes.length; i++) {
      const cd = new Date(ctimes[i]); const cds = `${cd.getFullYear()}-${String(cd.getMonth()+1).padStart(2,"0")}-${String(cd.getDate()).padStart(2,"0")}`; if (cds === dayStr) {
        dayPoints.push({ t: ctimes[i], h: correctedHeights[i] });
      }
    }
    if (!dayPoints.length) continue;

    // Find contiguous accessible windows where h > threshold
    const windows = [];
    let winStart = null;
    for (let i = 0; i < dayPoints.length; i++) {
      const accessible = dayPoints[i].h > DOCK_FLOAT_THRESHOLD_FT;
      if (accessible && winStart === null) winStart = i;
      if (!accessible && winStart !== null) {
        windows.push({ start: winStart, end: i - 1 });
        winStart = null;
      }
    }
    if (winStart !== null) windows.push({ start: winStart, end: dayPoints.length - 1 });

    // Filter to usable hours
    const usableWindows = windows.map(w => {
      // Trim to usable hours
      let s = w.start, e = w.end;
      while (s <= e) {
        const hr = new Date(dayPoints[s].t).getHours();
        if (hr >= DOCK_USABLE_HOUR_START) break;
        s++;
      }
      while (e >= s) {
        const hr = new Date(dayPoints[e].t).getHours();
        if (hr < DOCK_USABLE_HOUR_END) break;
        e--;
      }
      if (s > e) return null;
      const startMs = new Date(dayPoints[s].t).getTime();
      const endMs   = new Date(dayPoints[e].t).getTime();
      const durMin  = Math.round((endMs - startMs) / 60000);
      const midMs   = (startMs + endMs) / 2;

      // Weather at midpoint of window
      const temp    = nearestHourly(htemps,   midMs);
      const wspd    = nearestHourly(hwind,    midMs);
      const wdir    = nearestHourly(hwinddir, midMs);
      const precip  = nearestHourly(hprecip,  midMs);

      // Peak height during window
      const peakH = Math.max(...dayPoints.slice(s, e+1).map(p => p.h));

      // Wind impact score (same exposure model as wind card)
      const wgust   = nearestHourly(hourly.wind_gusts || [], midMs);
      const impactRaw = combinedWindImpact(wspd, wgust, wdir);
      // Normalize to 0-1 scale: 0 impact = 1.0 score (perfect), WORRY_SEVERE+ = 0.0
      const windSc = Math.max(0, 1 - impactRaw / WORRY_SEVERE);

      // Temp score: 75°F=1.0, 60°F=0.5, 50°F=0.1, below 45°F=0
      // Hard reality: below 50°F is not a beach day regardless of other factors
      const tempSc = temp == null ? 0.5 :
        temp < 50 ? 0.0 :
        temp < 65 ? (temp - 50) / 30 :
        Math.min(1, (temp - 65) / 30 + 0.5);

      // Precip score
      const precipSc = precip == null ? 0.5 :
        Math.max(0, 1 - precip / 60);

      // Duration score: 3h+ = 1.0, 1h = 0.33
      const durSc = Math.min(1, durMin / 180);

      // Water temp score (from buoy) — bonus factor
      const wtSc = waterTempRaw == null ? 0.5 :
        waterTempRaw < 50 ? 0.2 :
        waterTempRaw < 65 ? (waterTempRaw - 50) / 25 + 0.2 :
        1.0;

      // Overall score — temp and wind are gatekeepers
      // If temp < 45 or wind > 20kt, score can't exceed 0.3
      const rawScore = windSc * 0.35 + tempSc * 0.35 + precipSc * 0.15 + durSc * 0.10 + wtSc * 0.05;
      const score = (temp != null && temp < 45) || (wspd != null && wspd > 20)
        ? Math.min(rawScore, 0.3)
        : rawScore;

      // Wind direction label relative to dock
      let windRelLabel = "";
      if (wdir != null) {
        let diff = Math.abs(wdir - DOCK_FACE_DEG);
        if (diff > 180) diff = 360 - diff;
        if (diff < 45)       windRelLabel = "onshore";
        else if (diff > 135) windRelLabel = "offshore";
        else                 windRelLabel = "crosswind";
      }

      const dirName = wdir != null ? toCompass(wdir, false) : "--";

      return {
        startTime: new Date(dayPoints[s].t),
        endTime:   new Date(dayPoints[e].t),
        durMin, peakH, temp, wspd, wdir, dirName, precip,
        windRelLabel, score, windSc, tempSc, precipSc
      };
    }).filter(Boolean);

    // Day label
    const dateObj = new Date(dayStr + "T12:00:00");
    const isToday = dayStr === days[0];
    const dayLabel = isToday ? "Today" : "Tomorrow";
    const dateLabel = dateObj.toLocaleDateString("en-US", { weekday:"short", month:"short", day:"numeric" });

    // Best window score for the day
    const bestScore = usableWindows.length
      ? Math.max(...usableWindows.map(w => w.score))
      : 0;

    dayCards.push({ dayLabel, dateLabel, usableWindows, bestScore, dayStr });
  }

  if (!dayCards.length) {
    el.innerHTML = `<div style="color:${isLight() ? 'rgba(0,0,0,0.4)' : 'rgba(255,255,255,0.4)'};font-size:0.85rem;">No tide data available</div>`;
    return;
  }

  const light = isLight();
  const dTileBg    = light ? "rgba(255,255,255,0.55)" : "rgba(255,255,255,0.03)";
  const dTileBd    = light ? "rgba(0,0,0,0.08)"   : "rgba(255,255,255,0.08)";
  const dDayLbl    = light ? "rgba(0,0,0,0.75)"   : "rgba(255,255,255,0.45)";
  const dDateLbl   = light ? "rgba(0,0,0,0.50)"   : "rgba(255,255,255,0.3)";
  const dDryTxt    = light ? "rgba(0,0,0,0.45)"   : "rgba(255,255,255,0.3)";
  const dWinBg     = light ? "rgba(0,0,0,0.03)"   : "rgba(255,255,255,0.04)";
  const dTimeTxt   = light ? "rgba(0,0,0,0.85)"   : "rgba(255,255,255,0.85)";
  const dDurTxt    = light ? "rgba(0,0,0,0.50)"   : "rgba(255,255,255,0.35)";
  const dPeakTxt   = light ? "rgba(0,0,0,0.45)"   : "rgba(255,255,255,0.3)";
  const dBarBg     = light ? "rgba(0,0,0,0.10)"   : "rgba(255,255,255,0.1)";
  const dDetailTxt = light ? "rgba(0,0,0,0.60)"   : "rgba(255,255,255,0.5)";
  const dFooter    = light ? "rgba(0,0,0,0.45)"   : "rgba(255,255,255,0.22)";

  // Render
  function scoreLabel(s) {
    if (light) {
      if (s >= 0.75) return { label:"Great day",  color:"rgba(20,140,50,0.95)" };
      if (s >= 0.58) return { label:"Good day",   color:"rgba(70,140,20,0.95)" };
      if (s >= 0.38) return { label:"Marginal",   color:"rgba(180,120,0,0.95)" };
      if (s >= 0.20) return { label:"Poor",       color:"rgba(180,60,30,0.9)" };
      return            { label:"Stay inside", color:"rgba(150,40,40,0.9)" };
    }
    if (s >= 0.75) return { label:"Great day",  color:"rgba(80,220,120,0.95)" };
    if (s >= 0.58) return { label:"Good day",   color:"rgba(160,220,80,0.9)" };
    if (s >= 0.38) return { label:"Marginal",   color:"rgba(255,190,50,0.85)" };
    if (s >= 0.20) return { label:"Poor",       color:"rgba(200,100,60,0.85)" };
    return            { label:"Stay inside", color:"rgba(150,50,50,0.9)" };
  }

  function fmtTime(d) {
    return d.toLocaleTimeString("en-US", { hour:"numeric", minute:"2-digit" });
  }

  // Build headline from today's beach day data
  let dockHeadline = "";
  if (dayCards.length > 0) {
    const td = dayCards[0];
    const sl = scoreLabel(td.bestScore);
    if (td.usableWindows && td.usableWindows.length > 0) {
      // Find best window (longest duration)
      const bestW = td.usableWindows.reduce((a, b) => (b.endTime - b.startTime) > (a.endTime - a.startTime) ? b : a);
      const startFmt = fmtTime(bestW.startTime);
      const endFmt   = fmtTime(bestW.endTime);
      const hrs = Math.round((bestW.endTime - bestW.startTime) / 3600000);
      const isPast = bestW.endTime < now;
      const verb = isPast ? "was wet" : "wet";
      dockHeadline = `${sl.label} — swim float ${verb} ${startFmt}–${endFmt} (${hrs}h)`;
    } else {
      dockHeadline = `Swim float dry all day — tide too low`;
    }
  }

  let html = dockHeadline
    ? `<div style="font-size:0.95rem;font-weight:600;color:${dayCards.length > 0 ? scoreLabel(dayCards[0].bestScore).color : 'rgba(255,255,255,0.7)'};margin-bottom:14px;padding:10px 14px;background:rgba(255,255,255,0.04);border-radius:0;border-left:4px solid ${dayCards.length > 0 ? scoreLabel(dayCards[0].bestScore).color : 'rgba(255,255,255,0.2)'};">${dockHeadline}</div>`
    : "";
  html += `<div class="dock-day-grid" style="display:grid;grid-template-columns:repeat(${dayCards.length},minmax(130px,1fr));gap:12px;">`;

  for (const day of dayCards) {
    const sl = scoreLabel(day.bestScore);
    
    // Store today's and tomorrow's score for Right Now card
    if (day.dayLabel === "Today") {
      window.__todayDockScore = {score: day.bestScore, label: sl.label, color: sl.color};
    }
    if (day.dayLabel === "Tomorrow") {
      window.__tomorrowDockScore = {score: day.bestScore, label: sl.label, color: sl.color};
    }
    
    html += `<div style="background:${dTileBg};border:1px solid ${dTileBd};border-radius:10px;padding:14px 12px;">`;
    html += `<div style="font-size:0.78rem;font-weight:800;color:${dDayLbl};margin-bottom:2px;">${day.dayLabel}</div>`;
    html += `<div style="font-size:0.72rem;color:${dDateLbl};margin-bottom:8px;">${day.dateLabel}</div>`;

    if (!day.usableWindows.length) {
      html += ``;
      html += `<div style="font-size:0.82rem;font-weight:900;color:rgba(180,80,80,0.8);">Float dry all day</div>`;
      html += `<div style="font-size:0.72rem;color:${dDryTxt};margin-top:6px;">Low tide falls within usable hours</div>`;
    } else {
      html += ``;
      html += `<div style="font-size:0.88rem;font-weight:900;color:${sl.color};margin-bottom:10px;">${sl.label} <span style="font-size:0.75rem;opacity:0.7;">(${Math.round(day.bestScore * 100)})</span></div>`;

      for (const w of day.usableWindows) {
        const durH = Math.floor(w.durMin / 60);
        const durM = w.durMin % 60;
        const durStr = durH > 0 ? `${durH}h ${durM}m` : `${durM}m`;
        const barW = Math.round(w.score * 100);

        html += `<div style="background:${dWinBg};border-radius:7px;padding:8px 10px;margin-bottom:8px;">`;
        html += `<div style="font-size:0.82rem;font-weight:900;color:${dTimeTxt};margin-bottom:2px;">`;
        html += `${fmtTime(w.startTime)} – ${fmtTime(w.endTime)}`;
        html += `<span style="font-size:0.7rem;font-weight:700;color:${dDurTxt};margin-left:6px;">${durStr}</span></div>`;
        html += `<div style="font-size:0.7rem;color:${dPeakTxt};margin-bottom:6px;">`;
        html += `Peak ${w.peakH.toFixed(1)} ft`;
        if (DOCK_TIDE_OFFSET_FT !== 0) html += ` <span style="color:rgba(255,200,80,0.6);">(corrected +${DOCK_TIDE_OFFSET_FT} ft)</span>`;
        html += `</div>`;
        html += `<div style="height:3px;background:${dBarBg};border-radius:2px;overflow:hidden;margin-bottom:8px;">`;
        html += `<div style="height:100%;width:${barW}%;background:${scoreLabel(w.score).color};border-radius:2px;"></div></div>`;
        html += `<div style="display:grid;grid-template-columns:1fr 1fr;gap:2px;font-size:0.7rem;color:${dDetailTxt};">`;
        html += `<div>${w.temp != null ? Math.round(w.temp)+"°F" : "--"}</div>`;
        html += `<div>💧 ${w.precip != null ? w.precip+"%" : "--"} precip</div>`;
        html += `<div>`;
        html += `${w.wspd != null ? Math.round(w.wspd)+" kt" : "--"} ${w.dirName}`;
        html += ` <span style="color:${w.windRelLabel==='offshore'?'rgba(80,220,120,0.8)':w.windRelLabel==='onshore'?'rgba(220,80,80,0.8)':'rgba(255,200,80,0.8)'};">(${w.windRelLabel})</span></div>`;
        if (waterTempRaw != null) {
          html += `<div>${Math.round(waterTempRaw)}°F water</div>`;
        }
        html += `</div></div>`;
      }
    }
    html += `</div>`;
  }
  html += `</div>`;

  // Footer note
  const offsetNote = DOCK_TIDE_OFFSET_FT !== 0
    ? `Tide heights corrected by ${DOCK_TIDE_OFFSET_FT > 0 ? "+" : ""}${DOCK_TIDE_OFFSET_FT} ft empirical offset. `
    : `No tide correction applied yet — update <code>DOCK_TIDE_OFFSET_FT</code> when empirical data available. `;
  html += `<div style="font-size:0.71rem;color:${dFooter};margin-top:10px;">`;
  html += `Float threshold ${DOCK_FLOAT_THRESHOLD_FT} ft MLLW. ${offsetNote}`;
  html += `Wind scored relative to onshore direction. Usable hours ${DOCK_USABLE_HOUR_START}:00–${DOCK_USABLE_HOUR_END}:00.`;
  html += `</div>`;

  el.innerHTML = html;
  
  // Update collapsed preview — after 6 PM, show tomorrow's score if available
  if (dayCards.length > 0 && dayCards[0].dayLabel === "Today") {
    const beachNow = new Date(); const beachSunsetStr = data.daily?.sunset?.[0]; const afterCutoff = beachSunsetStr ? beachNow > new Date(beachSunsetStr) : beachNow.getHours() >= 18;
    const showDay = (afterCutoff && dayCards.length > 1) ? dayCards[1] : dayCards[0];
    const sl = scoreLabel(showDay.bestScore);
    const dockDayLabelEl = document.getElementById("swimFloatLabelCollapsed");
    const dockScoreEl = document.getElementById("swimFloatScoreCollapsed");
    
    if (dockDayLabelEl) dockDayLabelEl.textContent = showDay.dayLabel;
    
    if (dockScoreEl) dockScoreEl.textContent = sl.label + " (" + Math.round(showDay.bestScore * 100) + "/100)";
    
    // Apply gradient class based on score
    const dockCard = document.querySelector('[data-collapse-key="swim_float"]');
    if (dockCard) {
      dockCard.classList.remove('tile-dock-great', 'tile-dock-good', 'tile-dock-marginal', 'tile-dock-poor', 'tile-dock-stayinside');
      if (showDay.bestScore >= 0.80) dockCard.classList.add('tile-dock-great');
      else if (showDay.bestScore >= 0.65) dockCard.classList.add('tile-dock-good');
      else if (showDay.bestScore >= 0.45) dockCard.classList.add('tile-dock-marginal');
      else if (showDay.bestScore >= 0.25) dockCard.classList.add('tile-dock-poor');
      else dockCard.classList.add('tile-dock-stayinside');
    }
  }
}
