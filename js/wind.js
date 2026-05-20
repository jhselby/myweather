// wind.js — Wind compass tile, Wind Impact card, 48h wind chart
// Shared utilities (worryLevel, combinedWindImpact, worryScore,
// getExposureFactor, toCompass, fmtLocal, chartTextColor, chartGridColor)
// remain in app-main.js as globals.

let windChartObj    = null;
let _gustWindowHours = 12;
let _susWindowHours  = 12;

// ── Color helper ────────────────────────────────────────────────────────────

function windColor(mph) {
  if (mph == null) return "rgba(255,255,255,0.08)";
  if (mph < 10)   return "rgba(80,200,120,0.85)";
  if (mph < 20)   return "rgba(220,200,60,0.85)";
  if (mph < 30)   return "rgba(240,140,40,0.85)";
  if (mph < 40)   return "rgba(220,60,60,0.85)";
  return                 "rgba(160,60,220,0.85)";
}

// ── Chart hover data bar ─────────────────────────────────────────────────────

function updateWindDataBar(index, times, speeds, gusts, directions) {
  const time = times[index];
  const speed = speeds[index];
  const gust = gusts[index];
  const dir = directions[index];

  const dt = new Date(time);
  const hour = dt.getHours();
  const nextHour = (hour + 1) % 24;
  const weekday = dt.toLocaleDateString("en-US", { weekday: "short" });
  const month   = dt.toLocaleDateString("en-US", { month: "short" });
  const day     = dt.getDate();
  const timeStr = `${weekday} ${month} ${day}, ${hour % 12 || 12}-${nextHour % 12 || 12}${nextHour < 12 ? 'am' : 'pm'}`;

  const dirStr        = dir != null ? toCompass(dir, true) : "—";
  const combined      = dir != null ? Math.round(combinedWindImpact(speed, gust, dir)) : null;
  const combinedLevel = combined != null ? worryLevel(combined) : null;
  const impactStr     = combined != null ? `Impact: ${combined} ${combinedLevel.label}` : "Impact: --";
  const spdStr        = speed != null ? `${Math.round(speed)} mph` : "--";
  const gustStr       = gust  != null ? `Gusts ${Math.round(gust)} mph` : "";

  document.getElementById("windDataTime").textContent = timeStr + " ·";
  document.getElementById("windDataLine").textContent =
    `${spdStr}${gustStr ? " · " + gustStr : ""} · ${dirStr} · ${impactStr}`;
}

// ── 48h wind chart ────────────────────────────────────────────────────────────

function buildWindChart(times, speeds, gusts, directions) {
  const labels      = times.map(t => new Date(t).toLocaleTimeString("en-US", { hour: "numeric" }));
  const ctx         = document.getElementById("windChart").getContext("2d");
  if (windChartObj) windChartObj.destroy();
  const speedColors = speeds.map(v => windColor(v));

  const sustainedImpact = speeds.map((speed, i) => {
    const dir = directions?.[i];
    if (speed == null || dir == null) return null;
    return worryScore(speed, getExposureFactor(dir));
  });

  const gustImpact = gusts.map((gust, i) => {
    const dir = directions?.[i];
    if (gust == null || dir == null) return null;
    return worryScore(gust, getExposureFactor(dir));
  });

  const allImpacts = [...sustainedImpact, ...gustImpact].filter(v => v != null);
  const maxImpact  = allImpacts.length > 0 ? Math.max(...allImpacts) : 10;
  const axisMax    = Math.ceil(maxImpact * 1.1);

  windChartObj = new Chart(ctx, {
    data: {
      labels,
      datasets: [
        {
          type: "bar",
          label: "Wind (mph)",
          data: speeds.map(v => v ?? null),
          yAxisID: "y1",
          backgroundColor: "rgba(150,150,150,0.3)",
          borderColor: "transparent",
          borderRadius: 3,
        },
        {
          type: "line",
          label: "Gust (mph)",
          data: gusts.map(v => v ?? null),
          yAxisID: "y1",
          tension: 0.25,
          borderColor: "rgba(150,150,150,0.6)",
          backgroundColor: "rgba(255,180,100,0.15)",
          pointRadius: 0,
          borderWidth: 2,
        },
        {
          type: "line",
          label: "Sustained Impact",
          data: sustainedImpact,
          yAxisID: "y",
          tension: 0.25,
          borderColor: "rgba(140,100,200,0.95)",
          backgroundColor: "transparent",
          pointRadius: 0,
          borderWidth: 2,
        },
        {
          type: "line",
          label: "Gust Impact",
          data: gustImpact,
          yAxisID: "y",
          tension: 0.25,
          borderColor: "rgba(255,80,60,0.95)",
          backgroundColor: "transparent",
          pointRadius: 0,
          borderWidth: 2,
        }
      ]
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      onClick: (event, activeElements) => {
        if (activeElements.length > 0)
          updateWindDataBar(activeElements[0].index, times, speeds, gusts, directions);
      },
      onHover: (event, activeElements) => {
        const dataBar = document.getElementById("windDataBar");
        if (dataBar && activeElements.length > 0)
          updateWindDataBar(activeElements[0].index, times, speeds, gusts, directions);
      },
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false },
        impactZones: {
          beforeDatasetsDraw: (chart) => {
            const {ctx, chartArea: {left, right, top, bottom}, scales: {y}} = chart;
            if (!y) return;
            const zones = [
              {min: 0,  max: 5,   color: 'rgba(100,150,255,0.15)'},
              {min: 5,  max: 12,  color: 'rgba(100,200,255,0.15)'},
              {min: 12, max: 20,  color: 'rgba(255,235,100,0.15)'},
              {min: 20, max: 30,  color: 'rgba(255,180,100,0.15)'},
              {min: 30, max: 40,  color: 'rgba(255,100,80,0.15)'},
              {min: 40, max: 100, color: 'rgba(200,50,50,0.15)'},
            ];
            zones.forEach(zone => {
              const yTop    = y.getPixelForValue(zone.max);
              const yBottom = y.getPixelForValue(zone.min);
              ctx.fillStyle = zone.color;
              ctx.fillRect(left, yTop, right - left, yBottom - yTop);
            });
          }
        }
      },
      scales: {
        x: {
          ticks: {
            color: chartTextColor(),
            maxRotation: 0,
            autoSkip: false,
            font: { size: 10 },
            callback: function(value, index) {
              const dt = new Date(times[index]);
              const h = dt.getHours();
              const m = dt.getMinutes();
              if (m !== 0) return null;
              if (h === 0) return dt.toLocaleDateString("en-US", { weekday: "short" });
              if (h % 6 === 0) return h === 12 ? "12pm" : h < 12 ? h + "am" : (h-12) + "pm";
              return null;
            }
          },
          grid: { color: chartGridColor() }
        },
        y: {
          position: "left",
          ticks: { color: chartTextColor(), font: { size: 10 } },
          grid:  { color: chartGridColor() },
          min: 0,
          max: axisMax
        },
        y1: {
          position: "right",
          ticks: { color: chartTextColor(), font: { size: 10 }, callback: v => v + " mph" },
          grid:  { drawOnChartArea: false }
        }
      }
    }
  });
}

// ── Peak worry (window picker) ────────────────────────────────────────────────

function computePeakWorry(hourly, windowHours, useGusts) {
  const values = useGusts ? (hourly?.wind_gusts || []) : (hourly?.wind_speed || []);
  const dirs   = hourly?.wind_direction || [];
  const times  = hourly?.times || [];

  const currentHour = new Date();
  currentHour.setMinutes(0, 0, 0);
  let startIdx = times.findIndex(t => new Date(t) >= currentHour);
  if (startIdx === -1) startIdx = 0;

  const n = Math.min(startIdx + windowHours, values.length, dirs.length);
  let bestScore = -1, bestIdx = -1;
  for (let i = startIdx; i < n; i++) {
    const v = values[i], d = dirs[i];
    if (v == null || d == null) continue;
    const ws = worryScore(v, getExposureFactor(d));
    if (ws > bestScore) { bestScore = ws; bestIdx = i; }
  }
  if (bestIdx < 0) return null;

  const d  = dirs[bestIdx];
  const ef = getExposureFactor(d);
  return {
    speed:          values[bestIdx],
    directionDeg:   d,
    exposureFactor: ef,
    score:          worryScore(values[bestIdx], ef),
    timeISO:        times[bestIdx] || null
  };
}

// ── Fill worry card detail rows ───────────────────────────────────────────────

function fillWorryCard(ids, peak, windowHours) {
  function setEl(id, val, isHTML) {
    const el = document.getElementById(id);
    if (!el) return;
    if (isHTML) el.innerHTML = val; else el.textContent = val;
  }
  if (!peak) {
    setEl(ids.score,    "--");
    setEl(ids.peakSpd,  "-- mph");
    setEl(ids.dir,      "--");
    setEl(ids.exposure, "--");
    setEl(ids.time,     "--");
    return;
  }
  const wl = worryLevel(peak.score);
  setEl(ids.score,      `<span class="badge ${wl.cls}">${peak.score.toFixed(1)}</span> (${wl.label})`, true);
  setEl(ids.scoreLabel, `Peak Impact (next ${windowHours}h)`);
  setEl(ids.peakSpd,   `${Math.round(peak.speed)} mph`);
  setEl(ids.dir,        toCompass(peak.directionDeg));
  setEl(ids.exposure,  `${(peak.exposureFactor * 100).toFixed(0)}%`);
  setEl(ids.time,       peak.timeISO ? fmtLocal(peak.timeISO) : "--");
}

// ── Wind Impact expanded card ─────────────────────────────────────────────────

function renderWindRisk(data) {
  const hyp    = data.hyperlocal || {};
  const hourly = data.hourly || {};
  let gustPeak = computePeakWorry(hourly, _gustWindowHours, true);
  let susPeak  = computePeakWorry(hourly, _susWindowHours,  false);

  fillWorryCard(
    { score:"gustCurrentScore", scoreLabel:"windImpactScoreLabel", peakSpd:"gustPeak",
      dir:"gustDir", exposure:"gustExposure", time:"gustTime", note:"gustNote" },
    gustPeak, _gustWindowHours
  );
  fillWorryCard(
    { score:"susCurrentScore", scoreLabel:"windImpactScoreLabel", peakSpd:"susPeak",
      dir:"susDir", exposure:"susExposure", time:"susTime", note:"susNote" },
    susPeak, _susWindowHours
  );

  const noteEl = document.getElementById("gustNote");
  if (noteEl) noteEl.textContent = `Wind impact over next ${_gustWindowHours}h. Score reflects sustained wind when calm, gusts when conditions are notable.`;

  const cur = data.current || {};
  const curWindSpeed = hyp.corrected_wind_speed ?? cur.wind_speed;
  const curGustSpeed = hyp.corrected_wind_gusts ?? cur.wind_gusts;

  // If observed current gust/sustained exceeds forecast peak, use observed as peak
  if (cur.wind_direction != null) {
    const obsDir = cur.wind_direction;
    const obsEf  = getExposureFactor(obsDir);
    const obsGustScore = curGustSpeed != null ? worryScore(curGustSpeed, obsEf) : 0;
    const obsSusScore  = curWindSpeed != null ? worryScore(curWindSpeed, obsEf) : 0;
    if (obsGustScore > (gustPeak?.score ?? 0)) {
      gustPeak = { speed: curGustSpeed, directionDeg: obsDir, exposureFactor: obsEf,
                   score: obsGustScore, timeISO: new Date().toISOString() };
    }
    if (obsSusScore > (susPeak?.score ?? 0)) {
      susPeak = { speed: curWindSpeed, directionDeg: obsDir, exposureFactor: obsEf,
                  score: obsSusScore, timeISO: new Date().toISOString() };
    }
  }

  if (cur.wind_direction != null && (curWindSpeed != null || curGustSpeed != null)) {
    const combined      = Math.round(combinedWindImpact(curWindSpeed, curGustSpeed, cur.wind_direction));
    const combinedLevel = worryLevel(combined);
    const combinedEl    = document.getElementById("windImpactCombinedScore");
    if (combinedEl) combinedEl.innerHTML = `<span class="badge ${combinedLevel.cls}">${combined}</span> (${combinedLevel.label})`;

    const peakCombined = Math.round(gustPeak?.score ?? 0);
    const peakLevel    = worryLevel(peakCombined);
    const peakEl       = document.getElementById("windImpactPeakScore");
    const labelEl      = document.getElementById("windImpactScoreLabel");
    if (peakEl)  peakEl.innerHTML  = `<span class="badge ${peakLevel.cls}">${peakCombined}</span> (${peakLevel.label})`;
    if (labelEl) labelEl.textContent = `Peak Impact (next ${_gustWindowHours}h)`;
  }
}

// ── Window pills ──────────────────────────────────────────────────────────────

function initWindPills(data) {
  document.querySelectorAll(".wpill").forEach(btn => {
    btn.addEventListener("click", () => {
      const target = btn.dataset.target;
      const hours  = parseInt(btn.dataset.hours, 10);
      document.querySelectorAll(`.wpill[data-target="${target}"]`)
        .forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      if (target === "wind_impact") { _gustWindowHours = hours; _susWindowHours = hours; }
      else if (target === "gust")    _gustWindowHours = hours;
      else                           _susWindowHours  = hours;
      renderWindRisk(window.__lastWeatherData || data);
    });
  });
}

// ── Right Now compass tile ────────────────────────────────────────────────────

function renderWindTile(data) {
  const hyp = data.hyperlocal || {};
  const cur = data.current || {};
  const windSpeed = hyp.corrected_wind_speed ?? cur.wind_speed;
  const gustSpeed = hyp.corrected_wind_gusts ?? cur.wind_gusts;
  const windDir   = cur.wind_direction;

  const speedEl    = document.getElementById("weatherWindSustainedSpeed");
  const gustsEl    = document.getElementById("weatherWindGustsLine");
  const lullEl     = document.getElementById("weatherWindLullLine");
  const lullRowEl  = document.getElementById("weatherWindLullRow");
  const dirEl      = document.getElementById("weatherWindDirectionIndicator");
  const dirLabelEl = document.getElementById("weatherWindDirLabel");
  const impactEl   = document.getElementById("weatherWindImpactBar");

  if (!speedEl || !gustsEl || !impactEl) return;

  speedEl.textContent = windSpeed != null ? Math.round(windSpeed) : '--';
  gustsEl.textContent = gustSpeed != null ? Math.round(gustSpeed) : '--';

  if (dirLabelEl) {
    dirLabelEl.textContent = windDir != null ? toCompass(windDir, false) : '--';
  }

  // Lull from Tempest stations (minimum lull across reporters)
  if (lullEl && lullRowEl) {
    const stations  = data.tempest?.stations || [];
    const lullVals  = stations.map(s => s.wind_lull_mph).filter(v => v != null && v >= 0);
    const lullMph   = lullVals.length > 0 ? Math.min(...lullVals) : null;
    if (lullMph != null) {
      lullEl.textContent       = Math.round(lullMph);
      lullRowEl.style.display  = '';
    } else {
      lullRowEl.style.display  = 'none';
    }
  }

  // Direction arrow — needle points north by default, center at (42,42)
  if (dirEl && windDir != null) {
    const arrowRotation = (windDir + 180) % 360;
    dirEl.setAttribute('transform', `rotate(${arrowRotation}, 42, 42)`);
    dirEl.style.transform      = '';
    dirEl.style.transformOrigin = '';
  }

  // Impact bar
  const windBarClasses = ['wind-bar-calm','wind-bar-light','wind-bar-moderate','wind-bar-strong','wind-bar-severe'];
  const windTintClasses = ['wind-tint-calm','wind-tint-light','wind-tint-moderate','wind-tint-strong','wind-tint-severe'];
  const windCard = document.querySelector('[data-collapse-key="48h_wind"]');
  impactEl.classList.remove(...windBarClasses);
  if (windCard) windCard.classList.remove(...windTintClasses);
  if (windDir != null && (windSpeed != null || gustSpeed != null)) {
    const combined      = Math.round(combinedWindImpact(windSpeed, gustSpeed, windDir));
    const combinedLevel = worryLevel(combined);
    impactEl.textContent = `Impact: ${combined} ${combinedLevel.label}`;
    const colorCls = combined <= 2 ? 'calm' : combined <= 4 ? 'light' : combined <= 7 ? 'moderate' : combined <= 10 ? 'strong' : 'severe';
    impactEl.classList.add(`wind-bar-${colorCls}`);
    if (windCard) windCard.classList.add(`wind-tint-${colorCls}`);
  } else {
    impactEl.textContent = 'Impact: --';
  }
}

// ── Wind Impact collapsed tile ────────────────────────────────────────────────

function renderWindImpactCollapsed(data) {
  const hyp = data.hyperlocal || {};
  const cur = data.current || {};
  const windRisk = data.wind_risk || {};

  const collapsedEl = document.getElementById("windImpactCollapsed");
  const labelEl     = document.getElementById("windImpactLabel");
  const peakEl      = document.getElementById("windImpactPeakCollapsed");

  const cwSpeed = hyp.corrected_wind_speed ?? cur.wind_speed;
  const cwGust  = hyp.corrected_wind_gusts ?? cur.wind_gusts;
  const cwDir   = cur.wind_direction;

  if (collapsedEl && cwDir != null) {
    const combined      = Math.round(combinedWindImpact(cwSpeed, cwGust, cwDir));
    const combinedLevel = worryLevel(combined);
    const dirStr        = toCompass(cwDir, false);
    if (collapsedEl) collapsedEl.textContent = combined.toString();
    if (labelEl)     labelEl.textContent     = combinedLevel.label;
    if (peakEl)      peakEl.textContent      =
      `${dirStr} · ${cwSpeed != null ? Math.round(cwSpeed) : '--'} mph · Gusts ${cwGust != null ? Math.round(cwGust) : '--'} mph`;
    const windCard = document.querySelector('[data-collapse-key="wind_impact"]');
    if (windCard) {
      windCard.classList.remove('tile-wind-calm','tile-wind-light','tile-wind-moderate','tile-wind-strong','tile-wind-severe');
      const cls = combined <= 2 ? 'calm' : combined <= 4 ? 'light' : combined <= 7 ? 'moderate' : combined <= 10 ? 'strong' : 'severe';
      windCard.classList.add(`tile-wind-${cls}`);
    }
  } else if (collapsedEl) {
    collapsedEl.textContent = '--';
    if (labelEl) labelEl.textContent = 'No data';
    if (peakEl)  peakEl.textContent  = '';
  }

  // Gust detail rows in expanded body (collector wind_risk data)
  const gustData = windRisk.gust || {};
  if (gustData.worry_score !== undefined) {
    const gustScore = Math.round(gustData.worry_score);
    const gustLevel = worryLevel(gustScore);
    const gustEl    = document.getElementById("gustCurrentScore");
    if (gustEl) gustEl.innerHTML = `<span class="badge ${gustLevel.cls}">${gustScore}</span> (${gustLevel.label})`;
    const gustPeakEl = document.getElementById("gustPeak");
    if (gustPeakEl) gustPeakEl.textContent = `${gustData.peak_mph || "--"} mph`;
    const gustDirEl = document.getElementById("gustDir");
    if (gustDirEl)  gustDirEl.textContent  = gustData.direction_deg != null ? `${gustData.direction_deg}° ${toCompass(gustData.direction_deg, false)}` : "--";
    const gustExpEl = document.getElementById("gustExposure");
    if (gustExpEl)  gustExpEl.textContent  = gustData.exposure_factor != null ? `${(gustData.exposure_factor * 100).toFixed(0)}%` : "--";
    const gustTimeEl = document.getElementById("gustTime");
    if (gustTimeEl) gustTimeEl.textContent = gustData.peak_time ? fmtLocal(gustData.peak_time) : "--";
  }
}

// ── 48h chart entry point ─────────────────────────────────────────────────────

function renderWindChart(data) {
  const hourly   = data.hourly || {};
  const allTimes = hourly.times || [];

  const now         = new Date();
  const currentHour = new Date(now.getFullYear(), now.getMonth(), now.getDate(), now.getHours());
  let startIdx = allTimes.findIndex(t => new Date(t) >= currentHour);
  if (startIdx === -1) startIdx = 0;

  const times = allTimes.slice(startIdx, startIdx + 48);
  const speeds = (hourly.wind_speed     || []).slice(startIdx, startIdx + 48);
  const gusts  = (hourly.wind_gusts     || []).slice(startIdx, startIdx + 48);
  const dirs   = (hourly.wind_direction || []).slice(startIdx, startIdx + 48);

  // Substitute current hour with hyperlocal observed values so impact lines
  // reflect actual conditions rather than (often wrong) model forecast direction
  const hyp = data.hyperlocal || {};
  const cur = data.current    || {};
  const obsSpeed = hyp.corrected_wind_speed ?? cur.wind_speed;
  const obsGust  = hyp.corrected_wind_gusts ?? cur.wind_gusts;
  const obsDir   = cur.wind_direction;
  if (obsSpeed != null) speeds[0] = obsSpeed;
  if (obsGust  != null) gusts[0]  = obsGust;
  if (obsDir   != null) dirs[0]   = obsDir;

  buildWindChart(times, speeds, gusts, dirs);
  updateWindDataBar(0, times, speeds, gusts, dirs);
}
