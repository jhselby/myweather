// feelslike.js — Feels-like card + fog detail

function renderFeelsLikeCard(data) {
  const hyp = data.hyperlocal || {};
  const cur = data.current || {};
  const hourly = data.hourly || {};

  // Current corrected values for tile front
  const T = hyp.corrected_temp ?? cur.temperature;
  const wind = hyp.corrected_wind_speed ?? cur.wind_speed ?? 0;
  const RH = hyp.corrected_humidity ?? cur.humidity ?? 50;

  // Use corrected feels-like from collector (single source of truth)
  const der = data.derived || {};
  const feelsLike = der.corrected_feels_like ?? T;
  // Update tile front
  const valEl = document.getElementById("feelsLikeCardValue");
  const lblEl = document.getElementById("feelsLikeCardLabel");
  const light = isLight();
  if (valEl) valEl.textContent = T != null ? Math.round(feelsLike) + "\u00b0" : "--\u00b0";
  if (lblEl) {
    lblEl.textContent = "Feels Like";
    lblEl.style.color = light ? "rgba(0,0,0,0.6)" : "rgba(255,255,255,0.6)";
  }

  // Build 48-hour dataset from HRRR hourly
  const times  = hourly.times       || [];
  const htemps = hourly.corrected_temperature || hourly.temperature || [];
  const hApparent = hourly.corrected_apparent_temperature || hourly.apparent_temperature || [];

  const chartTimes = [], chartFL = [], chartAir = [];
  for (let i = 0; i < times.length; i++) {
    chartTimes.push(times[i]);
    chartAir.push(htemps[i] != null ? Math.round(htemps[i]) : null);
    chartFL.push(hApparent[i] != null ? Math.round(hApparent[i]) : null);
  }

  // Data bar update
  function updateFLDataBar(idx) {
    const timeEl = document.getElementById("feelsLikeDataTime");
    const lineEl = document.getElementById("feelsLikeDataLine");
    if (!timeEl || !lineEl || idx == null || idx < 0) return;
    const dt = new Date(chartTimes[idx]);
    const hour = dt.getHours();
    const nextHour = (hour + 1) % 24;
    const weekday = dt.toLocaleDateString("en-US", { weekday: "short" });
    const month   = dt.toLocaleDateString("en-US", { month: "short" });
    const day     = dt.getDate();
    const timeStr = `${weekday} ${month} ${day}, ${hour % 12 || 12}-${nextHour % 12 || 12}${nextHour < 12 ? "am" : "pm"}`;
    const fl  = chartFL[idx]  != null ? chartFL[idx]  + "\u00b0F" : "--";
    const air = chartAir[idx] != null ? chartAir[idx] + "\u00b0F" : "--";
    timeEl.textContent = timeStr + " \u00b7";
    lineEl.textContent = `Feels Like: ${fl} \u00b7 Air: ${air}`;
  }

  const lineColor = "rgba(180,180,255,0.8)";
  const fillColor = "rgba(180,180,255,0.05)";

  const canvas = document.getElementById("feelsLikeChart");
  if (!canvas || !chartFL.length) return;
  if (canvas._flChart) { canvas._flChart.destroy(); canvas._flChart = null; }

  const textColor = chartTextColor();
  const gridColor = chartGridColor();
  const labels = chartTimes.map(t => new Date(t).toLocaleTimeString("en-US", { hour: "numeric" }));

  canvas._flChart = new Chart(canvas, {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Feels Like",
          data: chartFL,
          borderColor: lineColor,
          backgroundColor: fillColor,
          borderWidth: 2,
          fill: true,
          tension: 0.4,
          pointRadius: 0,
        },
        {
          label: "Air Temp",
          data: chartAir,
          borderColor: isLight() ? "rgba(100,100,100,0.4)" : "rgba(200,200,200,0.4)",
          backgroundColor: isLight() ? "rgba(100,100,100,0.4)" : "rgba(200,200,200,0.4)",
          borderDash: [4, 4],
          borderWidth: 1,
          fill: false,
          tension: 0.4,
          pointRadius: 0,
        }
      ]
    },
    options: {
      responsive: true,
      interaction: { mode: "index", intersect: false },
      onClick: (event, activeElements) => {
        if (activeElements.length > 0) updateFLDataBar(activeElements[0].index);
      },
      onHover: (event, activeElements) => {
        if (activeElements.length > 0) updateFLDataBar(activeElements[0].index);
      },
      plugins: {
        legend: { display: false },
        tooltip: { enabled: false }
      },
      scales: {
        x: {
          ticks: {
            color: textColor,
            font: { size: 10 },
            maxRotation: 0,
            autoSkip: false,
            callback: function(value, index) {
              const dt = new Date(chartTimes[index]);
              const h = dt.getHours();
              const m = dt.getMinutes();
              if (m !== 0) return null;
              if (h === 0) return dt.toLocaleDateString("en-US", { weekday: "short" });
              if (h % 6 === 0) return h === 12 ? "12pm" : h < 12 ? h + "am" : (h-12) + "pm";
              return null;
            }
          },
          grid: { color: gridColor }
        },
        y: {
          ticks: { color: textColor, font: { size: 9 }, callback: v => v + "\u00b0" },
          grid: { color: gridColor }
        }
      }
    }
  });

  // Init data bar to current hour
  const nowIso = new Date().toISOString().slice(0, 13);
  const initIdx = chartTimes.findIndex(t => t.slice(0, 13) >= nowIso);
  updateFLDataBar(initIdx >= 0 ? initIdx : 0);
}


    function renderFogDetail(data) {
  const der = data.derived || {};
  const cur = data.current || {};
  
  // Update the main values
  const labelEl = document.getElementById("fogCurrentLabel");
  const probEl = document.getElementById("fogCurrentProb");
  
  const fogLabel = der.fog_label ?? "--";
  const fogProb = der.fog_probability;
  
  // Build fog headline
  let fogHeadline;
  const fogLikelihood = fogProb ?? 0;
  if (fogLikelihood >= 60) {
    fogHeadline = `Fog likely — air near saturation`;
  } else if (fogLikelihood >= 30) {
    fogHeadline = `Fog possible — humidity borderline`;
  } else if (fogLikelihood > 0) {
    fogHeadline = `Low fog risk — air is too dry`;
  } else {
    fogHeadline = `No fog risk`;
  }
  const fogHeadlineColor = fogLikelihood >= 60 ? "rgba(220,200,60,0.9)" : fogLikelihood >= 30 ? "rgba(200,160,60,0.85)" : "rgba(100,200,120,0.9)";

  // Inject or update headline element above the card rows
  let fogHLEl = document.getElementById("fogHeadline");
  if (!fogHLEl) {
    fogHLEl = document.createElement("div");
    fogHLEl.id = "fogHeadline";
    fogHLEl.style.cssText = "font-size:0.95rem;font-weight:600;margin-bottom:14px;padding:10px 14px;background:rgba(255,255,255,0.04);border-radius:0;";
    const fogBody = document.querySelector('[data-collapse-key="fog_risk"] .card-body');
    if (fogBody) fogBody.insertBefore(fogHLEl, fogBody.firstChild);
  }
  if (fogHLEl) {
    fogHLEl.textContent = fogHeadline;
    fogHLEl.style.color = fogHeadlineColor;
    fogHLEl.style.borderLeft = `3px solid ${fogHeadlineColor}`;
  }

  if (labelEl) labelEl.textContent = fogLabel;
  if (probEl) probEl.textContent = fogProb != null ? `${fogProb}%` : "--";
  
  // Calculate the inputs and effects for the breakdown table
  const hyp = data.hyperlocal || {};
  const temp = hyp.corrected_temp ?? cur.temperature;
  const humidity = hyp.corrected_humidity ?? cur.humidity;
  const dewpt = der.corrected_dew_point ?? cur.dew_point;
  const windSpeed = hyp.corrected_wind_speed ?? cur.wind_speed;
  
  const spread = (temp != null && dewpt != null) ? temp - dewpt : null;
  
  // Determine spread effect
  let spreadEffect = "--";
  if (spread != null) {
    if (spread <= 2.0) spreadEffect = "85% base";
    else if (spread <= 3.5) spreadEffect = "60% base";
    else if (spread <= 5.0) spreadEffect = "30% base";
    else spreadEffect = "0% (too dry)";
  }
  
  // Determine humidity effect
  let humidityEffect = "--";
  if (humidity != null) {
    if (humidity >= 95) humidityEffect = "+10%";
    else if (humidity >= 90) humidityEffect = "+5%";
    else if (humidity < 80) humidityEffect = "-15%";
    else humidityEffect = "0%";
  }
  
  // Determine wind effect
  let windEffect = "--";
  if (windSpeed != null) {
    if (windSpeed <= 3) windEffect = "+10%";
    else if (windSpeed >= 10) windEffect = "-20%";
    else if (windSpeed >= 7) windEffect = "-10%";
    else windEffect = "0%";
  }
  
  const spreadEl = document.getElementById("fogSpreadValue");
  const spreadEffEl = document.getElementById("fogSpreadEffect");
  const humidityEl = document.getElementById("fogHumidityValue");
  const humidityEffEl = document.getElementById("fogHumidityEffect");
  const windEl = document.getElementById("fogWindValue");
  const windEffEl = document.getElementById("fogWindEffect");
  
  if (spreadEl) spreadEl.textContent = spread != null ? `${spread.toFixed(1)}°F` : "--";
  if (spreadEffEl) spreadEffEl.textContent = spreadEffect;
  if (humidityEl) humidityEl.textContent = humidity != null ? `${Math.round(humidity)}%` : "--";
  if (humidityEffEl) humidityEffEl.textContent = humidityEffect;
  if (windEl) windEl.textContent = windSpeed != null ? `${windSpeed.toFixed(1)} mph` : "--";
  if (windEffEl) windEffEl.textContent = windEffect;
}
