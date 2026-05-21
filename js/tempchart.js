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

function buildTempPrecipChart(times, temps, pop, wetBulbs, temps850mb, cloudLow, cloudMid, cloudHigh, cloudTotal, sunrise, sunset, obsEntries) {
  // Prepend observed past hours before the forecast window
  const obsPast = (obsEntries || []).filter(e => e.time < times[0]);
  const allTimes = [...obsPast.map(e => e.time), ...times];
  const obsCount = obsPast.length;

  // Observed temp array: real values for past, null for forecast
  const obsTemps = [
    ...obsPast.map(e => e.temp ?? null),
    ...new Array(times.length).fill(null)
  ];
  // Forecast temp array: null for past, real values for forecast
  const fcTemps = [
    ...new Array(obsCount).fill(null),
    ...temps
  ];
  // Precip / cloud arrays padded with nulls for past
  const allPop       = [...new Array(obsCount).fill(0),   ...pop];
  const allWetBulbs  = [...new Array(obsCount).fill(null), ...wetBulbs];
  const allT850      = [...new Array(obsCount).fill(null), ...temps850mb];
  const allCloudLow  = [...new Array(obsCount).fill(null), ...cloudLow];
  const allCloudMid  = [...new Array(obsCount).fill(null), ...cloudMid];
  const allCloudHigh = [...new Array(obsCount).fill(null), ...cloudHigh];
  const allCloudTotal= [...new Array(obsCount).fill(null), ...cloudTotal];

  const labels = allTimes.map(t => new Date(t).toLocaleTimeString("en-US", { hour: "numeric" }));
  const ctx    = document.getElementById("tempPrecipChart").getContext("2d");
  if (tempPrecipChart) tempPrecipChart.destroy();

  // Precip bar colors by precipitation type (forecast portion only)
  const precipData   = allPop.map(p => p ?? 0);
  const precipColors = allWetBulbs.map((wb, i) => {
    if (i < obsCount) return "rgba(0,0,0,0)"; // no precip bars for observed past
    const surfTemp = fcTemps[i];
    const temp850  = allT850?.[i];
    if (allPop[i] === 0) return "rgba(0,0,0,0)";
    if (wb == null) return "rgba(80,140,255,0.85)";
    if (wb <= 28)   return "rgba(230,240,255,0.95)";
    if (temp850 != null && temp850 > 32 && surfTemp != null && surfTemp < 32) {
      return "rgba(255,140,40,0.85)";
    }
    if (wb <= 32)   return "rgba(180,200,240,0.90)";
    if (wb <= 35)   return "rgba(160,100,220,0.85)";
    return "rgba(80,150,255,0.85)";
  });

  // "NOW" vertical line plugin
  const nowLinePlugin = {
    id: "nowLine",
    afterDatasetsDraw(chart) {
      if (obsCount === 0) return;
      const { ctx, chartArea: { top, bottom }, scales: { x } } = chart;
      const xPos = x.getPixelForValue(obsCount - 0.5);
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(xPos, top);
      ctx.lineTo(xPos, bottom);
      ctx.strokeStyle = "rgba(255,255,255,0.35)";
      ctx.lineWidth = 1;
      ctx.setLineDash([4, 4]);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.font = "9px sans-serif";
      ctx.fillStyle = "rgba(255,255,255,0.4)";
      ctx.textAlign = "center";
      ctx.fillText("NOW", xPos, top + 10);
      ctx.restore();
    }
  };

  // Sky background plugin — paints per-column gradient behind bars on every render
  const skyBgPlugin = {
    id: "skyBackground",
    beforeDatasetsDraw(chart) {
      const { ctx, chartArea: { left, top, right, bottom }, scales } = chart;
      const n = allTimes.length;
      const colW = (right - left) / n;
      ctx.save();
      for (let i = 0; i < n; i++) {
        const time     = new Date(allTimes[i]);
        const hour     = time.getHours() + time.getMinutes() / 60;
        const daylight = (hour >= sunrise && hour <= sunset)
          ? Math.max(0, Math.sin(Math.PI * (hour - sunrise) / (sunset - sunrise)))
          : 0;
        const cc = Math.min(1, (allCloudTotal[i] ?? 0) / 100);
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
    plugins: [skyBgPlugin, nowLinePlugin],
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
          label: "Observed Temp",
          data: obsTemps,
          yAxisID: "y",
          tension: 0.25,
          borderColor: "rgba(120,200,255,0.85)",
          backgroundColor: "transparent",
          pointRadius: 0,
          borderDash: [],
          order: 0,
          spanGaps: false,
        },
        {
          type: "line",
          label: "Forecast Temp",
          data: fcTemps,
          yAxisID: "y",
          tension: 0.25,
          borderColor: "rgba(255,180,80,0.9)",
          backgroundColor: "transparent",
          pointRadius: 0,
          order: 0,
          spanGaps: false,
        }
      ]
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      onClick: (event, activeElements) => {
        if (activeElements.length > 0) {
          updateTempPrecipDataBar(activeElements[0].index, allTimes, [...obsTemps.map((v,i) => v ?? fcTemps[i])], allPop, allWetBulbs, allT850, allCloudLow, allCloudMid, allCloudHigh, allCloudTotal);
        }
      },
      onHover: (event, activeElements) => {
        const dataBar = document.getElementById("tempPrecipDataBar");
        if (dataBar && activeElements.length > 0) {
          updateTempPrecipDataBar(activeElements[0].index, allTimes, [...obsTemps.map((v,i) => v ?? fcTemps[i])], allPop, allWetBulbs, allT850, allCloudLow, allCloudMid, allCloudHigh, allCloudTotal);
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
              const dt = new Date(allTimes[index]);
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
