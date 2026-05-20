// thunderstorm.js — Thunderstorm detector card

let _tsChartObj = null;

const TS_SEVERITY_CONFIG = {
  clear:  { label: "No Risk",    cls: "calm",        tileClass: "" },
  watch:  { label: "Watch",      cls: "notable",     tileClass: "tile-ts-watch" },
  active: { label: "Active",     cls: "significant", tileClass: "tile-ts-active" },
  severe: { label: "Severe",     cls: "severe",      tileClass: "tile-ts-severe" },
};

function _capeColor(cape) {
  if (cape == null)    return "rgba(120,120,120,0.5)";
  if (cape >= 4000)    return "rgba(180,60,220,0.85)";
  if (cape >= 2500)    return "rgba(220,60,60,0.85)";
  if (cape >= 1000)    return "rgba(240,140,40,0.85)";
  if (cape >= 500)     return "rgba(220,200,60,0.85)";
  return                      "rgba(80,160,80,0.5)";
}

function _fmtTime(unixSec) {
  if (!unixSec) return "";
  const d = new Date(unixSec * 1000);
  const h = d.getHours();
  return h === 0 ? "midnight" : h < 12 ? `${h}am` : h === 12 ? "noon" : `${h - 12}pm`;
}

function renderThunderstormCard(data) {
  const ts = data?.derived?.thunderstorm;
  const cfg = TS_SEVERITY_CONFIG[ts?.severity || "clear"];

  // ── Collapsed tile ────────────────────────────────────────────────────────
  const card = document.querySelector('[data-collapse-key="thunderstorm"]');
  if (card) {
    Object.values(TS_SEVERITY_CONFIG).forEach(c => {
      if (c.tileClass) card.classList.remove(c.tileClass);
    });
    if (cfg.tileClass) card.classList.add(cfg.tileClass);
  }

  const tileStatus = document.getElementById("tsStatusCollapsed");
  const tileDetail = document.getElementById("tsDetailCollapsed");
  const tileCape   = document.getElementById("tsCapeCollapsed");

  if (tileStatus) tileStatus.textContent = cfg.label;
  if (tileDetail && ts) {
    if (ts.active && ts.lightning_count > 0) {
      const dist = ts.min_distance_km != null ? ` · ${ts.min_distance_km} km away` : "";
      tileDetail.textContent = `${ts.lightning_count} strikes/hr${dist}`;
      tileDetail.style.display = "";
    } else if (ts.severity === "watch") {
      tileDetail.textContent = "Conditions favorable";
      tileDetail.style.display = "";
    } else {
      tileDetail.style.display = "none";
    }
  }
  if (tileCape && ts?.cape_current != null) {
    tileCape.textContent = `CAPE ${ts.cape_current} J/kg · ${ts.cape_label}`;
  }

  // ── Expanded card ─────────────────────────────────────────────────────────
  if (!ts) return;

  const setT = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
  const setH = (id, val) => { const el = document.getElementById(id); if (el) el.innerHTML  = val; };

  // Status badge
  setH("tsStatusBadge", `<span class="badge ${cfg.cls}">${cfg.label}</span>`);

  // Live lightning rows
  const lightningSection = document.getElementById("tsLightningSection");
  if (lightningSection) {
    lightningSection.style.display = ts.active ? "" : "none";
  }
  setT("tsStrikesValue",  ts.lightning_count > 0 ? `${ts.lightning_count} in past hour` : "--");
  setT("tsStrikes3hrValue", ts.lightning_count_3hr > 0 ? `${ts.lightning_count_3hr} in past 3 hours` : "--");
  setT("tsDistanceValue", ts.min_distance_km != null ? `${ts.min_distance_km} km` : "Unknown");

  // CAPE rows
  setT("tsCapeValue",     ts.cape_current != null ? `${ts.cape_current} J/kg` : "--");
  setT("tsCapeLabelValue", ts.cape_label || "--");
  if (ts.cape_peak_value != null && ts.cape_peak_hour != null) {
    setT("tsCapePeakValue", `${ts.cape_peak_value} J/kg at ${_fmtTime(ts.cape_peak_hour)}`);
  } else {
    setT("tsCapePeakValue", "--");
  }

  // CAPE chart
  _buildCapeChart(ts.cape_hourly || []);
}

function _buildCapeChart(hourly) {
  const ctx = document.getElementById("tsCapeChart");
  if (!ctx) return;
  if (_tsChartObj) { _tsChartObj.destroy(); _tsChartObj = null; }
  if (!hourly.length) return;

  const labels = hourly.map(pt => _fmtTime(pt.time));
  const values = hourly.map(pt => pt.cape ?? 0);
  const colors = values.map(_capeColor);
  const maxVal = Math.max(...values, 500);

  _tsChartObj = new Chart(ctx.getContext("2d"), {
    type: "bar",
    data: {
      labels,
      datasets: [{
        data: values,
        backgroundColor: colors,
        borderRadius: 3,
        borderSkipped: false,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      layout: { padding: { bottom: 4 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => `${ctx.parsed.y} J/kg`,
          },
        },
      },
      scales: {
        x: {
          ticks: { color: chartTextColor(), font: { size: 10 }, maxRotation: 0, maxTicksLimit: 7 },
          grid:  { color: chartGridColor() },
        },
        y: {
          min: 0,
          max: Math.ceil(maxVal * 1.1 / 500) * 500,
          ticks: { color: chartTextColor(), font: { size: 10 }, stepSize: 500 },
          grid:  { color: chartGridColor() },
          title: { display: true, text: "J/kg", color: chartTextColor(), font: { size: 9 } },
        },
      },
    },
  });
}
