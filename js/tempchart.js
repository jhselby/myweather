// tempchart.js — 48h temperature / precipitation chart

// ======================================================
// Charts
// ======================================================
let tempPrecipChart = null;

function updateTempPrecipDataBar(index, times, temps, pop, wetBulbs, temps850mb, cloudLow, cloudMid, cloudHigh, cloudTotal) {
  const time = times[index];
  const temp = temps[index];
  const precipProb = pop[index] ?? 0;
  const wb = wetBulbs[index];
  const surfTemp = temps[index];
  const temp850 = temps850mb?.[index];
  
  const dt = new Date(time);
  const hour = dt.getHours();
  const nextHour = (hour + 1) % 24;
  const weekday = dt.toLocaleDateString("en-US", { weekday: "short" });
  const month = dt.toLocaleDateString("en-US", { month: "short" });
  const day = dt.getDate();
  const timeStr = `${weekday} ${month} ${day}, ${hour % 12 || 12}-${nextHour % 12 || 12}${nextHour < 12 ? 'am' : 'pm'}`;
  let typeStr = "none";
  if (precipProb > 0 && wb != null) {
    if (wb <= 28) typeStr = "snow";
    else if (wb <= 32) typeStr = "snow likely";
    else if (wb <= 35) typeStr = "mixed/slush";
    else if (temp850 != null && temp850 > 32 && surfTemp != null && surfTemp < 32) {
      typeStr = "freezing rain";
    }
    else typeStr = "rain";
  }

  const cloudPct = cloudTotal[index] != null ? Math.round(cloudTotal[index]) : 0;
  const sunPct = 100 - cloudPct;
  const skyStr = cloudPct >= sunPct ? `${cloudPct}% clouds` : `${sunPct}% sun`;

  document.getElementById("tempPrecipDataTime").textContent = timeStr + " ·";
  document.getElementById("tempPrecipDataLine").textContent =
    `${temp != null ? Math.round(temp) : "—"}° · ${precipProb}% ${typeStr} · ${skyStr}`;
}

function buildTempPrecipChart(times, temps, pop, wetBulbs, temps850mb, cloudLow, cloudMid, cloudHigh, cloudTotal, sunrise, sunset, precipIntensity) {
  const labels = times.map(t => new Date(t).toLocaleTimeString("en-US", { hour: "numeric" }));
  const ctx    = document.getElementById("tempPrecipChart").getContext("2d");
  if (tempPrecipChart) tempPrecipChart.destroy();

  // Precip bar colors by type, shaded light→dark blue by rain intensity
  const precipData   = pop.map(p => p ?? 0);
  const maxIntensity = precipIntensity ? Math.max(...precipIntensity.map(v => v ?? 0), 0.01) : 1;
  const precipColors = (wetBulbs || []).map((wb, i) => {
    const surfTemp = temps[i];
    const temp850  = temps850mb?.[i];
    if (pop[i] === 0) return "rgba(0,0,0,0)";
    // Snow, ice, sleet — keep fixed type colors
    if (wb != null && wb <= 28)   return "rgba(230,240,255,0.95)";
    if (temp850 != null && temp850 > 32 && surfTemp != null && surfTemp < 32) {
      return "rgba(255,140,40,0.85)";
    }
    if (wb != null && wb <= 32)   return "rgba(180,200,240,0.90)";
    if (wb != null && wb <= 35)   return "rgba(160,100,220,0.85)";
    // Rain: shade light→dark blue by intensity
    const intensity = precipIntensity?.[i] ?? 0;
    const t = Math.min(intensity / 0.40, 1.0); // 0.40 in/hr = full dark
    const r = Math.round(140 - 100 * t);  // 140 → 40
    const g = Math.round(190 - 140 * t);  // 190 → 50
    const b = Math.round(255 - 55  * t);  // 255 → 200
    const a = (0.45 + 0.50 * t).toFixed(2);
    return `rgba(${r},${g},${b},${a})`;
  });

  // Sky background plugin — paints per-column gradient behind bars on every render
  const skyBgPlugin = {
    id: "skyBackground",
    beforeDatasetsDraw(chart) {
      const { ctx, chartArea: { left, top, right, bottom }, scales } = chart;
      const n = times.length;
      const colW = (right - left) / n;
      ctx.save();
      for (let i = 0; i < n; i++) {
        const time     = new Date(times[i]);
        const hour     = time.getHours() + time.getMinutes() / 60;
        const daylight = (hour >= sunrise && hour <= sunset)
          ? Math.max(0, Math.sin(Math.PI * (hour - sunrise) / (sunset - sunrise)))
          : 0;
        const cc = Math.min(1, (cloudTotal[i] ?? 0) / 100);
        const x0 = left + i * colW;

        // Sky color: blend sunny yellow → cloudy gray, modulated by daylight
        // Heavy clouds (cc > 0.7) pull hard to cool gray regardless of sun
        const cloudWeight = Math.pow(cc, 0.6); // non-linear: clouds dominate quickly
        const sunWeight   = (1 - cloudWeight) * daylight;
        const twlWeight   = (1 - cloudWeight) * Math.max(0, daylight > 0 ? 0 : 0) ;

        // Base colors
        const sunR = 255, sunG = 210, sunB = 55;          // warm yellow
        const twlR = 220, twlG = 130, twlB = 40;          // twilight orange
        const cldDayR = 95,  cldDayG = 100, cldDayB = 115; // cool overcast day
        const cldNgtR = 15,  cldNgtG = 20,  cldNgtB = 45;  // dark overcast night
        const clrNgtR = 10,  clrNgtG = 15,  clrNgtB = 40;  // clear night

        let r, g, b, a;
        if (daylight > 0) {
          // Daytime or twilight: blend sun vs overcast
          const daylitCloudR = cldDayR + (cldNgtR - cldDayR) * (1 - daylight);
          const daylitCloudG = cldDayG + (cldNgtG - cldDayG) * (1 - daylight);
          const daylitCloudB = cldDayB + (cldNgtB - cldDayB) * (1 - daylight);
          r = Math.round(sunR * sunWeight + daylitCloudR * cloudWeight + sunR * (1 - cloudWeight - sunWeight));
          g = Math.round(sunG * sunWeight + daylitCloudG * cloudWeight + sunG * (1 - cloudWeight - sunWeight));
          b = Math.round(sunB * sunWeight + daylitCloudB * cloudWeight + sunB * (1 - cloudWeight - sunWeight));
          // Twilight tint when daylight is low
          if (daylight < 0.3) {
            const tw = (0.3 - daylight) / 0.3;
            r = Math.round(r * (1 - tw * 0.4) + twlR * tw * 0.4);
            g = Math.round(g * (1 - tw * 0.4) + twlG * tw * 0.4);
            b = Math.round(b * (1 - tw * 0.4) + twlB * tw * 0.4);
          }
          a = 0.32 + sunWeight * 0.18;
        } else {
          // Nighttime
          r = Math.round(clrNgtR + (cldNgtR - clrNgtR) * cc);
          g = Math.round(clrNgtG + (cldNgtG - clrNgtG) * cc);
          b = Math.round(clrNgtB + (cldNgtB - clrNgtB) * cc);
          a = 0.55 + cc * 0.1;
        }

        const grad = ctx.createLinearGradient(0, top, 0, bottom);
        grad.addColorStop(0, `rgba(${r},${g},${b},${a.toFixed(2)})`);
        grad.addColorStop(1, `rgba(${r},${g},${b},${(a * 0.35).toFixed(2)})`);
        ctx.fillStyle = grad;
        ctx.fillRect(x0, top, colW, bottom - top);
      }
      ctx.restore();
    }
  };

  tempPrecipChart = new Chart(ctx, {
    plugins: [skyBgPlugin],
    data: {
      labels,
      datasets: [
        {
          type: "bar",
          label: "Precip %",
          data: precipData,
          yAxisID: "y1",
          backgroundColor: precipColors,
          borderColor: "transparent",
          order: 1,
          borderRadius: { topLeft: 3, topRight: 3, bottomLeft: 0, bottomRight: 0 },
          borderSkipped: false,
        },
        {
          type: "line",
          label: "Temp (°F)",
          data: temps.map(v => v ?? null),
          yAxisID: "y",
          tension: 0.25,
          borderColor: "rgba(255,180,80,0.9)",
          backgroundColor: "transparent",
          pointRadius: 0,
          order: 0,
        }
      ]
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      onClick: (event, activeElements) => {
        if (activeElements.length > 0) {
          updateTempPrecipDataBar(activeElements[0].index, times, temps, pop, wetBulbs, temps850mb, cloudLow, cloudMid, cloudHigh, cloudTotal);
        }
      },
      onHover: (event, activeElements) => {
        const dataBar = document.getElementById("tempPrecipDataBar");
        if (dataBar && activeElements.length > 0) {
          updateTempPrecipDataBar(activeElements[0].index, times, temps, pop, wetBulbs, temps850mb, cloudLow, cloudMid, cloudHigh, cloudTotal);
        }
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
              const dt = new Date(times[index]);
              const h = dt.getHours();
              const m = dt.getMinutes();
              if (m !== 0) return null;
              if (h === 0) {
                const day = dt.toLocaleDateString("en-US", { weekday: "short" });
                return day;
              }
              if (h % 6 === 0) {
                return h === 12 ? "12pm" : h < 12 ? h + "am" : (h - 12) + "pm";
              }
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
          position: "right", min: 0, max: 100,
          ticks: { color: chartTextColor(), font: { size: 10 }, callback: v => v === 0 || v === 50 || v === 100 ? v + "%" : null },
          grid: { drawOnChartArea: false }
        }
      },
      barPercentage: 0.55,
      categoryPercentage: 0.70
    }
  });
}
