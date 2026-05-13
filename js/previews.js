// previews.js — Populate collapsed tile preview text

function populateCollapsedPreviews(data) {
  // Helper to safely set text
  const setText = (id, text) => {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  };
  
  // Helper to safely set HTML
  const setHTML = (id, html) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = html;
  };
  
  // Extract daily and hourly from data
  const daily = data.daily || {};
  const hourly = data.hourly || {};
  
  // ═══════════════════════════════════════════════════════════════
  // ALMANAC TILES
  // ═══════════════════════════════════════════════════════════════
  
  // Today Almanac - show sunrise/sunset times
  const today = new Date();
  const dayName = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"][today.getDay()];
  const monthName = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][today.getMonth()];
  setText("todayDateCollapsed", `${monthName} ${today.getDate()}`);
  setText("todayDayCollapsed", dayName);
  
  // Add sunrise/sunset times
  const sunrise = data.sun?.sunrise;
  const sunset = data.sun?.sunset;
  if (sunrise && sunset) {
    const sunriseTime = new Date(sunrise).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
    const sunsetTime = new Date(sunset).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
    const daylight = data.sun?.daylight_duration || "";
    setHTML("todayTimesCollapsed", `
      <div>Rise ${sunriseTime}</div>
      <div>Set ${sunsetTime}</div>
      ${daylight ? `<div style="opacity:0.65;font-size:0.72rem;margin-top:4px;">${daylight}</div>` : ''}
    `);
  }
  
  // Tides - populated by renderTides()
  
  // Ocean/Buoy - update to new 3-row structure
  const waterTemp = data.salem_water_temp_f ?? data.buoy_44013?.water_temp_f;
  const waveHt = data.buoy_44013?.wave_ht_ft;
  const buoyWind = data.buoy_44013?.wind_mph;
  const buoyDir = data.buoy_44013?.wind_dir;
  if (waterTemp) setText("waterTempCollapsed", `${waterTemp}°F`);
  if (waveHt !== undefined) setText("wavesCollapsed", waveHt > 0 ? `${waveHt} ft` : "Calm");
  if (buoyWind && buoyDir) {
    setText("buoyWindCollapsed", `${buoyWind} mph ${toCompass(buoyDir, false)}`);
  }
  
  // Sun - apply astronomical gradient and populate arc
  const sunCard = document.querySelector('[data-collapse-key="sun"]');
  if (sunCard) {
    sunCard.classList.add('tile-astro');
  }
  
  // Moon - apply astronomical gradient
  const moonCard = document.querySelector('[data-collapse-key="moon"]');
  if (moonCard) {
    moonCard.classList.add('tile-astro');
  }
  
  // Planets - apply astronomical gradient
  const planetsCard = document.querySelector('[data-collapse-key="solar_system"]');
  if (planetsCard) {
    planetsCard.classList.add('tile-astro');
  }
  
  // Frost/Freeze - already populated correctly
  const frostDays = data.frost_stats?.days_since_last_frost;
  if (frostDays !== undefined) {
    setText("frostStatusCollapsed", frostDays === 0 ? "Frost today" : `${frostDays} days since`);
    setText("frostDaysCollapsed", `Last year: ${data.frost_stats?.days_since_last_frost_last_year || "—"}`);
  }
  
  // ═══════════════════════════════════════════════════════════════
  // HYPERLOCAL TILES
  // ═══════════════════════════════════════════════════════════════
  
  renderCorrectionsCard(data);
  
  // Fog Risk - populate and apply gradient
  const fogProb = data.derived?.fog_probability;
  const fogLabel = data.derived?.fog_label;
  if (fogProb !== undefined && fogLabel) {
    setHTML("fogPctCollapsed", `${fogProb}<span style="font-size:1.8rem;opacity:0.6;">%</span>`);
    setText("fogRiskCollapsed", fogLabel);
    
    // Apply fog gradient class
    const fogCard = document.querySelector('[data-collapse-key="fog_risk"]');
    if (fogCard) {
      fogCard.classList.remove('tile-fog-low', 'tile-fog-moderate', 'tile-fog-high');
      if (fogProb < 30) fogCard.classList.add('tile-fog-low');
      else if (fogProb < 60) fogCard.classList.add('tile-fog-moderate');
      else fogCard.classList.add('tile-fog-high');
    }
  } else {
    setHTML("fogPctCollapsed", `--<span style="font-size:1.8rem;opacity:0.6;">%</span>`);
    setText("fogRiskCollapsed", "No data");
  }
  
  // Wind Gust Impact - populated by Right Now card data
  // Wind Sustained Impact - populated by Right Now card data
  // Sea Breeze - populated by renderSeaBreezeDetail()
  // Sunset Quality - populated by renderSunsetQuality()
  // Beach Day - populated by renderDockDay()
}
