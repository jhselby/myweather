// ======================================================
    // Settings — theme + pressure units
    // ======================================================
    let _pressureUnit = localStorage.getItem('pressureUnit') || 'hpa';

    function toggleSettings() {
      const panel = document.getElementById('settingsPanel');
      panel.style.display = panel.style.display === 'none' ? '' : 'none';
    }

    function setTheme(mode) {
      localStorage.setItem('theme', mode);
      applyTheme(mode);
      updateSettingBtns();
    }

    function applyTheme(mode) {
      const body = document.body;
      body.classList.remove('theme-light', 'theme-dark');
      const isLight = mode === 'light' || (mode === 'system' && window.matchMedia('(prefers-color-scheme: light)').matches);
      if (isLight) {
        body.classList.add('theme-light');
        document.documentElement.style.background = '#f0f2f5';
        document.querySelector('meta[name="theme-color"]')?.setAttribute('content', '#f0f2f5');
      } else {
        document.documentElement.style.background = '#0b1220';
        document.querySelector('meta[name="theme-color"]')?.setAttribute('content', '#0b1220');
      }
    }

    function setPressureUnit(unit) {
      _pressureUnit = unit;
      localStorage.setItem('pressureUnit', unit);
      updateSettingBtns();
      rerenderPressure();
    }

    function updateSettingBtns() {
      const theme = localStorage.getItem('theme') || 'system';
      ['themeLight','themeDark','themeSystem'].forEach(id => {
        document.getElementById(id)?.classList.remove('active');
      });
      const map = { light:'themeLight', dark:'themeDark', system:'themeSystem' };
      document.getElementById(map[theme])?.classList.add('active');

      ['pressHpa','pressInhg'].forEach(id => document.getElementById(id)?.classList.remove('active'));
      document.getElementById(_pressureUnit === 'inhg' ? 'pressInhg' : 'pressHpa')?.classList.add('active');
    }

    function isLight() {
      return document.body.classList.contains('theme-light');
    }
    function chartTextColor() {
      return document.body.classList.contains('theme-light')
        ? "rgba(0,0,0,0.7)" : "rgba(255,255,255,0.85)";
    }
    function chartGridColor() {
      return document.body.classList.contains('theme-light')
        ? "rgba(0,0,0,0.08)" : "rgba(255,255,255,0.06)";
    }

    function hpaToInhg(hpa) {
      return (hpa * 0.02953).toFixed(2);
    }

    function fmtPressure(hpaVal) {
      if (hpaVal == null || hpaVal === '--') return '--';
      const n = parseFloat(hpaVal);
      if (isNaN(n)) return hpaVal;
      return _pressureUnit === 'inhg'
        ? hpaToInhg(n) + ' inHg'
        : n.toFixed(1) + ' hPa';
    }
    function degToCompass(deg) {
      if (deg == null) return "";
      const directions = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];
      const index = Math.round(((deg % 360) / 22.5));
      return directions[index % 16];
    }

    // Re-render all pressure fields using last fetched data
    function rerenderPressure() {
      const data = window.__lastWeatherData;
      if (!data) return;
      const h = data.hourly || {};
      const cur = Array.isArray(h.time) ? 0 : null;

      // Today's Summary
      const pModel = h.surface_pressure?.[0];
      const pEl = document.getElementById('pressureNow');
      if (pEl && pModel != null) pEl.textContent = fmtPressure(pModel);

      // Wind tab pressure now
      const wpEl = document.getElementById('windNowPressure');
      if (wpEl && pModel != null) wpEl.textContent = fmtPressure(pModel);

      // Buoy pressure
      const buoyP = window.__lastBuoyPressure;
      const bpEl = document.getElementById('buoyPressure');
      if (bpEl && buoyP != null) bpEl.textContent = fmtPressure(buoyP);
    }

    // Apply theme on load
    (function() {
      applyTheme(localStorage.getItem('theme') || 'system');
      // Listen for system theme changes
      window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
        if ((localStorage.getItem('theme') || 'system') === 'system') applyTheme('system');
      });
    })();

    // ======================================================
    // Tab behavior — Weather / Wind / Almanac
    // ======================================================
    function showTab(which) {
      const views = { weather: "weatherView", almanac: "almanacView", overhead: "overheadView", hyperlocal: "hyperlocalView", sources: "sourcesView" };
      const tabs  = { weather: "tabWeather",  almanac: "tabAlmanac",  overhead: "tabOverhead", hyperlocal: "tabHyperlocal", sources: "tabSources" };
      Object.keys(views).forEach(k => {
        const v = document.getElementById(views[k]);
        const t = document.getElementById(tabs[k]);
        if (v) v.style.display = (k === which) ? "" : "none";
        if (t) {
          t.classList.toggle("active", k === which);
          t.setAttribute("aria-selected", String(k === which));
        }
      });
      // Stop overhead live refresh when leaving that tab
      if (which !== "overhead" && window.ohStopLive) {
        window.ohStopLive();
      }
      try { localStorage.setItem("activeTab", which); } catch(e) {}
      if (which === "overhead") {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            if (window.ohInitMap) window.ohInitMap();
            if (window.ohMap) window.ohMap.invalidateSize();
          });
        });
      }

      // Scroll so tab content is visible below sticky header
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    (function restoreTab() {
      try {
        const t = localStorage.getItem("activeTab");
        if (["almanac","overhead","hyperlocal","sources"].includes(t)) showTab(t);
      } catch(e) {}
    })();

    // ======================================================
    // Formatting helpers
    // ======================================================
    const weatherEmoji = {
      0: "&#9728;&#65039;", 1: "&#127780;&#65039;", 2: "&#9925;", 3: "&#9729;&#65039;",
      45: "&#127787;&#65039;", 48: "&#127787;&#65039;",
      51: "&#127782;&#65039;", 53: "&#127783;&#65039;", 55: "&#127783;&#65039;",
      61: "&#127783;&#65039;", 63: "&#127783;&#65039;", 65: "&#127783;&#65039;",
      71: "&#127784;&#65039;", 73: "&#127784;&#65039;", 75: "&#127784;&#65039;",
      77: "&#127784;&#65039;", 80: "&#127782;&#65039;", 81: "&#127782;&#65039;", 82: "&#127783;&#65039;",
      85: "&#127784;&#65039;", 86: "&#127784;&#65039;",
      95: "&#9928;&#65039;", 96: "&#9928;&#65039;", 99: "&#9928;&#65039;"
    };

    const weatherDesc = {
      0: "Clear", 1: "Mostly Clear", 2: "Partly Cloudy", 3: "Overcast",
      45: "Fog", 48: "Freezing Fog",
      51: "Light Drizzle", 53: "Drizzle", 55: "Heavy Drizzle",
      61: "Light Rain", 63: "Rain", 65: "Heavy Rain",
      71: "Light Snow", 73: "Snow", 75: "Heavy Snow",
      77: "Snow Grains", 80: "Light Showers", 81: "Showers", 82: "Heavy Showers",
      85: "Light Snow Showers", 86: "Heavy Snow Showers",
      95: "Thunderstorm", 96: "Thunderstorm + Hail", 99: "Severe Thunderstorm"
    };

    function fmtLocal(dt) {
      if (!dt) return "--";
      const d = new Date(dt);
      if (isNaN(d.getTime())) return "--";
      return d.toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
    }

    // Single canonical compass function — replaces both old degreesToCompass and degToCompass
    function toCompass(deg, withDeg = true) {
      if (deg == null || isNaN(deg)) return "--";
      const d = ((deg % 360) + 360) % 360;
      const dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];
      const label = dirs[Math.round(d / 22.5) % 16];
      return withDeg ? `${Math.round(d)}° ${label}` : label;
    }

    // ======================================================
    // Wind Exposure Table (mirrors collector.py exactly)
    // ======================================================
   

    const WIND_EXPOSURE_TABLE = [
      [  0,  25, 1.00],  // N-NNE - open harbor, max exposure
      [ 25,  45, 0.70],  // NE - 39ft terrain ~200ft away, partial blocking
      [ 45, 100, 0.25],  // E-ESE - 39-68ft Westlot/Ridge terrain close, heavy blocking
      [100, 200, 0.08],  // SE-S - Marblehead + local terrain, maximum shelter
      [200, 260, 0.10],  // SSW-WSW - 39-78ft Crestwood/Pinecliff close, heavy blocking
      [260, 290, 0.40],  // W - 39ft close but harbor opens beyond, moderate
      [290, 320, 0.75],  // WNW-NW - harbor opening, high exposure
    [320, 360, 1.00],  // NW-N - open harbor, max exposure
];
    const WORRY_NOTICEABLE  =  5;
    const WORRY_NOTABLE     = 10;
    const WORRY_SIGNIFICANT = 16;
    const WORRY_SEVERE      = 30;

    function getExposureFactor(deg) {
      const d = ((deg % 360) + 360) % 360;
      for (const [minD, maxD, factor] of WIND_EXPOSURE_TABLE) {
        if (minD <= maxD) {
          if (d >= minD && d < maxD) return factor;
        } else {
          if (d >= minD || d < maxD) return factor;
        }
      }
      return 0.5;
    }

    function worryScore(speed, expFactor) {
      return speed * Math.pow(expFactor, 1.5);
    }

    function worryLevel(score) {
      if (score >= WORRY_SEVERE)      return { label: "Very windy",  cls: "severe"      };
      if (score >= WORRY_SIGNIFICANT) return { label: "Windy",       cls: "significant" };
      if (score >= WORRY_NOTABLE)     return { label: "Breezy",      cls: "notable"     };
      if (score >= WORRY_NOTICEABLE)  return { label: "Light winds", cls: "breezy"      };
      return                                 { label: "Calm",         cls: "calm"        };
    }

    function computePeakWorry(hourly, windowHours, useGusts) {
      const values = useGusts ? (hourly?.wind_gusts || []) : (hourly?.wind_speed || []);
      const dirs   = hourly?.wind_direction || [];
      const times  = hourly?.times || [];
      
      // Find the current hour index (start of forward-looking window)
      const currentHour = new Date();
      currentHour.setMinutes(0, 0, 0);
      let startIdx = times.findIndex(t => new Date(t) >= currentHour);
      if (startIdx === -1) startIdx = 0; // fallback
      
      const n = Math.min(startIdx + windowHours, values.length, dirs.length);

      let bestScore = -1, bestIdx = -1;
      for (let i = startIdx; i < n; i++) {
        const v = values[i], d = dirs[i];
        if (v == null || d == null) continue;
        const ef = getExposureFactor(d);
        const ws = worryScore(v, ef);
        if (ws > bestScore) { bestScore = ws; bestIdx = i; }
      }
      if (bestIdx < 0) return null;

      const d = dirs[bestIdx];
      const ef = getExposureFactor(d);
      return {
        speed:          values[bestIdx],
        directionDeg:   d,
        exposureFactor: ef,
        score:          worryScore(values[bestIdx], ef),
        timeISO:        times[bestIdx] || null
      };
    }

    // ======================================================
    // Charts
    // ======================================================
    let tempPrecipChart = null;
    let windChartObj    = null;

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
      const weekday = dt.toLocaleDateString("en-US", { weekday: "long" });
      const month = dt.toLocaleDateString("en-US", { month: "long" });
      const day = dt.getDate();
      const timeStr = `${weekday}, ${month} ${day}, ${hour % 12 || 12}-${nextHour % 12 || 12}${nextHour < 12 ? 'am' : 'pm'}`;
      let typeStr = "None";
      if (precipProb > 0 && wb != null) {
        if (wb <= 28) typeStr = "❄️ Snow";
        else if (wb <= 32) typeStr = "🌨 Likely snow";
        else if (wb <= 35) typeStr = "🟣 Mixed/slush";
        else if (temp850 != null && temp850 > 32 && surfTemp != null && surfTemp < 32) {
          typeStr = "🟠 Freezing rain";
        }
        else typeStr = "🔵 Rain";
      }
      
      const cloudPct = cloudTotal[index] != null ? Math.round(cloudTotal[index]) : 0;
      const clearPct = 100 - cloudPct;
      
      document.getElementById("tempPrecipDataTime").textContent = timeStr;
      document.getElementById("tempPrecipDataLine").innerHTML = 
        `Temp: ${temp != null ? Math.round(temp) : "—"}°F | POP: ${precipProb}% | Type: ${typeStr}<br>` +
        `Sky: Cloud: ${cloudPct}% | Clear: ${clearPct}%`;
    }

    function updateWindDataBar(index, times, speeds, gusts, directions) {
      const time = times[index];
      const speed = speeds[index];
      const gust = gusts[index];
      const dir = directions[index];
      
      const dt = new Date(time);
      const hour = dt.getHours();
      const nextHour = (hour + 1) % 24;
      const weekday = dt.toLocaleDateString("en-US", { weekday: "long" });
      const month = dt.toLocaleDateString("en-US", { month: "long" });
      const day = dt.getDate();
      const timeStr = `${weekday}, ${month} ${day}, ${hour % 12 || 12}-${nextHour % 12 || 12}${nextHour < 12 ? 'am' : 'pm'}`;
      
      // Calculate impact scores
      const exposure = dir != null ? getExposureFactor(dir) : 1.0;
      const sustainedImpact = speed != null ? worryScore(speed, exposure) : 0;
      const gustImpact = gust != null ? worryScore(gust, exposure) : 0;
      
      // Impact labels
      const sustainedLabel = sustainedImpact <= 5 ? "Calm" :
                            sustainedImpact <= 12 ? "Breezy" :
                            sustainedImpact <= 20 ? "Notable" :
                            sustainedImpact <= 30 ? "Significant" :
                            sustainedImpact <= 40 ? "Severe" : "Extreme";
      
      const gustLabel = gustImpact <= 5 ? "Calm" :
                       gustImpact <= 12 ? "Breezy" :
                       gustImpact <= 20 ? "Notable" :
                       gustImpact <= 30 ? "Significant" :
                       gustImpact <= 40 ? "Severe" : "Extreme";
      
      // Direction conversion
      const dirStr = dir != null ? toCompass(dir, true) : "—";
      
      document.getElementById("windDataTime").textContent = timeStr;
      document.getElementById("windDataLine").innerHTML = 
        `Sustained: ${speed != null ? Math.round(speed) : "—"}mph (Impact: ${Math.round(sustainedImpact)}, ${sustainedLabel}) | ` +
        `Gust: ${gust != null ? Math.round(gust) : "—"}mph (Impact: ${Math.round(gustImpact)}, ${gustLabel})<br>` +
        `Direction: ${dirStr}`;
    }

    function buildTempPrecipChart(times, temps, pop, wetBulbs, temps850mb, cloudLow, cloudMid, cloudHigh, cloudTotal, sunrise, sunset) {
      const labels = times.map(t => new Date(t).toLocaleTimeString("en-US", { hour: "numeric" }));
      const ctx    = document.getElementById("tempPrecipChart").getContext("2d");
      if (tempPrecipChart) tempPrecipChart.destroy();

      const precipColors = (wetBulbs || []).map((wb, i) => {
        const surfTemp = temps[i];
        const temp850 = temps850mb?.[i];
        if (wb == null) return "rgba(80,140,255,0.85)";
        if (wb <= 28)   return "rgba(230,240,255,0.95)";
        if (temp850 != null && temp850 > 32 && surfTemp != null && surfTemp < 32) {
          return "rgba(255,140,40,0.85)";
        }
        if (wb <= 32)   return "rgba(180,200,240,0.90)";
        if (wb <= 35)   return "rgba(160,100,220,0.85)";
        return "rgba(80,150,255,0.85)";
      });

      function lerp(a, b, t) {
        return a + (b - a) * Math.max(0, Math.min(1, t));
      }

      function getSkyColor(i) {
        const time = new Date(times[i]);
        const hour = time.getHours() + time.getMinutes() / 60;
        const daylight = hour >= sunrise && hour <= sunset
          ? Math.max(0, Math.sin(Math.PI * (hour - sunrise) / (sunset - sunrise)))
          : 0;
        
        if (daylight > 0.5) {
          // Full daytime: yellow/golden sun
          return "rgba(255, 220, 100, 0.88)";
        } else if (daylight > 0) {
          // Sunrise/sunset: subtle orange (close to yellow)
          return "rgba(255, 200, 80, 0.88)";
        } else {
          // Nighttime: dark blue/black
          return "rgba(10, 15, 35, 0.88)";
        }
      }

      // Three stacked segments per hour, summing to 100
      const precipData = pop.map(p => p ?? 0);
      const cloudData  = times.map((_, i) => {
        const p = pop[i] ?? 0;
        const cc = (cloudTotal[i] ?? 0) / 100;
        return Math.round((100 - p) * cc);
      });
      const clearData  = times.map((_, i) => {
        const p = pop[i] ?? 0;
        const cc = (cloudTotal[i] ?? 0) / 100;
        return Math.round((100 - p) * (1 - cc));
      });

      const clearColors = times.map((_, i) => getSkyColor(i));

      // Cloud segment: gray, slightly lighter at day
      const cloudColors = times.map((_, i) => {
        const time = new Date(times[i]);
        const hour = time.getHours() + time.getMinutes() / 60;
        const low = (cloudLow[i] ?? 0) / 100;
        const mid = (cloudMid[i] ?? 0) / 100;
        const high = (cloudHigh[i] ?? 0) / 100;
        const totalCloud = low + mid + high;
        
        const daylight = hour >= sunrise && hour <= sunset
          ? Math.max(0, Math.sin(Math.PI * (hour - sunrise) / (sunset - sunrise)))
          : 0;
        
        // Daytime cloud colors (pure gray - R=G=B)
        const dayLowR = 80, dayLowG = 80, dayLowB = 80;       // dark gray
        const dayMidR = 120, dayMidG = 120, dayMidB = 120;    // medium gray
        const dayHighR = 160, dayHighG = 160, dayHighB = 160; // light gray
        
        // Nighttime cloud colors (blue-tinted gray)
        const nightLowR = 40, nightLowG = 45, nightLowB = 60;    // dark blue-gray
        const nightMidR = 60, nightMidG = 65, nightMidB = 85;    // medium blue-gray
        const nightHighR = 90, nightHighG = 95, nightHighB = 110; // light blue-gray
        
        // Weighted blend of cloud layers
        let r, g, b;
        if (totalCloud > 0) {
          const lowWeight = low / totalCloud;
          const midWeight = mid / totalCloud;
          const highWeight = high / totalCloud;
          
          const dayR = dayLowR * lowWeight + dayMidR * midWeight + dayHighR * highWeight;
          const dayG = dayLowG * lowWeight + dayMidG * midWeight + dayHighG * highWeight;
          const dayB = dayLowB * lowWeight + dayMidB * midWeight + dayHighB * highWeight;
          
          const nightR = nightLowR * lowWeight + nightMidR * midWeight + nightHighR * highWeight;
          const nightG = nightLowG * lowWeight + nightMidG * midWeight + nightHighG * highWeight;
          const nightB = nightLowB * lowWeight + nightMidB * midWeight + nightHighB * highWeight;
          
          r = Math.round(lerp(nightR, dayR, daylight));
          g = Math.round(lerp(nightG, dayG, daylight));
          b = Math.round(lerp(nightB, dayB, daylight));
        } else {
          // No clouds - shouldn't happen but fallback to medium gray
          r = Math.round(lerp(60, 120, daylight));
          g = Math.round(lerp(65, 120, daylight));
          b = Math.round(lerp(85, 120, daylight));
        }
        
        return "rgba(" + r + "," + g + "," + b + ",0.85)";
      });

      tempPrecipChart = new Chart(ctx, {
        data: {
          labels,
          datasets: [
            {
              type: "bar",
              label: "Clear",
              data: clearData,
              yAxisID: "y1",
              backgroundColor: clearColors,
              borderColor: "transparent",
              stack: "sky",
              order: 3,
              borderRadius: { topLeft: 0, topRight: 0, bottomLeft: 3, bottomRight: 3 },
              borderSkipped: false,
            },
            {
              type: "bar",
              label: "Cloud",
              data: cloudData,
              yAxisID: "y1",
              backgroundColor: cloudColors,
              borderColor: "transparent",
              stack: "sky",
              order: 2,
              borderRadius: 0,
              borderSkipped: false,
            },
            {
              type: "bar",
              label: "Precip %",
              data: precipData,
              yAxisID: "y1",
              backgroundColor: precipColors,
              borderColor: "transparent",
              stack: "sky",
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
              backgroundColor: "rgba(255,180,80,0.15)",
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
              const index = activeElements[0].index;
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
            x:  { stacked: true, ticks: { color: chartTextColor() }, grid: { color: chartGridColor() } },
            y:  { ticks: { color: chartTextColor() }, grid: { color: chartGridColor() } },
            y1: { position: "right", stacked: true, min: 0, max: 100,
                  ticks: { color: chartTextColor() }, grid: { drawOnChartArea: false } }
          },
          barPercentage: 1.0,
          categoryPercentage: 0.95
        }
      });
    }

    function windColor(mph) {
      if (mph == null) return "rgba(255,255,255,0.08)";
      if (mph < 10)   return "rgba(80,200,120,0.85)";
      if (mph < 20)   return "rgba(220,200,60,0.85)";
      if (mph < 30)   return "rgba(240,140,40,0.85)";
      if (mph < 40)   return "rgba(220,60,60,0.85)";
      return                 "rgba(160,60,220,0.85)";
    }

    function buildWindChart(times, speeds, gusts, directions) {
      const labels      = times.map(t => new Date(t).toLocaleTimeString("en-US", { hour: "numeric" }));
      const ctx         = document.getElementById("windChart").getContext("2d");
      if (windChartObj) windChartObj.destroy();
      const speedColors = speeds.map(v => windColor(v));
      // Calculate impact scores
      const sustainedImpact = speeds.map((speed, i) => {
        const dir = directions?.[i];
        if (speed == null || dir == null) return null;
        const exposure = getExposureFactor(dir);
        return worryScore(speed, exposure);
      });
      
      const gustImpact = gusts.map((gust, i) => {
        const dir = directions?.[i];
        if (gust == null || dir == null) return null;
        const exposure = getExposureFactor(dir);
        return worryScore(gust, exposure);
      });
      
      // Calculate max impact score for axis scaling
      const allImpacts = [...sustainedImpact, ...gustImpact].filter(v => v != null);
      const maxImpact = allImpacts.length > 0 ? Math.max(...allImpacts) : 10;
      const axisMax = Math.ceil(maxImpact * 1.1); // 10% headroom, rounded up
      
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
            if (activeElements.length > 0) {
              const index = activeElements[0].index;
              updateWindDataBar(activeElements[0].index, times, speeds, gusts, directions);
            }
          },
          onHover: (event, activeElements) => {
            const dataBar = document.getElementById("windDataBar");
            if (dataBar && activeElements.length > 0) {
              updateWindDataBar(activeElements[0].index, times, speeds, gusts, directions);
            }
          },
          plugins: {
            legend: { display: false },
            tooltip: { enabled: false },
            impactZones: {
              beforeDatasetsDraw: (chart) => {
                const {ctx, chartArea: {left, right, top, bottom}, scales: {y}} = chart;
                if (!y) return;
                
                const zones = [
                  {min: 0, max: 5, color: 'rgba(100, 150, 255, 0.15)', label: 'Calm'},
                  {min: 5, max: 12, color: 'rgba(100, 200, 255, 0.15)', label: 'Breezy'},
                  {min: 12, max: 20, color: 'rgba(255, 235, 100, 0.15)', label: 'Notable'},
                  {min: 20, max: 30, color: 'rgba(255, 180, 100, 0.15)', label: 'Significant'},
                  {min: 30, max: 40, color: 'rgba(255, 100, 80, 0.15)', label: 'Severe'},
                  {min: 40, max: 100, color: 'rgba(200, 50, 50, 0.15)', label: 'Extreme'}
                ];
                
                zones.forEach(zone => {
                  const yTop = y.getPixelForValue(zone.max);
                  const yBottom = y.getPixelForValue(zone.min);
                  ctx.fillStyle = zone.color;
                  ctx.fillRect(left, yTop, right - left, yBottom - yTop);
                });
              }
            }
          },
          scales: {
            x: { ticks: { color: chartTextColor() }, grid: { color: chartGridColor() } },
            y: { 
              position: "left",
              title: { display: true, text: "Wind Impact Score", color: chartTextColor() },
              ticks: { color: chartTextColor() }, 
              grid: { color: chartGridColor() },
              min: 0,
              max: axisMax
            },
            y1: { 
              position: "right",
              title: { display: true, text: "Wind Speed (mph)", color: chartTextColor() },
              ticks: { color: chartTextColor() }, 
              grid: { drawOnChartArea: false }
            }
          }
        }
      });
    }

    // ======================================================
    // Rendering functions
    // ======================================================
    function renderTodayAlmanac(daily) {
      const el = document.getElementById("todayAlmanacContent");
      if (!el) return;

      const now    = new Date();
      const light  = isLight();

      // ── Date basics ──────────────────────────────────────────
      const fullDate = now.toLocaleDateString("en-US", {
        weekday:"long", year:"numeric", month:"long", day:"numeric"
      });
      const startOfYear = new Date(now.getFullYear(), 0, 0);
      const dayOfYear   = Math.floor((now - startOfYear) / 86400000);
      const isLeap      = (now.getFullYear() % 4 === 0 && now.getFullYear() % 100 !== 0) || now.getFullYear() % 400 === 0;
      const daysInYear  = isLeap ? 366 : 365;
      const weekNum     = Math.ceil(dayOfYear / 7);

      // ── Season ────────────────────────────────────────────────
      // Meteorological seasons (Dec 1, Mar 1, Jun 1, Sep 1)
      const yr = now.getFullYear();
      const seasons = [
        { name:"Winter",  start: new Date(yr-1, 11, 1), next: new Date(yr, 2, 1),  nextName:"Spring" },
        { name:"Spring",  start: new Date(yr, 2, 1),    next: new Date(yr, 5, 1),  nextName:"Summer" },
        { name:"Summer",  start: new Date(yr, 5, 1),    next: new Date(yr, 8, 1),  nextName:"Fall"   },
        { name:"Fall",    start: new Date(yr, 8, 1),    next: new Date(yr, 11, 1), nextName:"Winter" },
      ];
      let season = seasons[0];
      for (const s of seasons) {
        if (now >= s.start) season = s;
      }
      const daysToNext  = Math.ceil((season.next - now) / 86400000);
      const seasonEmoji = { Winter:"❄️", Spring:"🌱", Summer:"☀️", Fall:"🍂" }[season.name];

      // ── Daylight ──────────────────────────────────────────────
      let daylightStr = "--";
      let daylightMins = null;
      if (typeof SunCalc !== "undefined") {
        const times0    = SunCalc.getTimes(now, HOME_LAT, HOME_LON);
        const riseMs    = times0.sunrise?.getTime();
        const setMs     = times0.sunset?.getTime();
        if (riseMs && setMs) {
          daylightMins = Math.round((setMs - riseMs) / 60000);
          const h = Math.floor(daylightMins / 60);
          const m = daylightMins % 60;
          daylightStr = `${h}h ${m}m`;
        }
      }

      // Daylight change vs yesterday
      let changeStr = "";
      if (typeof SunCalc !== "undefined" && daylightMins !== null) {
        const yesterday = new Date(now.getTime() - 86400000);
        const ty = SunCalc.getTimes(yesterday, HOME_LAT, HOME_LON);
        if (ty.sunrise && ty.sunset) {
          const yMins = Math.round((ty.sunset - ty.sunrise) / 60000);
          const diff  = daylightMins - yMins;
          const sign  = diff >= 0 ? "+" : "−";
          const absDiff = Math.abs(diff);
          const diffM = Math.floor(absDiff / 60);
          const diffS = absDiff % 60;  // diff is in minutes — get seconds from fractional
          // Actually SunCalc gives millisecond precision — redo in seconds
          const tyMs   = ty.sunset.getTime() - ty.sunrise.getTime();
          const t0Ms   = SunCalc.getTimes(now, HOME_LAT, HOME_LON);
          const todayMs2 = t0Ms.sunset?.getTime() - t0Ms.sunrise?.getTime();
          if (todayMs2 && tyMs) {
            const diffSec = Math.round((todayMs2 - tyMs) / 1000);
            const dSign   = diffSec >= 0 ? "+" : "−";
            const dAbs    = Math.abs(diffSec);
            const dM      = Math.floor(dAbs / 60);
            const dS      = dAbs % 60;
            const dColor  = diffSec >= 0
              ? (light ? "rgba(20,140,60,0.9)" : "rgba(100,220,120,0.9)")
              : (light ? "rgba(180,60,20,0.9)" : "rgba(220,100,80,0.9)");
            changeStr = `<span style="color:${dColor};font-weight:800;">${dSign}${dM > 0 ? dM+"m " : ""}${dS}s vs yesterday</span>`;
          }
        }
      }

      // ── Sunrise / Sunset ──────────────────────────────────────
      let riseStr = "--", setStr = "--";
      if (typeof SunCalc !== "undefined") {
        const t = SunCalc.getTimes(now, HOME_LAT, HOME_LON);
        if (t.sunrise) riseStr = fmtTime(t.sunrise);
        if (t.sunset)  setStr  = fmtTime(t.sunset);
      }

      // ── Moon ──────────────────────────────────────────────────
      let moonPhase = "", moonIllum = "";
      if (typeof SunCalc !== "undefined") {
        const mi = SunCalc.getMoonIllumination(now);
        const phases = [
          [0.025, "🌑 New Moon"],      [0.25,  "🌒 Waxing Crescent"],
          [0.275, "🌓 First Quarter"], [0.5,   "🌔 Waxing Gibbous"],
          [0.525, "🌕 Full Moon"],     [0.75,  "🌖 Waning Gibbous"],
          [0.775, "🌗 Last Quarter"],  [1.0,   "🌘 Waning Crescent"],
        ];
        moonPhase = phases.find(([t]) => mi.phase < t)?.[1] ?? "🌑 New Moon";
        moonIllum = Math.round(mi.fraction * 100) + "% illuminated";
      }

      // ── Render ────────────────────────────────────────────────
      const labelCol = light ? "rgba(0,0,0,0.50)"  : "rgba(255,255,255,0.65)";
      const valCol   = light ? "rgba(0,0,0,0.88)"  : "rgba(255,255,255,0.92)";
      const dimCol   = light ? "rgba(0,0,0,0.38)"  : "rgba(255,255,255,0.50)";
      const divCol   = light ? "rgba(0,0,0,0.06)"  : "rgba(255,255,255,0.08)";

      // Use pure inline styles — no .label/.value classes to avoid !important conflicts
      const rowStyle  = `display:flex;justify-content:flex-start;align-items:baseline;` +
                        `padding:9px 0;border-bottom:1px solid ${divCol};gap:12px;`;
      const lblStyle  = `font-size:0.82rem;color:${labelCol};flex-shrink:0;`;
      const valStyle  = `font-size:0.88rem;font-weight:700;color:${valCol};text-align:right;margin-left:auto;`;
      const subStyle  = `font-size:0.72rem;color:${dimCol};margin-top:1px;font-weight:400;`;

      const row = (label, value, sub = "") => `
        <div style="${rowStyle}">
          <div style="${lblStyle}">${label}</div>
          <div style="${valStyle}">${value}${sub ? `<div style="${subStyle}">${sub}</div>` : ""}</div>
        </div>`;

      el.innerHTML = `
        <div style="font-size:1.05rem;font-weight:900;color:${valCol};margin-bottom:14px;">${fullDate}</div>
        ${row("Day of year",    `${dayOfYear} of ${daysInYear}`, `Week ${weekNum}`)}
        ${row("Season (meteorological)",`${seasonEmoji} ${season.name}`, `${daysToNext} days until ${season.nextName}`)}
        ${row("Sunrise",        riseStr)}
        ${row("Sunset",         setStr)}
        ${row("Daylight",       daylightStr, changeStr)}
        ${row("Moon",           moonPhase, moonIllum)}
      `;
    }

    function renderFrostTracker(frost) {
      const el = document.getElementById("frostTracker");
      if (!el || !frost) return;
      const light = isLight();
      const textFaint  = light ? "rgba(0,0,0,0.40)" : "rgba(255,255,255,0.4)";
      const textMid    = light ? "rgba(0,0,0,0.55)" : "rgba(255,255,255,0.5)";
      const textSub    = light ? "rgba(0,0,0,0.38)" : "rgba(255,255,255,0.35)";
      const textHead   = light ? "rgba(0,0,0,0.65)" : "rgba(255,255,255,0.55)";
      const tile1bg    = light ? "rgba(30,120,255,0.06)"  : "rgba(100,180,255,0.08)";
      const tile1bd    = light ? "rgba(30,120,255,0.20)"  : "rgba(100,180,255,0.18)";
      const tile1num   = light ? "rgba(20,80,200,0.90)"   : "rgba(180,220,255,0.9)";
      const tile2bg    = light ? "rgba(30,80,220,0.06)"   : "rgba(60,120,255,0.08)";
      const tile2bd    = light ? "rgba(30,80,220,0.20)"   : "rgba(60,120,255,0.18)";
      const tile2num   = light ? "rgba(20,60,200,0.90)"   : "rgba(140,180,255,0.9)";
      const tile3bg    = light ? "rgba(10,30,160,0.06)"   : "rgba(20,60,180,0.08)";
      const tile3bd    = light ? "rgba(10,30,160,0.22)"   : "rgba(20,60,180,0.25)";
      const tile3num   = light ? "rgba(10,40,180,0.90)"   : "rgba(100,140,255,0.9)";
      const upcomingColor = light ? "rgba(20,70,200,0.85)" : "rgba(180,210,255,0.8)";

      if (!frost.season_start) {
        el.innerHTML = `<div style="color:${textFaint};font-size:0.85rem;">No frost data yet — will populate after first overnight run.</div>`;
        return;
      }

      const [sy, sm, sd] = frost.season_start.split("-").map(Number);
      const seasonStart = new Date(sy, sm-1, sd).toLocaleDateString("en-US", { month:"short", day:"numeric", year:"numeric" });
      const fmt = d => d ? new Date(d).toLocaleDateString("en-US", { month:"short", day:"numeric" }) : "None this season";

      const upcoming = frost.upcoming_freeze_days || [];
      const upcomingHtml = upcoming.length === 0
        ? `<span style="color:${textFaint};">None in 10-day forecast</span>`
        : upcoming.map(u => {
            const label = u.min_f <= 20 ? "❄️❄️" : u.min_f <= 28 ? "❄️" : "🌡️";
            const d = new Date(u.date).toLocaleDateString("en-US", { weekday:"short", month:"short", day:"numeric" });
            return `<span style="margin-right:12px;">${label} ${d} (${u.min_f}°F)</span>`;
          }).join("");

      el.innerHTML = `
        <div style="font-size:0.78rem;color:${textFaint};margin-bottom:10px;">Season from ${seasonStart}</div>
        <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:14px;" class="mobile-3col">
          <div style="background:${tile1bg};border:1px solid ${tile1bd};border-radius:10px;padding:10px;text-align:center;">
            <div style="font-size:1.8rem;font-weight:900;color:${tile1num};">${frost.freeze_days ?? 0}</div>
            <div style="font-size:0.78rem;color:${textMid};margin-top:2px;">Freeze days</div>
            <div style="font-size:0.72rem;color:${textSub};margin-top:3px;">min ≤ 32°F</div>
            <div style="font-size:0.72rem;color:${textFaint};margin-top:4px;">Last: ${fmt(frost.last_freeze)}</div>
          </div>
          <div style="background:${tile2bg};border:1px solid ${tile2bd};border-radius:10px;padding:10px;text-align:center;">
            <div style="font-size:1.8rem;font-weight:900;color:${tile2num};">${frost.hard_freeze_days ?? 0}</div>
            <div style="font-size:0.78rem;color:${textMid};margin-top:2px;">Hard freeze days</div>
            <div style="font-size:0.72rem;color:${textSub};margin-top:3px;">min ≤ 28°F</div>
            <div style="font-size:0.72rem;color:${textFaint};margin-top:4px;">Last: ${fmt(frost.last_hard)}</div>
          </div>
          <div style="background:${tile3bg};border:1px solid ${tile3bd};border-radius:10px;padding:10px;text-align:center;">
            <div style="font-size:1.8rem;font-weight:900;color:${tile3num};">${frost.severe_days ?? 0}</div>
            <div style="font-size:0.78rem;color:${textMid};margin-top:2px;">Severe freeze days</div>
            <div style="font-size:0.72rem;color:${textSub};margin-top:3px;">min ≤ 20°F</div>
            <div style="font-size:0.72rem;color:${textFaint};margin-top:4px;">Last: ${fmt(frost.last_severe)}</div>
          </div>
        </div>
        <div style="font-size:0.82rem;font-weight:800;color:${textHead};margin-bottom:6px;">Upcoming freeze nights (10-day forecast):</div>
        <div style="font-size:0.82rem;color:${upcomingColor};line-height:1.8;">${upcomingHtml}</div>
      `;
    }

    // ======================================================
    // Solar System (VSOP87 truncated — no API needed)
    // ======================================================
    // ======================================================
    // Sunset Quality Forecast
    // Algorithm based on SunsetWx methodology:
    //   Score = mid_cloud × (1 - low_cloud_penalty) × humidity_factor
    // Best sunsets: 30-70% mid/high cloud, <20% low cloud, dry air
    // ======================================================
    function renderSunsetQuality(data) {
      const el = document.getElementById("sunsetQualityContent");
      if (!el) return;

      const sunsetDir = data.sunset_directional || [];
      
      if (!sunsetDir.length) {
        el.innerHTML = `<div style="color:rgba(255,255,255,0.4);font-size:0.85rem;">Sunset data unavailable</div>`;
        return;
      }

      const scores = [];
      
      for (const day of sunsetDir) {
        const clouds = day.clouds || {};
        const cloud10 = clouds['10mi'];
        const cloud25 = clouds['25mi'];
        const cloud50 = clouds['50mi'];
        
        if (!cloud10 || !cloud25 || !cloud50) continue;
        
        const sunsetTime = new Date(day.sunset_time);
        const sunsetIdx = cloud25.times.findIndex(t => new Date(t).getTime() >= sunsetTime.getTime());
        
        if (sunsetIdx < 0) continue;
        
        const low10 = cloud10.cloud_low[sunsetIdx] ?? 0;
        const mid25 = cloud25.cloud_mid[sunsetIdx] ?? 0;
        const mid50 = cloud50.cloud_mid[sunsetIdx] ?? 0;
        const high25 = cloud25.cloud_high[sunsetIdx] ?? 0;
        const high50 = cloud50.cloud_high[sunsetIdx] ?? 0;
        const hum25 = cloud25.humidity[sunsetIdx] ?? 50;
        
        const totalCloud = (low10 + mid25 + high25) / 3;
        
        if (totalCloud < 15 && hum25 < 60) {
          const dayLabel = day.day === 0 ? "Today" : day.day === 1 ? "Tomorrow"
            : sunsetTime.toLocaleDateString("en-US", { weekday:"short", month:"short", day:"numeric" });
          const timeLabel = sunsetTime.toLocaleTimeString("en-US", { hour:"numeric", minute:"2-digit" });
          
          scores.push({
            dayLabel, timeLabel,
            score: 45,
            label: "Good",
            color: "rgba(255,220,100,0.9)",
            emoji: "🌤️",
            avgLow: low10.toFixed(0),
            avgMid: mid25.toFixed(0),
            avgHigh: high25.toFixed(0),
            avgHum: hum25.toFixed(0),
            note: "Clear sky"
          });
          continue;
        }
        
        if (low10 > 60) {
          const dayLabel = day.day === 0 ? "Today" : day.day === 1 ? "Tomorrow"
            : sunsetTime.toLocaleDateString("en-US", { weekday:"short", month:"short", day:"numeric" });
          const timeLabel = sunsetTime.toLocaleTimeString("en-US", { hour:"numeric", minute:"2-digit" });
          
          scores.push({
            dayLabel, timeLabel,
            score: 10,
            label: "Poor",
            color: "rgba(120,120,120,0.6)",
            emoji: "☁️",
            avgLow: low10.toFixed(0),
            avgMid: mid25.toFixed(0),
            avgHigh: high25.toFixed(0),
            avgHum: hum25.toFixed(0),
            note: "Overcast"
          });
          continue;
        }
        
        const midCloudAvg = mid25 * 0.7 + mid50 * 0.3;
        
        const midScore = midCloudAvg <= 70 
          ? midCloudAvg / 70 
          : Math.max(0.3, (100 - midCloudAvg) / 40);
        
        const highBonus = Math.min((high25 + high50) / 2, 60) / 60 * 0.3;
        const lowPenalty = Math.min(low10 / 80, 1.0);
        const humFactor = 1 - Math.max(0, (hum25 - 60)) / 80;
        
        let score = (midScore * 0.7 + highBonus) * (1 - lowPenalty * 0.6) * humFactor;
        score = Math.max(1, Math.min(100, Math.round(score * 100)));
        
        let label, color, emoji;
        if (score >= 75)      { label = "Spectacular";  color = "rgba(255,160,40,0.95)";  emoji = "🔥"; }
        else if (score >= 55) { label = "Very Good";    color = "rgba(255,200,60,0.95)";  emoji = "🌅"; }
        else if (score >= 35) { label = "Good";         color = "rgba(255,220,100,0.9)";  emoji = "🌤️"; }
        else if (score >= 18) { label = "Fair";         color = "rgba(180,180,180,0.8)";  emoji = "🌥️"; }
        else                    { label = "Poor";         color = "rgba(120,120,120,0.6)";  emoji = "☁️"; }
        
        const dayLabel = day.day === 0 ? "Today" : day.day === 1 ? "Tomorrow"
          : sunsetTime.toLocaleDateString("en-US", { weekday:"short", month:"short", day:"numeric" });
        const timeLabel = sunsetTime.toLocaleTimeString("en-US", { hour:"numeric", minute:"2-digit" });
        
        scores.push({
          dayLabel, timeLabel, score, label, color, emoji,
          avgLow: low10.toFixed(0),
          avgMid: midCloudAvg.toFixed(0),
          avgHigh: ((high25 + high50) / 2).toFixed(0),
          avgHum: hum25.toFixed(0)
        });
        
        // Store today's score for Right Now card
        if (day.day === 0) {
          window.__todaySunsetScore = {score, label, emoji, color};
        }
      }

      if (!scores.length) {
        el.innerHTML = `<div style="color:${isLight() ? 'rgba(0,0,0,0.4)' : 'rgba(255,255,255,0.4)'};font-size:0.85rem;">No sunset data in forecast window</div>`;
        return;
      }

      const light = isLight();
      const tileBg   = light ? "rgba(0,0,0,0.03)"   : "rgba(255,255,255,0.04)";
      const tileBd   = light ? "rgba(0,0,0,0.09)"   : "rgba(255,255,255,0.08)";
      const dayCol   = light ? "rgba(0,0,0,0.60)"   : "rgba(255,255,255,0.6)";
      const timeCol  = light ? "rgba(0,0,0,0.38)"   : "rgba(255,255,255,0.35)";
      const barBg    = light ? "rgba(0,0,0,0.08)"   : "rgba(255,255,255,0.1)";
      const detCol   = light ? "rgba(0,0,0,0.40)"   : "rgba(255,255,255,0.4)";
      const noteCol  = light ? "rgba(0,0,0,0.35)"   : "rgba(255,255,255,0.3)";

      let html = `<div class="scroll-day-grid" style="display:grid;grid-template-columns:repeat(${scores.length},1fr);gap:10px;margin-bottom:12px;">`;
      for (const s of scores) {
        const barW = Math.round(s.score * 100);
        const noteHtml = s.note ? `<div style="font-size:0.72rem;color:${noteCol};margin-top:4px;">${s.note}</div>` : '';
        html += `
          <div style="background:${tileBg};border:1px solid ${tileBd};
                      border-radius:10px;padding:16px 12px;text-align:center;">
            <div style="font-size:0.9rem;font-weight:800;color:${dayCol};margin-bottom:6px;">${s.dayLabel}</div>
            <div style="font-size:2rem;margin-bottom:6px;">${s.emoji}</div>
            <div style="font-size:1.05rem;font-weight:900;color:${s.color};margin-bottom:6px;">${s.label} <span style="font-size:0.8rem;opacity:0.7;">(${Math.round(s.score)})</span></div>
            <div style="font-size:0.8rem;color:${timeCol};margin-bottom:10px;">Sunset ${s.timeLabel}</div>
            <div style="height:5px;background:${barBg};border-radius:3px;overflow:hidden;margin-bottom:10px;">
              <div style="height:100%;width:${barW}%;background:${s.color};border-radius:3px;transition:width 0.4s;"></div>
            </div>
            <div style="font-size:0.78rem;color:${detCol};line-height:2;">
              <span data-tip="Low clouds at 10mi (local horizon). High values block view.">Low ${s.avgLow}%</span> ·
              <span data-tip="Mid-level clouds 25mi west. Sweet spot: 30–70%.">Mid ${s.avgMid}%</span> ·
              <span data-tip="High clouds 25-50mi west. Add color and atmosphere.">High ${s.avgHigh}%</span>
            </div>
            ${noteHtml}
          </div>`;
      }
      html += `</div>`;
      html += `<div style="font-size:0.78rem;color:${noteCol};margin-top:4px;">
        Clouds sampled 10-50 miles west along actual sunset direction (not overhead).
        Best sunsets: 30-70% mid clouds at distance, clear horizon nearby, dry air. Clear skies with low humidity score "Good".
      </div>`;

      el.innerHTML = html;
      
      // Update collapsed preview with today's data
      if (scores.length > 0 && scores[0].dayLabel === "Today") {
        const today = scores[0];
        const sunsetScoreEl = document.getElementById("sunsetScoreCollapsed");
        const sunsetTimeEl = document.getElementById("sunsetTimeCollapsed");
        if (sunsetScoreEl) sunsetScoreEl.innerHTML = `${today.dayLabel}<br>${today.emoji}`;
        if (sunsetTimeEl) sunsetTimeEl.textContent = today.label;
      }
    }

    function renderSolarSystem() {
      const el = document.getElementById("solarSystemGrid");
      if (!el) return;

      const now   = new Date();
      const jd    = 2440587.5 + now.getTime() / 86400000;
      const T     = (jd - 2451545.0) / 36525.0;

      // Planet orbital elements [L0, L1, a, e0, e1, i0, i1, Om0, Om1, w0, w1]
      const EL = {
        Mercury: [252.250906,149474.0722491,0.387098310,0.20563175, 0.000020407, 7.004986, 0.0018215,48.330893,1.1861883, 77.456119,1.5564776],
        Venus:   [181.979801, 58519.2130302,0.723329820,0.00677188,-0.000047766, 3.394662, 0.0010037,76.679920,0.9011190,131.563703,1.4022288],
        Mars:    [355.433000, 19141.6964471,1.523679342,0.09340062, 0.000090483, 1.849726,-0.0006011,49.558093,0.7720959,336.060234,1.8410449],
        Jupiter: [ 34.351519,  3036.3027748,5.202603209,0.04849485, 0.000163244, 1.303270,-0.0054966,100.464407,1.0209774,14.331207,1.6126352],
        Saturn:  [ 50.077444,  1223.5110686,9.554909192,0.05550825,-0.000346641, 2.488878, 0.0025515,113.665503,0.8770880,93.057237,1.9637613],
      };

      const EMOJIS = { Mercury:"☿", Venus:"♀️", Mars:"♂️", Jupiter:"♃", Saturn:"🪐" };
      const COLORS = {
        Mercury:"rgba(180,160,130,0.9)",
        Venus:  "rgba(255,220,100,0.9)",
        Mars:   "rgba(220,80,60,0.9)",
        Jupiter:"rgba(200,160,100,0.9)",
        Saturn: "rgba(210,190,130,0.9)",
      };

      const r2d = r => r * 180 / Math.PI;
      const d2r = d => d * Math.PI / 180;

      // Earth heliocentric position
      const M_e  = d2r(((357.529092 + 35999.0502909*T) % 360 + 360) % 360);
      const e_e  = 0.016708617 - 0.000042037*T;
      let   E_e  = M_e;
      for (let i=0;i<10;i++) E_e -= (E_e - e_e*Math.sin(E_e) - M_e)/(1 - e_e*Math.cos(E_e));
      const w_e  = d2r(102.937348 + 1.7195366*T);
      const xe0  = 1.000001018*(Math.cos(E_e) - e_e);
      const ye0  = 1.000001018*Math.sqrt(1-e_e*e_e)*Math.sin(E_e);
      const xe   = Math.cos(w_e)*xe0 - Math.sin(w_e)*ye0;
      const ye   = Math.sin(w_e)*xe0 + Math.cos(w_e)*ye0;

      // Greenwich Sidereal Time & Local Sidereal Time
      const GMST = ((280.46061837 + 360.98564736629*(jd-2451545.0) + 0.000387933*T*T) % 360 + 360) % 360;
      const LST  = (GMST + HOME_LON + 360) % 360;
      const LAT  = d2r(HOME_LAT);
      const eps  = d2r(23.439291 - 0.013004*T);

      const dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];

      const results = [];

      for (const [name, el] of Object.entries(EL)) {
        const L   = d2r(((el[0] + el[1]*T) % 360 + 360) % 360);
        const a   = el[2];
        const e   = el[3] + el[4]*T;
        const inc = d2r(el[5] + el[6]*T);
        const Om  = d2r(el[7] + el[8]*T);
        const w   = d2r(el[9] + el[10]*T);
        const M   = ((L - w) % (2*Math.PI) + 2*Math.PI) % (2*Math.PI);
        let   E   = M;
        for (let i=0;i<10;i++) E -= (E - e*Math.sin(E) - M)/(1 - e*Math.cos(E));
        const xo  = a*(Math.cos(E) - e);
        const yo  = a*Math.sqrt(1-e*e)*Math.sin(E);
        const cOm=Math.cos(Om),sOm=Math.sin(Om),cw=Math.cos(w-Om),sw=Math.sin(w-Om),ci=Math.cos(inc),si=Math.sin(inc);
        const xh=(cOm*cw-sOm*sw*ci)*xo+(-cOm*sw-sOm*cw*ci)*yo;
        const yh=(sOm*cw+cOm*sw*ci)*xo+(-sOm*sw+cOm*cw*ci)*yo;
        const zh=si*(sw*xo+cw*yo);
        const gx=xh-xe, gy=yh-ye, gz=zh;
        const dist=Math.sqrt(gx*gx+gy*gy+gz*gz);
        // Equatorial
        const xeq=gx, yeq=gy*Math.cos(eps)-gz*Math.sin(eps), zeq=gy*Math.sin(eps)+gz*Math.cos(eps);
        const ra  =((r2d(Math.atan2(yeq,xeq))%360)+360)%360;
        const dec =r2d(Math.asin(zeq/dist));
        // Elongation
        const sx=-xe,sy=-ye,sz=0;
        const sdist=Math.sqrt(sx*sx+sy*sy+sz*sz);
        const dot=Math.max(-1,Math.min(1,(gx*sx+gy*sy+gz*sz)/(dist*sdist)));
        const elong=r2d(Math.acos(dot));
        // Alt/Az
        const HA = d2r(((LST - ra) % 360 + 360) % 360);
        const decR=d2r(dec);
        const alt =r2d(Math.asin(Math.sin(LAT)*Math.sin(decR)+Math.cos(LAT)*Math.cos(decR)*Math.cos(HA)));
        const azR =Math.atan2(-Math.cos(decR)*Math.sin(HA), Math.sin(decR)*Math.cos(LAT)-Math.cos(decR)*Math.cos(HA)*Math.sin(LAT));
        const az  =((r2d(azR)%360)+360)%360;
        const dirIdx=Math.round(az/22.5)%16;

        // Four states:
        //   'visible' — above horizon, elongation OK, dark enough (after dusk or before dawn)
        //   'daytime' — above horizon, elongation OK, but sun is up (sky too bright)
        //   'glare'   — above horizon, too close to sun (<15° elongation)
        //   'below'   — below horizon
        let state;
        const sunTimes  = (typeof SunCalc !== "undefined") ? SunCalc.getTimes(now, HOME_LAT, HOME_LON) : null;
        const isDark    = sunTimes
          ? (now >= sunTimes.dusk || now <= sunTimes.dawn)
          : false;
        if (alt <= 5)              state = 'below';
        else if (elong <= 15)      state = 'glare';
        else if (!isDark)          state = 'daytime';
        else                       state = 'visible';

        results.push({name, emoji:EMOJIS[name], color:COLORS[name], alt:alt.toFixed(0), az:az.toFixed(0),
                      dir:dirs[dirIdx], dist:dist.toFixed(2), elong:elong.toFixed(0), visible: state === 'visible', state});
      }

      // Sort: visible → daytime → glare → below
      results.sort((a,b) => {
        const rank = { visible:0, daytime:1, glare:2, below:3 };
        if (rank[a.state] !== rank[b.state]) return rank[a.state] - rank[b.state];
        return b.alt - a.alt;
      });

      const trulyVisible = results.filter(r => r.state === 'visible').length;
      const timeStr  = now.toLocaleTimeString("en-US", {hour:"numeric", minute:"2-digit"});

      const light = isLight();
      const subTxt    = light ? "rgba(0,0,0,0.40)" : "rgba(255,255,255,0.4)";
      const dimTxt    = light ? "rgba(0,0,0,0.28)" : "rgba(255,255,255,0.25)";
      const faintTxt  = light ? "rgba(0,0,0,0.35)" : "rgba(255,255,255,0.3)";
      const dirTxt    = light ? "rgba(0,0,0,0.50)" : "rgba(255,255,255,0.5)";
      const visBg     = light ? "rgba(255,255,255,1.0)" : "rgba(255,255,255,0.08)";
      const visShadow = light ? "0 1px 6px rgba(0,0,0,0.10)" : "none";
      const dimBg     = light ? "rgba(0,0,0,0.025)" : "rgba(255,255,255,0.02)";
      const dimBd     = light ? "rgba(0,0,0,0.07)"  : "rgba(255,255,255,0.06)";
      const headerTxt = light ? "rgba(0,0,0,0.45)"  : "rgba(255,255,255,0.4)";
      const glareColor= light ? "rgba(180,110,0,0.85)" : "rgba(255,190,60,0.85)";
      const dayColor  = light ? "rgba(30,90,200,0.80)" : "rgba(140,180,255,0.85)";

      const headerMsg = trulyVisible > 0
        ? `${trulyVisible} planet${trulyVisible!==1?"s":""} visible at ${timeStr}`
        : `No planets visible at ${timeStr}`;

      let html = `<div style="font-size:0.78rem;color:${headerTxt};margin-bottom:12px;">
        ${headerMsg} — geometric position, not naked-eye visibility
      </div>`;

      html += `<div class="solar-grid" style="display:grid;grid-template-columns:repeat(5,1fr);gap:8px;">`;
      for (const p of results) {
        const isVis   = p.state === 'visible';
        const isDay   = p.state === 'daytime';
        const isGlare = p.state === 'glare';
        const isBelow = p.state === 'below';

        const nameColor   = isVis   ? p.color
                          : isDay   ? (light ? "rgba(0,0,0,0.55)" : "rgba(180,200,255,0.7)")
                          : isGlare ? (light ? "rgba(0,0,0,0.50)" : "rgba(200,200,200,0.6)")
                          :           (light ? "rgba(0,0,0,0.32)" : "rgba(150,150,150,0.4)");
        const borderColor = isVis   ? p.color.replace("0.9","0.5")
                          : isDay   ? (light ? "rgba(30,90,200,0.20)" : "rgba(140,180,255,0.18)")
                          : dimBd;
        const bg          = isVis   ? visBg : dimBg;
        const shadow      = isVis   ? visShadow : "none";
        const emojiOp     = isVis   ? "1"
                          : isDay   ? (light ? "0.60" : "0.50")
                          : isGlare ? (light ? "0.50" : "0.40")
                          :           (light ? "0.30" : "0.22");
        const dataOp      = isVis ? "1" : isDay ? "0.80" : isGlare ? "0.70" : "0.50";

        let statusLine;
        if (isVis) {
          statusLine = `<span style="color:rgba(60,180,80,0.9);">${p.alt}° alt · ${p.dir} ${p.az}°</span>`;
        } else if (isDay) {
          statusLine = `<span style="color:${dayColor};" data-tip="Planet is above the horizon with enough separation from the sun, but the sky is too bright right now. Visible after dusk.">${p.alt}° alt · sky too bright</span>`;
        } else if (isGlare) {
          statusLine = `<span style="color:${glareColor};" data-tip="Planet is above the horizon but only ${p.elong}° from the sun — lost in solar glare.">☀️ solar glare</span>`;
        } else {
          statusLine = `<span style="color:${faintTxt};">below horizon</span>`;
        }

        html += `
          <div style="background:${bg};border:1px solid ${borderColor};border-radius:10px;
                      padding:10px 8px;text-align:center;box-shadow:${shadow};">
            <div style="font-size:1.5rem;margin-bottom:4px;opacity:${emojiOp};">${p.emoji}</div>
            <div style="font-size:0.82rem;font-weight:900;color:${nameColor};margin-bottom:5px;">${p.name}</div>
            <div style="font-size:0.72rem;margin-bottom:4px;">${statusLine}</div>
            <div style="font-size:0.68rem;color:${faintTxt};opacity:${dataOp};">${p.elong}° from Sun · ${p.dist} AU</div>
          </div>`;
      }
      html += `</div>`;

      el.innerHTML = html;
      document.getElementById("solarSystemNote").textContent =
        "Positions calculated client-side using VSOP87 truncated series. Accurate to ~1°.";
    }

    const SOURCE_META = {
      gfs_current:  { name: "GFS",          desc: "Global Forecast System — current conditions baseline (NOAA)" },
      hrrr_hourly:  { name: "HRRR",         desc: "High-Resolution Rapid Refresh — 48h hourly forecast, cloud layers, upper-air (NOAA)" },
      ecmwf_daily:  { name: "ECMWF",        desc: "European Centre model — 10-day daily forecast (Open-Meteo)" },
      pws:          { name: "PWS",           desc: "Single weather station KMAMARBL63 (Castle Hill, 0.27mi) — fallback only" },
      wu_stations:  { name: "WU Multi",     desc: "15 local weather stations — distance- and elevation-weighted, quality-filtered (Weather Underground API)" },
      kbos:         { name: "KBOS",         desc: "Boston Logan Airport ASOS — observed temp, pressure, tendency (NWS/aviationweather.gov)" },
      kbvy:         { name: "KBVY",         desc: "Beverly Airport ASOS — observed temp, wind (NWS/aviationweather.gov)" },
      buoy_44013:   { name: "Buoy 44013",   desc: "NOAA Boston Buoy (16mi ENE) — water temp, waves, offshore wind (NDBC)" },
      tides:        { name: "Tides",        desc: "NOAA CO-OPS tide predictions — Salem Harbor station 8442645" },
      nws_forecast: { name: "NWS Forecast", desc: "NWS Boston text forecast and hourly details (api.weather.gov)" },
      nws_alerts:   { name: "NWS Alerts",   desc: "Active NWS watches, warnings, advisories for Marblehead (api.weather.gov)" },
    };

    const STATIC_SOURCES = [
      { name: "IEM NEXRAD",   desc: "Radar tile source — NOAA NEXRAD base reflectivity composite via Iowa Environmental Mesonet, 5-minute archives (mesonet.agron.iastate.edu)" },
      { name: "CartoDB",      desc: "Dark Matter basemap tiles for radar view — no API key required (carto.com)" },
      { name: "SunCalc",      desc: "Client-side sun/moon position and phase calculations (mourner/suncalc)" },
      { name: "VSOP87",       desc: "Client-side planetary position calculations — solar system card (truncated series, ~1° accuracy)" },
      { name: "Open-Meteo",   desc: "Cloud layer data (low/mid/high) for sunset quality forecast — HRRR product" },
    ];

    function renderSources(sources, pwsStale) {
      if (!sources) return;
      const order = Object.keys(SOURCE_META);

      // Count errors for tab color
      let anyError = false;
      order.forEach(key => {
        const s = sources[key];
        if (s && s.status !== "ok") anyError = true;
      });
      const tabBtn = document.getElementById("tabSources");
      if (tabBtn) {
        tabBtn.style.background    = anyError ? "rgba(255,80,80,0.18)"  : "rgba(80,200,100,0.15)";
        tabBtn.style.borderColor   = anyError ? "rgba(255,80,80,0.45)"  : "rgba(80,200,100,0.4)";
        tabBtn.style.color         = anyError ? "rgba(255,180,180,0.95)" : "rgba(140,240,160,0.95)";
        tabBtn.textContent         = anyError ? "⚠️ Sources" : "✓ Sources";
      }

      // Build sources table
      const table = document.getElementById("sourcesTable");
      if (!table) return;
      const pwsName = pwsStale ? "PWS (cached)" : "PWS (live)";

      // Sources rendered as flex rows — works on any screen width
      const rowStyle = "display:flex;gap:8px;align-items:baseline;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);flex-wrap:wrap;";
      const nameStyle = "font-weight:800;color:rgba(255,255,255,0.9);font-size:0.85rem;min-width:90px;flex-shrink:0;";
      const descStyle = "color:rgba(255,255,255,0.5);font-size:0.8rem;flex:1;min-width:0;";
      const badgeStyle = ok => `font-size:0.75rem;font-weight:800;white-space:nowrap;color:${ok ? "rgba(140,240,160,0.9)" : "rgba(255,120,120,0.9)"};`;
      const ageStyle  = ok => `font-size:0.75rem;font-weight:700;color:${ok ? "rgba(255,255,255,0.4)" : "rgba(255,120,120,0.7)"};white-space:nowrap;`;

      table.innerHTML = `
        <div style="font-weight:900;font-size:0.75rem;color:rgba(255,255,255,0.35);letter-spacing:0.8px;text-transform:uppercase;margin-bottom:8px;">Live Data Sources</div>
        ${order.map(key => {
          const s = sources[key];
          if (!s) return "";
          const ok   = s.status === "ok";
          const age  = typeof s.age_minutes === "number" ? s.age_minutes.toFixed(1) + "m ago" : "--";
          const meta = SOURCE_META[key];
          const name = key === "pws" ? pwsName : meta.name;
          
          let extraDetail = "";
          // Add WU station breakdown if this is the wu_stations source
          if (key === "wu_stations" && ok) {
            const wu = window.__lastWeatherData?.wu_stations;
            if (wu && wu.stations) {
              const quality = wu.quality || {};
              extraDetail = `
                <div style="margin-top:8px;padding:10px;background:rgba(255,255,255,0.03);border-radius:8px;font-size:0.75rem;">
                  <div style="font-weight:800;margin-bottom:6px;color:rgba(255,255,255,0.7);">
                    ${wu.stations.length} Stations • ${quality.stations_used_temp || 0} used for temp • ${quality.stations_used_wind || 0} used for wind
                  </div>
                  <div style="color:rgba(255,255,255,0.5);line-height:1.6;">
                    ${wu.stations.map(st => 
                      `${st.station_id} (${st.distance_mi}mi) - ${st.temperature_f?.toFixed(1)}°F, ${st.wind_speed_mph?.toFixed(1)}mph`
                    ).join('<br>')}
                  </div>
                </div>`;
            }
          }
          
          return `<div style="${rowStyle}">
            <span style="${nameStyle}">${ok ? "✅" : "❌"} ${name}</span>
            <span style="${ageStyle(ok)}">${age}</span>
            <span style="${descStyle}">${meta.desc}${s.error ? ` <span style="color:rgba(255,120,120,0.8);">— ${s.error}</span>` : ""}</span>
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
    }

    let tideChartObj = null;

    // ======================================================
    // Dock Day Score
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

    function dockWindScore(windDirDeg, windSpeedKt) {
      // Returns 0 (bad) to 1 (good) based on wind angle AND speed
      if (windDirDeg == null || windSpeedKt == null) return 0.7;
      // Hard cap — above 20 kt is unpleasant regardless of direction
      if (windSpeedKt > 20) return 0.0;
      if (windSpeedKt < 5)  return 1.0;   // calm = always fine
      // Angle between wind direction and dock face
      let diff = Math.abs(windDirDeg - DOCK_FACE_DEG);
      if (diff > 180) diff = 360 - diff;
      // 0° = wind from exactly dock direction (onshore) = score 0
      // 180° = wind from behind dock (offshore) = score 1
      const dirScore  = diff / 180;
      // Speed penalty: 5kt=mild, 15kt=significant, 20kt=hard cap above
      const speedPenalty = Math.min((windSpeedKt - 5) / 15, 1.0);
      // Onshore winds penalized harder at speed
      const onshoreBoost = dirScore < 0.33 ? 1.5 : 1.0;
      return Math.max(0, dirScore - speedPenalty * 0.5 * onshoreBoost);
    }

    function renderDockDay(data) {
      const el = document.getElementById("dockDayContent");
      if (!el) return;

      const curve   = (data.tide_curve || {});
      const ctimes  = curve.times   || [];
      const cheights= curve.heights || [];
      const hourly  = data.hourly   || {};
      const htimes  = hourly.times  || [];
      const htemps  = hourly.temperature || [];
      const hwind   = hourly.wind_speed  || [];
      const hwinddir= hourly.wind_direction || [];
      const hprecip = hourly.precipitation_probability || [];
      const buoy    = data.buoy     || {};
      const waterTempRaw = buoy.water_temp_f;

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
        return date.toISOString().slice(0, 10);
      });

      const dayCards = [];

      for (const dayStr of days) {
        // Find all 6-min curve points for this day
        const dayPoints = [];
        for (let i = 0; i < ctimes.length; i++) {
          if (ctimes[i].startsWith(dayStr)) {
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

          // Wind score for dock
          const windSc = dockWindScore(wdir, wspd);

          // Temp score: 75°F=1.0, 60°F=0.5, 50°F=0.1, below 45°F=0
          // Hard reality: below 50°F is not a dock day regardless of other factors
          const tempSc = temp == null ? 0.5 :
            temp < 45 ? 0.0 :
            temp < 55 ? Math.max(0, (temp - 45) / 20) :
            Math.min(1, (temp - 55) / 25 + 0.5);

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
      const dTileBg    = light ? "rgba(0,0,0,0.02)"   : "rgba(255,255,255,0.03)";
      const dTileBd    = light ? "rgba(0,0,0,0.08)"   : "rgba(255,255,255,0.08)";
      const dDayLbl    = light ? "rgba(0,0,0,0.55)"   : "rgba(255,255,255,0.45)";
      const dDateLbl   = light ? "rgba(0,0,0,0.38)"   : "rgba(255,255,255,0.3)";
      const dDryTxt    = light ? "rgba(0,0,0,0.30)"   : "rgba(255,255,255,0.3)";
      const dWinBg     = light ? "rgba(0,0,0,0.03)"   : "rgba(255,255,255,0.04)";
      const dTimeTxt   = light ? "rgba(0,0,0,0.82)"   : "rgba(255,255,255,0.85)";
      const dDurTxt    = light ? "rgba(0,0,0,0.38)"   : "rgba(255,255,255,0.35)";
      const dPeakTxt   = light ? "rgba(0,0,0,0.35)"   : "rgba(255,255,255,0.3)";
      const dBarBg     = light ? "rgba(0,0,0,0.08)"   : "rgba(255,255,255,0.1)";
      const dDetailTxt = light ? "rgba(0,0,0,0.52)"   : "rgba(255,255,255,0.5)";
      const dFooter    = light ? "rgba(0,0,0,0.28)"   : "rgba(255,255,255,0.22)";

      // Render
      function scoreLabel(s) {
        if (s >= 0.75) return { label:"Great day",  color:"rgba(80,220,120,0.95)",  emoji:"🟢" };
        if (s >= 0.58) return { label:"Good day",   color:"rgba(160,220,80,0.9)",   emoji:"🟡" };
        if (s >= 0.38) return { label:"Marginal",   color:"rgba(255,190,50,0.85)",  emoji:"🟠" };
        if (s >= 0.20) return { label:"Poor",       color:"rgba(200,100,60,0.85)",  emoji:"🔴" };
        return            { label:"Stay inside", color:"rgba(150,50,50,0.9)",    emoji:"❌" };
      }

      function fmtTime(d) {
        return d.toLocaleTimeString("en-US", { hour:"numeric", minute:"2-digit" });
      }

      let html = `<div class="dock-day-grid" style="display:grid;grid-template-columns:repeat(${dayCards.length},minmax(130px,1fr));gap:12px;">`;

      for (const day of dayCards) {
        const sl = scoreLabel(day.bestScore);
        
        // Store today's score for Right Now card
        if (day.dayLabel === "Today") {
          window.__todayDockScore = {score: day.bestScore, label: sl.label, emoji: sl.emoji, color: sl.color};
        }
        
        html += `<div style="background:${dTileBg};border:1px solid ${dTileBd};border-radius:10px;padding:14px 12px;">`;
        html += `<div style="font-size:0.78rem;font-weight:800;color:${dDayLbl};margin-bottom:2px;">${day.dayLabel}</div>`;
        html += `<div style="font-size:0.72rem;color:${dDateLbl};margin-bottom:8px;">${day.dateLabel}</div>`;

        if (!day.usableWindows.length) {
          html += `<div style="font-size:1.4rem;margin-bottom:4px;">🔴</div>`;
          html += `<div style="font-size:0.82rem;font-weight:900;color:rgba(180,80,80,0.8);">Dock dry all day</div>`;
          html += `<div style="font-size:0.72rem;color:${dDryTxt};margin-top:6px;">Low tides fall within usable hours</div>`;
        } else {
          html += `<div style="font-size:1.4rem;margin-bottom:4px;">${sl.emoji}</div>`;
          html += `<div style="font-size:0.88rem;font-weight:900;color:${sl.color};margin-bottom:10px;">${sl.label} <span style="font-size:0.75rem;opacity:0.7;">(${Math.round(day.bestScore)})</span></div>`;

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
            html += `<div>🌡️ ${w.temp != null ? Math.round(w.temp)+"°F" : "--"}</div>`;
            html += `<div>💧 ${w.precip != null ? w.precip+"%" : "--"} precip</div>`;
            html += `<div data-tip="Wind direction relative to your 315° NW-facing dock. NW wind is directly onshore — kicks up chop against the dock. SE wind is offshore — flat calm. NE/SW is crosswind, moderate effect.">`;
            html += `💨 ${w.wspd != null ? Math.round(w.wspd)+" kt" : "--"} ${w.dirName}`;
            html += ` <span style="color:${w.windRelLabel==='offshore'?'rgba(80,220,120,0.8)':w.windRelLabel==='onshore'?'rgba(220,80,80,0.8)':'rgba(255,200,80,0.8)'};">(${w.windRelLabel})</span></div>`;
            if (waterTempRaw != null) {
              html += `<div>🌊 ${Math.round(waterTempRaw)}°F water</div>`;
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
      html += `Wind scored relative to ${DOCK_FACE_DEG}° dock face. Usable hours ${DOCK_USABLE_HOUR_START}:00–${DOCK_USABLE_HOUR_END}:00.`;
      html += `</div>`;

      el.innerHTML = html;
      
      // Update collapsed preview with today's data
      if (dayCards.length > 0 && dayCards[0].dayLabel === "Today") {
        const today = dayCards[0];
        const sl = scoreLabel(today.bestScore);
        const dockScoreEl = document.getElementById("dockScoreCollapsed");
        const dockConditionsEl = document.getElementById("dockConditionsCollapsed");
        if (dockScoreEl) dockScoreEl.innerHTML = `${today.dayLabel}<br>${sl.emoji}`;
        if (dockConditionsEl) dockConditionsEl.textContent = sl.label;
      }
    }

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
        // Update preview to show no data
        if (nextTideEl) nextTideEl.textContent = "No tide data";
        if (nextTideTimeEl) nextTideTimeEl.textContent = "";
        return;
      }

      const today = new Date();
      const todayStr = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
      const nowMins  = today.getHours() * 60 + today.getMinutes();


      // Find next upcoming tide
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
      

      // Group by date, cap at 4 per day, total 8 max
      const byDate = {};
      let total = 0;
      tides.forEach(t => {
        if (total >= 8) return;
        const d = t.date || todayStr;
        if (!byDate[d]) byDate[d] = [];
        if (byDate[d].length >= 4) return;
        byDate[d].push(t);
        total++;
      });

      const todayISO = new Date().toISOString().split("T")[0];
      const tmrw  = new Date(Date.now() + 86400000).toISOString().split("T")[0];

      let tideIdx = 0;
      Object.keys(byDate).sort().forEach(dateKey => {
        const label = dateKey === todayISO ? "Today" :
                      dateKey === tmrw  ? "Tomorrow" :
                      new Date(dateKey + "T12:00:00").toLocaleDateString("en-US",
                        { weekday:"long", month:"short", day:"numeric" });

        const hdr = document.createElement("div");
        hdr.style.cssText = "font-size:0.8rem;font-weight:900;color:rgba(255,255,255,0.45);" +
                            "letter-spacing:0.8px;text-transform:uppercase;margin:12px 0 6px;";
        hdr.textContent = label;
        grid.appendChild(hdr);

        const row = document.createElement("div");
        row.style.cssText = "display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:4px;"; row.className = "nws-hourly-row";

        const dayTiles = byDate[dateKey];
        dayTiles.forEach(t => {
          const isNext = (tideIdx === nextIdx);
          const tile   = document.createElement("div");
          tile.className = "tide-item";
          if (isNext) tile.style.cssText =
            "border:1px solid rgba(100,200,255,0.45);background:rgba(100,200,255,0.08);border-radius:10px;";
          
          // Convert 24-hour time to 12-hour with AM/PM
          let time12hr = t.time;
          if (t.time && t.time.includes(":")) {
            const [hours, mins] = t.time.split(":").map(Number);
            const period = hours >= 12 ? "PM" : "AM";
            const hours12 = hours === 0 ? 12 : hours > 12 ? hours - 12 : hours;
            time12hr = `${hours12}:${mins.toString().padStart(2, '0')} ${period}`;
          }
          
          tile.innerHTML =
            '<div class="tide-type">' + (isNext ? "&#9654; " : "") +
              (t.type === "H" ? "High" : "Low") + '</div>' +
            '<div class="tide-time">' + time12hr + '</div>' +
            '<div class="tide-height">' + (t.height ?? "--") + ' ft</div>';
          row.appendChild(tile);
          tideIdx++;
        });

        // Pad empty cells so grid stays 4-column
        for (let i = dayTiles.length; i < 4; i++) {
          row.appendChild(document.createElement("div"));
        }

        grid.appendChild(row);
      });

      if (note) note.textContent = "Salem Harbor (8442645) \u2014 harmonic predictions. \u25b6 = next tide.";
      
      // Update collapsed preview with next tide (elements already retrieved at top of function)
      if (nextIdx >= 0 && tides[nextIdx]) {
        const nextTide = tides[nextIdx];
        const type = nextTide.type === "H" ? "High" : "Low";
        const height = nextTide.height ? `${nextTide.height} ft` : "--";
        
        // Convert 24-hour time to 12-hour with AM/PM
        let time12hr = nextTide.time || "--";
        if (nextTide.time && nextTide.time.includes(":")) {
          const [hours, mins] = nextTide.time.split(":").map(Number);
          const period = hours >= 12 ? "PM" : "AM";
          const hours12 = hours === 0 ? 12 : hours > 12 ? hours - 12 : hours;
          time12hr = `${hours12}:${mins.toString().padStart(2, '0')} ${period}`;
        }
        
        if (nextTideEl) nextTideEl.textContent = `${type} tide`;
        if (nextTideTimeEl) nextTideTimeEl.textContent = `${time12hr} · ${height}`;
      } else {
        // No upcoming tide found
        if (nextTideEl) nextTideEl.textContent = "No upcoming tide";
        if (nextTideTimeEl) nextTideTimeEl.textContent = "";
      }
    }

    function buildTideChart(curve, events) {
      const ctx = document.getElementById("tideChart");
      if (!ctx || !curve || !Array.isArray(curve.times) || curve.times.length === 0) return;

      // Thin to every 3rd point (~18-min resolution) to keep chart snappy
      const step = 3;
      const labels  = [];
      const heights = [];
      for (let i = 0; i < curve.times.length; i += step) {
        const raw = curve.times[i]; // "YYYY-MM-DD HH:MM"
        const d   = new Date(raw.replace(" ", "T"));
        labels.push(d.toLocaleTimeString("en-US",
          { weekday: undefined, hour: "numeric", minute: "2-digit" }));
        heights.push(curve.heights[i]);
      }

      // Now-line index (closest point to current time)
      const nowMs = Date.now();
      let nowLineIdx = 0;
      let minDiff   = Infinity;
      for (let i = 0; i < curve.times.length; i += step) {
        const d    = new Date(curve.times[i].replace(" ", "T"));
        const diff = Math.abs(d.getTime() - nowMs);
        if (diff < minDiff) { minDiff = diff; nowLineIdx = Math.floor(i / step); }
      }

      // Annotation points for H/L events
      const pointColors = heights.map(() => "transparent");
      const pointRadius = heights.map(() => 0);

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
            // Vertical now-line via a second dataset with a single point
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
                color: "rgba(255,255,255,0.45)",
                maxTicksLimit: 12,
                maxRotation: 0,
                font: { size: 10, weight: "700" }
              },
              grid: { color: "rgba(255,255,255,0.04)" }
            },
            y: {
              ticks: {
                color: "rgba(255,255,255,0.55)",
                callback: v => v.toFixed(1) + " ft",
                font: { size: 10, weight: "700" }
              },
              grid: { color: "rgba(255,255,255,0.06)" }
            }
          }
        }
      });
    }

    let _selectedForecastDate = null;

    function renderForecast(forecastText) {
      const el = document.getElementById("forecastList");
      if (!el || !Array.isArray(forecastText)) return;
      el.innerHTML = "";

      // Group forecast_text into 10 days (combine day/night periods into single row)
      const days = [];
      const seenDates = new Set();
      
      for (const period of forecastText) {
        const dateStr = period.date;
        
        if (seenDates.has(dateStr)) continue;
        seenDates.add(dateStr);
        
        // Find day and night periods for this date
        const dayPeriod = forecastText.find(p => p.date === dateStr && p.is_daytime);
        const nightPeriod = forecastText.find(p => p.date === dateStr && !p.is_daytime);
        
        // For simple dailies, just use the single period
        const isSimple = period.is_simple_daily;
        
        const high = isSimple ? period.temperature : (dayPeriod?.temperature || period.temperature);
        const low = isSimple ? parseInt((period.text || "").match(/low (\d+)/)?.[1] || period.temperature) : (nightPeriod?.temperature || period.temperature);
        
        // Extract precip probability
        const combinedText = isSimple ? period.text : ((dayPeriod?.text || "") + " " + (nightPeriod?.text || ""));
        const precipMatch = (combinedText || "").match(/\((\d+)%\)/);
        const pop = precipMatch ? parseInt(precipMatch[1]) : 0;
        
        // Emoji
        let emoji = "☀️";
        const text = (combinedText || "").toLowerCase();
        if (text.includes("thunder")) emoji = "⛈️";
        else if (text.includes("snow")) emoji = "🌨️";
        else if (text.includes("rain")) emoji = "🌧️";
        else if (text.includes("fog")) emoji = "🌫️";
        else if (text.includes("overcast") || text.includes("mostly cloudy")) emoji = "☁️";
        else if (text.includes("partly cloudy")) emoji = "⛅";
        
        const date = new Date(dateStr + "T00:00:00");
        const day = date.toLocaleDateString("en-US", { weekday: "short" });
        const dateNum = date.toLocaleDateString("en-US", { month:"numeric", day:"numeric" });
        
        days.push({ dateStr, day, dateNum, high, low, emoji, pop });
        
        if (days.length >= 10) break;
      }

      // Render 10 daily rows
      for (const d of days) {
        const row = document.createElement("div");
        row.className = "row forecast-day-row";
        row.dataset.date = d.dateStr;
        row.style.cssText = "border-radius:8px;margin:0 -6px;padding:7px 6px;";

        // Click handler removed - days are no longer clickable

        row.innerHTML = `
          <div class="label" style="display:flex;align-items:center;gap:8px;">
            <span style="font-weight:900;min-width:32px;">${d.day}</span>
            <span style="font-size:0.85rem;color:rgba(255,255,255,0.35);">${d.dateNum}</span>
            <span>${d.emoji}</span>
            ${d.pop > 10 ? `<span style="font-size:0.75rem;color:rgba(140,180,255,0.7);font-weight:800;">${d.pop}%</span>` : ""}
          </div>
          <div class="value">${d.high}° / ${d.low}°</div>`;

        el.appendChild(row);
      }

      updateForecastSelection();

      // Hint
      const hint = document.createElement("div");
      hint.id = "forecastSelectionHint";
      hint.style.cssText = "font-size:0.75rem;color:rgba(255,255,255,0.35);margin-top:8px;font-weight:700;";
      el.appendChild(hint);
      updateForecastSelection();
    }

    function selectForecastDay(dateStr) {
      if (_selectedForecastDate === dateStr) {
        // Deselect — show all periods
        _selectedForecastDate = null;
        filterHyperlocalByDate(null);
      } else {
        _selectedForecastDate = dateStr;
        filterHyperlocalByDate(dateStr);
        // Auto-expand Wyman Cove card
        const card = document.querySelector('[data-collapse-key="hyperlocal_forecast"]');
        if (card) {
          const body = card.querySelector(".card-body");
          const title = card.querySelector(".card-title-collapsible");
          if (body && body.style.display === "none") {
            body.style.display = "";
            if (title) {
              const chev = title.querySelector(".collapse-chevron");
              if (chev) chev.style.transform = "rotate(180deg)";
            }
            try { localStorage.setItem("collapse_hyperlocal_forecast", "open"); } catch(e) {}
          }
          // Scroll into view
          setTimeout(() => card.scrollIntoView({ behavior:"smooth", block:"nearest" }), 100);
        }
      }
      updateForecastSelection();
    }

    function updateForecastSelection() {
      document.querySelectorAll(".forecast-day-row").forEach(row => {
        const isSelected = row.dataset.date === _selectedForecastDate;
        row.style.background = isSelected ? "rgba(100,160,255,0.12)" : "";
      });

      const hint = document.getElementById("forecastSelectionHint");
      if (hint) {
        hint.textContent = _selectedForecastDate
          ? "Tap again to clear · Detail below"
          : "Tap a day to see detailed forecast";
      }
    }

    function filterHyperlocalByDate(dateStr) {
      const list = document.getElementById("hyperlocalForecastList");
      if (!list) return;

      const rows = list.querySelectorAll("div[style*='grid-template-columns']");
      
      if (!dateStr) {
        // No filter - show all rows
        rows.forEach(row => row.style.display = "");
        return;
      }

      // Filter to show only periods matching the selected date
      if (!window._currentForecastText) {
        rows.forEach(row => row.style.display = "");
        return;
      }

      // Get all periods for the selected date
      const matchingPeriods = window._currentForecastText.filter(p => p.date === dateStr);
      const matchingNames = new Set(matchingPeriods.map(p => p.period_name));

      // Show/hide rows based on period name match
      rows.forEach((row, idx) => {
        const period = window._currentForecastText[idx];
        row.style.display = (period && matchingNames.has(period.period_name)) ? "" : "none";
      });
    }
    function fillWorryCard(ids, peak, windowHours) {
      // ids: { score, scoreLabel, peakSpd, dir, exposure, time, note }
      if (!peak) {
        document.getElementById(ids.score).textContent   = "--";
        document.getElementById(ids.peakSpd).textContent = "-- mph";
        document.getElementById(ids.dir).textContent     = "--";
        document.getElementById(ids.exposure).textContent= "--";
        document.getElementById(ids.time).textContent    = "--";
        return;
      }
      const wl = worryLevel(peak.score);
      document.getElementById(ids.score).innerHTML =
        `<span class="badge ${wl.cls}">${peak.score.toFixed(1)}</span> (${wl.label})`;
      document.getElementById(ids.scoreLabel).textContent = `Peak Impact (next ${windowHours}h)`;
      document.getElementById(ids.peakSpd).textContent = `${Math.round(peak.speed)} mph`;
      document.getElementById(ids.dir).textContent     = toCompass(peak.directionDeg);
      document.getElementById(ids.exposure).textContent= `${(peak.exposureFactor * 100).toFixed(0)}%`;
      document.getElementById(ids.time).textContent    = peak.timeISO ? fmtLocal(peak.timeISO) : "--";
    }

    // Per-card window state
    let _gustWindowHours = 12;
    let _susWindowHours  = 12;

    function renderWindRisk(data) {
      const hyp   = data.hyperlocal || {};
      const hourly = data.hourly || {};
      const gustPeak = computePeakWorry(hourly, _gustWindowHours, true);
      const susPeak  = computePeakWorry(hourly, _susWindowHours,  false);

      fillWorryCard(
        { score:"gustScore", scoreLabel:"gustScoreLabel", peakSpd:"gustPeak",
          dir:"gustDir", exposure:"gustExposure", time:"gustTime", note:"gustNote" },
        gustPeak, _gustWindowHours
      );
      fillWorryCard(
        { score:"susScore", scoreLabel:"susScoreLabel", peakSpd:"susPeak",
          dir:"susDir", exposure:"susExposure", time:"susTime", note:"susNote" },
        susPeak, _susWindowHours
      );

      const noteEl = document.getElementById("gustNote");
      if (noteEl) noteEl.textContent = `Peak gust wind impact over next ${_gustWindowHours}h. Score = gust × exposure¹·⁵.`;
      const susNoteEl = document.getElementById("susNote");
      if (susNoteEl) susNoteEl.textContent = `Peak sustained impact over next ${_susWindowHours}h. Sustained = dock lines, outdoor use.`;

      // Add current impact scores to cards
      const cur = data.current || {};
      if (cur.wind_gusts != null && cur.wind_direction != null) {
        const exposure = getExposureFactor(cur.wind_direction);
        const gustScore = Math.round(worryScore(cur.wind_gusts, exposure));
        const gustLevel = worryLevel(gustScore);
        const gustCurEl = document.getElementById("gustCurrentScore");
        if (gustCurEl) gustCurEl.innerHTML = `<span class="badge ${gustLevel.cls}">${gustScore}</span> (${gustLevel.label})`;
      }
      if (cur.wind_speed != null && cur.wind_direction != null) {
        const exposure = getExposureFactor(cur.wind_direction);
        const susScore = Math.round(worryScore(hyp.corrected_wind_speed ?? cur.wind_speed, exposure));
        const susLevel = worryLevel(susScore);
        const susCurEl = document.getElementById("susCurrentScore");
        if (susCurEl) susCurEl.innerHTML = `<span class="badge ${susLevel.cls}">${susScore}</span> (${susLevel.label})`;
      }
    }

    // ======================================================
    // Water Temp Calibration Logger (hidden)
    // Records: timestamp, water_temp_f, tide_height_ft, buoy_temp_f, month
    // Stored in localStorage as JSON array under key 'wt_cal_log'
    // ======================================================
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

    function renderSeaBreezeDetail(data) {
      const sb = data.sea_breeze || {};
      const el = document.getElementById("seaBreezeDetail");
      if (!el) return;

      if (!sb.likelihood) {
        el.innerHTML = `<div style="text-align:center;color:rgba(255,255,255,0.5);padding:20px;">No sea breeze data available</div>`;
        return;
      }

      const scores = sb.scores || {};
      const hyp = data.hyperlocal || {};
      const buoy = data.buoy_44013 || {};
      const cur = data.current || {};

      let statusColor, statusIcon, statusText;
      if (sb.active) {
        statusColor = "rgba(100,200,120,0.95)";
        statusIcon = "🌊";
        statusText = "Active";
      } else if (sb.likelihood >= 40) {
        statusColor = "rgba(220,200,60,0.85)";
        statusIcon = "⚠️";
        statusText = "Possible";
      } else {
        statusColor = "rgba(150,150,150,0.6)";
        statusIcon = "";
        statusText = "Unlikely";
      }

      const html = `
        <div style="text-align:center;margin-bottom:20px;">
          <div style="font-size:2.5rem;color:${statusColor};margin-bottom:8px;">${statusIcon} ${sb.likelihood}%</div>
          <div style="font-size:1.1rem;opacity:0.9;">${statusText}</div>
          <div style="font-size:0.9rem;opacity:0.7;margin-top:4px;">${sb.reason}</div>
        </div>

        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:20px;">
          <div>
            <div style="opacity:0.7;font-size:0.85rem;margin-bottom:4px;">Temp Differential</div>
            <div style="font-size:1.3rem;">${scores.temp || 0}%</div>
            <div style="opacity:0.6;font-size:0.8rem;margin-top:2px;">Land: ${cur.temperature?.toFixed(1) || "--"}°F | Water: ${buoy.water_temp_f?.toFixed(1) || "--"}°F</div>
          </div>
          <div>
            <div style="opacity:0.7;font-size:0.85rem;margin-bottom:4px;">Wind Speed</div>
            <div style="font-size:1.3rem;">${scores.wind_speed || 0}%</div>
            <div style="opacity:0.6;font-size:0.8rem;margin-top:2px;">${(hyp.corrected_wind_speed ?? cur.wind_speed)?.toFixed(1) || "--"} mph</div>
          </div>
          <div>
            <div style="opacity:0.7;font-size:0.85rem;margin-bottom:4px;">Direction</div>
            <div style="font-size:1.3rem;">${scores.direction || 0}%</div>
            <div style="opacity:0.6;font-size:0.8rem;margin-top:2px;">${cur.wind_direction ? Math.round(cur.wind_direction) + "° " + toCompass(cur.wind_direction) : "--"}</div>
          </div>
          <div>
            <div style="opacity:0.7;font-size:0.85rem;margin-bottom:4px;">Time of Day</div>
            <div style="font-size:1.3rem;">${scores.time || 0}%</div>
            <div style="opacity:0.6;font-size:0.8rem;margin-top:2px;">${new Date().toLocaleTimeString("en-US", {hour: "numeric", minute: "2-digit"})}</div>
          </div>
        </div>

        <div style="opacity:0.7;font-size:0.85rem;line-height:1.5;">
          <strong>Calculation:</strong> Likelihood = (Temp × 40%) + (Direction × 30%) + (Wind Speed × 20%) + (Time × 10%)<br>
          = (${scores.temp || 0} × 0.4) + (${scores.direction || 0} × 0.3) + (${scores.wind_speed || 0} × 0.2) + (${scores.time || 0} × 0.1) = ${sb.likelihood}%
        </div>
      `;

      el.innerHTML = html;
      
      // Update collapsed preview
      const seaBreezeCollapsedEl = document.getElementById("seaBreezeCollapsed");
      const seaBreezeProbCollapsedEl = document.getElementById("seaBreezeProbCollapsed");
      if (seaBreezeCollapsedEl) seaBreezeCollapsedEl.textContent = `${sb.likelihood}% likelihood`;
      if (seaBreezeProbCollapsedEl) seaBreezeProbCollapsedEl.textContent = statusText;
    }

    function renderFogDetail(data) {
      const der = data.derived || {};
      const cur = data.current || {};
      
      // Update the main values
      const labelEl = document.getElementById("fogCurrentLabel");
      const probEl = document.getElementById("fogCurrentProb");
      
      const fogLabel = der.fog_label ?? "--";
      const fogProb = der.fog_probability;
      
      if (labelEl) labelEl.textContent = fogLabel;
      if (probEl) probEl.textContent = fogProb != null ? `${fogProb}%` : "--";
      
      // Calculate the inputs and effects for the breakdown table
      const temp = cur.temperature;
      const dewpt = cur.dew_point;
      const humidity = cur.humidity;
      const hyp = data.hyperlocal || {};
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

    function initWindPills(data) {
      document.querySelectorAll(".wpill").forEach(btn => {
        btn.addEventListener("click", () => {
          const target = btn.dataset.target;
          const hours  = parseInt(btn.dataset.hours, 10);
          // Update active state for this group
          document.querySelectorAll(`.wpill[data-target="${target}"]`)
            .forEach(b => b.classList.remove("active"));
          btn.classList.add("active");
          if (target === "gust") _gustWindowHours = hours;
          else                   _susWindowHours  = hours;
          renderWindRisk(window.__lastWeatherData || data);
        });
      });
    }

    // ======================================================
    // Sun (SunCalc)
    // ======================================================
    function renderSun(daily) {
      if (typeof SunCalc === "undefined") return;

      const now  = new Date();
      const pos  = SunCalc.getPosition(now, HOME_LAT, HOME_LON);
      const times= SunCalc.getTimes(now, HOME_LAT, HOME_LON);

      // Altitude and status
      const altDeg = Math.round(pos.altitude * 180 / Math.PI);
      let status, emoji;
      if (altDeg >= 20)       { status = "Above horizon";        emoji = "\u2600\uFE0F"; }
      else if (altDeg >= 5)   { status = "Low in sky";           emoji = "\uD83C\uDF05"; }
      else if (altDeg >= 0)   { status = "Just above horizon";   emoji = "\uD83C\uDF05"; }
      else if (altDeg >= -6)  { status = "Civil twilight";       emoji = "\uD83C\uDF06"; }
      else if (altDeg >= -12) { status = "Nautical twilight";    emoji = "\uD83C\uDF06"; }
      else if (altDeg >= -18) { status = "Astronomical twilight";emoji = "\uD83C\uDF11"; }
      else                    { status = "Below horizon (night)"; emoji = "\uD83C\uDF11"; }

      document.getElementById("sunEmoji").textContent   = emoji;
      document.getElementById("sunStatus").textContent  = status;
      
      // Update collapsed preview - show next event only (sunrise or sunset)
      const sunStatusCollapsedEl = document.getElementById("sunStatusCollapsed");
      const sunTimesCollapsedEl = document.getElementById("sunTimesCollapsed");
      
      if (sunStatusCollapsedEl && sunTimesCollapsedEl) {
        // Determine next event
        const now = new Date();
        const sunrise = times.sunrise;
        const sunset = times.sunset;
        
        let nextEvent, nextTime;
        if (now < sunrise) {
          nextEvent = "Sunrise";
          nextTime = fmtTime(sunrise);
        } else if (now < sunset) {
          nextEvent = "Sunset";
          nextTime = fmtTime(sunset);
        } else {
          // After sunset - show tomorrow's sunrise
          const tomorrow = new Date(now);
          tomorrow.setDate(tomorrow.getDate() + 1);
          const tomorrowTimes = SunCalc.getTimes(tomorrow, HOME_LAT, HOME_LON);
          nextEvent = "Sunrise";
          nextTime = fmtTime(tomorrowTimes.sunrise);
        }
        
        sunStatusCollapsedEl.textContent = nextEvent;
        sunTimesCollapsedEl.textContent = nextTime;
      }

      // Azimuth
      const azDeg = Math.round(((pos.azimuth * 180 / Math.PI) + 180 + 360) % 360);
      const dirs  = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];
      const compass = dirs[Math.round(azDeg / 22.5) % 16];
      document.getElementById("sunAzimuth").textContent  = azDeg + "\u00b0 " + compass;
      document.getElementById("sunAltitude").textContent = altDeg + "\u00b0";

      // Twilight times from SunCalc
      document.getElementById("civilDawn").textContent =
        fmtTime(times.dawn)    || "--";
      document.getElementById("civilDusk").textContent =
        fmtTime(times.dusk)    || "--";

      // Golden hour
      document.getElementById("goldenHourAM").textContent =
        (times.goldenHourEnd ? fmtTime(times.sunrise) + "\u2013" + fmtTime(times.goldenHourEnd) : "--");
      document.getElementById("goldenHourPM").textContent =
        (times.goldenHour    ? fmtTime(times.goldenHour) + "\u2013" + fmtTime(times.sunset)      : "--");

      // Solar noon from SunCalc (more precise than midpoint calc)
      document.getElementById("solarNoonLabel").textContent =
        "Solar noon: " + (fmtTime(times.solarNoon) || "--");

      // Daylight from the daily JSON (already computed in boot)
      // Note: sunNote shows calculation time
      document.getElementById("sunNote").textContent =
        "Position calculated for " +
        now.toLocaleTimeString("en-US", { hour:"numeric", minute:"2-digit" }) + " local time.";
    }

    // ======================================================
    // Radar — NOAA NEXRAD via IEM WMS
    // 5-minute archive interval (vs RainViewer's 10-minute)
    // WMS endpoint: https://mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0r-t.cgi
    // Layer: nexrad-n0r-wmst (time-enabled NEXRAD base reflectivity composite)
    // Time format: YYYY-MM-DDTHH:MM:00Z
    // ======================================================
    let radarMap       = null;
    let radarInited    = false;
    let radarPlaying   = false;
    let radarTimer     = null;
    let radarFrameIdx  = 0;
    let radarFrames    = [];   // [{ts, kind}]  kind = "past" (no nowcast with NEXRAD)
    let radarLayers    = {};   // _active -> current L.TileLayer
    let radarLayerType = "radar";   // only radar for now (satellite can be added later)

    let radarTileLayers = {};  // street and satellite base map layers
    let radarCurrentTile = "satellite";  // default to satellite
    const RADAR_CENTER  = [42.5014, -70.8750];
    const RADAR_ZOOM    = 7;
    const FRAME_DELAY   = 400;
    const NEXRAD_FRAMES = 24;   // 24 frames * 5min = 2 hours of history

    function mrmsTimeString(date) {
      // Format: YYYY-MM-DDTHH:MM:00Z (rounded to nearest 5-min boundary)
      const d = new Date(date);
      const minutes = Math.floor(d.getUTCMinutes() / 5) * 5;  // round down to 5-min boundary
      d.setUTCMinutes(minutes, 0, 0);
      return d.toISOString().replace(/\.\d{3}Z$/, 'Z').replace(/:\d{2}Z$/, ':00Z');
    }

    function generateMRMSFrames() {
      radarFrames = [];
      const now = new Date();
      
      // NEXRAD archives update every 5 minutes, generate last N frames
      for (let i = 0; i < NEXRAD_FRAMES; i++) {
        const frameTime = new Date(now - (NEXRAD_FRAMES - 1 - i) * 5 * 60 * 1000);
        radarFrames.push({
          ts: frameTime,
          kind: "past"
        });
      }


      // Update scrubber
      const scrubber = document.getElementById("radarScrubber");
      if (scrubber) {
        scrubber.max   = radarFrames.length - 1;
        scrubber.value = radarFrames.length - 1;
      }
      const fmt = d => d.toLocaleTimeString("en-US", { hour:"numeric", minute:"2-digit" });
      if (radarFrames.length) {
        const startEl = document.getElementById("radarScrubStart");
        const endEl   = document.getElementById("radarScrubEnd");
        if (startEl) startEl.textContent = fmt(radarFrames[0].ts);
        if (endEl)   endEl.textContent   = fmt(radarFrames[radarFrames.length - 1].ts);
      }

      // Preload all frame layers (hidden)
      preloadFrames();

      // Show most recent frame
      showFrame(radarFrames.length - 1);
    }

    function preloadFrames() {
      // Clear any existing radar layer
      if (radarLayers._active) {
        radarMap.removeLayer(radarLayers._active);
        radarLayers._active = null;
      }
      radarLayers = {};
    }

    function showFrame(idx) {
      if (!radarMap || !radarFrames.length) return;
      idx = Math.max(0, Math.min(idx, radarFrames.length - 1));
      radarFrameIdx = idx;
      const frame = radarFrames[idx];

      // Add new layer with NEXRAD WMS
      const timeStr = mrmsTimeString(frame.ts);
      
      const layer = L.tileLayer.wms("https://mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0r-t.cgi", {
        layers: 'nexrad-n0r-wmst',  // Note: -wmst suffix for time-enabled layer
        format: 'image/png',
        transparent: true,
        opacity: 0.75,
        attribution: '&copy; <a href="https://mesonet.agron.iastate.edu/">IEM NEXRAD</a>',
        time: timeStr
      });
      
      // Track loading state - need to wait for ALL tiles, not just first one
      layer._loaded = false;
      layer._tilesLoading = 0;
      const oldLayer = radarLayers._active;
      
      layer.on('tileloadstart', () => { 
        layer._tilesLoading++; 
      });
      
      layer.on('tileload', () => { 
        layer._tilesLoading--;
        if (layer._tilesLoading === 0) {
          layer._loaded = true;
          // Remove old layer once ALL new tiles are loaded
          if (oldLayer && radarMap.hasLayer(oldLayer)) {
            radarMap.removeLayer(oldLayer);
          }
        }
      });
      
      layer.on('tileerror', () => { 
        layer._tilesLoading--;
        if (layer._tilesLoading === 0) {
          layer._loaded = true;
          // Remove old layer even with errors
          if (oldLayer && radarMap.hasLayer(oldLayer)) {
            radarMap.removeLayer(oldLayer);
          }
        }
      });
      
      layer.addTo(radarMap);
      radarLayers._active = layer;

      // Timestamp display
      const displayTime = frame.ts.toLocaleTimeString("en-US", { hour:"numeric", minute:"2-digit" });
      document.getElementById("radarTimestamp").textContent = displayTime;
      document.getElementById("radarScrubber").value = idx;

      // Simple scrubber track color (all past frames, no nowcast)
      const curPct = idx / Math.max(radarFrames.length - 1, 1) * 100;
      const scrubber = document.getElementById("radarScrubber");
      if (scrubber) {
        scrubber.style.background = `linear-gradient(to right,
          rgba(100,180,255,0.8) 0%,
          rgba(100,180,255,0.8) ${curPct}%,
          rgba(255,255,255,0.15) ${curPct}%,
          rgba(255,255,255,0.15) 100%)`;
      }
    }

    function initRadar() {
      if (radarInited) return;
      radarInited = true;

      radarMap = L.map("radarMap", {
        center:  RADAR_CENTER,
        zoom:    RADAR_ZOOM,
        minZoom: 4,
        maxZoom: 12,
        zoomControl: true,
        attributionControl: true,
      });
      // Create both base map layers (like overhead)
      radarTileLayers.street = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 18 });
      radarTileLayers.satellite = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", { maxZoom: 19 });
      radarTileLayers.satellite.addTo(radarMap);  // Start with satellite


      // Home marker
      L.circleMarker(RADAR_CENTER, {
        radius: 7, fillColor: "rgba(100,220,255,1)",
        color: "rgba(255,255,255,0.9)", weight: 2, fillOpacity: 1,
        pane: "markerPane",
      }).bindTooltip("Wyman Cove", { permanent: false }).addTo(radarMap);

      setTimeout(() => { if (radarMap) radarMap.invalidateSize(); }, 300);
      generateMRMSFrames();

      // Refresh frames every 5 minutes (matches NEXRAD archive frequency)
      setInterval(generateMRMSFrames, 5 * 60 * 1000);
    }

    function radarTogglePlay() {
      radarPlaying = !radarPlaying;
      const btn = document.getElementById("radarPlayBtn");
      if (radarPlaying) {
        btn.innerHTML = "&#9646;&#9646; Pause";
        radarAdvance();
      } else {
        btn.innerHTML = "&#9654; Play";
        clearTimeout(radarTimer);
      }
    }

    function radarAdvance() {
      if (!radarPlaying) return;
      
      // Wait for current frame to finish loading before advancing
      if (radarLayers._active && !radarLayers._active._loaded) {
        radarTimer = setTimeout(radarAdvance, 100);  // check again in 100ms
        return;
      }
      
      let next = radarFrameIdx + 1;
      if (next >= radarFrames.length) {
        next = 0;
        // Brief pause at end before looping
        radarTimer = setTimeout(() => { showFrame(next); radarTimer = setTimeout(radarAdvance, FRAME_DELAY); }, 800);
        return;
      }
      showFrame(next);
      radarTimer = setTimeout(radarAdvance, FRAME_DELAY);
    }

    function radarScrubTo(val) {
      radarPlaying = false;
      document.getElementById("radarPlayBtn").innerHTML = "&#9654; Play";
      clearTimeout(radarTimer);
      showFrame(parseInt(val));
    }

    function radarToggleMapType() {
      if (!radarMap) return;
      radarMap.removeLayer(radarTileLayers[radarCurrentTile]);
      radarCurrentTile = radarCurrentTile === "street" ? "satellite" : "street";
      radarTileLayers[radarCurrentTile].addTo(radarMap);
      document.getElementById("radarMapBtn").innerHTML =
        radarCurrentTile === "street" ? "🛰 satellite" : "🗺 map";
    }


    // ======================================================
    // Moon (SunCalc)
    // ======================================================
    const HOME_LAT = 42.5014;
    const HOME_LON = -70.8750;

    const MOON_PHASES = [
      { name: "New Moon",        emoji: "\u{1F311}", min: 0,     max: 0.025 },
      { name: "Waxing Crescent", emoji: "\u{1F312}", min: 0.025, max: 0.235 },
      { name: "First Quarter",   emoji: "\u{1F313}", min: 0.235, max: 0.265 },
      { name: "Waxing Gibbous",  emoji: "\u{1F314}", min: 0.265, max: 0.485 },
      { name: "Full Moon",       emoji: "\u{1F315}", min: 0.485, max: 0.515 },
      { name: "Waning Gibbous",  emoji: "\u{1F316}", min: 0.515, max: 0.735 },
      { name: "Last Quarter",    emoji: "\u{1F317}", min: 0.735, max: 0.765 },
      { name: "Waning Crescent", emoji: "\u{1F318}", min: 0.765, max: 0.975 },
      { name: "New Moon",        emoji: "\u{1F311}", min: 0.975, max: 1.0   },
    ];

    function getMoonPhase(fraction) {
      return MOON_PHASES.find(p => fraction >= p.min && fraction < p.max) || MOON_PHASES[0];
    }

    function fmtTime(date) {
      if (!date || isNaN(date.getTime())) return "--";
      return date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
    }

    function azimuthToSky(azRad) {
      const d = ((azRad * 180 / Math.PI) + 180 + 360) % 360;
      const dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];
      const compass = dirs[Math.round(d / 22.5) % 16];
      return { deg: Math.round(d), compass };
    }

    function altitudeDescription(altRad) {
      const deg = Math.round(altRad * 180 / Math.PI);
      let text;
      if (deg < 0)  text = "Below horizon";
      else if (deg < 10) text = "Just above horizon";
      else if (deg < 30) text = "Low in sky";
      else if (deg < 60) text = "Mid sky";
      else               text = "High overhead";
      return { deg, text };
    }

    function daysUntilNextFullMoon() {
      const now = new Date();
      let prev = SunCalc.getMoonIllumination(now).phase;
      for (let d = 1; d <= 30; d++) {
        const candidate = new Date(now.getTime() + d * 86400000);
        const phase = SunCalc.getMoonIllumination(candidate).phase;
        if (prev < 0.5 && phase >= 0.5) return d;
        prev = phase;
      }
      return null;
    }

    function renderMoon() {
      if (typeof SunCalc === "undefined") {
        document.getElementById("moonNote").textContent = "SunCalc library not loaded.";
        return;
      }
      const now   = new Date();
      const illum = SunCalc.getMoonIllumination(now);
      const times = SunCalc.getMoonTimes(now, HOME_LAT, HOME_LON);
      const pos   = SunCalc.getMoonPosition(now, HOME_LAT, HOME_LON);

      const phase = getMoonPhase(illum.phase);
      document.getElementById("moonEmoji").textContent        = phase.emoji;
      document.getElementById("moonPhaseName").textContent    = phase.name;
      document.getElementById("moonIllumination").textContent = Math.round(illum.fraction * 100) + "% illuminated";
      
      // Update collapsed preview
      if (document.getElementById("moonPhaseCollapsed")) {
        document.getElementById("moonPhaseCollapsed").textContent = phase.name;
      }
      if (document.getElementById("moonIllumCollapsed")) {
        document.getElementById("moonIllumCollapsed").textContent = Math.round(illum.fraction * 100) + "% illuminated";
      }

      document.getElementById("moonrise").textContent =
        times.rise ? fmtTime(times.rise) : (times.alwaysUp ? "Up all night" : "Doesn't rise today");
      document.getElementById("moonset").textContent =
        times.set  ? fmtTime(times.set)  : (times.alwaysDown ? "Below horizon all day" : "--");

      const daysToFull = daysUntilNextFullMoon();
      document.getElementById("nextFullMoon").textContent =
        daysToFull === null ? "--" :
        daysToFull === 0    ? "Tonight" :
        daysToFull === 1    ? "Tomorrow" :
        "In " + daysToFull + " days";

      const az  = azimuthToSky(pos.azimuth);
      const alt = altitudeDescription(pos.altitude);
      document.getElementById("moonAzimuth").textContent  = az.deg + "\u00b0 " + az.compass;
      document.getElementById("moonAltitude").textContent = alt.deg + "\u00b0 \u2014 " + alt.text;
      document.getElementById("moonVisible").textContent  = alt.deg >= 0 ? "Yes" : "No (below horizon)";
      document.getElementById("moonNote").textContent     =
        "Position calculated for " + now.toLocaleTimeString("en-US", { hour:"numeric", minute:"2-digit" }) + " local time.";
    }

    // ======================================================
    // NWS Detailed Forecast
    // ======================================================
    
    // Navigate to Hyperlocal tab and open a specific card
    function navigateToHyperlocalCard(cardKey) {
      // Close any open modal cards and remove backdrop
      const openCards = document.querySelectorAll(".card-expanded");
      openCards.forEach(c => c.classList.remove("card-expanded"));
      const backdrop = document.getElementById("modalBackdrop");
      if (backdrop) backdrop.remove();
      
      // Switch to Hyperlocal tab
      
      showTab('hyperlocal');
      
      const rnCard = document.querySelector("[data-collapse-key=\"right_now\"]");
      // Find the card and open it if closed
      const card = document.querySelector(`[data-collapse-key="${cardKey}"]`);
      if (!card) return;
      
      const body = card.querySelector('.card-body');
      if (!body) return;
      
      // Open the card if it's closed
      if (body.style.display === 'none') {
        const titleEl = card.querySelector('.card-title-collapsible');
        if (titleEl) {
          toggleCard(cardKey, titleEl);
        }
      }
      
      // Scroll the card into view with some padding
      setTimeout(() => {
        card.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 100);
    }
    
    function toggleCard(key, el) {
      // Close all other cards first
      // Remove any existing backdrop first
      const existingBackdrop = document.getElementById("modalBackdrop");
      if (existingBackdrop) existingBackdrop.remove();
      
      document.querySelectorAll("[data-collapse-key]").forEach(otherCard => {
      const allCards = document.querySelectorAll("[data-collapse-key]");
      allCards.forEach(c => {
        const k = c.getAttribute("data-collapse-key");
        const b = c.querySelector(".card-body");
      });
        const otherKey = otherCard.getAttribute("data-collapse-key");
        if (otherKey !== key) {
          const otherBody = otherCard.querySelector(".card-body");
          const otherPreview = otherCard.querySelector(".card-collapsed-preview");
          const otherChev = otherCard.querySelector(".collapse-chevron");
          if (otherBody && otherBody.style.display !== "none") {
            otherBody.style.display = "none";
            if (otherPreview) otherPreview.style.display = "";
            otherCard.classList.remove("card-expanded");
            const otherClose = otherCard.querySelector(".card-close-btn");
            if (otherClose) otherClose.style.display = "none";
            if (otherChev) {
              otherChev.style.display = "";
              otherChev.style.transform = "rotate(-90deg)";
            }
          }
        }
      });
      
      const card  = el.closest(".card");
      const body  = card.querySelector(".card-body");
      const preview = card.querySelector(".card-collapsed-preview");
      const chev  = el.querySelector(".collapse-chevron");
      if (!body) return;
      const isOpen = body.style.display !== "none";
      body.style.display = isOpen ? "none" : ""; if (preview) preview.style.display = isOpen ? "" : "none"; if (!isOpen) { const bd = document.createElement("div"); bd.className = "modal-backdrop"; bd.id = "modalBackdrop"; document.body.appendChild(bd); card.classList.add("card-expanded"); } else { const bd = document.getElementById("modalBackdrop"); if (bd) bd.remove(); card.classList.remove("card-expanded"); }
      const closeBtn = card.querySelector(".card-close-btn"); if (closeBtn) closeBtn.style.display = isOpen ? "none" : "flex"; if (chev) { if (card.querySelector(".card-close-btn")) { chev.style.display = "none"; } else { chev.style.display = isOpen ? "" : "none"; chev.style.transform = isOpen ? "rotate(-90deg)" : ""; } }
      try { localStorage.setItem("card_" + key, isOpen ? "0" : "1"); } catch(e) {}
      
      // Initialize radar when radar card is opened
      if (key === "radar" && !isOpen) {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            initRadar();
            if (radarMap) radarMap.invalidateSize();
          });
        });
      }
    }

    function initCollapsibleCards() {
      document.querySelectorAll("[data-collapse-key]").forEach(card => {
        const key     = card.getAttribute("data-collapse-key");
        const openDef = card.getAttribute("data-default-open") !== "false";
        const body    = card.querySelector(".card-body");
        if (!body) return;
        let isOpen = false;  // Always start closed on page load
        body.style.display = isOpen ? "" : "none"; const preview = card.querySelector(".card-collapsed-preview"); if (preview) preview.style.display = isOpen ? "none" : ""; if (card.querySelector(".card-collapsed-preview")) { card.classList.toggle("col-12", isOpen); card.classList.toggle("col-6", !isOpen); }
        const chev = card.querySelector(".collapse-chevron");
        if (chev) { chev.style.transform = isOpen ? "" : "rotate(-90deg)"; if (card.querySelector(".card-close-btn")) chev.style.display = "none"; }
      });
    }

    function toggleAlert(id) {
      const body = document.getElementById(id);
      if (!body) return;
      const idx = id.replace("alertBody_", "");
      const chevron = document.getElementById("alertChevron_" + idx);
      const isOpen = body.style.display !== "none";
      body.style.display = isOpen ? "none" : "block";
      if (chevron) chevron.innerHTML = isOpen ? "&#9660; Show" : "&#9650; Hide";
    }

    function collapseAllAlerts() {
      document.querySelectorAll("[id^='alertBody_']").forEach((body, i) => {
        body.style.display = "none";
        const chev = document.getElementById("alertChevron_" + i);
        if (chev) chev.innerHTML = "&#9660; Show";
      });
    }

  

      function toggleAlertPanel() {
  const panel = document.getElementById("alertsContainer");
  const chev  = document.getElementById("alertSummaryChev");
  if (!panel) return;
  const isOpen = panel.style.display !== "none";
  panel.style.display = isOpen ? "none" : "";
  if (chev) chev.innerHTML = isOpen ? "&#9660; Show" : "&#9650; Hide";
  
  // If opening panel and there's only 1 alert, auto-expand it
  if (!isOpen) {
    const alertBodies = panel.querySelectorAll('[id^="alertBody_"]');
    if (alertBodies.length === 1) {
      const firstAlertId = alertBodies[0].id;
      toggleAlert(firstAlertId);
    }
  }
}

    let nwsShowAll = false;
    const NWS_PREVIEW = 14;  // periods shown before "show all"

    function renderHyperlocalForecast(forecasts) {
      const list = document.getElementById("hyperlocalForecastList");
      if (!list || !Array.isArray(forecasts) || forecasts.length === 0) {
        if (list) list.innerHTML = '<div style="color:rgba(255,255,255,0.4);font-size:0.88rem;padding:8px 0;">No forecast available.</div>';
        return;
      }

      list.innerHTML = "";
      
      forecasts.forEach((p, i) => {
        const row = document.createElement("div");
        row.style.cssText =
          "display:grid;grid-template-columns:130px 1fr;" +
          "gap:0;border-bottom:1px solid rgba(255,255,255,0.06);" +
          "padding:10px 0;";

        // Left: period name + temp + wind (extract wind from text if present)
        const left = document.createElement("div");
        left.style.cssText = "padding-right:16px;";
        
        // Use wind data from forecast object
        let windText = p.wind_full || "";
        
        left.innerHTML =
          '<div style="font-weight:900;font-size:0.9rem;color:rgba(255,255,255,0.9);">' +
            p.period_name + '</div>' +
          '<div style="font-size:1.4rem;font-weight:900;color:rgba(255,255,255,0.85);margin:2px 0;">' +
            p.temperature + "\u00b0F</div>" +
          '<div style="font-size:0.78rem;color:rgba(255,255,255,0.5);font-weight:700;">' +
            windText + '</div>';

        // Right: forecast text (no need for bold short forecast since we already have full text)
        const right = document.createElement("div");
        right.innerHTML =
          '<div style="font-size:0.85rem;color:rgba(255,255,255,0.6);line-height:1.5;">' +
            p.text + '</div>';

        row.appendChild(left);
        row.appendChild(right);
        list.appendChild(row);
      });

      // Last row — remove bottom border
      const rows = list.querySelectorAll("div[style*='border-bottom']");
      if (rows.length > 0) rows[rows.length-1].style.borderBottom = "none";
    }
    function renderNWSForecast(periods) {
      _selectedForecastDate = null;  // clear any day filter on fresh data load
      updateForecastSelection();
      const list = document.getElementById("nwsForecastList");
      const btn  = document.getElementById("nwsExpandBtn");
      if (!list || !Array.isArray(periods) || periods.length === 0) {
        if (list) list.innerHTML =
          '<div style="color:rgba(255,255,255,0.4);font-size:0.88rem;padding:8px 0;">No forecast available.</div>';
        return;
      }

      function renderPeriods(all) {
        const toShow = all ? periods : periods.slice(0, NWS_PREVIEW);
        list.innerHTML = "";
        toShow.forEach((p, i) => {
          const isDay   = p.is_daytime !== false;
          const bgAlpha = isDay ? "0.05" : "0.03";
          const row     = document.createElement("div");
          row.style.cssText =
            "display:grid;grid-template-columns:130px 1fr;" +
            "gap:0;border-bottom:1px solid rgba(255,255,255,0.06);" +
            "padding:10px 0;";

          // Left: name + temp + wind
          const left = document.createElement("div");
          left.style.cssText = "padding-right:16px;";
          left.innerHTML =
            '<div style="font-weight:900;font-size:0.9rem;color:rgba(255,255,255,0.9);">' +
              p.name + '</div>' +
            '<div style="font-size:1.4rem;font-weight:900;color:rgba(255,255,255,0.85);margin:2px 0;">' +
              (p.temperature != null ? p.temperature + "\u00b0F" : "--") + '</div>' +
            '<div style="font-size:0.78rem;color:rgba(255,255,255,0.5);font-weight:700;">' +
              (p.wind_speed || "") + " " + (p.wind_direction || "") + '</div>';

          // Right: short forecast bold + detailed text
          const right = document.createElement("div");
          right.innerHTML =
            '<div style="font-weight:900;font-size:0.88rem;color:rgba(255,255,255,0.8);margin-bottom:4px;">' +
              p.short_forecast + '</div>' +
            '<div style="font-size:0.85rem;color:rgba(255,255,255,0.6);line-height:1.5;">' +
              p.detailed + '</div>';

          row.appendChild(left);
          row.appendChild(right);
          list.appendChild(row);
        });

        // Last row — remove bottom border
        const rows = list.querySelectorAll("div[style*='border-bottom']");
        if (rows.length > 0) rows[rows.length-1].style.borderBottom = "none";
      }

      renderPeriods(false);

      if (periods.length > NWS_PREVIEW) {
        btn.style.display = "inline-block";
        btn.textContent   = "Show all " + periods.length + " periods \u25be";
      } else {
        btn.style.display = "none";
      }
    }

    function nwsToggleExpand() {
      const btn     = document.getElementById("nwsExpandBtn");
      const periods = window._nwsPeriods || [];
      nwsShowAll    = !nwsShowAll;

      const list = document.getElementById("nwsForecastList");
      const toShow = nwsShowAll ? periods : periods.slice(0, NWS_PREVIEW);
      list.innerHTML = "";
      toShow.forEach(p => {
        const row = document.createElement("div");
        row.style.cssText =
          "display:grid;grid-template-columns:130px 1fr;" +
          "gap:0;border-bottom:1px solid rgba(255,255,255,0.06);padding:10px 0;";
        const left = document.createElement("div");
        left.style.cssText = "padding-right:16px;";
        left.innerHTML =
          '<div style="font-weight:900;font-size:0.9rem;color:rgba(255,255,255,0.9);">' + p.name + '</div>' +
          '<div style="font-size:1.4rem;font-weight:900;color:rgba(255,255,255,0.85);margin:2px 0;">' +
            (p.temperature != null ? p.temperature + "\u00b0F" : "--") + '</div>' +
          '<div style="font-size:0.78rem;color:rgba(255,255,255,0.5);font-weight:700;">' +
            (p.wind_speed || "") + " " + (p.wind_direction || "") + '</div>';
        const right = document.createElement("div");
        right.innerHTML =
          '<div style="font-weight:900;font-size:0.88rem;color:rgba(255,255,255,0.8);margin-bottom:4px;">' +
            p.short_forecast + '</div>' +
          '<div style="font-size:0.85rem;color:rgba(255,255,255,0.6);line-height:1.5;">' +
            p.detailed + '</div>';
        row.appendChild(left);
        row.appendChild(right);
        list.appendChild(row);
      });
      const rows = list.querySelectorAll("div[style*='border-bottom']");
      if (rows.length > 0) rows[rows.length-1].style.borderBottom = "none";

      btn.textContent = nwsShowAll
        ? "Show fewer \u25b4"
        : "Show all " + periods.length + " periods \u25be";
    }

    // ======================================================
    // Boot: load data and populate all views
    // ======================================================
    document.getElementById("pageLoaded").textContent =
      new Date().toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

    // ═══════════════════════════════════════════════════════════════
    // Populate Collapsed Tile Previews
    // ═══════════════════════════════════════════════════════════════
    function populateCollapsedPreviews(data) {
      // Helper to safely set text
      const setText = (id, text) => {
        const el = document.getElementById(id);
        if (el) el.textContent = text;
      };
      
      // Extract daily and hourly from data
      const daily = data.daily || {};
      const hourly = data.hourly || {};
      
      // Sky & Precip (48h) - needs to be populated AFTER main data processing
      // This will be called separately after cur/emoji/desc are available
      
      // Wind - shows Wind Impact (sustained) and Gust Impact
      // This will be populated AFTER main data processing where wind impact is calculated
      
      // 10-Day
      const hiToday = daily?.temperature_2m_max?.[0];
      const loToday = daily?.temperature_2m_min?.[0];
      const hi10 = daily?.temperature_2m_max?.[9];
      const lo10 = daily?.temperature_2m_min?.[9];
      if (hiToday && loToday) {
        setText("tenDayRangeCollapsed", `Today ${Math.round(hiToday)}°/${Math.round(loToday)}°`);
        if (hi10 && lo10) {
          setText("tenDayTrendCollapsed", `Day 10: ${Math.round(hi10)}°/${Math.round(lo10)}°`);
        }
      }
      
      // Detailed Forecast
      const periods = data.hyperlocal_forecast?.periods || [];
      if (periods.length > 0) {
        setText("hyperlocalSummaryCollapsed", periods[0].short_summary || "Loading...");
      }
      
      // NWS Forecast
      const nwsPeriods = data.nws_forecast?.periods || [];
      if (nwsPeriods.length > 0) {
        setText("nwsSummaryCollapsed", nwsPeriods[0].name + ": " + (nwsPeriods[0].shortForecast || ""));
      }
      
      // Today Almanac
      const today = new Date();
      const dayName = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"][today.getDay()];
      const monthName = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][today.getMonth()];
      setText("todayDateCollapsed", `${monthName} ${today.getDate()}`);
      setText("todayDayCollapsed", dayName);
      
      // Tides - populated by renderTides()
      
      // Ocean/Buoy
      const waterTemp = data.buoy_44013?.water_temp_f;
      const waveHt = data.buoy_44013?.wave_ht_ft;
      if (waterTemp) setText("waterTempCollapsed", `${waterTemp}°F water`);
      if (waveHt !== undefined) setText("wavesCollapsed", waveHt > 0 ? `${waveHt} ft waves` : "Calm");
      
      // Solar System
      setText("solarStatusCollapsed", "Planets visible tonight");
      
      // Frost/Freeze
      const frostDays = data.frost_stats?.days_since_last_frost;
      if (frostDays !== undefined) {
        setText("frostStatusCollapsed", frostDays === 0 ? "Frost today" : `${frostDays} days since frost`);
        setText("frostDaysCollapsed", `Last year: ${data.frost_stats?.days_since_last_frost_last_year || "—"}`);
      }
      
      // Wind Gust Impact - populated by Right Now card data
      // Wind Sustained Impact - populated by Right Now card data
      
      // Sea Breeze - populated by renderSeaBreezeDetail()
      
      // Sunset Quality - populated by renderSunsetQuality()
      // Dock Day - populated by renderDockDay()
      
      // Fog Risk - use data.derived
      const fogProb = data.derived?.fog_probability;
      const fogLabel = data.derived?.fog_label;
      if (fogProb !== undefined && fogLabel) {
        setText("fogRiskCollapsed", fogLabel);
        setText("fogProbCollapsed", `${fogProb}%`);
      }
    }

    // ═══════════════════════════════════════════════════════════════
    // Main Data Load
    // ═══════════════════════════════════════════════════════════════
    fetch("weather_data.json?t=" + Date.now())
      .then(r => r.json())
      .then(data => {
        window.__lastWeatherData = data;

        // Header
        // // document.getElementById("location").textContent    = data.location?.name ?? "Wyman Cove";
        document.getElementById("dataUpdated").textContent = fmtLocal(data.generated_at || data.location?.updated);
        renderSources(data.sources, (data.pws || {}).stale);
        renderFrostTracker(data.frost_log);
        renderSunsetQuality(data);
        renderDockDay(data);
        renderSolarSystem();

        // Alerts — consolidated summary bar, panel collapsed by default
        const alertsContainer = document.getElementById("alertsContainer");
        const alertSummaryBar = document.getElementById("alertSummaryBar");
        const alertSummaryText = document.getElementById("alertSummaryText");
        alertsContainer.innerHTML = "";
        if (data.alerts && data.alerts.length > 0) {
          const n = data.alerts.length;
          
          // Only show summary bar if there are multiple alerts
          if (alertSummaryBar) {
            alertSummaryBar.style.display = n > 1 ? "flex" : "none";
          }
          
          if (alertSummaryText) {
            alertSummaryText.textContent = `⚠️ ${n} active alert${n > 1 ? "s" : ""}: ${data.alerts.map(a => a.event || "Alert").join(" · ")}`;
          }
          
          // For single alert, show the detail panel directly
          if (n === 1) {
            alertsContainer.style.display = "block";
          }
          
          alertsContainer.innerHTML = data.alerts.map((a, i) => {
            const id = `alertBody_${i}`;
            return `
            <div class="alert-banner">
              <div class="alert-title" onclick="toggleAlert('${id}')" style="cursor:pointer;display:flex;align-items:center;justify-content:flex-start;">
                <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0;">&#9888;&#65039; ${a.event || a.headline?.split(" issued")[0] || "Weather Alert"}</span>
                <span id="alertChevron_${i}" style="font-size:0.8rem;color:rgba(255,255,255,0.5);margin-left:8px;">&#9660; Show</span>
              </div>
              <div id="${id}" class="alert-desc" style="display:none;margin-top:8px;">${a.description || ""}
                ${a.url ? `<div style="margin-top:8px;"><a href="${a.url}" target="_blank" style="color:rgba(100,200,255,0.8);font-size:0.82rem;">Full details &#8599;</a></div>` : ""}
              </div>
            </div>`;
          }).join("");
        }

        // Current conditions
        const cur   = data.current || {};
        const code  = cur.weather_code;
        const emoji = cur.emoji || weatherEmoji[code] || "&#127777;&#65039;";
        const desc  = cur.condition_override || cur.weather_description || weatherDesc[code] || "—";
        document.getElementById("currentTemp").innerHTML =
          `${Math.round(data.hyperlocal?.corrected_temp ?? cur.temperature ?? 0)}<span class="temp-unit">°F</span>`;
        const ctc = document.getElementById("currentTempCollapsed"); if (ctc) ctc.innerHTML = `${Math.round(data.hyperlocal?.corrected_temp ?? cur.temperature ?? 0)}<span class="temp-unit">°F</span>`;
        
        // Hyperlocal data
        const hyp = data.hyperlocal || {};
        const wu = data.wu_stations || {};
        const der = data.derived || {};
        
        // Calculate corrected Feels Like from corrected temp + wind
        let correctedFeelsLike = cur.apparent_temperature ?? 0;
        if (hyp.corrected_temp != null) {
          const T = hyp.corrected_temp;
          const windSpeed = hyp.corrected_wind_speed ?? cur.wind_speed ?? 0;
          let feelsLike = T;
          // Wind chill (if T <= 50°F and wind > 3 mph)
          if (T <= 50 && windSpeed > 3) {
            feelsLike = 35.74 + (0.6215 * T) - (35.75 * Math.pow(windSpeed, 0.16)) + (0.4275 * T * Math.pow(windSpeed, 0.16));
          }
          // Heat index (if T >= 80°F and humidity available)
          else if (T >= 80 && hyp.corrected_humidity != null) {
            const RH = hyp.corrected_humidity;
            feelsLike = -42.379 + (2.04901523 * T) + (10.14333127 * RH) - (0.22475541 * T * RH) - 
                        (0.00683783 * T * T) - (0.05481717 * RH * RH) + (0.00122874 * T * T * RH) +
                        (0.00085282 * T * RH * RH) - (0.00000199 * T * T * RH * RH);
          }
          correctedFeelsLike = feelsLike;
        }
        
        document.getElementById("feelsLike").textContent =
          `Feels like ${Math.round(correctedFeelsLike)}°F`;
        const flc = document.getElementById("feelsLikeCollapsed"); if (flc) flc.textContent = `Feels like ${Math.round(correctedFeelsLike)}°F`;
        const obsTag = cur.condition_source === "KBVY observed" ? " <span style='font-size:0.75rem;opacity:0.5;'>[obs]</span>" : "";
        document.getElementById("condition").innerHTML = `${emoji} ${desc}${obsTag}`;
        // Removed conditionCollapsed - sky condition now goes in Sky & Precip tile
        
        // Populate Sky & Precip tile preview
        const skyEl = document.getElementById("skyCollapsed");
        const precipEl = document.getElementById("precipCollapsed");
        if (skyEl) skyEl.innerHTML = `${emoji} ${desc}`;
        if (precipEl) {
          const precipProb = data.hourly?.precipitation_probability?.[0] || 0;
          const cloudCover = data.hourly?.cloud_cover?.[0] || 0;
          const clearSky = 100 - cloudCover;
          
          let skyText = `${precipProb}% precip`;
          if (cloudCover > 0 && clearSky > 0) {
            skyText += ` | ${Math.round(cloudCover)}% clouds | ${Math.round(clearSky)}% clear`;
          } else if (cloudCover === 100) {
            skyText += ` | 100% clouds`;
          } else if (cloudCover === 0) {
            skyText += ` | Clear`;
          }
          
          precipEl.textContent = skyText;
        }   

        // Update Smart Correction table
        if (hyp) {
          // Primary corrections table
          const scModelTemp = document.getElementById("scModelTemp");
          const scBiasTemp = document.getElementById("scBiasTemp");
          const scCorrectedTemp = document.getElementById("scCorrectedTemp");
          if (scModelTemp) scModelTemp.textContent = hyp.model_temp != null ? hyp.model_temp.toFixed(1) + "°F" : "--";
          if (scBiasTemp) {
            const bias = hyp.weighted_bias ?? hyp.bias_temp;
            scBiasTemp.textContent = bias != null ? (bias >= 0 ? "+" : "") + bias.toFixed(1) + "°F" : "--";
          }
          if (scCorrectedTemp) scCorrectedTemp.textContent = hyp.corrected_temp != null ? Math.round(hyp.corrected_temp) + "°F" : "--";
          
          const scModelHumidity = document.getElementById("scModelHumidity");
          const scBiasHumidity = document.getElementById("scBiasHumidity");
          const scCorrectedHumidity = document.getElementById("scCorrectedHumidity");
          if (scModelHumidity) scModelHumidity.textContent = hyp.model_humidity != null ? Math.round(hyp.model_humidity) + "%" : "--";
          if (scBiasHumidity) scBiasHumidity.textContent = hyp.bias_humidity != null ? (hyp.bias_humidity >= 0 ? "+" : "") + hyp.bias_humidity.toFixed(1) + "%" : "--";
          if (scCorrectedHumidity) scCorrectedHumidity.textContent = hyp.corrected_humidity != null ? Math.round(hyp.corrected_humidity) + "%" : "--";
          
          const scModelPressure = document.getElementById("scModelPressure");
          const scBiasPressure = document.getElementById("scBiasPressure");
          const scCorrectedPressure = document.getElementById("scCorrectedPressure");
          if (scModelPressure) scModelPressure.textContent = hyp.model_pressure_in != null ? hyp.model_pressure_in.toFixed(2) : "--";
          if (scBiasPressure && hyp.model_pressure_in != null && hyp.corrected_pressure_in != null) {
            const pBias = hyp.corrected_pressure_in - hyp.model_pressure_in;
            scBiasPressure.textContent = (pBias >= 0 ? "+" : "") + pBias.toFixed(2);
          } else if (scBiasPressure) {
            scBiasPressure.textContent = "--";
          }
          if (scCorrectedPressure) scCorrectedPressure.textContent = hyp.corrected_pressure_in != null ? hyp.corrected_pressure_in.toFixed(2) : "--";
          
          const scModelGusts = document.getElementById("scModelGusts");
          const scBiasGusts = document.getElementById("scBiasGusts");
          const scCorrectedGusts = document.getElementById("scCorrectedGusts");
          if (scModelGusts) scModelGusts.textContent = hyp.model_wind_gusts != null ? Math.round(hyp.model_wind_gusts) + " mph" : "--";
          if (scBiasGusts) scBiasGusts.textContent = hyp.bias_wind_gusts != null ? (hyp.bias_wind_gusts >= 0 ? "+" : "") + hyp.bias_wind_gusts.toFixed(1) + " mph" : "--";
          if (scCorrectedGusts) scCorrectedGusts.textContent = hyp.corrected_wind_gusts != null ? Math.round(hyp.corrected_wind_gusts) + " mph" : "--";
          
          // Derived values table
          const scModelDewpoint = document.getElementById("scModelDewpoint");
          const scCorrectedDewpoint = document.getElementById("scCorrectedDewpoint");
          if (scModelDewpoint) scModelDewpoint.textContent = cur.dew_point != null ? Math.round(cur.dew_point) + "°F" : "--";
          // Calculate corrected dew point from corrected temp + humidity
          if (scCorrectedDewpoint && hyp.corrected_temp != null && hyp.corrected_humidity != null) {
            const T = hyp.corrected_temp;
            const RH = hyp.corrected_humidity;
            const a = 17.27;
            const b = 237.7;
            const alpha = ((a * T) / (b + T)) + Math.log(RH / 100.0);
            const correctedDewpoint = (b * alpha) / (a - alpha);
            scCorrectedDewpoint.textContent = Math.round(correctedDewpoint) + "°F";
          } else if (scCorrectedDewpoint) {
            scCorrectedDewpoint.textContent = "--";
          }
          
          const scModelFeelsLike = document.getElementById("scModelFeelsLike");
          const scCorrectedFeelsLike = document.getElementById("scCorrectedFeelsLike");
          // Model feels like from apparent_temperature
          if (scModelFeelsLike) scModelFeelsLike.textContent = cur.apparent_temperature != null ? Math.round(cur.apparent_temperature) + "°F" : "--";
          // Calculate corrected feels like from corrected temp + wind
          if (scCorrectedFeelsLike && hyp.corrected_temp != null) {
            const T = hyp.corrected_temp;
            const windSpeed = hyp.corrected_wind_speed ?? cur.wind_speed ?? 0;
            let feelsLike = T;
            // Wind chill (if T <= 50°F and wind > 3 mph)
            if (T <= 50 && windSpeed > 3) {
              feelsLike = 35.74 + (0.6215 * T) - (35.75 * Math.pow(windSpeed, 0.16)) + (0.4275 * T * Math.pow(windSpeed, 0.16));
            }
            // Heat index (if T >= 80°F and humidity available)
            else if (T >= 80 && hyp.corrected_humidity != null) {
              const RH = hyp.corrected_humidity;
              feelsLike = -42.379 + (2.04901523 * T) + (10.14333127 * RH) - (0.22475541 * T * RH) - 
                          (0.00683783 * T * T) - (0.05481717 * RH * RH) + (0.00122874 * T * T * RH) +
                          (0.00085282 * T * RH * RH) - (0.00000199 * T * T * RH * RH);
            }
            scCorrectedFeelsLike.textContent = Math.round(feelsLike) + "°F";
          } else if (scCorrectedFeelsLike) {
            scCorrectedFeelsLike.textContent = "--";
          }
          
          // Wet Bulb Temp
          const scModelWetBulb = document.getElementById("scModelWetBulb");
          const scCorrectedWetBulb = document.getElementById("scCorrectedWetBulb");
          if (scModelWetBulb) scModelWetBulb.textContent = cur.wet_bulb != null ? Math.round(cur.wet_bulb) + "°F" : "--";
          if (scCorrectedWetBulb) scCorrectedWetBulb.textContent = der.corrected_wet_bulb != null ? Math.round(der.corrected_wet_bulb) + "°F" : "--";
          
          // Precip Type (only show if precipitation is likely)
          const scModelPrecipType = document.getElementById("scModelPrecipType");
          const scCorrectedPrecipType = document.getElementById("scCorrectedPrecipType");
          const precipLikely = (cur.precipitation_probability ?? 0) > 20;
          if (precipLikely) {
            // Model precip type from weather code
            const wc = cur.weather_code ?? 0;
            let modelPType = "None";
            if (wc >= 95) modelPType = "Thunderstorm";
            else if (wc >= 85 || (wc >= 71 && wc <= 77)) modelPType = "Snow";
            else if (wc >= 66 && wc <= 67) modelPType = "Freezing Rain";
            else if (wc >= 51 && wc <= 65) modelPType = "Rain";
            if (scModelPrecipType) scModelPrecipType.textContent = modelPType;
            
            // Corrected precip type from surface classification
            const correctedPType = der.surface_precip_type;
            if (scCorrectedPrecipType && correctedPType) {
              const displayType = correctedPType === "freezing_rain" ? "Freezing Rain" :
                                  correctedPType.charAt(0).toUpperCase() + correctedPType.slice(1);
              scCorrectedPrecipType.textContent = displayType;
            } else if (scCorrectedPrecipType) {
              scCorrectedPrecipType.textContent = "--";
            }
          } else {
            if (scModelPrecipType) scModelPrecipType.textContent = "None";
            if (scCorrectedPrecipType) scCorrectedPrecipType.textContent = "None";
          }
          
          // Station count and confidence
          const stationsUsedCount = document.getElementById("stationsUsedCount");
          if (stationsUsedCount) stationsUsedCount.textContent = hyp.stations_used ?? "--";
          
          const hyperlocalConfidence = document.getElementById("hyperlocalConfidence");
          if (hyperlocalConfidence) hyperlocalConfidence.textContent = hyp.confidence || "";
          
          const hyperlocalStationsDiag = document.getElementById("hyperlocalStationsDiag");
          if (hyperlocalStationsDiag) hyperlocalStationsDiag.textContent = `${hyp.stations_used ?? "--"} of ${hyp.stations_total ?? "--"} stations used`;
          
          const hyperlocalConfidenceDiag = document.getElementById("hyperlocalConfidenceDiag");
          if (hyperlocalConfidenceDiag) hyperlocalConfidenceDiag.textContent = `${hyp.confidence || "Unknown"} confidence`;
        }

        // Fog risk detail (Hyperlocal tab)
        renderFogDetail(data);

        // Today summary
        const daily = data.daily || {};

        const kbos  = data.kbos   || {};
        
        // Calculate today's high/low from corrected HRRR hourly data
        const hourlyData = data.hourly || {};
        const hourlyTimes = hourlyData.times || [];
        const hourlyTemps = hourlyData.temperature || [];
        const bias = hyp.weighted_bias ?? 0;
        const today = new Date();
        const todayStr = today.toISOString().split('T')[0];
        let todayHigh = null, todayLow = null;
        hourlyTimes.forEach((timeStr, i) => {
          if (timeStr.startsWith(todayStr)) {
            const temp = hourlyTemps[i];
            if (temp != null) {
              const correctedTemp = temp + bias;
              todayHigh = todayHigh === null ? correctedTemp : Math.max(todayHigh, correctedTemp);
              todayLow = todayLow === null ? correctedTemp : Math.min(todayLow, correctedTemp);
            }
          }
        });
        document.getElementById("hiLo").textContent =
          (todayHigh != null && todayLow != null) ? `${Math.round(todayHigh)}° / ${Math.round(todayLow)}°` : "-- / --";
        const popMax = daily.precipitation_probability_max?.[0];
        // RIGHT NOW card - new fields
        
        // Precip type + chance
        const todayCode = daily.weather_code?.[0] ?? code;
        let precipType = "None";
        if (todayCode >= 95) precipType = "Thunderstorm";
        else if (todayCode >= 85 || (todayCode >= 71 && todayCode <= 77)) precipType = "Snow";
        else if (todayCode >= 66 && todayCode <= 67) precipType = "Freezing Rain";
        else if (todayCode >= 51 && todayCode <= 65) precipType = "Rain";
        const precipChanceVal = popMax != null ? `${Math.round(popMax)}%` : "--%";
        document.getElementById("precipNow").textContent = 
          precipType !== "None" ? `${precipType} ${precipChanceVal}` : precipChanceVal;
        
        // Wind Impact now - combined score and wind data
        const windImpactNowEl = document.getElementById("windImpactNow");
        if (windImpactNowEl) {
          const windSpeed = Math.round(hyp.corrected_wind_speed ?? cur.wind_speed ?? 0);
          const windDir = cur.wind_direction != null ? degToCompass(cur.wind_direction) : "";
          
          if (cur.wind_speed != null && cur.wind_direction != null) {
            const exposure = getExposureFactor(cur.wind_direction);
            const sustainedScore = Math.round(worryScore(hyp.corrected_wind_speed ?? cur.wind_speed, exposure));
            const sustainedLevel = worryLevel(sustainedScore);
            const windText = windSpeed > 0 ? `${windDir} ${windSpeed} mph` : "Calm";
            windImpactNowEl.innerHTML = `${sustainedScore} (${sustainedLevel.label}) · ${windText}`;
          } else {
            windImpactNowEl.textContent = windSpeed > 0 ? `-- · ${windDir} ${windSpeed} mph` : "-- · Calm";
          }
        }
        
        // Gust Impact now - combined score and gust data
        const gustImpactNowEl = document.getElementById("gustImpactNow");
        if (gustImpactNowEl) {
          const gustValue = hyp.corrected_wind_gusts ?? cur.wind_gusts;
          const windDir = cur.wind_direction != null ? degToCompass(cur.wind_direction) : "";
          
          if (gustValue != null && cur.wind_direction != null) {
            const exposure = getExposureFactor(cur.wind_direction);
            const gustScore = Math.round(worryScore(gustValue, exposure));
            const gustLevel = worryLevel(gustScore);
            gustImpactNowEl.innerHTML = `${gustScore} (${gustLevel.label}) · ${windDir} ${Math.round(gustValue)} mph`;
          } else if (gustValue != null) {
            gustImpactNowEl.textContent = `-- · ${Math.round(gustValue)} mph`;
          } else {
            gustImpactNowEl.textContent = "--";
          }
        }
        
        // Populate Wind tile preview with same Wind Impact + Gust Impact data (Weather page)
        const windNowCollapsedEl = document.getElementById("windNowCollapsed");
        const windPeakCollapsedEl = document.getElementById("windPeakCollapsed");
        if (windNowCollapsedEl && windImpactNowEl) {
          windNowCollapsedEl.innerHTML = `<strong>Wind Impact</strong><br>${windImpactNowEl.innerHTML}`;
        }
        if (windPeakCollapsedEl && gustImpactNowEl) {
          windPeakCollapsedEl.innerHTML = `<strong>Gust Impact</strong><br>${gustImpactNowEl.innerHTML}`;
        }
        
        // Populate Hyperlocal page Gust Impact and Sustained Wind Impact tiles
        const gustImpactCollapsedEl = document.getElementById("gustImpactCollapsed");
        const gustPeakCollapsedEl = document.getElementById("gustPeakCollapsed");
        const susImpactCollapsedEl = document.getElementById("susImpactCollapsed");
        const susPeakCollapsedEl = document.getElementById("susPeakCollapsed");
        
        if (gustImpactCollapsedEl && gustImpactNowEl) {
          gustImpactCollapsedEl.innerHTML = gustImpactNowEl.innerHTML;
        }
        if (gustPeakCollapsedEl) {
          gustPeakCollapsedEl.textContent = ""; // Clear second line for gust tile
        }
        
        if (susImpactCollapsedEl && windImpactNowEl) {
          susImpactCollapsedEl.innerHTML = windImpactNowEl.innerHTML;
        }
        if (susPeakCollapsedEl) {
          susPeakCollapsedEl.textContent = ""; // Clear second line for sustained tile
        }
        
        // Pressure now (with trend inline)
        const pressure = cur.pressure != null ? hpaToInhg(cur.pressure) + ' inHg' : "--";
        const trend = der.pressure_trend || kbos.tendency_label || "";
        const trendShort = der.best_pressure_tend != null 
          ? (der.best_pressure_tend > 0.5 ? "↑" : der.best_pressure_tend < -0.5 ? "↓" : "") 
          : (trend.includes("Rising") ? "↑" : trend.includes("Falling") ? "↓" : "");
        const pressureChange = der.best_pressure_tend != null ? ` ${der.best_pressure_tend > 0 ? '+' : ''}${der.best_pressure_tend.toFixed(1)} hPa` : "";
        const pressureColType = "";
        document.getElementById("pressureNow").textContent = `${pressure} ${trendShort}${pressureChange}${pressureColType}`.trim();
        
        // Humidity now
        document.getElementById("humidityNow").textContent = 
          cur.humidity != null ? `${Math.round(cur.humidity)}%` : "--%";
        
        // Visibility now
        document.getElementById("visibilityNow").textContent = 
          cur.visibility != null ? `${(cur.visibility / 1609.34).toFixed(1)} mi` : "-- mi";

        document.getElementById("dewPointNow").textContent = cur.dew_point != null ? `${Math.round(cur.dew_point)}°F` : "--°F";
        
        // Dewpoint depression
        const dewDepEl = document.getElementById("dewPointDepression");
        if (cur.dew_point != null && cur.temperature != null) {
          const depression = cur.temperature - cur.dew_point;
          dewDepEl.textContent = ` (${depression.toFixed(1)}° spread)`;
        } else {
          dewDepEl.textContent = "";
        }

        // Model pressure
        const modelPressEl = document.getElementById("pressureModel");
        if (modelPressEl && cur.pressure != null) {
          modelPressEl.textContent = fmtPressure(cur.pressure);
        }

        // UV now
        document.getElementById("uvNow").textContent = 
          cur.uv_index != null ? cur.uv_index.toFixed(1) : "N/A";

        // Sea breeze now
        const seaBreeze = data.sea_breeze || {};
        const sbEl = document.getElementById("seaBreezeNow");
        if (sbEl) {
          if (seaBreeze.likelihood != null) {
            const likelihood = seaBreeze.likelihood;
            let icon = "";
            if (seaBreeze.active) {
              icon = "🌊 ";
            } else if (likelihood >= 40) {
              icon = "⚠️ ";
            }
            sbEl.innerHTML = `${icon}${likelihood}% <span style="opacity:0.6;font-size:0.85rem;">${seaBreeze.reason || ""}</span>`;
          } else {
            sbEl.textContent = "N/A";
          }
        }
        
          // KBOS observed pressure + tendency
        const kbosEl = document.getElementById("pressureKBOS");
        if (kbosEl) {
          if (kbos.pressure_hpa != null) {
            const kbDiff = cur.pressure != null
              ? ` (${(kbos.pressure_hpa - cur.pressure) >= 0 ? "+" : ""}${(kbos.pressure_hpa - cur.pressure).toFixed(1)})`
              : "";
            kbosEl.textContent = fmtPressure(kbos.pressure_hpa) + kbDiff;
            kbosEl.title = "Difference from model";
          } else {
            kbosEl.textContent = "--";
          }
        }

        // KBOS / KBVY observed temps
        const kbvy  = data.kbvy || {};
        const tempObsEl = document.getElementById("tempObsStations");
        if (tempObsEl) {
          const kbosT = kbos.temp_f != null ? kbos.temp_f.toFixed(1) + "°F" : "--";
          const kbvyT = kbvy.temp_f != null ? kbvy.temp_f.toFixed(1) + "°F" : "--";
          tempObsEl.textContent = `${kbosT} / ${kbvyT}`;
        }

        

        // Fog risk
        const fogEl = document.getElementById("fogRiskNow");
        if (fogEl) {
          const fogLabel = der.fog_label ?? "--";
          const fogPct   = der.fog_probability;
          fogEl.textContent = fogPct != null ? `${fogLabel} (${fogPct}%)` : fogLabel;
          fogEl.style.color = fogLabel === "Likely"     ? "rgba(255,220,80,0.9)"
                            : fogLabel === "Possible"   ? "rgba(255,200,100,0.85)"
                            : fogLabel === "Low chance" ? "rgba(200,200,200,0.7)"
                            : "rgba(255,255,255,0.85)";
        }

        // Sunset Score - read from renderSunsetQuality()
        const sunsetScoreEl = document.getElementById("sunsetScoreNow");
        if (sunsetScoreEl && window.__todaySunsetScore) {
          const s = window.__todaySunsetScore;
          sunsetScoreEl.innerHTML = `${s.emoji} ${s.label} <span style="opacity:0.6;font-size:0.85rem;">(${Math.round(s.score)})</span>`;
          sunsetScoreEl.style.color = s.color;
        } else if (sunsetScoreEl) {
          sunsetScoreEl.textContent = "No data";
        }

        // Dock Day Score - read from renderDockDay()
        const dockDayScoreEl = document.getElementById("dockDayScoreNow");
        if (dockDayScoreEl && window.__todayDockScore) {
          const d = window.__todayDockScore;
          dockDayScoreEl.innerHTML = `${d.emoji} ${d.label} <span style="opacity:0.6;font-size:0.85rem;">(${Math.round(d.score)})</span>`;
          dockDayScoreEl.style.color = d.color;
        } else if (dockDayScoreEl) {
          dockDayScoreEl.textContent = "No data";
        }

        // Make hyperlocal fields tappable with click handlers
        if (windImpactNowEl) {
          windImpactNowEl.classList.add('hyperlocal-link');
          windImpactNowEl.onclick = (e) => { e.stopPropagation(); navigateToHyperlocalCard('wind_sus_impact'); };
        }
        if (gustImpactNowEl) {
          gustImpactNowEl.classList.add('hyperlocal-link');
          gustImpactNowEl.onclick = (e) => { e.stopPropagation(); navigateToHyperlocalCard('wind_gust_impact'); };
        }
        if (sbEl) {
          sbEl.classList.add('hyperlocal-link');
          sbEl.onclick = (e) => { e.stopPropagation(); navigateToHyperlocalCard('sea_breeze_detail'); };
        }
        if (fogEl) {
          fogEl.classList.add('hyperlocal-link');
          fogEl.onclick = (e) => { e.stopPropagation(); navigateToHyperlocalCard('fog_risk'); };
        }
        if (sunsetScoreEl) {
          sunsetScoreEl.classList.add('hyperlocal-link');
          sunsetScoreEl.onclick = (e) => { e.stopPropagation(); navigateToHyperlocalCard('sunset_quality'); };
        }
        if (dockDayScoreEl) {
          dockDayScoreEl.classList.add('hyperlocal-link');
          dockDayScoreEl.onclick = (e) => { e.stopPropagation(); navigateToHyperlocalCard('dock_day'); };
        }

        // Pressure alarm banner
        const alarmBanner = document.getElementById("pressureAlarmBanner");
        if (alarmBanner) {
          const alarm      = der.pressure_alarm;
          const alarmLabel = der.pressure_alarm_label;
          if (alarm && alarmLabel) {
            alarmBanner.textContent  = alarmLabel;
            alarmBanner.className    = `pressure-alarm ${alarm}`;
            alarmBanner.style.display = "";
          } else {
            const tend = der.best_pressure_tend;
            const src  = der.best_pressure_tend_src ?? "model";
            const sign = tend != null && tend > 0 ? "+" : "";
            const tendStr = tend != null ? ` (${sign}${tend.toFixed(1)} hPa, ${src})` : "";
            alarmBanner.textContent  = `Pressure: Normal${tendStr}`;
            alarmBanner.className    = "pressure-alarm";
            alarmBanner.style.display = "";
            alarmBanner.style.background = "rgba(255,255,255,0.04)";
            alarmBanner.style.border = "1px solid rgba(255,255,255,0.08)";
            alarmBanner.style.color  = "rgba(255,255,255,0.45)";
          }
        }

        // Storm mode — triggers when 2+ alarm conditions align
        // Integrates into the consolidated alert summary bar
        const stormBanner  = document.getElementById("stormModeBanner");
        const stormDetails = document.getElementById("stormModeDetails");
        const stormFlags = [];
        if (der.pressure_alarm === "falling") stormFlags.push("⬇️ Pressure falling fast");
        if (der.trough_signal === "Approaching") stormFlags.push("🌀 850mb trough approaching");
        const gustWorry = (data.wind_risk?.gust?.level ?? "");
        if (["High","Extreme"].includes(gustWorry)) stormFlags.push(`💨 Gust wind impact: ${gustWorry}`);
        const pop0 = (data.daily?.precipitation_probability_max?.[0] ?? 0);
        if (pop0 >= 60 && der.col_precip_type && der.col_precip_type !== "Rain")
          stormFlags.push(`❄️ Precip likely — column type: ${der.col_precip_type}`);
        
        // Add rain intensity flag for moderate/heavy rain
        const dailyPrecip = (data.daily?.precipitation_sum?.[0] ?? 0);
        if (pop0 >= 60 && dailyPrecip >= 0.5)
          stormFlags.push(`🌧️ Moderate/heavy rain expected (${dailyPrecip.toFixed(1)}")`);

        if (stormBanner && stormDetails) {
          if (stormFlags.length >= 2) {
            stormBanner.style.display = "";
            stormDetails.innerHTML = stormFlags.map(f => `• ${f}`).join("<br>");
            
            // Update banner title based on severity
            const bannerTitle = stormBanner.querySelector("div:first-child");
            if (bannerTitle && bannerTitle.firstChild && bannerTitle.firstChild.nodeType === 3) {
              const severity = stormFlags.length >= 3 ? "⛈️ Storm conditions developing" : "🌧️ Active weather developing";
              bannerTitle.firstChild.textContent = severity + " ";
            }
          } else {
            stormBanner.style.display = "none";
          }
        }
        // Sea breeze indicator
        const sbRow   = document.getElementById("seaBreezeRow");
        const sbLabel = document.getElementById("seaBreezeLabel");
        const sbText  = der.sea_breeze_label;
        const lsDiff  = der.land_sea_diff_f;
        if (sbRow && sbLabel) {
          sbRow.style.display = "";
          if (sbText && sbText !== "No sea breeze") {
            const diffStr = lsDiff != null ? ` (Δ${lsDiff > 0 ? "+" : ""}${lsDiff}°F)` : "";
            sbLabel.textContent = sbText + diffStr;
            sbLabel.style.color = sbText.includes("likely")     ? "rgba(100,200,255,0.95)"
                                 : sbText.includes("possible")   ? "rgba(150,220,255,0.85)"
                                 : sbText.includes("developing") ? "rgba(180,230,255,0.75)"
                                 : sbText.includes("Land")       ? "rgba(200,200,255,0.75)"
                                 : "rgba(255,255,255,0.75)";
          } else {
            const diffStr = lsDiff != null ? ` (land ${lsDiff > 0 ? "+" : ""}${lsDiff}°F vs water)` : "";
            sbLabel.textContent = `None${diffStr}`;
            sbLabel.style.color = "rgba(255,255,255,0.4)";
          }
        }

        // Wet bulb precip type + 850mb column type — only show when precip is likely
        const precipCode = cur.weather_code || 0;
        const precipTypeRow = document.getElementById("precipTypeRow");
        const precipTypeEl  = document.getElementById("precipType");
        const precipTypeOLD    = cur.precip_type;
        const pop = (data.daily?.precipitation_probability_max?.[0] ?? 0);
        const precipCodes = [51,53,55,61,63,65,71,73,75,77,80,81,82,85,86];
        const showPrecip = pop >= 20 || precipCodes.includes(precipCode);

        if (precipTypeRow && precipTypeEl && precipTypeOLD && showPrecip) {
          precipTypeRow.style.display = "";
          precipTypeEl.textContent = precipTypeOLD;
          const wb = cur.wet_bulb;
          precipTypeEl.style.color = wb != null && wb <= 32
            ? "rgba(160,220,255,0.95)"
            : wb != null && wb <= 35
            ? "rgba(255,220,120,0.9)"
            : "rgba(255,255,255,0.85)";
        }


        // Wet bulb temperature display
        const wetBulbRow = document.getElementById("wetBulbRow");
        const wetBulbEl  = document.getElementById("wetBulbTemp");
        const wb = cur.wet_bulb;
        if (wetBulbRow && wetBulbEl && wb != null && showPrecip) {
          wetBulbRow.style.display = "";
          wetBulbEl.textContent = wb.toFixed(1) + "°F";
          // Color based on precip type thresholds
          wetBulbEl.style.color = wb <= 32
            ? "rgba(160,220,255,0.95)"  // Snow
            : wb <= 35
            ? "rgba(255,220,120,0.9)"   // Mixed
            : "rgba(255,255,255,0.85)"; // Rain
        }
        // 850mb column type
        const col850Row  = document.getElementById("col850Row");
        const col850El   = document.getElementById("col850Type");
        const colType    = der.col_precip_type;
        const colConf    = der.col_precip_conf;
        const t850now    = der.temp_850hpa_now;
        if (col850Row && col850El && colType && showPrecip) {
          col850Row.style.display = "";
          const t850str = t850now != null ? ` (${t850now}°F at 850mb)` : "";
          col850El.textContent = `${colType}${t850str}`;
          col850El.style.color = colType.includes("Heavy snow") ? "rgba(100,180,255,1)"
            : colType.includes("Snow")  ? "rgba(160,220,255,0.95)"
            : colType.includes("Mixed") ? "rgba(255,220,120,0.9)"
            : "rgba(255,255,255,0.85)";
        }

        // Trough signal
        const troughEl   = document.getElementById("troughSignal");
        const troughSig  = der.trough_signal;
        const zTend      = der.height_850hpa_tend_6h;
        if (troughEl && troughSig) {
          const zStr = zTend != null ? ` (${zTend > 0 ? "+" : ""}${zTend}m/6h)` : "";
          troughEl.textContent = troughSig + zStr;
          troughEl.style.color = troughSig === "Approaching"
            ? "rgba(255,180,80,0.9)"
            : troughSig === "Ridging"
            ? "rgba(100,220,120,0.9)"
            : "rgba(255,255,255,0.75)";
        }


        // Forecast
        renderForecast(data.forecast_text);

        // 48h charts - start from current hour
        const hourly = data.hourly || {};
        const allTimes = hourly.times || [];
        
        // Find current hour index
        const now = new Date();
        const currentHour = new Date(now.getFullYear(), now.getMonth(), now.getDate(), now.getHours());
        let startIdx = allTimes.findIndex(t => new Date(t) >= currentHour);
        if (startIdx === -1) startIdx = 0; // fallback if not found
        
        const times = allTimes.slice(startIdx, startIdx + 48);
        const sunTimes = (typeof SunCalc !== "undefined")
          ? SunCalc.getTimes(new Date(), HOME_LAT, HOME_LON)
          : null;
        const srHour = sunTimes?.sunrise
          ? sunTimes.sunrise.getHours() + sunTimes.sunrise.getMinutes() / 60
          : 6.0;
        const ssHour = sunTimes?.sunset
          ? sunTimes.sunset.getHours() + sunTimes.sunset.getMinutes() / 60
          : 18.0;
        buildTempPrecipChart(
          times,
          (hourly.temperature || []).map((t, i) => { const bias = hyp.weighted_bias ?? 0; return t != null ? t + bias : null; }).slice(startIdx, startIdx + 48),
          (hourly.precipitation_probability || []).slice(startIdx, startIdx + 48),
          (hourly.corrected_wet_bulb || hourly.wet_bulb || []).slice(startIdx, startIdx + 48),
          (hourly.temperature_850hPa || []).slice(startIdx, startIdx + 48),
          (hourly.cloud_cover_low || []).slice(startIdx, startIdx + 48),
          (hourly.cloud_cover_mid || []).slice(startIdx, startIdx + 48),
          (hourly.cloud_cover_high || []).slice(startIdx, startIdx + 48),
          (hourly.cloud_cover || []).slice(startIdx, startIdx + 48),
          srHour,
          ssHour
        );

        buildWindChart(
          times,
          (hourly.wind_speed     || []).slice(startIdx, startIdx + 48),
          (hourly.wind_gusts     || []).slice(startIdx, startIdx + 48),
          (hourly.wind_direction || []).slice(startIdx, startIdx + 48)
        );

        // Initialize data bars with hour 0 data
        const tempData = (hourly.temperature || []).map((t, i) => { const bias = hyp.weighted_bias ?? 0; return t != null ? t + bias : null; }).slice(startIdx, startIdx + 48);
        const popData = (hourly.precipitation_probability || []).slice(startIdx, startIdx + 48);
        const wbData = (hourly.corrected_wet_bulb || hourly.wet_bulb || []).slice(startIdx, startIdx + 48);
        const t850Data = (hourly.temperature_850hPa || []).slice(startIdx, startIdx + 48);
        const cloudLowData = (hourly.cloud_cover_low || []).slice(startIdx, startIdx + 48);
        const cloudMidData = (hourly.cloud_cover_mid || []).slice(startIdx, startIdx + 48);
        const cloudHighData = (hourly.cloud_cover_high || []).slice(startIdx, startIdx + 48);
        const cloudTotalData = (hourly.cloud_cover || []).slice(startIdx, startIdx + 48);
        
        updateTempPrecipDataBar(0, times, tempData, popData, wbData, t850Data, cloudLowData, cloudMidData, cloudHighData, cloudTotalData);
        
        const windSpeedData = (hourly.wind_speed || []).slice(startIdx, startIdx + 48);
        const windGustData = (hourly.wind_gusts || []).slice(startIdx, startIdx + 48);
        const windDirData = (hourly.wind_direction || []).slice(startIdx, startIdx + 48);
        
        updateWindDataBar(0, times, windSpeedData, windGustData, windDirData);

        // Wind tab
        renderWindRisk(data);
        renderSeaBreezeDetail(data);
        initWindPills(data);

        const windNowEl      = document.getElementById("windNowWind");
        const windGustsEl    = document.getElementById("windGustsWind");
        const pressureNowEl  = document.getElementById("pressureNowWind");
        const pressureTrendEl= document.getElementById("pressureTrendWind");
        if (windNowEl) windNowEl.textContent =
          (cur.wind_speed != null && cur.wind_direction != null)
            ? `${Math.round(cur.wind_speed)} mph • ${toCompass(cur.wind_direction)}`
            : "--";
        if (windGustsEl)     windGustsEl.textContent     = cur.wind_gusts != null ? `${Math.round(cur.wind_gusts)} mph` : "--";
        if (pressureNowEl)   pressureNowEl.textContent   = cur.pressure  != null ? fmtPressure(cur.pressure) : "--";
        if (pressureTrendEl) {
          const trend3h = der.pressure_trend_hpa_3h != null 
          ? `${der.pressure_trend_hpa_3h > 0 ? '+' : ''}${der.pressure_trend_hpa_3h.toFixed(1)} hPa/3h`
          : "--";
        pressureTrendEl.textContent = trend3h;
        }

        // Sustained and Gust Impact Scores
        const sustainedImpactEl = document.getElementById("sustainedImpactWind");
        const gustImpactEl = document.getElementById("gustImpactWind");
        
        if (cur.wind_speed != null && cur.wind_direction != null) {
          const exposure = getExposureFactor(cur.wind_direction);
          const sustainedScore = Math.round(worryScore(cur.wind_speed, exposure));
          const sustainedLevel = worryLevel(sustainedScore);
          if (sustainedImpactEl) {
            sustainedImpactEl.innerHTML = `${sustainedScore} <span style="opacity:0.6;font-size:0.85rem;">(${sustainedLevel.label})</span>`;
          }
        } else if (sustainedImpactEl) {
          sustainedImpactEl.textContent = "N/A";
        }
        
        if (cur.wind_gusts != null && cur.wind_direction != null) {
          const exposure = getExposureFactor(cur.wind_direction);
          const gustScore = Math.round(worryScore(cur.wind_gusts, exposure));
          const gustLevel = worryLevel(gustScore);
          if (gustImpactEl) {
            gustImpactEl.innerHTML = `${gustScore} <span style="opacity:0.6;font-size:0.85rem;">(${gustLevel.label})</span>`;
          }
        } else if (gustImpactEl) {
          gustImpactEl.textContent = "N/A";
        }

        // Sea breeze - Wind tab
        const sbWindEl = document.getElementById("seaBreezeWind");
        if (sbWindEl) {
          if (seaBreeze.likelihood != null) {
            let icon = "";
            if (seaBreeze.active) icon = "🌊 ";
            else if (seaBreeze.likelihood >= 40) icon = "⚠️ ";
            sbWindEl.innerHTML = `${icon}${seaBreeze.likelihood}% <span style="opacity:0.6;font-size:0.85rem;">${seaBreeze.reason || ""}</span>`;
          } else {
            sbWindEl.textContent = "N/A";
          }
        }

        // NWS Forecast
        window._nwsPeriods = data.nws_forecast || [];
        const nwsOfficeEl = document.getElementById('nwsOfficeLabel');
        if (nwsOfficeEl && data.sources && data.sources.nws_forecast) {
          nwsOfficeEl.textContent = data.sources.nws_forecast.office
            ? 'NWS Boston' : '';
        }

        // Hyperlocal forecast
        if (data.forecast_text) {
          window._currentForecastText = data.forecast_text; renderHyperlocalForecast(data.forecast_text);
        }
        renderNWSForecast(window._nwsPeriods);

        // Almanac tab
        renderTides(data.tides?.events);
        initCollapsibleCards();
        
        // Check if radar card is open on page load and initialize it
        const radarCard = document.querySelector('[data-collapse-key="radar"]');
        if (radarCard) {
          const radarBody = radarCard.querySelector('.card-body');
          if (radarBody && radarBody.style.display !== 'none') {
            // Radar is open, initialize it
            requestAnimationFrame(() => {
              requestAnimationFrame(() => {
                initRadar();
                if (radarMap) radarMap.invalidateSize();
              });
            });
          }
        }
        
        renderWaterTempLog();

        // Touch tooltip support — tap to show, tap away to dismiss
        if ('ontouchstart' in window) {
          document.querySelectorAll('[data-tip]').forEach(el => {
            el.addEventListener('touchend', e => {
              e.preventDefault();
              const already = el.classList.contains('tip-active');
              document.querySelectorAll('.tip-active').forEach(t => t.classList.remove('tip-active'));
              if (!already) el.classList.add('tip-active');
            });
          });
          document.addEventListener('touchend', e => {
            if (!e.target.closest('[data-tip]'))
              document.querySelectorAll('.tip-active').forEach(t => t.classList.remove('tip-active'));
          });
        }

        // Buoy 44013
        const buoy = data.buoy_44013 || {};
        const toCompassDir = deg => deg != null ? toCompass(deg, false) : "--";
        const setEl = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

        setEl("buoyWaterTemp", buoy.water_temp_f != null ? buoy.water_temp_f.toFixed(1) + "°F" : "--");
        setEl("buoyAirTemp",   buoy.air_temp_f   != null ? buoy.air_temp_f.toFixed(1)   + "°F" : "--");
        setEl("buoyPressure",  buoy.pressure_hpa != null ? fmtPressure(buoy.pressure_hpa) : "--");
        window.__lastBuoyPressure = buoy.pressure_hpa ?? null;

        const buoyWindEl = document.getElementById("buoyWind");
        if (buoyWindEl) {
          if (buoy.wind_mph != null) {
            const dir = toCompassDir(buoy.wind_dir);
            const gust = buoy.gust_mph != null ? ` (gust ${buoy.gust_mph})` : "";
            buoyWindEl.textContent = `${buoy.wind_mph} mph ${dir}${gust}`;
          } else {
            buoyWindEl.textContent = "--";
          }
        }

        const buoyPtdyEl = document.getElementById("buoyPtdy");
        if (buoyPtdyEl && buoy.pressure_tend_hpa != null) {
          const sign = buoy.pressure_tend_hpa > 0 ? "+" : "";
          buoyPtdyEl.textContent = `${sign}${buoy.pressure_tend_hpa.toFixed(1)} hPa`;
          buoyPtdyEl.style.color = buoy.pressure_tend_hpa <= -3
            ? "rgba(255,100,100,0.9)"
            : buoy.pressure_tend_hpa <= -0.6
            ? "rgba(255,180,80,0.9)"
            : buoy.pressure_tend_hpa >= 0.6
            ? "rgba(100,220,120,0.9)"
            : "rgba(255,255,255,0.75)";
        } else if (buoyPtdyEl) {
          buoyPtdyEl.textContent = "--";
        }

        const waveHtEl = document.getElementById("buoyWaveHt");
        if (waveHtEl) waveHtEl.textContent = buoy.wave_ht_ft != null ? buoy.wave_ht_ft + " ft" : "Calm";
        const wavePdEl = document.getElementById("buoyWavePeriod");
        if (wavePdEl) wavePdEl.textContent = buoy.wave_period_sec != null ? buoy.wave_period_sec + " sec" : "--";
        buildTideChart(data.tide_curve, data.tides);
        const rise = daily.sunrise?.[0]?.split("T")?.[1] ?? "--";
        const set  = daily.sunset?.[0]?.split("T")?.[1] ?? "--";
        document.getElementById("sunrise").textContent = rise;
        document.getElementById("sunset").textContent  = set;

        // Compute daylight duration
        if (rise !== "--" && set !== "--") {
          const [rh, rm] = rise.split(":").map(Number);
          const [sh, sm] = set.split(":").map(Number);
          const mins = (sh * 60 + sm) - (rh * 60 + rm);
          const h = Math.floor(mins / 60), m = mins % 60;
          document.getElementById("daylight").textContent = `${h}h ${m}m daylight`;
        }

        // Sun
        renderSun(daily);

        // Moon
        renderMoon();

        // Today almanac card
        renderTodayAlmanac(daily);
        
        // Populate all collapsed tile previews
        populateCollapsedPreviews(data);
        
        updateSettingBtns();
      })
      .catch(err => {
        console.error(err);
        // // document.getElementById("location").textContent = "Error loading weather_data.json";
      });

    document.getElementById('refreshBtn').addEventListener('click', function() {
      this.style.transform = 'rotate(360deg)';
      setTimeout(() => { this.style.transform = ''; location.reload(); }, 400);
    });