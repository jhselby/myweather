// sources.js — data source metadata and Sources card rendering

const SOURCE_META = {
  gfs_current:  { name: "GFS",          desc: "Global Forecast System — current conditions baseline (NOAA)" },
  hrrr_hourly:  { name: "HRRR",         desc: "High-Resolution Rapid Refresh — 48h hourly forecast, cloud layers, upper-air (NOAA)" },
  ecmwf_daily:  { name: "ECMWF",        desc: "European Centre model — 10-day daily forecast (Open-Meteo)" },
  pws:          { name: "PWS",           desc: "Single weather station KMAMARBL63 (Castle Hill, 0.27mi) — fallback only" },
  wu_stations:  { name: "WU Multi",     desc: "Distance- and elevation-weighted, quality-filtered local personal weather stations" },
  kbos:         { name: "KBOS",         desc: "Boston Logan Airport ASOS — observed temp, pressure, tendency (NWS/aviationweather.gov)" },
  kbvy:         { name: "KBVY",         desc: "Beverly Airport ASOS — observed temp, wind (NWS/aviationweather.gov)" },
  buoy_44013:   { name: "Buoy 44013",   desc: "NOAA Boston Buoy (16mi ENE) — water temp, waves, offshore wind (NDBC)" },
  tides:        { name: "Tides",        desc: "NOAA CO-OPS tide predictions — Salem Harbor station 8442645" },
  nws_alerts:   { name: "NWS Alerts",   desc: "Active NWS watches, warnings, advisories for Marblehead (api.weather.gov)" },
  pirate_weather: { name: "Pirate Weather", desc: "Pirate Weather API — next 60 minutes precipitation, plus solar and CAPE" },
  ebird:        { name: "eBird",        desc: "Cornell eBird recent and notable bird observations near Marblehead" },
  gemini:       { name: "Gemini 2.5 Flash-Lite", desc: "Google Gemini AI — primary briefing headline generator (free tier)" },
  groq:         { name: "Groq", desc: "Groq AI — fallback briefing waterfall: openai/gpt-oss-120b → llama-3.3-70b-versatile (free tier)" },
  tempest:      { name: "Tempest",      desc: "WeatherFlow Tempest — 3 public stations within 0.4mi (Willow Rd, Driftwood Rd, Neptune Rd); lightning, solar radiation, wind lull, wet bulb" },
};

const STATIC_SOURCES = [
  { name: "IEM NEXRAD",   desc: "Radar tile source — NOAA NEXRAD base reflectivity composite via Iowa Environmental Mesonet, 5-minute archives (mesonet.agron.iastate.edu)" },
  { name: "CartoDB",      desc: "Dark Matter basemap tiles for radar view — no API key required (carto.com)" },
  { name: "SunCalc",      desc: "Client-side sun/moon position and phase calculations (mourner/suncalc)" },
  { name: "VSOP87",       desc: "Client-side planetary position calculations — solar system card (truncated series, ~1° accuracy)" },
  { name: "Open-Meteo",   desc: "Cloud layer data (low/mid/high) for sunset quality forecast — HRRR product" },
];

function _fmtError(err) {
  if (!err) return '';
  const s = String(err);
  const httpMatch = s.match(/\b([45]\d{2})\b/);
  if (httpMatch) {
    const code = httpMatch[1];
    const labels = { '429': 'Rate limited', '404': 'Not found', '500': 'Server error',
                     '502': 'Bad gateway', '503': 'Unavailable', '504': 'Gateway timeout' };
    return labels[code] ? `${code} ${labels[code]}` : `HTTP ${code}`;
  }
  if (/connection reset/i.test(s))   return 'Connection reset';
  if (/connection aborted/i.test(s)) return 'Connection aborted';
  if (/timed?\s*out/i.test(s))       return 'Timeout';
  if (/ssl/i.test(s))                return 'SSL error';
  if (/connection/i.test(s))         return 'Connection error';
  return s.replace(/\s+/g, ' ').slice(0, 50);
}

function renderSources(sources, pwsStale) {
  if (!sources) return;
  const order = Object.keys(SOURCE_META);

  // Only critical sources trigger the alert dot — supplementary failures are silent
  const CRITICAL_SOURCES = new Set(['gfs_current', 'hrrr_hourly', 'wu_stations', 'pirate_weather', 'nws_alerts']);
  let anyError = false;
  let anyCriticalError = false;
  order.forEach(key => {
    const s = sources[key];
    if (s && s.status !== "ok") {
      anyError = true;
      if (CRITICAL_SOURCES.has(key)) anyCriticalError = true;
    }
  });
  // Briefing counts as critical only if both Gemini and Groq are unavailable.
  // briefing.model is "gemini" or "groq/<model-id>" (v0.6.130+).
  const briefingModel = window.__lastWeatherData?.briefing?.model;
  const briefingProvider = briefingModel?.startsWith("groq/") ? "groq" : briefingModel;
  const geminiOk = sources['gemini']?.status === 'ok' || briefingProvider === 'gemini';
  const groqOk   = sources['groq']?.status === 'ok'   || briefingProvider === 'groq';
  if (!geminiOk && !groqOk) anyCriticalError = true;

  const table = document.getElementById("sourcesTable");
  const tableModal = document.getElementById("sourcesTableModal");
  if (!table && !tableModal) return;
  const renderTarget = table || tableModal;
  const pwsName = pwsStale ? "PWS (cached)" : "PWS (live)";

  const rowStyle = "display:flex;gap:8px;align-items:baseline;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);flex-wrap:wrap;";
  const nameStyle = "font-weight:800;color:rgba(255,255,255,0.9);font-size:0.85rem;min-width:90px;flex-shrink:0;";
  const descStyle = "color:rgba(255,255,255,0.5);font-size:0.8rem;flex:1;min-width:0;";
  const badgeStyle = ok => `font-size:0.75rem;font-weight:800;white-space:nowrap;color:${ok ? "rgba(140,240,160,0.9)" : "rgba(255,120,120,0.9)"};`;
  const ageStyle  = ok => `font-size:0.75rem;font-weight:700;color:${ok ? "rgba(255,255,255,0.4)" : "rgba(255,120,120,0.7)"};white-space:nowrap;`;

  renderTarget.innerHTML = `
    <div style="font-weight:900;font-size:0.75rem;color:rgba(255,255,255,0.35);letter-spacing:0.8px;text-transform:uppercase;margin-bottom:8px;">Live Data Sources</div>
    ${order.map(key => {
      const s = sources[key];
      // briefing.model is "gemini" or "groq/<model-id>" (v0.6.130+).
      const briefingModel = window.__lastWeatherData?.briefing?.model || "gemini";
      const briefingProvider = briefingModel.startsWith("groq/") ? "groq" : briefingModel;
      const isBriefingSource = key === "gemini" || key === "groq";
      const isActiveBriefingSource = isBriefingSource && key === briefingProvider;
      const isStandbyBriefingSource = isBriefingSource && key !== briefingProvider;
      if (!s && !isBriefingSource) return "";
      const ok = isBriefingSource ? isActiveBriefingSource : s.status === "ok";
      let age = "--";
      if (isActiveBriefingSource && window.__lastWeatherData?.briefing?.cached_at) {
        const cachedAt = new Date(window.__lastWeatherData.briefing.cached_at);
        age = Math.round((Date.now() - cachedAt.getTime()) / 60000) + "m ago";
      } else if (isStandbyBriefingSource) {
        age = "standby";
      } else if (s && typeof s.age_minutes === "number") {
        age = Math.round(s.age_minutes) + "m ago";
      }
      const meta = SOURCE_META[key];
      const name = key === "pws" ? pwsName : meta.name;

      let extraDetail = "";
      if (key === "wu_stations" && ok) {
        const wu = window.__lastWeatherData?.wu_stations;
        const tempest = window.__lastWeatherData?.tempest;
        if (wu && wu.stations) {
          const quality = wu.quality || {};
          const tempestStations = tempest?.stations || [];
          const allStations = [
            ...wu.stations.map(st => ({
              label: st.station_id,
              dist: st.distance_mi,
              temp: st.temperature_f != null ? st.temperature_f.toFixed(1) + "°F" : "---",
              wind: st.wind_speed_mph != null ? st.wind_speed_mph.toFixed(1) + " mph" : "---",
              tag: "WU",
              valid: true,
            })),
            ...tempestStations.map(st => ({
              label: st.station_name,
              dist: st.distance_mi,
              temp: st.temperature_f != null ? st.temperature_f.toFixed(1) + "°F" : "---",
              wind: st.wind_avg_mph != null ? st.wind_avg_mph.toFixed(1) + " mph" : "---",
              tag: "T",
              valid: st.valid !== false,
            })),
          ].sort((a, b) => a.dist - b.dist);
          extraDetail = `
            <div style="margin-top:8px;padding:10px;background:rgba(255,255,255,0.03);border-radius:8px;font-size:0.75rem;">
              <div style="font-weight:800;margin-bottom:6px;color:rgba(255,255,255,0.7);">
                ${allStations.length} Stations • ${quality.stations_used_temp || 0} used for temp • ${quality.stations_used_wind || 0} used for wind
              </div>
              <div style="color:rgba(255,255,255,0.5);line-height:1.6;">
                ${allStations.map(st =>
                  `<span style="color:rgba(255,255,255,0.3);font-size:0.7rem;">[${st.tag}]</span> ${st.label} (${st.dist}mi) - ${st.temp}, ${st.wind}${st.valid ? "" : " ⚠︎"}`
                ).join('<br>')}
              </div>
            </div>`;
        }
      }

      const rowOpacity = isStandbyBriefingSource ? "opacity:0.4;" : "";
      const standbyTag = isStandbyBriefingSource ? ` <span style="font-size:0.7rem;opacity:0.6;">(standby)</span>` : "";
      // v0.6.131: stale-rescue detection. When generate_briefing() falls
      // through to the "last-good cached" branch because every live LLM tier
      // failed/was-rejected this tick, the collector stamps briefing.stale=true.
      // Surface that visually so an old-but-still-displayed briefing reads as
      // a stale rescue instead of a "fresh" headline that just happens to be
      // aging within the throttle window.
      const briefingStale = window.__lastWeatherData?.briefing?.stale === true;
      // When the Groq waterfall is active, surface WHICH Groq model is
      // serving (briefing.model is e.g. "groq/openai/gpt-oss-120b"). For
      // Gemini we already know the model id from the static name.
      let activeDetail = "";
      if (isActiveBriefingSource && key === "groq" && briefingModel.startsWith("groq/")) {
        activeDetail = `: ${briefingModel.slice(5)}`;
      }
      const activeTagColor = (isActiveBriefingSource && briefingStale)
        ? "rgba(250,180,80,0.9)"   // amber — stale rescue
        : "rgba(100,220,100,0.8)"; // green — fresh/throttled-normal
      const activeTagLabel = (isActiveBriefingSource && briefingStale)
        ? `stale rescue${activeDetail}`
        : `active${activeDetail}`;
      const activeTag = isActiveBriefingSource
        ? ` <span style="font-size:0.7rem;color:${activeTagColor};">(${activeTagLabel})</span>`
        : "";
      return `<div style="${rowStyle}${rowOpacity}">
        <span style="${badgeStyle(ok)}">${ok ? "●" : "○"}</span> <span style="${nameStyle}">${name}${activeTag}${standbyTag}</span>
        <span style="${ageStyle(ok)}">${age}</span>
        <span style="${descStyle}">${meta.desc}${s?.error ? ` <span style="color:rgba(255,120,120,0.8);">— ${_fmtError(s.error)}</span>` : ""}</span>
        ${extraDetail}
      </div>`;
    }).join("")}

    <div style="font-weight:900;font-size:0.75rem;color:rgba(255,255,255,0.35);letter-spacing:0.8px;text-transform:uppercase;margin:18px 0 8px;">Client-Side &amp; Static</div>
    ${STATIC_SOURCES.map(s => `
      <div style="${rowStyle}">
        <span style="${nameStyle}">📦 ${s.name}</span>
        <span style="${descStyle}">${s.desc}</span>
      </div>`).join("")}
  `;
  if (tableModal) tableModal.innerHTML = renderTarget.innerHTML;

  const srcDot = document.getElementById("sourcesStatusDot");
  if (srcDot) {
    srcDot.style.display = "inline-block";
    srcDot.style.background = anyError ? "#ef4444" : "#4ade80";
  }

  const settingsDot = document.getElementById("settingsAlertDot");
  if (settingsDot) {
    const genAt = window.__lastWeatherData?.generated_at;
    const staleMinutes = genAt ? (Date.now() - new Date(genAt).getTime()) / 60000 : 999;
    const isStale = staleMinutes > 25;
    // Light the gear only when the data shown is actually bad — stale, or
    // briefing genuinely empty. Transient source failures that the fallback
    // chain covers (Open-Meteo 429 with Pirate Weather backfill, Gemini 503
    // with cached headline, etc.) stay silent here. The sources-panel dot
    // still shows red on any source error for debug visibility.
    const briefing = window.__lastWeatherData?.briefing || {};
    const briefingEmpty = !briefing.headline;
    settingsDot.style.display = (isStale || briefingEmpty) ? "block" : "none";
  }
}
