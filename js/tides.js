// tides.js — NOAA CO-OPS tide predictions rendering (Salem Harbor 8442645)

let tideChartObj = null;

function renderTides(tides) {
  const grid = document.getElementById("tideGrid");
  const note = document.getElementById("nextTideNote");
  const nextTideEl = document.getElementById("nextTideCollapsed");
  const nextTideTimeEl = document.getElementById("nextTideTimeCollapsed");

  if (!grid) return;
  grid.innerHTML = "";
  if (note) note.textContent = "";

  if (!Array.isArray(tides) || tides.length === 0) {
    if (note) note.textContent = "No tide data available.";
    if (nextTideEl) nextTideEl.textContent = "No tide data";
    if (nextTideTimeEl) nextTideTimeEl.textContent = "";
    return;
  }

  const today = new Date();
  const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
  const nowMins  = today.getHours() * 60 + today.getMinutes();

  let nextIdx = -1;
  for (let i = 0; i < tides.length; i++) {
    const tDate = tides[i].date || todayStr;
    const [th, tm] = (tides[i].time || "00:00").split(":").map(Number);
    const tideMins = th * 60 + tm;
    if (tDate > todayStr || (tDate === todayStr && tideMins >= nowMins)) {
      nextIdx = i;
      break;
    }
  }

  const todayISO = (() => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`; })();
  const tmrw = (() => { const d = new Date(); d.setDate(d.getDate()+1); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}`; })();

  const byDate = {};
  let tideIdx = 0;
  tides.forEach(t => {
    const d = t.date || todayStr;
    if (!byDate[d]) byDate[d] = [];
    if (byDate[d].length < 4) { byDate[d].push({ ...t, globalIdx: tideIdx }); }
    tideIdx++;
  });
  const dateKeys = Object.keys(byDate).sort().slice(0, 3);

  const fmt12 = time => {
    if (!time || !time.includes(":")) return time || "--";
    const [h, m] = time.split(":").map(Number);
    const period = h >= 12 ? "PM" : "AM";
    const h12 = h === 0 ? 12 : h > 12 ? h - 12 : h;
    return `${h12}:${m.toString().padStart(2,"0")} ${period}`;
  };

  const dayLabel = dk =>
    dk === todayISO ? "Today" :
    dk === tmrw ? "Tomorrow" :
    new Date(dk + "T12:00:00").toLocaleDateString("en-US", { weekday:"short", month:"short", day:"numeric" });

  const cal = document.createElement("div");
  cal.style.cssText = "display:grid;grid-template-columns:repeat(" + dateKeys.length + ",1fr);gap:10px;margin-bottom:12px;";

  dateKeys.forEach(dk => {
    const col = document.createElement("div");
    col.style.cssText = "display:flex;flex-direction:column;gap:0;";

    const hdr = document.createElement("div");
    hdr.style.cssText = "font-size:0.72rem;font-weight:900;letter-spacing:0.8px;text-transform:uppercase;" +
      "color:var(--muted);padding:0 2px 8px;border-bottom:1px solid var(--border);margin-bottom:8px;";
    hdr.textContent = dayLabel(dk);
    col.appendChild(hdr);

    byDate[dk].forEach(t => {
      const isNext = (t.globalIdx === nextIdx);
      const isHigh = t.type === "H";

      const entry = document.createElement("div");
      entry.style.cssText =
        "display:flex;flex-direction:column;gap:1px;padding:9px 10px;border-radius:12px;margin-bottom:7px;" +
        (isNext
          ? "background:rgba(100,200,255,0.12);border:1px solid rgba(100,200,255,0.4);"
          : "background:var(--card-bg,rgba(255,255,255,0.04));border:1px solid var(--border);");

      const typeEl = document.createElement("div");
      typeEl.style.cssText = "display:flex;align-items:center;gap:5px;font-size:0.72rem;font-weight:900;" +
        "letter-spacing:0.5px;text-transform:uppercase;margin-bottom:3px;" +
        (isHigh ? (document.body.classList.contains("theme-light") ? "color:#0055aa;" : "color:rgba(100,200,255,0.9);") : "color:var(--muted);");
      typeEl.innerHTML = (isNext ? "&#9654; " : "") + (isHigh ? "High" : "Low");
      entry.appendChild(typeEl);

      const timeEl = document.createElement("div");
      timeEl.style.cssText = "font-size:0.95rem;font-weight:800;color:var(--text);line-height:1.1;";
      timeEl.textContent = fmt12(t.time);
      entry.appendChild(timeEl);

      const htEl = document.createElement("div");
      htEl.style.cssText = "font-size:0.82rem;font-weight:700;" +
        (isHigh ? (document.body.classList.contains("theme-light") ? "color:#0055aa;" : "color:rgba(100,200,255,0.9);") : "color:var(--muted);");
      htEl.textContent = (t.height ?? "--") + " ft";
      entry.appendChild(htEl);

      col.appendChild(entry);
    });

    cal.appendChild(col);
  });

  grid.appendChild(cal);
  if (note) note.textContent = "Salem Harbor (8442645) — harmonic predictions. ▶ = next tide.";

  if (nextIdx >= 0 && tides[nextIdx]) {
    const nextTide = tides[nextIdx];
    const type = nextTide.type === "H" ? "High" : "Low";
    const height = nextTide.height ? `${nextTide.height} ft` : "--";

    let time12hr = nextTide.time || "--";
    if (nextTide.time && nextTide.time.includes(":")) {
      const [hours, mins] = nextTide.time.split(":").map(Number);
      const period = hours >= 12 ? "PM" : "AM";
      const hours12 = hours === 0 ? 12 : hours > 12 ? hours - 12 : hours;
      time12hr = `${hours12}:${mins.toString().padStart(2, '0')} ${period}`;
    }

    if (nextTideEl) nextTideEl.textContent = `Next: ${type} Tide`;
    const isTomorrow = (nextTide.date || todayStr) !== todayStr;
    if (nextTideTimeEl) nextTideTimeEl.textContent = time12hr + (isTomorrow ? " (tomorrow)" : "");
    const nextTideHeightEl = document.getElementById("nextTideHeightCollapsed");
    if (nextTideHeightEl) nextTideHeightEl.textContent = height;

    const tideWaterEl = document.getElementById("tideWater");
    if (tideWaterEl && nextIdx >= 0) {
      const prevIdx = nextIdx - 1;
      if (prevIdx >= 0 && tides[prevIdx]) {
        const prevTide = tides[prevIdx];
        const prevHeight = parseFloat(prevTide.height) || 0;
        const nextHeight = parseFloat(nextTide.height) || 0;

        const now = new Date();
        const prevTime = new Date(`${prevTide.date || todayStr}T${prevTide.time || "00:00"}:00`);
        const nextTime = new Date(`${nextTide.date || todayStr}T${nextTide.time || "00:00"}:00`);
        const totalDuration = nextTime - prevTime;
        const elapsed = now - prevTime;
        const progress = Math.max(0, Math.min(1, elapsed / totalDuration));

        const currentHeight = prevHeight + (nextHeight - prevHeight) * progress;
        const minHeight = -2;
        const maxHeight = 12;
        const currentPercent = ((currentHeight - minHeight) / (maxHeight - minHeight)) * 100;
        const prevPercent = ((prevHeight - minHeight) / (maxHeight - minHeight)) * 100;

        const isRising = nextHeight > prevHeight;
        tideWaterEl._prevPercent = prevPercent;
        tideWaterEl._targetPercent = currentPercent;
        tideWaterEl.style.height = `${prevPercent}%`;

        setTimeout(() => {
          tideWaterEl.style.height = `${Math.max(12, Math.min(95, currentPercent))}%`;
          const direction = isRising ? "Coming in" : "Going out";
          const currentHeightFt = currentHeight.toFixed(1);
          let currentTideText = tideWaterEl.querySelector(".current-tide-text");
          if (!currentTideText) {
            currentTideText = document.createElement("div");
            currentTideText.className = "current-tide-text";
            currentTideText.style.cssText = "position:absolute;bottom:8px;left:50%;transform:translateX(-50%);font-size:13px;font-weight:600;color:rgba(255,255,255,0.5);text-align:center;z-index:3;white-space:nowrap;";
            tideWaterEl.appendChild(currentTideText);
          }
          currentTideText.textContent = `NOW: ${direction}, ${currentHeightFt} ft`;
        }, 100);
      }
    }
  } else {
    if (nextTideEl) nextTideEl.textContent = "No upcoming tide";
    if (nextTideTimeEl) nextTideTimeEl.textContent = "";
  }
}

function buildTideChart(curve, events) {
  const ctx = document.getElementById("tideChart");
  if (!ctx || !curve || !Array.isArray(curve.times) || curve.times.length === 0) return;

  const step = 3;
  const labels  = [];
  const heights = [];
  for (let i = 0; i < curve.times.length; i += step) {
    const raw = curve.times[i];
    const d   = new Date(raw.replace(" ", "T"));
    labels.push(d.toLocaleTimeString("en-US", { weekday: undefined, hour: "numeric", minute: "2-digit" }));
    heights.push(curve.heights[i]);
  }

  const nowMs = Date.now();
  let nowLineIdx = 0;
  let minDiff   = Infinity;
  for (let i = 0; i < curve.times.length; i += step) {
    const d    = new Date(curve.times[i].replace(" ", "T"));
    const diff = Math.abs(d.getTime() - nowMs);
    if (diff < minDiff) { minDiff = diff; nowLineIdx = Math.floor(i / step); }
  }

  if (tideChartObj) tideChartObj.destroy();
  tideChartObj = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Tide Height (ft)",
          data: heights,
          borderColor:     "rgba(100,180,255,0.85)",
          backgroundColor: "rgba(100,180,255,0.08)",
          borderWidth: 2,
          fill: true,
          tension: 0.4,
          pointRadius: 0,
          pointHoverRadius: 4,
        },
        {
          label: "Now",
          data: labels.map((_, i) => i === nowLineIdx ? heights[i] : null),
          borderColor:  "rgba(255,220,80,0.9)",
          backgroundColor: "rgba(255,220,80,0.9)",
          borderWidth: 0,
          pointRadius: labels.map((_, i) => i === nowLineIdx ? 8 : 0),
          pointStyle:  "triangle",
          fill: false,
          tension: 0,
          showLine: false,
        }
      ]
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => ctx.datasetIndex === 0
              ? " " + ctx.parsed.y.toFixed(1) + " ft"
              : " Now"
          }
        }
      },
      scales: {
        x: {
          ticks: {
            color: document.body.classList.contains("theme-light") ? "rgba(0,0,0,0.45)" : "rgba(255,255,255,0.45)",
            maxTicksLimit: 12,
            maxRotation: 0,
            font: { size: 10, weight: "700" }
          },
          grid: { color: document.body.classList.contains("theme-light") ? "rgba(0,0,0,0.06)" : "rgba(255,255,255,0.04)" }
        },
        y: {
          ticks: {
            color: document.body.classList.contains("theme-light") ? "rgba(0,0,0,0.55)" : "rgba(255,255,255,0.55)",
            callback: v => v.toFixed(1) + " ft",
            font: { size: 10, weight: "700" }
          },
          grid: { color: document.body.classList.contains("theme-light") ? "rgba(0,0,0,0.08)" : "rgba(255,255,255,0.06)" }
        }
      }
    }
  });
}

// Water temp calibration logger

function logWaterTemp() {
  const input  = document.getElementById("wtLogTemp");
  const status = document.getElementById("wtLogStatus");
  const temp   = parseFloat(input.value);
  if (isNaN(temp) || temp < 30 || temp > 95) {
    status.textContent = "Enter a valid temp (30–95°F)";
    status.style.color = "rgba(255,120,80,0.9)";
    return;
  }

  // Get current tide height from curve
  const data    = window.__lastWeatherData || {};
  const curve   = data.tide_curve || {};
  const ctimes  = curve.times   || [];
  const cheights= curve.heights || [];
  const nowMs   = Date.now();
  let tideH = null;
  let bestDiff = Infinity;
  for (let i = 0; i < ctimes.length; i++) {
    const diff = Math.abs(new Date(ctimes[i]).getTime() - nowMs);
    if (diff < bestDiff) { bestDiff = diff; tideH = cheights[i]; }
  }

  const buoyTemp = (data.buoy_44013 || {}).water_temp_f ?? null;
  const now      = new Date();
  const entry    = {
    ts:         now.toISOString(),
    local_time: now.toLocaleString("en-US"),
    water_temp_f: temp,
    tide_height_ft: tideH !== null ? Math.round(tideH * 100) / 100 : null,
    buoy_temp_f:  buoyTemp,
    offset_f:     buoyTemp !== null ? Math.round((temp - buoyTemp) * 10) / 10 : null,
    month:        now.getMonth() + 1,
  };

  // Save to localStorage
  let log = [];
  try { log = JSON.parse(localStorage.getItem("wt_cal_log") || "[]"); } catch(e) {}
  log.push(entry);
  try { localStorage.setItem("wt_cal_log", JSON.stringify(log)); } catch(e) {}

  input.value = "";
  status.textContent = `✓ Logged ${temp}°F at tide ${tideH !== null ? tideH.toFixed(1)+"ft" : "unknown"}`;
  status.style.color = "rgba(100,220,120,0.9)";
  renderWaterTempLog();
}

function renderWaterTempLog() {
  const el = document.getElementById("wtLogTable");
  if (!el) return;
  let log = [];
  try { log = JSON.parse(localStorage.getItem("wt_cal_log") || "[]"); } catch(e) {}
  if (!log.length) { el.innerHTML = "<em>No readings logged yet.</em>"; return; }

  // Show most recent 20, newest first
  const rows = [...log].reverse().slice(0, 20);
  let html = `<table style="width:100%;border-collapse:collapse;">
    <tr style="color:rgba(255,255,255,0.4);font-size:0.72rem;border-bottom:1px solid rgba(255,255,255,0.1);">
      <th style="text-align:left;padding:4px 8px;">Time</th>
      <th style="text-align:right;padding:4px 8px;">Harbor °F</th>
      <th style="text-align:right;padding:4px 8px;">Tide ft</th>
      <th style="text-align:right;padding:4px 8px;">Buoy °F</th>
      <th style="text-align:right;padding:4px 8px;">Offset</th>
    </tr>`;
  for (const e of rows) {
    html += `<tr style="border-bottom:1px solid rgba(255,255,255,0.05);">
      <td style="padding:4px 8px;color:rgba(255,255,255,0.45);">${e.local_time}</td>
      <td style="padding:4px 8px;text-align:right;font-weight:800;">${e.water_temp_f}°</td>
      <td style="padding:4px 8px;text-align:right;">${e.tide_height_ft !== null ? e.tide_height_ft+"ft" : "--"}</td>
      <td style="padding:4px 8px;text-align:right;">${e.buoy_temp_f !== null ? e.buoy_temp_f+"°" : "--"}</td>
      <td style="padding:4px 8px;text-align:right;color:${e.offset_f > 0 ? "rgba(100,220,120,0.8)" : "rgba(255,120,80,0.8)"};">
        ${e.offset_f !== null ? (e.offset_f > 0 ? "+" : "") + e.offset_f+"°" : "--"}
      </td>
    </tr>`;
  }
  html += `</table>`;
  if (log.length > 20) html += `<div style="margin-top:6px;color:rgba(255,255,255,0.3);font-size:0.72rem;">${log.length} total readings stored.</div>`;
  el.innerHTML = html;
}
