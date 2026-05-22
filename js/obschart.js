// obschart.js — Observed 48h temperature / wind / gust chart

let obsChart = null;

function updateObsDataBar(index, entries) {
  const e = entries[index];
  if (!e) return;
  const dt = new Date(e.time);
  const weekday = dt.toLocaleDateString("en-US", { weekday: "short" });
  const month = dt.toLocaleDateString("en-US", { month: "short" });
  const day = dt.getDate();
  const hour = dt.getHours();
  const h12 = hour % 12 || 12;
  const ampm = hour >= 12 ? "pm" : "am";
  const timeStr = `${weekday} ${month} ${day}, ${h12}${ampm}`;

  const temp = e.temp != null ? Math.round(e.temp) + "°" : "—°";

  let windStr = "";
  if (e.wind_mph != null && e.gust_mph != null) {
    windStr = ` · Wind ${Math.round(e.wind_mph)} / Gust ${Math.round(e.gust_mph)} mph`;
  } else if (e.gust_mph != null) {
    windStr = ` · Gust ${Math.round(e.gust_mph)} mph`;
  } else if (e.wind_mph != null) {
    windStr = ` · Wind ${Math.round(e.wind_mph)} mph`;
  }

  let impactStr = "";
  if (e.wind_dir != null && (e.wind_mph != null || e.gust_mph != null) && window._combinedWindImpact && window._worryLevel) {
    const score = window._combinedWindImpact(e.wind_mph ?? null, e.gust_mph ?? null, e.wind_dir);
    const level = window._worryLevel(score);
    if (level) impactStr = ` (${level.label.toLowerCase()})`;
  }

  const dewpt = e.dew_point_f != null ? ` · Dew ${Math.round(e.dew_point_f)}°` : "";
  const press = e.pressure_in != null ? ` · ${e.pressure_in.toFixed(2)} inHg` : "";
  const precip = (e.precip_in != null && e.precip_in > 0.005)
    ? ` · ${e.precip_in.toFixed(2)}" rain` : "";

  const timeEl = document.getElementById("obsDataTime");
  const lineEl = document.getElementById("obsDataLine");
  if (timeEl) timeEl.textContent = timeStr + " ·";
  if (lineEl) lineEl.textContent = temp + dewpt + press + windStr + impactStr + precip;
}

function buildObsChart(entries) {
  if (!entries || entries.length === 0) return;
  const canvas = document.getElementById("obsChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (obsChart) obsChart.destroy();

  const todayStr = new Date().toLocaleDateString("en-US");
  const hasWind = entries.some(e => e.wind_mph != null);

  const labels = entries.map(e => {
    const dt = new Date(e.time);
    return dt.toLocaleTimeString("en-US", { hour: "numeric" });
  });
  const temps   = entries.map(e => e.temp ?? null);
  const gusts   = entries.map(e => e.gust_mph ?? null);
  const winds   = entries.map(e => e.wind_mph ?? null);
  const dewpts  = entries.map(e => e.dew_point_f ?? null);
  const pressures = entries.map(e => e.pressure_in ?? null);

  const sustainedImpact = entries.map(e =>
    (e.wind_mph != null && e.wind_dir != null && window._combinedWindImpact)
      ? +(window._combinedWindImpact(e.wind_mph, null, e.wind_dir).toFixed(1))
      : null
  );
  const gustImpact = entries.map(e =>
    (e.gust_mph != null && e.wind_dir != null && window._combinedWindImpact)
      ? +(window._combinedWindImpact(null, e.gust_mph, e.wind_dir).toFixed(1))
      : null
  );

  // Scale pressure to temp axis range for visual trend
  const validTemps = temps.filter(v => v != null);
  const validPress = pressures.filter(v => v != null);
  const tMin = validTemps.length ? Math.min(...validTemps) : 40;
  const tMax = validTemps.length ? Math.max(...validTemps) : 80;
  const pMin = validPress.length ? Math.min(...validPress) : 29.5;
  const pMax = validPress.length ? Math.max(...validPress) : 30.5;
  const pRange = pMax - pMin || 0.01;
  const tRange = tMax - tMin || 10;
  const scaledPressure = pressures.map(p =>
    p != null ? tMin + ((p - pMin) / pRange) * tRange : null
  );

  const dayBgPlugin = {
    id: "obsDayBackground",
    beforeDatasetsDraw(chart) {
      const { ctx, chartArea: { left, top, right, bottom } } = chart;
      const n = entries.length;
      const colW = (right - left) / n;
      ctx.save();
      for (let i = 0; i < n; i++) {
        const isToday = new Date(entries[i].time).toLocaleDateString("en-US") === todayStr;
        ctx.fillStyle = isToday
          ? "rgba(255,200,100,0.04)"
          : "rgba(120,140,200,0.07)";
        ctx.fillRect(left + i * colW, top, colW, bottom - top);
      }
      for (let i = 1; i < n; i++) {
        const prevDay = new Date(entries[i - 1].time).toLocaleDateString("en-US");
        const curDay  = new Date(entries[i].time).toLocaleDateString("en-US");
        if (prevDay !== curDay) {
          const x = left + i * colW;
          ctx.strokeStyle = "rgba(255,255,255,0.18)";
          ctx.lineWidth = 1;
          ctx.setLineDash([3, 3]);
          ctx.beginPath();
          ctx.moveTo(x, top);
          ctx.lineTo(x, bottom);
          ctx.stroke();
          ctx.setLineDash([]);
        }
      }
      ctx.restore();
    }
  };

  // Gust bars: teal-green — distinct from rain blue
  const gustColors = gusts.map(g => g != null ? "rgba(60,200,160,0.6)" : "rgba(0,0,0,0)");

  const maxGust = Math.max(30, ...gusts.filter(g => g != null));
  const y1Max = Math.ceil(maxGust / 10) * 10;

  const datasets = [
    {
      type: "bar",
      label: "Gust (mph)",
      data: gusts,
      yAxisID: "y1",
      backgroundColor: gustColors,
      borderColor: "transparent",
      order: 3,
      borderRadius: { topLeft: 2, topRight: 2, bottomLeft: 0, bottomRight: 0 },
      borderSkipped: false,
    },
    {
      type: "line",
      label: "Temp (°F)",
      data: temps,
      yAxisID: "y",
      tension: 0.3,
      borderColor: "rgba(255,180,80,0.9)",
      backgroundColor: "transparent",
      pointRadius: 0,
      order: 0,
    },
    {
      type: "line",
      label: "Dew Point (°F)",
      data: dewpts,
      yAxisID: "y",
      tension: 0.3,
      borderColor: "rgba(60,130,255,0.9)",
      backgroundColor: "transparent",
      pointRadius: 0,
      borderDash: [3, 3],
      order: 1,
    },
    {
      type: "line",
      label: "Pressure (scaled)",
      data: scaledPressure,
      yAxisID: "y",
      tension: 0.4,
      borderColor: "rgba(180,180,180,0.45)",
      backgroundColor: "transparent",
      pointRadius: 0,
      order: 2,
    }
  ];

  if (hasWind) {
    datasets.push({
      type: "line",
      label: "Wind (mph)",
      data: winds,
      yAxisID: "y1",
      tension: 0.3,
      borderColor: "rgba(160,90,230,0.85)",
      backgroundColor: "transparent",
      pointRadius: 0,
      borderDash: [4, 3],
      order: 2,
    });
  }

  obsChart = new Chart(ctx, {
    plugins: [dayBgPlugin],
    data: { labels, datasets },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      onClick: (event, activeElements) => {
        if (activeElements.length > 0) updateObsDataBar(activeElements[0].index, entries);
      },
      onHover: (event, activeElements) => {
        if (activeElements.length > 0) updateObsDataBar(activeElements[0].index, entries);
      },
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false }
      },
      scales: {
        x: {
          ticks: {
            color: chartTextColor(),
            maxRotation: 0,
            autoSkip: false,
            callback: function(value, index) {
              const dt = new Date(entries[index].time);
              const h = dt.getHours();
              const m = dt.getMinutes();
              if (index === 0) return dt.toLocaleDateString("en-US", { weekday: "short" });
              const prev = new Date(entries[index - 1].time);
              if (prev.getDate() !== dt.getDate()) return dt.toLocaleDateString("en-US", { weekday: "short" });
              if (m < 10 && h % 6 === 0 && h !== 0) return h === 12 ? "12pm" : h < 12 ? h + "am" : (h - 12) + "pm";
              return null;
            },
            font: { size: 10 }
          },
          grid: { color: chartGridColor() }
        },
        y: {
          ticks: { color: chartTextColor(), font: { size: 10 }, callback: v => v + "°" },
          grid: { color: chartGridColor() }
        },
        y1: {
          position: "right",
          min: 0,
          max: y1Max,
          ticks: {
            color: chartTextColor(),
            font: { size: 10 },
            callback: v => (v === 0 || v === Math.round(y1Max / 2) || v === y1Max) ? v + " mph" : null
          },
          grid: { drawOnChartArea: false }
        }
      },
      barPercentage: 0.7,
      categoryPercentage: 0.85
    }
  });

  updateObsDataBar(entries.length - 1, entries);
}

function renderObsChartCollapsedPreview(entries) {
  if (!entries || entries.length === 0) return;

  const todayStr = new Date().toLocaleDateString("en-US");
  const todayEntries = entries.filter(e => new Date(e.time).toLocaleDateString("en-US") === todayStr);
  const yestEntries  = entries.filter(e => new Date(e.time).toLocaleDateString("en-US") !== todayStr);

  const hi = arr => arr.length ? Math.round(Math.max(...arr.map(e => e.temp).filter(v => v != null))) : null;
  const lo = arr => arr.length ? Math.round(Math.min(...arr.map(e => e.temp).filter(v => v != null))) : null;

  const todayHi = hi(todayEntries), todayLo = lo(todayEntries);
  const yestHi  = hi(yestEntries),  yestLo  = lo(yestEntries);

  const fmtRange = (h, l) => (h != null && l != null) ? `${l}°–${h}°` : "—";

  const primaryEl = document.getElementById("obsChartPrimaryCollapsed");
  const secondaryEl = document.getElementById("obsChartSecondaryCollapsed");
  if (primaryEl) primaryEl.textContent = `Today ${fmtRange(todayHi, todayLo)}`;
  if (secondaryEl) secondaryEl.textContent = `Yesterday ${fmtRange(yestHi, yestLo)}`;
}
