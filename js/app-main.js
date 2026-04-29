// ======================================================
    // Utility Functions
    // ======================================================
    
    /**
     * Calculate wet bulb temperature using Stull's formula
     * @param {number} t_f - Temperature in °F
     * @param {number} rh_pct - Relative humidity in %
     * @returns {number|null} - Wet bulb temperature in °F, or null if invalid
     */
    function calculateWetBulb(t_f, rh_pct) {
      if (t_f == null || rh_pct == null) return null;
      
      // Convert to Celsius
      const t = (t_f - 32) * 5/9;
      const rh = parseFloat(rh_pct);
      
      // Stull's formula
      const tw = (t * Math.atan(0.151977 * Math.pow(rh + 8.313659, 0.5))
                + Math.atan(t + rh)
                - Math.atan(rh - 1.676331)
                + 0.00391838 * Math.pow(rh, 1.5) * Math.atan(0.023101 * rh)
                - 4.686035);
      
      // Convert back to °F and round
      return Math.round((tw * 9/5 + 32) * 10) / 10;
    }

    // ======================================================
    // Menu drawer functions
    // ======================================================
    
    function toggleSettings() {
      const panel = document.getElementById('settingsPanel');
      panel.style.display = panel.style.display === 'none' ? '' : 'none';
    }

    function toggleMenu() {
      const drawer = document.getElementById('menuDrawer');
      const backdrop = document.getElementById('menuBackdrop');
      const isOpen = drawer.classList.contains('open');
      
      if (isOpen) {
        drawer.classList.remove('open');
        backdrop.classList.remove('open');
      } else {
        drawer.classList.add('open');
        backdrop.classList.add('open');
      }
    }

    function toggleMenuSection(sectionId) {
      const section = document.getElementById(sectionId);
      const isOpen = section.classList.contains('open');
      
      if (isOpen) {
        section.classList.remove('open');
      } else {
        section.classList.add('open');
      }
    }

    // ======================================================
    // Settings — theme + pressure units
    // ======================================================

    function setTheme(mode) {
      localStorage.setItem('theme', mode);
      applyTheme(mode);
      updateSettingBtns();
      location.reload();
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



    // Escape key closes any expanded card modal
    document.addEventListener('keydown', function(e) {
      if (e.key !== 'Escape') return;
      const expanded = document.querySelector('.card.card-expanded');
      if (expanded) {
        const titleEl = expanded.querySelector('.card-title-collapsible');
        if (titleEl) toggleCard(expanded.dataset.collapseKey, titleEl);
      }
    });

    function updateSettingBtns() {
      const theme = localStorage.getItem('theme') || 'system';
      // Update menu drawer buttons
      ['themeLightMenu','themeDarkMenu','themeSystemMenu'].forEach(id => {
        document.getElementById(id)?.classList.remove('active');
      });
      const themeMap = { light:'themeLightMenu', dark:'themeDarkMenu', system:'themeSystemMenu' };
      document.getElementById(themeMap[theme])?.classList.add('active');
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
      return hpaToInhg(n) + ' inHg';
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
      const views = { briefing: "briefingView", weather: "weatherView", almanac: "almanacView", overhead: "overheadView", hyperlocal: "hyperlocalView" };
      Object.keys(views).forEach(k => {
        const v = document.getElementById(views[k]);
        if (v) v.style.display = (k === which) ? "" : "none";
      });
      // Stop overhead live refresh when leaving that tab
      if (which !== "overhead" && window.ohStopLive) {
        window.ohStopLive();
      }
      try { localStorage.setItem("activeTab", which); } catch(e) {}
      
      // Fix map sizing when switching to tabs with Leaflet maps
      if (which === "overhead") {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            if (window.ohInitMap) window.ohInitMap();
            if (window.ohMap) window.ohMap.invalidateSize();
          });
        });
      }
      
      if (which === "weather") {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => {
            if (window.collapsedRadarMap) window.collapsedRadarMap.invalidateSize();
          });
        });
      }

      // Re-trigger tide animation when switching to Almanac
      if (which === "almanac") {
        const tw = document.getElementById("tideWater");
        if (tw && tw._prevPercent != null && tw._targetPercent != null) {
          tw.style.transition = "none";
          tw.style.height = Math.max(12, Math.min(95, tw._prevPercent)) + "%";
          void tw.offsetHeight;
          tw.style.transition = "height 2.5s ease-in-out";
          tw.style.height = Math.max(12, Math.min(95, tw._targetPercent)) + "%";
        }
      }

      // Scroll so tab content is visible below sticky header
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    (function restoreTab() {
      try {
        // Tab restore handled after bottom tab bar sync wrapper is initialized below
      } catch(e) {}
    })();


    // ======================================================
    // Swipe navigation between tabs
    // ======================================================
    (function initSwipeNav() {
      const tabOrder = ['briefing', 'weather', 'hyperlocal', 'almanac'];
      let touchStartX = 0;
      let touchStartY = 0;
      let touchStartTime = 0;

      document.addEventListener('touchstart', function(e) {
        touchStartX = e.changedTouches[0].screenX;
        touchStartY = e.changedTouches[0].screenY;
        touchStartTime = Date.now();
      }, { passive: true });

      document.addEventListener('touchend', function(e) {
        const dx = e.changedTouches[0].screenX - touchStartX;
        const dy = e.changedTouches[0].screenY - touchStartY;
        const dt = Date.now() - touchStartTime;

        // Must be horizontal, fast enough, and long enough
        if (Math.abs(dx) < 60 || Math.abs(dy) > Math.abs(dx) || dt > 400) return;

        // Don't swipe when a card is expanded
        if (document.querySelector('.card-expanded')) return;

        // Don't swipe on maps or scrubbers
        if (e.target.closest('#radarMap, #overheadMap, input[type=range]')) return;

        const current = localStorage.getItem('activeTab') || 'briefing';
        const idx = tabOrder.indexOf(current);
        if (idx === -1) return;

        if (dx < 0 && idx < tabOrder.length - 1) {
          showTab(tabOrder[idx + 1]);
          const v = document.getElementById({briefing:'briefingView',weather:'weatherView',hyperlocal:'hyperlocalView',almanac:'almanacView',overhead:'overheadView'}[tabOrder[idx + 1]]);
          if (v) { v.classList.remove('slide-in-left','slide-in-right'); void v.offsetWidth; v.classList.add('slide-in-right'); }
        } else if (dx > 0 && idx > 0) {
          showTab(tabOrder[idx - 1]);
          const v = document.getElementById({briefing:'briefingView',weather:'weatherView',hyperlocal:'hyperlocalView',almanac:'almanacView',overhead:'overheadView'}[tabOrder[idx - 1]]);
          if (v) { v.classList.remove('slide-in-left','slide-in-right'); void v.offsetWidth; v.classList.add('slide-in-left'); }
        }
      }, { passive: true });
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

    function combinedWindImpact(sustainedSpeed, gustSpeed, direction) {
      const exposure = getExposureFactor(direction);
      const sustainedScore = sustainedSpeed != null ? worryScore(sustainedSpeed, exposure) : 0;
      const gustScore      = gustSpeed      != null ? worryScore(gustSpeed,      exposure) : 0;
      return sustainedSpeed != null && sustainedSpeed < 15 ? sustainedScore : gustScore;
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
      
      const dirStr  = dir != null ? toCompass(dir, true) : "—";
      const combined      = dir != null ? Math.round(combinedWindImpact(speed, gust, dir)) : null;
      const combinedLevel = combined != null ? worryLevel(combined) : null;
      const impactStr     = combined != null ? `Impact: ${combined} ${combinedLevel.label}` : "Impact: --";
      const spdStr  = speed != null ? `${Math.round(speed)} mph` : "--";
      const gustStr = gust  != null ? `Gusts ${Math.round(gust)} mph` : "";

      document.getElementById("windDataTime").textContent = timeStr + " ·";
      document.getElementById("windDataLine").textContent =
        `${spdStr}${gustStr ? " · " + gustStr : ""} · ${dirStr} · ${impactStr}`;
    }

    function buildTempPrecipChart(times, temps, pop, wetBulbs, temps850mb, cloudLow, cloudMid, cloudHigh, cloudTotal, sunrise, sunset) {
      const labels = times.map(t => new Date(t).toLocaleTimeString("en-US", { hour: "numeric" }));
      const ctx    = document.getElementById("tempPrecipChart").getContext("2d");
      if (tempPrecipChart) tempPrecipChart.destroy();

      // Precip bar colors by precipitation type
      const precipData   = pop.map(p => p ?? 0);
      const precipColors = (wetBulbs || []).map((wb, i) => {
        const surfTemp = temps[i];
        const temp850  = temps850mb?.[i];
        if (pop[i] === 0) return "rgba(0,0,0,0)";
        if (wb == null) return "rgba(80,140,255,0.85)";
        if (wb <= 28)   return "rgba(230,240,255,0.95)";
        if (temp850 != null && temp850 > 32 && surfTemp != null && surfTemp < 32) {
          return "rgba(255,140,40,0.85)";
        }
        if (wb <= 32)   return "rgba(180,200,240,0.90)";
        if (wb <= 35)   return "rgba(160,100,220,0.85)";
        return "rgba(80,150,255,0.85)";
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
              grid: { color: chartGridColor() },
              min: 0,
              max: axisMax
            },
            y1: {
              position: "right",
              ticks: { color: chartTextColor(), font: { size: 10 }, callback: v => v + " mph" },
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
          [0.025, "New Moon"],      [0.25,  "Waxing Crescent"],
          [0.275, "First Quarter"], [0.5,   "Waxing Gibbous"],
          [0.525, "Full Moon"],     [0.75,  "Waning Gibbous"],
          [0.775, "Last Quarter"],  [1.0,   "Waning Crescent"],
        ];
        moonPhase = phases.find(([t]) => mi.phase < t)?.[1] ?? "New Moon";
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
        ${row("Season (meteorological)",`${season.name}`, `${daysToNext} days until ${season.nextName}`)}
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

      // Check if we have any meaningful frost data this season
      const hasFrostData = frost.season_start && (
        (frost.freeze_days ?? 0) > 0 ||
        (frost.hard_freeze_days ?? 0) > 0 ||
        (frost.severe_days ?? 0) > 0
      );

      if (!frost.season_start) {
        el.innerHTML = `<div style="color:${textFaint};font-size:0.85rem;">No frost data yet — will populate after first overnight run.</div>`;
        return;
      }

      if (!hasFrostData) {
        const upcoming = frost.upcoming_freeze_days || [];
        const upcomingHtml = upcoming.length === 0
          ? `<span style="color:${textFaint};">None in 10-day forecast</span>`
          : upcoming.map(u => {
              const label = u.min_f <= 20 ? "Hard freeze" : u.min_f <= 28 ? "Frost" : "Cool night";
              const d = new Date(u.date).toLocaleDateString("en-US", { weekday:"short", month:"short", day:"numeric" });
              return `<span style="margin-right:12px;">${label} ${d} (${u.min_f}°F)</span>`;
            }).join("");
        el.innerHTML = `
          <div style="text-align:center;padding:12px 0 8px;">
            <div style="font-size:1.8rem;margin-bottom:6px;">❄️</div>
            <div style="font-size:0.92rem;font-weight:600;color:${textFaint};margin-bottom:4px;">No frost events this season</div>
            <div style="font-size:0.78rem;color:${textFaint};margin-bottom:14px;">Season started ${new Date(frost.season_start).toLocaleDateString("en-US",{month:"short",day:"numeric",year:"numeric"})}</div>
          </div>
          <div style="font-size:0.82rem;font-weight:800;color:${textHead};margin-bottom:6px;">Upcoming freeze nights (10-day):</div>
          <div style="font-size:0.82rem;color:${upcomingColor};line-height:1.8;">${upcomingHtml}</div>
        `;
        return;
      }

      const [sy, sm, sd] = frost.season_start.split("-").map(Number);
      const seasonStart = new Date(sy, sm-1, sd).toLocaleDateString("en-US", { month:"short", day:"numeric", year:"numeric" });
      const fmt = d => d ? new Date(d).toLocaleDateString("en-US", { month:"short", day:"numeric" }) : "None this season";

      const upcoming = frost.upcoming_freeze_days || [];
      const upcomingHtml = upcoming.length === 0
        ? `<span style="color:${textFaint};">None in 10-day forecast</span>`
        : upcoming.map(u => {
            const label = u.min_f <= 20 ? "Hard freeze" : u.min_f <= 28 ? "Frost" : "Cool";
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
        
        // Need at least one distance to calculate score
        if (!cloud10 && !cloud25 && !cloud50) continue;
        
        // Use the first available cloud data for timing
        const timeSource = cloud25 || cloud50 || cloud10;
        const sunsetTime = new Date(day.sunset_time);
        const sunsetIdx = timeSource.times.findIndex(t => new Date(t).getTime() >= sunsetTime.getTime());
        
        if (sunsetIdx < 0) continue;
        
        // Use available data, estimate missing with nearby values
        const low10 = cloud10 ? (cloud10.cloud_low[sunsetIdx] ?? 0) 
                              : cloud25 ? (cloud25.cloud_low[sunsetIdx] ?? 0) : 0;
        const mid25 = cloud25 ? (cloud25.cloud_mid[sunsetIdx] ?? 0)
                              : cloud50 ? (cloud50.cloud_mid[sunsetIdx] ?? 0)
                              : cloud10 ? (cloud10.cloud_mid[sunsetIdx] ?? 0) : 0;
        const mid50 = cloud50 ? (cloud50.cloud_mid[sunsetIdx] ?? 0)
                              : cloud25 ? (cloud25.cloud_mid[sunsetIdx] ?? 0) : mid25;
        const high25 = cloud25 ? (cloud25.cloud_high[sunsetIdx] ?? 0)
                               : cloud50 ? (cloud50.cloud_high[sunsetIdx] ?? 0)
                               : cloud10 ? (cloud10.cloud_high[sunsetIdx] ?? 0) : 0;
        const high50 = cloud50 ? (cloud50.cloud_high[sunsetIdx] ?? 0)
                               : cloud25 ? (cloud25.cloud_high[sunsetIdx] ?? 0) : high25;
        const hum25 = (cloud25 || cloud50 || cloud10)?.humidity[sunsetIdx] ?? 50;
        
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
        
        let label, color;
        if (score >= 75)      { label = "Spectacular";  color = "rgba(255,160,40,0.95)";  ; }
        else if (score >= 55) { label = "Very Good";    color = "rgba(255,200,60,0.95)";  ; }
        else if (score >= 35) { label = "Good";         color = "rgba(255,220,100,0.9)"; }
        else if (score >= 18) { label = "Fair";         color = "rgba(180,180,180,0.8)"; }
        else                    { label = "Poor";         color = "rgba(120,120,120,0.6)"; }
        
        const dayLabel = day.day === 0 ? "Today" : day.day === 1 ? "Tomorrow"
          : sunsetTime.toLocaleDateString("en-US", { weekday:"short", month:"short", day:"numeric" });
        const timeLabel = sunsetTime.toLocaleTimeString("en-US", { hour:"numeric", minute:"2-digit" });
        
        scores.push({
          dayLabel, timeLabel, score, label, color,
          avgLow: low10.toFixed(0),
          avgMid: midCloudAvg.toFixed(0),
          avgHigh: ((high25 + high50) / 2).toFixed(0),
          avgHum: hum25.toFixed(0)
        });
        

      }

      // Store today sunset score for Right Now card
      const todayScore = scores.find(s => s.dayLabel === "Today");
      if (todayScore) window.__todaySunsetScore = {score: todayScore.score, label: todayScore.label, color: todayScore.color};

      if (!scores.length) {
        el.innerHTML = `<div style="color:${isLight() ? 'rgba(0,0,0,0.4)' : 'rgba(255,255,255,0.4)'};font-size:0.85rem;">No sunset data in forecast window</div>`;
        return;
      }

      const light = isLight();
      const tileBg   = light ? "rgba(0,0,0,0.03)"   : "rgba(255,255,255,0.04)";
      const tileBd   = light ? "rgba(0,0,0,0.09)"   : "rgba(255,255,255,0.08)";
      const dayCol   = light ? "rgba(0,0,0,0.75)"   : "rgba(255,255,255,0.6)";
      const timeCol  = light ? "rgba(0,0,0,0.50)"   : "rgba(255,255,255,0.35)";
      const barBg    = light ? "rgba(0,0,0,0.10)"   : "rgba(255,255,255,0.1)";
      const detCol   = light ? "rgba(0,0,0,0.55)"   : "rgba(255,255,255,0.4)";
      const noteCol  = light ? "rgba(0,0,0,0.50)"   : "rgba(255,255,255,0.3)";

      // Adjust score colors for light mode readability
      function adjustScoreColor(color) {
        if (!light) return color;
        if (color.includes("120,120,120")) return "rgba(0,0,0,0.7)";     // Poor: darker gray
        if (color.includes("180,180,180")) return "rgba(60,60,60,0.9)";     // Fair: darker gray
        if (color.includes("255,220,100")) return "rgba(180,140,0,0.95)";      // Good: dark gold
        if (color.includes("255,200,60"))  return "rgba(180,130,0,0.95)";      // Very Good: dark gold
        if (color.includes("255,160,40"))  return "rgba(200,100,0,0.95)";      // Spectacular: dark orange
        return color;
      }

      let html = ``;

      // Headline from today's (or next available) sunset score
      if (scores.length > 0) {
        const ts = scores[0];
        const scoreCol = adjustScoreColor(ts.color);
        let sunsetHL;
        const mid = parseInt(ts.avgMid);
        const low = parseInt(ts.avgLow);
        if (ts.note === "Clear sky") {
          sunsetHL = `Good sunset tonight — clear horizon, low humidity`;
        } else if (ts.label === "Spectacular" || ts.label === "Very Good") {
          sunsetHL = `${ts.label} sunset tonight — mid-level clouds at distance (${mid}%)`;
        } else if (ts.label === "Good") {
          sunsetHL = `Decent sunset tonight — some color likely`;
        } else if (ts.label === "Fair") {
          sunsetHL = `Fair sunset tonight — limited color expected`;
        } else if (low > 60) {
          sunsetHL = `Poor sunset tonight — overcast blocks the horizon`;
        } else {
          sunsetHL = `Poor sunset tonight — clouds limit color`;
        }
        html += `<div style="font-size:0.95rem;font-weight:600;color:${scoreCol};margin-bottom:14px;padding:10px 14px;background:rgba(255,255,255,0.04);border-radius:0;border-left:4px solid ${scoreCol};">${sunsetHL}</div>`;
      }

      html += `<div class="scroll-day-grid" style="display:grid;grid-template-columns:repeat(${scores.length},1fr);gap:10px;margin-bottom:12px;">`;
      for (const s of scores) {
        const barW = Math.round(s.score * 100);
        const scoreCol = adjustScoreColor(s.color);
        const noteHtml = s.note ? `<div style="font-size:0.72rem;color:${noteCol};margin-top:4px;">${s.note}</div>` : '';
        html += `
          <div style="background:${tileBg};border:1px solid ${tileBd};
                      border-radius:10px;padding:16px 12px;text-align:center;">
            <div style="font-size:0.9rem;font-weight:800;color:${dayCol};margin-bottom:6px;">${s.dayLabel}</div>
            
            <div style="font-size:1.05rem;font-weight:900;color:${scoreCol};margin-bottom:6px;">${s.label} <span style="font-size:0.8rem;opacity:0.7;">(${Math.round(s.score)})</span></div>
            <div style="font-size:0.8rem;color:${timeCol};margin-bottom:10px;">Sunset ${s.timeLabel}</div>
            <div style="height:5px;background:${barBg};border-radius:3px;overflow:hidden;margin-bottom:10px;">
              <div style="height:100%;width:${barW}%;background:${scoreCol};border-radius:3px;transition:width 0.4s;"></div>
            </div>
            <div style="font-size:0.78rem;color:${detCol};line-height:2;">
              <span>Low ${s.avgLow}%</span> ·
              <span>Mid ${s.avgMid}%</span> ·
              <span>High ${s.avgHigh}%</span>
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
      
      // Update collapsed preview with next sunset's data
      // Determine if we should show today or tomorrow based on current time vs civil dusk
      const now = new Date();
      let nextSunset = scores.length > 0 ? scores[0] : null;
      
      // Check if we're past civil dusk - if so, show tomorrow
      const civilDuskStr = data.sun?.civil_dusk;
      if (civilDuskStr && nextSunset) {
        const civilDusk = new Date(civilDuskStr);
        if (now > civilDusk && scores.length > 1) {
          nextSunset = scores[1]; // Show tomorrow
        }
      }
      
      if (nextSunset) {
        const sunsetDayEl = document.getElementById("sunsetDayCollapsed");
        const sunsetIconEl = document.getElementById("sunsetIconCollapsed");
        const sunsetScoreEl = document.getElementById("sunsetScoreCollapsed");
        
        if (sunsetDayEl) sunsetDayEl.textContent = nextSunset.dayLabel;
        
        if (sunsetScoreEl) sunsetScoreEl.innerHTML = `${nextSunset.label} <span style="font-size:0.85rem;opacity:0.7;">(${nextSunset.score}/100)</span>`;
        
        // Apply gradient class based on score
        const sunsetCard = document.querySelector('[data-collapse-key="sunset_quality"]');
        if (sunsetCard) {
          sunsetCard.classList.remove('tile-sunset-poor', 'tile-sunset-fair', 'tile-sunset-good', 'tile-sunset-verygood', 'tile-sunset-spectacular');
          if (nextSunset.score < 20) sunsetCard.classList.add('tile-sunset-poor');
          else if (nextSunset.score < 35) sunsetCard.classList.add('tile-sunset-fair');
          else if (nextSunset.score < 55) sunsetCard.classList.add('tile-sunset-good');
          else if (nextSunset.score < 75) sunsetCard.classList.add('tile-sunset-verygood');
          else sunsetCard.classList.add('tile-sunset-spectacular');
        }
      }
    }

    function getPlanetSVG(planetName, size) {
      const s = size || 40;
      const c = s / 2; // center
      const r = (s / 2) * 0.8; // radius
      
      const gradients = {
        Mercury: `<radialGradient id="mercury-grad-${s}"><stop offset="30%" stop-color="#9D9993"/><stop offset="100%" stop-color="#5C5A57"/></radialGradient>`,
        Venus: `<radialGradient id="venus-grad-${s}"><stop offset="30%" stop-color="#F5E6C8"/><stop offset="100%" stop-color="#D4BE8F"/></radialGradient>`,
        Mars: `<radialGradient id="mars-grad-${s}"><stop offset="30%" stop-color="#E27B58"/><stop offset="100%" stop-color="#AD3E1A"/></radialGradient>`,
        Jupiter: `<radialGradient id="jupiter-grad-${s}"><stop offset="30%" stop-color="#D4A574"/><stop offset="100%" stop-color="#9E7550"/></radialGradient>`,
        Saturn: `<radialGradient id="saturn-grad-${s}"><stop offset="30%" stop-color="#EAE0C8"/><stop offset="100%" stop-color="#BAA888"/></radialGradient>`
      };
      
      const fills = {
        Mercury: `url(#mercury-grad-${s})`,
        Venus: `url(#venus-grad-${s})`,
        Mars: `url(#mars-grad-${s})`,
        Jupiter: `url(#jupiter-grad-${s})`,
        Saturn: `url(#saturn-grad-${s})`
      };
      
      if (planetName === 'Saturn') {
        const ringRx = r * 1.8;
        const ringRy = r * 0.4;
        const saturnR = r * 0.65;
        return `<svg width="${s}" height="${s}" viewBox="0 0 ${s} ${s}" style="display:inline-block;vertical-align:middle;">
          <defs>${gradients.Saturn}</defs>
          <ellipse cx="${c}" cy="${c}" rx="${ringRx}" ry="${ringRy}" fill="none" stroke="#C4B69A" stroke-width="${s/20}" opacity="0.5"/>
          <circle cx="${c}" cy="${c}" r="${saturnR}" fill="${fills.Saturn}"/>
          <ellipse cx="${c}" cy="${c}" rx="${ringRx}" ry="${ringRy}" fill="none" stroke="#C4B69A" stroke-width="${s/20}" opacity="0.3" clip-path="inset(50% 0 0 0)"/>
        </svg>`;
      }
      
      return `<svg width="${s}" height="${s}" viewBox="0 0 ${s} ${s}" style="display:inline-block;vertical-align:middle;">
        <defs>${gradients[planetName] || gradients.Mercury}</defs>
        <circle cx="${c}" cy="${c}" r="${r}" fill="${fills[planetName] || fills.Mercury}"/>
      </svg>`;
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
      
      // SVG planet functions (40px for collapsed, 60px for expanded)
      const getPlanetSVG = (name, size = 40) => {
        const r = size === 40 ? 16 : 24;
        const cx = size / 2;
        const cy = size / 2;
        
        if (name === "Mercury") {
          return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
            <defs><radialGradient id="mercury-g-${size}"><stop offset="30%" stop-color="#9D9993"/><stop offset="100%" stop-color="#5C5A57"/></radialGradient></defs>
            <circle cx="${cx}" cy="${cy}" r="${r}" fill="url(#mercury-g-${size})"/>
          </svg>`;
        } else if (name === "Venus") {
          return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
            <defs><radialGradient id="venus-g-${size}"><stop offset="30%" stop-color="#F5E6C8"/><stop offset="100%" stop-color="#D4BE8F"/></radialGradient></defs>
            <circle cx="${cx}" cy="${cy}" r="${r}" fill="url(#venus-g-${size})"/>
          </svg>`;
        } else if (name === "Mars") {
          return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
            <defs><radialGradient id="mars-g-${size}"><stop offset="30%" stop-color="#E27B58"/><stop offset="100%" stop-color="#AD3E1A"/></radialGradient></defs>
            <circle cx="${cx}" cy="${cy}" r="${r}" fill="url(#mars-g-${size})"/>
          </svg>`;
        } else if (name === "Jupiter") {
          return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
            <defs><radialGradient id="jupiter-g-${size}"><stop offset="30%" stop-color="#D4A574"/><stop offset="100%" stop-color="#9E7550"/></radialGradient></defs>
            <circle cx="${cx}" cy="${cy}" r="${r}" fill="url(#jupiter-g-${size})"/>
          </svg>`;
        } else if (name === "Saturn") {
          const ringRx = size === 40 ? 22 : 33;
          const ringRy = size === 40 ? 5 : 7.5;
          const planetR = size === 40 ? 12 : 18;
          return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
            <defs><radialGradient id="saturn-g-${size}"><stop offset="30%" stop-color="#EAE0C8"/><stop offset="100%" stop-color="#BAA888"/></radialGradient></defs>
            <ellipse cx="${cx}" cy="${cy}" rx="${ringRx}" ry="${ringRy}" fill="none" stroke="#C4B69A" stroke-width="${size === 40 ? 1.5 : 2}" opacity="0.5"/>
            <circle cx="${cx}" cy="${cy}" r="${planetR}" fill="url(#saturn-g-${size})"/>
            <ellipse cx="${cx}" cy="${cy}" rx="${ringRx}" ry="${ringRy}" fill="none" stroke="#C4B69A" stroke-width="${size === 40 ? 1.5 : 2}" opacity="0.3" clip-path="inset(50% 0 0 0)"/>
          </svg>`;
        }
        return EMOJIS[name] || "•";
      };
      
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
          statusLine = `<span style="color:${dayColor};">${p.alt}° alt · sky too bright</span>`;
        } else if (isGlare) {
          statusLine = `<span style="color:${glareColor};">solar glare</span>`;
        } else {
          statusLine = `<span style="color:${faintTxt};">below horizon</span>`;
        }

        html += `
          <div style="background:${bg};border:1px solid ${borderColor};border-radius:10px;
                      padding:10px 8px;text-align:center;box-shadow:${shadow};">
            <div style="margin-bottom:4px;opacity:${emojiOp};display:flex;justify-content:center;">${getPlanetSVG(p.name, 60)}</div>
            <div style="font-size:0.82rem;font-weight:900;color:${nameColor};margin-bottom:5px;">${p.name}</div>
            <div style="font-size:0.72rem;margin-bottom:4px;">${statusLine}</div>
            <div style="font-size:0.68rem;color:${faintTxt};opacity:${dataOp};">${p.elong}° from Sun · ${p.dist} AU</div>
          </div>`;
      }
      html += `</div>`;

      el.innerHTML = html;
      document.getElementById("solarSystemNote").textContent =
        "Positions calculated client-side using VSOP87 truncated series. Accurate to ~1°.";
      
      // Update collapsed preview with visible planets
      const visiblePlanets = results.filter(r => r.state === 'visible');
      const planetsIconsEl = document.getElementById("planetsIconsCollapsed");
      const planetsNamesEl = document.getElementById("planetsNamesCollapsed");
      
      if (planetsIconsEl && planetsNamesEl) {
        if (visiblePlanets.length > 0) {
          const icons = visiblePlanets.map(p => getPlanetSVG(p.name, 40)).join('');
          const names = visiblePlanets.map(p => p.name).join(', ');
          planetsIconsEl.innerHTML = icons;
          planetsNamesEl.textContent = names; planetsNamesEl.style.fontSize = ''; planetsNamesEl.style.opacity = ''; planetsNamesEl.style.fontWeight = '';
          const labelEl = document.getElementById('planetsVisibleLabel');
          if (labelEl) labelEl.style.display = '';
        } else {
          planetsIconsEl.innerHTML = '';
          planetsNamesEl.textContent = 'None visible now';
          planetsNamesEl.style.fontSize = '20px';
          planetsNamesEl.style.opacity = '0.75';
          planetsNamesEl.style.fontWeight = '400';
          const labelEl2 = document.getElementById('planetsVisibleLabel');
          if (labelEl2) labelEl2.style.display = 'none';
        }
      }
    }

    const SOURCE_META = {
      gfs_current:  { name: "GFS",          desc: "Global Forecast System — current conditions baseline (NOAA)" },
      hrrr_hourly:  { name: "HRRR",         desc: "High-Resolution Rapid Refresh — 48h hourly forecast, cloud layers, upper-air (NOAA)" },
      ecmwf_daily:  { name: "ECMWF",        desc: "European Centre model — 10-day daily forecast (Open-Meteo)" },
      pws:          { name: "PWS",           desc: "Single weather station KMAMARBL63 (Castle Hill, 0.27mi) — fallback only" },
      wu_stations:  { name: "WU Multi",     desc: "Distance- and elevation-weighted, quality-filtered local weather stations (Weather Underground API)" },
      kbos:         { name: "KBOS",         desc: "Boston Logan Airport ASOS — observed temp, pressure, tendency (NWS/aviationweather.gov)" },
      kbvy:         { name: "KBVY",         desc: "Beverly Airport ASOS — observed temp, wind (NWS/aviationweather.gov)" },
      buoy_44013:   { name: "Buoy 44013",   desc: "NOAA Boston Buoy (16mi ENE) — water temp, waves, offshore wind (NDBC)" },
      tides:        { name: "Tides",        desc: "NOAA CO-OPS tide predictions — Salem Harbor station 8442645" },
      nws_alerts:   { name: "NWS Alerts",   desc: "Active NWS watches, warnings, advisories for Marblehead (api.weather.gov)" },
      pirate_weather: { name: "Pirate Weather", desc: "Pirate Weather API — next 60 minutes precipitation, plus solar and CAPE" },
      ebird:        { name: "eBird",        desc: "Cornell eBird recent and notable bird observations near Marblehead" },
      gemini:       { name: "Gemini",       desc: "Google Gemini AI — briefing headline and subheadline generator (free tier)" },
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
      // Build sources table
      const table = document.getElementById("sourcesTable");
      const tableModal = document.getElementById("sourcesTableModal");
      if (!table && !tableModal) return;
      const renderTarget = table || tableModal;
      const pwsName = pwsStale ? "PWS (cached)" : "PWS (live)";

      // Sources rendered as flex rows — works on any screen width
      const rowStyle = "display:flex;gap:8px;align-items:baseline;padding:8px 0;border-bottom:1px solid rgba(255,255,255,0.05);flex-wrap:wrap;";
      const nameStyle = "font-weight:800;color:rgba(255,255,255,0.9);font-size:0.85rem;min-width:90px;flex-shrink:0;";
      const descStyle = "color:rgba(255,255,255,0.5);font-size:0.8rem;flex:1;min-width:0;";
      const badgeStyle = ok => `font-size:0.75rem;font-weight:800;white-space:nowrap;color:${ok ? "rgba(140,240,160,0.9)" : "rgba(255,120,120,0.9)"};`;
      const ageStyle  = ok => `font-size:0.75rem;font-weight:700;color:${ok ? "rgba(255,255,255,0.4)" : "rgba(255,120,120,0.7)"};white-space:nowrap;`;

      renderTarget.innerHTML = `
        <div style="font-weight:900;font-size:0.75rem;color:rgba(255,255,255,0.35);letter-spacing:0.8px;text-transform:uppercase;margin-bottom:8px;">Live Data Sources</div>
        ${order.map(key => {
          const s = sources[key];
          if (!s) return "";
          const ok   = s.status === "ok";
          let age = "--";
          if (key === "gemini" && window.__lastWeatherData?.briefing?.cached_at) {
            const cachedAt = new Date(window.__lastWeatherData.briefing.cached_at);
            age = Math.round((Date.now() - cachedAt.getTime()) / 60000) + "m ago";
          } else if (typeof s.age_minutes === "number") {
            age = Math.round(s.age_minutes) + "m ago";
          }
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
                      `${st.station_id} (${st.distance_mi}mi) - ${st.temperature_f != null ? st.temperature_f.toFixed(1) + "°F" : "---"}, ${st.wind_speed_mph != null ? st.wind_speed_mph.toFixed(1) + "mph" : "---"}`
                    ).join('<br>')}
                  </div>
                </div>`;
            }
          }
          
          return `<div style="${rowStyle}">
            <span style="${badgeStyle(ok)}">${ok ? "●" : "○"}</span> <span style="${nameStyle}">${name}</span>
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
      if (tableModal) tableModal.innerHTML = renderTarget.innerHTML;
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

    function renderHairDay(data) {
      window.__lastWeatherData = data;
      const el = document.getElementById("hairDayContent");
      if (!el) return;

      const hourly  = data.hourly || {};
      const htimes  = hourly.times || [];
      const hhumid  = hourly.humidity || [];
      const htemp   = hourly.temperature || [];
      const hwind   = hourly.wind_gusts || [];  // gusts rip styled hair; sustained just moves it
      const hprecip = hourly.precipitation_probability || [];
      const hcode   = hourly.weather_code || [];
      const hpamt   = hourly.precipitation || [];

      // --- Dew point from temp + RH (Magnus approximation) ---
      function dewPointF(tempF, rh) {
        if (tempF == null || rh == null) return null;
        const Tc = (tempF - 32) * 5 / 9;
        const gamma = Math.log(rh / 100) + (17.625 * Tc) / (243.04 + Tc);
        const dpC = 243.04 * gamma / (17.625 - gamma);
        return dpC * 9 / 5 + 32;
      }

      // --- Absolute humidity (g/m³) from dew point + air temp ---
      // AH = (e * 216.7) / T_kelvin  where e = vapor pressure at dew point in hPa
      function absHumidity(dpF, tempF) {
        if (dpF == null || tempF == null) return null;
        const dpC  = (dpF  - 32) * 5 / 9;
        const tC   = (tempF - 32) * 5 / 9;
        const e    = 6.112 * Math.exp((17.67 * dpC) / (dpC + 243.5));
        return (e * 216.7) / (tC + 273.15);
      }

      // --- Precip type from WMO weather code ---
      function precipType(code) {
        if (code == null) return null;
        if ((code >= 71 && code <= 77) || code === 85 || code === 86) return "Snow";
        if (code === 66 || code === 67) return "Freezing rain";
        if (code >= 51 && code <= 67) return "Rain";
        if (code >= 80 && code <= 84) return "Showers";
        if (code >= 95) return "Thunderstorm";
        return null;
      }


      // --- Hair type profiles ---
      const HAIR_PROFILES = {
        straight: {
          label: "Straight",
          // Straight hair goes limp in humidity, static in dry air
          scoreAH(ah) {
            if (ah == null) return 70;
            if (ah < 2)    return 45;  // static, flyaways
            if (ah < 4)    return 85;
            if (ah < 5)    return 95;  // sweet spot
            if (ah < 6)    return 90;
            if (ah < 7)    return 80;
            if (ah < 10)   return 65;  // getting limp
            if (ah < 14)   return 45;
            if (ah < 17)   return 30;
            return 15;
          },
          windThreshold: 28,  // straight hair handles wind better
          weights: { ah: 0.55, precip: 0.30, wind: 0.15 },
          dryWarning: "Very dry — static and flyaways likely",
          humidWarning: "High humidity — hair may fall flat"
        },
        wavy: {
          label: "Wavy",
          scoreAH(ah) {
            if (ah == null) return 70;
            if (ah < 2)    return 55;
            if (ah < 4)    return 82;
            if (ah < 5)    return 92;
            if (ah < 6)    return 85;
            if (ah < 7)    return 75;
            if (ah < 10)   return 55;
            if (ah < 14)   return 30;
            if (ah < 17)   return 15;
            return 5;
          },
          windThreshold: 22,
          weights: { ah: 0.60, precip: 0.25, wind: 0.15 },
          dryWarning: "Very dry — waves may lose definition",
          humidWarning: "Humid — frizz and puffiness likely"
        },
        curly: {
          label: "Curly",
          scoreAH(ah) {
            if (ah == null) return 70;
            if (ah < 2)    return 50;
            if (ah < 4)    return 72;
            if (ah < 5)    return 88;
            if (ah < 6)    return 80;
            if (ah < 7)    return 68;
            if (ah < 10)   return 45;
            if (ah < 14)   return 22;
            if (ah < 17)   return 10;
            return 5;
          },
          windThreshold: 20,
          weights: { ah: 0.70, precip: 0.20, wind: 0.10 },
          dryWarning: "Very dry — curls may lose definition and frizz",
          humidWarning: "Humid — frizz and volume expansion likely"
        },
        coily: {
          label: "Coily",
          // Coily hair needs moisture — dry air is the enemy
          scoreAH(ah) {
            if (ah == null) return 70;
            if (ah < 2)    return 25;  // very bad — shrinkage, breakage
            if (ah < 4)    return 55;
            if (ah < 5)    return 75;
            if (ah < 6)    return 88;
            if (ah < 7)    return 92;  // sweet spot is higher
            if (ah < 10)   return 85;
            if (ah < 14)   return 70;
            if (ah < 17)   return 55;
            return 40;
          },
          windThreshold: 18,  // more fragile
          weights: { ah: 0.75, precip: 0.15, wind: 0.10 },
          dryWarning: "Very dry — risk of breakage and excess shrinkage",
          humidWarning: "Humid but manageable — seal ends well"
        }
      };

      function getHairType() {
        try { return localStorage.getItem("hairType") || "curly"; } catch(e) { return "curly"; }
      }
      function setHairType(t) {
        try { localStorage.setItem("hairType", t); } catch(e) {}
      }
      const hairProfile = HAIR_PROFILES[getHairType()];

      // --- AH-based scoring (inverted U — sweet spot 4-5 g/m³) ---
      // Too dry (<2) = flyaways/static. Too humid (>14) = frizz.
      // Based on curly hair expert consensus: dew point 35-50°F is optimal.
      function scoreAH(ah) {
        if (ah == null) return 70;
        if (ah < 2)    return 60;  // very dry — flyaways, static
        if (ah < 4)    return 78;  // dry but okay
        if (ah < 5)    return 95;  // sweet spot
        if (ah < 6)    return 88;
        if (ah < 7)    return 80;
        if (ah < 10)   return 60;
        if (ah < 14)   return 35;
        if (ah < 17)   return 15;
        return 5;                  // tropical, brutal
      }

      // --- Precip scoring — type matters ---
      // Snow/freezing rain penalized more heavily than rain
      function scorePrecip(pop, type, amtMm) {
        if (pop == null) return 80;
        let typeMultiplier = 1.0;
        if (type === "Snow" || type === "Freezing rain") typeMultiplier = 1.4;
        const intensity = amtMm != null && amtMm > 5 ? 1.2 : 1.0; // heavy precip extra penalty
        const baseScore = pop < 10  ? 100 :
                          pop < 25  ? 78  :
                          pop < 50  ? 50  :
                          pop < 75  ? 25  : 8;
        return Math.max(5, Math.round(baseScore / (typeMultiplier * intensity)));
      }

      // --- Wind scoring — tuned for curly hair ---
      // Score based on how late in the day wind first crosses threshold.
      // Later bad wind = better score (more of the day happens before ruin).
      // badStartHour is the first hour (6-20) where sustained wind >= 15 mph.
      // Returns null-equivalent 100 if wind stays calm all day.
      const WIND_THRESHOLD_MPH = hairProfile.windThreshold;  // gust threshold (sustained-equivalent ~14-15 mph)
      function scoreWind(badStartHour) {
        if (badStartHour == null) return 100;   // calm all day
        if (badStartHour >= 18)    return 95;   // late evening — day was fine
        if (badStartHour >= 13)    return 80;   // afternoon — morning was good
        if (badStartHour >= 10)    return 60;   // mid-morning — styling window was clean
        if (badStartHour >= 7)     return 35;   // early morning — day ruined from start
        return 20;                              // windy from wake-up
      }

      function labelFor(score) {
        if (score >= 88) return { label: "Great hair day", emoji: "💁",  color: "rgba(100,220,130,0.95)" };
        if (score >= 74) return { label: "Good hair day",  emoji: "😊",  color: "rgba(130,210,100,0.95)" };
        if (score >= 58) return { label: "Manageable",     emoji: "🤷",  color: "rgba(200,190,80,0.95)"  };
        if (score >= 40) return { label: "Frizz risk",     emoji: "😬",  color: "rgba(220,150,60,0.95)"  };
        if (score >= 25) return { label: "Bad hair day",   emoji: "😤",  color: "rgba(220,100,60,0.95)"  };
        return             { label: "Stay inside",         emoji: "🙈",  color: "rgba(200,60,60,0.95)"   };
      }

      // --- Hour weight for morning-biased aggregation ---
      function hourWeight(hr) {
        if (hr >= 6  && hr < 10) return 3.0;  // styling window
        if (hr >= 10 && hr < 14) return 1.0;
        if (hr >= 14 && hr <= 20) return 0.5;
        return 0;
      }

      function aggregateDay(dateStr) {
        let sumDp = 0, sumAH = 0, sumRH = 0, sumTemp = 0;
        let sumPrecip = 0, sumPrecipAmt = 0, totalW = 0;
        let peakMorningDp = null;
        let peakWind = 0;
        let morningWindSum = 0, morningWindW = 0;
        let dominantCode = null, maxCodeW = 0;

        for (let i = 0; i < htimes.length; i++) {
          if (!htimes[i] || !htimes[i].startsWith(dateStr)) continue;
          const hr = new Date(htimes[i]).getHours();
          const w  = hourWeight(hr);
          if (w === 0) continue;

          const dp  = dewPointF(htemp[i], hhumid[i]);
          const ah  = absHumidity(dp, htemp[i]);

          if (dp   != null) { sumDp   += dp   * w; }
          if (ah   != null) { sumAH   += ah   * w; }
          if (hhumid[i] != null) { sumRH   += hhumid[i] * w; }
          if (htemp[i]  != null) { sumTemp  += htemp[i]  * w; }
          totalW += w;

          if (hprecip[i] != null) sumPrecip    += hprecip[i] * w;
          if (hpamt[i]   != null) sumPrecipAmt += hpamt[i]   * w;

          // Dominant weather code by weight
          if (hcode[i] != null && w > maxCodeW) { dominantCode = hcode[i]; maxCodeW = w; }

          const wind = hwind[i];
          if (wind != null) {
            if (wind > peakWind) peakWind = wind;
            if (hr >= 6 && hr < 10) { morningWindSum += wind; morningWindW++; }
          }

          if (hr >= 6 && hr < 10 && dp != null) {
            if (peakMorningDp === null || dp > peakMorningDp) peakMorningDp = dp;
          }
        }

        if (totalW === 0) return null;

        const avgDp       = sumDp    / totalW;
        const avgAH       = sumAH    / totalW;
        const avgRH       = sumRH    / totalW;
        const avgPrecip   = sumPrecip / totalW;
        const avgPrecipAmt= sumPrecipAmt / totalW;
        const morningGust = morningWindW > 0 ? morningWindSum / morningWindW : peakWind;
        const pType       = precipType(dominantCode);

        // --- Walk hours 6-20 to find wind crossover and restyle window ---
        let badStartHour = null;
        const hoursOfDay = [];  // [{hr, wind}] for 6-20 on this date
        for (let i = 0; i < htimes.length; i++) {
          if (!htimes[i] || !htimes[i].startsWith(dateStr)) continue;
          const hr = new Date(htimes[i]).getHours();
          if (hr < 6 || hr > 20) continue;
          hoursOfDay.push({ hr, wind: hwind[i] });
        }
        hoursOfDay.sort((a, b) => a.hr - b.hr);

        for (const h of hoursOfDay) {
          if (h.wind != null && h.wind >= WIND_THRESHOLD_MPH) { badStartHour = h.hr; break; }
        }

        // Restyle window: 2+ consecutive calm hours after badStart, before 7pm
        let restyleWindow = null;
        if (badStartHour != null) {
          let winStart = null, winEnd = null;
          for (const h of hoursOfDay) {
            if (h.hr <= badStartHour || h.hr >= 19) continue;
            if (h.wind != null && h.wind < WIND_THRESHOLD_MPH) {
              if (winStart == null) winStart = h.hr;
              winEnd = h.hr;
            } else {
              if (winStart != null && (winEnd - winStart) >= 1) break;  // had a window, it ended
              winStart = null; winEnd = null;
            }
          }
          if (winStart != null && winEnd != null && (winEnd - winStart) >= 1) {
            restyleWindow = { start: winStart, end: winEnd };
          }
        }

        return { avgDp, avgAH, avgRH, avgPrecip, avgPrecipAmt, pType,
                 peakMorningDp, morningGust, peakGust: peakWind,
                 badStartHour, restyleWindow };
      }

      // --- Build day objects ---
      const now = new Date();
      const days = [];

      for (let d = 0; d <= 2; d++) {
        const date = new Date(now);
        date.setDate(date.getDate() + d);
        const dateStr   = date.toISOString().slice(0, 10);
        const dayName   = d === 0 ? "Today" : d === 1 ? "Tomorrow"
                        : date.toLocaleDateString("en-US", { weekday: "long" });
        const dateLabel = date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });

        const agg = aggregateDay(dateStr);
        if (!agg) continue;

        const ahScore     = hairProfile.scoreAH(agg.avgAH);
        const precipScore = scorePrecip(agg.avgPrecip, agg.pType, agg.avgPrecipAmt);
        const windScore   = scoreWind(agg.badStartHour);
        const rhPenalty    = agg.avgRH == null ? 1.0 : agg.avgRH > 90 ? 0.65 : agg.avgRH > 80 ? 0.80 : agg.avgRH > 70 ? 0.92 : 1.0;
        const score       = Math.round((ahScore * hairProfile.weights.ah + precipScore * hairProfile.weights.precip + windScore * hairProfile.weights.wind) * rhPenalty);
        const lf          = labelFor(score);

        // Flags
        const morningWarning = agg.peakMorningDp != null && agg.peakMorningDp >= 60
          ? `Dew point peaks ${Math.round(agg.peakMorningDp)}°F in morning — style before going out`
          : (agg.avgAH != null && agg.avgAH < 2
          ? hairProfile.dryWarning
          : null);

        // --- Composed wind flag ---
        function fmtHr(h) {
          const ampm = h >= 12 ? "pm" : "am";
          const h12  = h === 0 ? 12 : h > 12 ? h - 12 : h;
          return `${h12}${ampm}`;
        }
        let windFlag = null;
        if (agg.badStartHour != null) {
          if (agg.restyleWindow) {
            windFlag = `Windy from ${fmtHr(agg.badStartHour)}, calms ${fmtHr(agg.restyleWindow.start)}–${fmtHr(agg.restyleWindow.end)} — restyle opportunity`;
          } else if (agg.badStartHour >= 13) {
            windFlag = `Wind picks up after ${fmtHr(agg.badStartHour)}`;
          } else {
            windFlag = `Windy from ${fmtHr(agg.badStartHour)} — tough day for hair`;
          }
        }

        days.push({
          label: dayName, dateLabel,
          avgAH: agg.avgAH, avgRH: agg.avgRH, avgDp: agg.avgDp,
          avgPrecip: agg.avgPrecip, pType: agg.pType,
          morningGust: agg.morningGust,
          score, scoreLabel: lf.label, emoji: lf.emoji, color: lf.color,
          morningWarning, windFlag
        });
      }

      if (!days.length) { el.innerHTML = '<div style="opacity:0.5;">No forecast data available</div>'; return; }

      // Store today and tomorrow for Right Now / Briefing cards
      window.__todayHairScore = days[0];
      if (days.length > 1) window.__tomorrowHairScore = days[1];

      // Update collapsed preview — after 6 PM show tomorrow
      const afterCutoff = new Date().getHours() >= 18;
      const showDay = (afterCutoff && days.length > 1) ? days[1] : days[0];
      const showDayLabel = (afterCutoff && days.length > 1) ? "Tomorrow" : "Today";
      const emojiEl = document.getElementById("hairDayEmojiCollapsed");
      const labelEl = document.getElementById("hairDayLabelCollapsed");
      const scoreEl = document.getElementById("hairDayScoreCollapsed");
      if (emojiEl) emojiEl.textContent = showDay.emoji;
      if (labelEl) { labelEl.textContent = showDay.scoreLabel; labelEl.style.color = showDay.color; }
      if (scoreEl) scoreEl.textContent = `${showDayLabel}: ${showDay.score}/100`;

      // --- Headline ---
      function hairHeadline(day) {
        const ah = day.avgAH;
        let reason;
        if (ah == null)     reason = "";
        else if (ah < 2)    reason = " — very dry, watch for static";
        else if (ah < 5)    reason = " — dry air, great conditions";
        else if (ah < 7)    reason = " — comfortable moisture";
        else if (ah < 10)   reason = " — humidity building";
        else if (ah < 14)   reason = " — humid, frizz likely";
        else                reason = " — very humid, frizz certain";
        return `${day.scoreLabel}${reason}`;
      }

      // --- Day card ---
      function dayCard(day, isToday) {
        const ahVal   = day.avgAH   != null ? day.avgAH.toFixed(1) + " g/m³"  : "--";
        const rhVal   = day.avgRH   != null ? Math.round(day.avgRH) + "%"               : "--";
        const rainVal = day.avgPrecip != null
          ? Math.round(day.avgPrecip) + "%" + (day.pType ? " · " + day.pType : "")
          : "--";
        const gustVal = day.morningGust != null ? Math.round(day.morningGust) + " mph"  : "--";

        // AH bar: 0–20 g/m³ range, peak (green) at 4-5 g/m³
        const ahBarPct = day.avgAH != null ? Math.max(0, Math.min(100, Math.round(day.score))) : 50;
        const ahBarColor = ahBarPct >= 80 ? "rgba(100,210,120,0.7)" : ahBarPct >= 55 ? "rgba(200,180,60,0.7)" : "rgba(210,80,60,0.7)";

        const flags = [day.morningWarning, day.windFlag].filter(Boolean);
        const flagsHtml = flags.length
          ? flags.map(f => `<div style="font-size:0.68rem;margin-top:6px;padding:4px 8px;background:rgba(255,200,80,0.1);border-left:2px solid rgba(255,200,80,0.5);border-radius:0 4px 4px 0;opacity:0.85;">${f}</div>`).join("")
          : "";

        return `
          <div style="background:rgba(255,255,255,${isToday ? "0.06" : "0.03"});border:1px solid rgba(255,255,255,${isToday ? "0.14" : "0.07"});border-radius:10px;padding:12px 10px;display:flex;flex-direction:column;align-items:center;min-width:0;">
            <div style="font-size:0.78rem;font-weight:700;margin-bottom:2px;opacity:${isToday ? "1" : "0.7"};">${day.label}</div>
            <div style="font-size:0.68rem;opacity:0.45;margin-bottom:6px;">${day.dateLabel}</div>
            <div style="font-size:2rem;line-height:1;margin-bottom:4px;">${day.emoji}</div>
            <div style="font-size:0.8rem;font-weight:600;color:${day.color};text-align:center;margin-bottom:8px;">${day.scoreLabel}</div>
            <div style="font-size:1.4rem;font-weight:300;margin-bottom:6px;">${day.score}<span style="font-size:0.65rem;opacity:0.5;">/100</span></div>
            <div style="width:100%;display:flex;align-items:center;gap:4px;margin-bottom:12px;">
              <span style="font-size:0.6rem;opacity:0.3;flex-shrink:0;">0</span>
              <div style="flex:1;background:rgba(255,255,255,0.08);border-radius:3px;height:4px;overflow:hidden;">
                <div style="width:${day.score}%;height:100%;background:${day.color};border-radius:3px;"></div>
              </div>
              <span style="font-size:0.6rem;opacity:0.3;flex-shrink:0;">100</span>
            </div>
            <div style="width:100%;font-size:0.7rem;display:grid;grid-template-columns:auto 1fr;gap:3px 0;">
              <span style="opacity:0.5;">RH</span><span style="font-weight:600;text-align:right;">${rhVal}</span>
              <span style="opacity:0.5;">AH</span><span style="font-weight:600;text-align:right;">${ahVal}</span>
              <span style="opacity:0.5;">Rain</span><span style="font-weight:600;text-align:right;">${rainVal}</span>
              <span style="opacity:0.5;line-height:1.3;">Morning<br>Gust</span><span style="font-weight:600;text-align:right;">${gustVal}</span>
            </div>
            ${flagsHtml}
          </div>`;
      }

      const today = days[0];
      const headline = hairHeadline(today);
      const currentType = getHairType();
      const selectorHtml = `<div style="display:flex;gap:6px;margin-bottom:14px;justify-content:center;">` +
        Object.keys(HAIR_PROFILES).map(k => {
          const p = HAIR_PROFILES[k];
          const active = k === currentType;
          return `<button onclick="event.stopPropagation(); localStorage.setItem('hairType','${k}'); renderHairDay(window.__lastWeatherData);"
            style="padding:5px 12px;border-radius:999px;border:1px solid ${active ? 'rgba(255,255,255,0.4)' : 'rgba(255,255,255,0.12)'};
            background:${active ? 'rgba(255,255,255,0.15)' : 'rgba(255,255,255,0.04)'};
            color:${active ? 'rgba(255,255,255,0.95)' : 'rgba(255,255,255,0.5)'};
            font-size:0.72rem;font-weight:${active ? '700' : '500'};cursor:pointer;
            transition:all 0.2s;">${p.label}</button>`;
        }).join("") + `</div>`;
      el.innerHTML =
        selectorHtml +
        `<div style="font-size:0.95rem;font-weight:600;color:${today.color};margin-bottom:14px;padding:10px 14px;background:rgba(255,255,255,0.04);border-radius:0;border-left:4px solid ${today.color};">${headline}</div>` +
        `<div style="display:grid;grid-template-columns:repeat(${days.length},1fr);gap:8px;margin-bottom:12px;">` +
        days.map((d, i) => dayCard(d, i === 0)).join("") +
        `</div>`;
    }

    function renderDockDay(data) {
      const el = document.getElementById("dockDayContent");
      if (!el) return;

      const curve   = (data.tide_curve || {});
      const ctimes  = curve.times   || [];
      const cheights= curve.heights || [];
      const hourly  = data.hourly   || {};
      const htimes  = hourly.times  || [];
      const _rawHtemps = hourly.temperature || [];
      const _dockBias = (data.hyperlocal || {}).weighted_bias ?? 0;
      const htemps  = _rawHtemps.map(t => t != null ? t + _dockBias : null);
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
            temp < 50 ? 0.0 :
            temp < 65 ? (temp - 50) / 30 :
            Math.min(1, (temp - 65) / 30 + 0.5);

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
      const dTileBg    = light ? "rgba(255,255,255,0.55)" : "rgba(255,255,255,0.03)";
      const dTileBd    = light ? "rgba(0,0,0,0.08)"   : "rgba(255,255,255,0.08)";
      const dDayLbl    = light ? "rgba(0,0,0,0.75)"   : "rgba(255,255,255,0.45)";
      const dDateLbl   = light ? "rgba(0,0,0,0.50)"   : "rgba(255,255,255,0.3)";
      const dDryTxt    = light ? "rgba(0,0,0,0.45)"   : "rgba(255,255,255,0.3)";
      const dWinBg     = light ? "rgba(0,0,0,0.03)"   : "rgba(255,255,255,0.04)";
      const dTimeTxt   = light ? "rgba(0,0,0,0.85)"   : "rgba(255,255,255,0.85)";
      const dDurTxt    = light ? "rgba(0,0,0,0.50)"   : "rgba(255,255,255,0.35)";
      const dPeakTxt   = light ? "rgba(0,0,0,0.45)"   : "rgba(255,255,255,0.3)";
      const dBarBg     = light ? "rgba(0,0,0,0.10)"   : "rgba(255,255,255,0.1)";
      const dDetailTxt = light ? "rgba(0,0,0,0.60)"   : "rgba(255,255,255,0.5)";
      const dFooter    = light ? "rgba(0,0,0,0.45)"   : "rgba(255,255,255,0.22)";

      // Render
      function scoreLabel(s) {
        if (light) {
          if (s >= 0.75) return { label:"Great day",  color:"rgba(20,140,50,0.95)" };
          if (s >= 0.58) return { label:"Good day",   color:"rgba(70,140,20,0.95)" };
          if (s >= 0.38) return { label:"Marginal",   color:"rgba(180,120,0,0.95)" };
          if (s >= 0.20) return { label:"Poor",       color:"rgba(180,60,30,0.9)" };
          return            { label:"Stay inside", color:"rgba(150,40,40,0.9)" };
        }
        if (s >= 0.75) return { label:"Great day",  color:"rgba(80,220,120,0.95)" };
        if (s >= 0.58) return { label:"Good day",   color:"rgba(160,220,80,0.9)" };
        if (s >= 0.38) return { label:"Marginal",   color:"rgba(255,190,50,0.85)" };
        if (s >= 0.20) return { label:"Poor",       color:"rgba(200,100,60,0.85)" };
        return            { label:"Stay inside", color:"rgba(150,50,50,0.9)" };
      }

      function fmtTime(d) {
        return d.toLocaleTimeString("en-US", { hour:"numeric", minute:"2-digit" });
      }

      // Build headline from today's dock data
      let dockHeadline = "";
      if (dayCards.length > 0) {
        const td = dayCards[0];
        const sl = scoreLabel(td.bestScore);
        if (td.usableWindows && td.usableWindows.length > 0) {
          const w = td.usableWindows[0];
          const startFmt = fmtTime(w.startTime);
          const endFmt   = fmtTime(w.endTime);
          const hrs = Math.round((w.endTime - w.startTime) / 3600000);
          dockHeadline = `${sl.label} — dock accessible ${startFmt}–${endFmt} (${hrs}h)`;
        } else {
          dockHeadline = `No usable dock access today — tide too low`;
        }
      }

      let html = dockHeadline
        ? `<div style="font-size:0.95rem;font-weight:600;color:${dayCards.length > 0 ? scoreLabel(dayCards[0].bestScore).color : 'rgba(255,255,255,0.7)'};margin-bottom:14px;padding:10px 14px;background:rgba(255,255,255,0.04);border-radius:0;border-left:4px solid ${dayCards.length > 0 ? scoreLabel(dayCards[0].bestScore).color : 'rgba(255,255,255,0.2)'};">${dockHeadline}</div>`
        : "";
      html += `<div class="dock-day-grid" style="display:grid;grid-template-columns:repeat(${dayCards.length},minmax(130px,1fr));gap:12px;">`;

      for (const day of dayCards) {
        const sl = scoreLabel(day.bestScore);
        
        // Store today's and tomorrow's score for Right Now card
        if (day.dayLabel === "Today") {
          window.__todayDockScore = {score: day.bestScore, label: sl.label, color: sl.color};
        }
        if (day.dayLabel === "Tomorrow") {
          window.__tomorrowDockScore = {score: day.bestScore, label: sl.label, color: sl.color};
        }
        
        html += `<div style="background:${dTileBg};border:1px solid ${dTileBd};border-radius:10px;padding:14px 12px;">`;
        html += `<div style="font-size:0.78rem;font-weight:800;color:${dDayLbl};margin-bottom:2px;">${day.dayLabel}</div>`;
        html += `<div style="font-size:0.72rem;color:${dDateLbl};margin-bottom:8px;">${day.dateLabel}</div>`;

        if (!day.usableWindows.length) {
          html += ``;
          html += `<div style="font-size:0.82rem;font-weight:900;color:rgba(180,80,80,0.8);">Dock dry all day</div>`;
          html += `<div style="font-size:0.72rem;color:${dDryTxt};margin-top:6px;">Low tides fall within usable hours</div>`;
        } else {
          html += ``;
          html += `<div style="font-size:0.88rem;font-weight:900;color:${sl.color};margin-bottom:10px;">${sl.label} <span style="font-size:0.75rem;opacity:0.7;">(${Math.round(day.bestScore * 100)})</span></div>`;

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
            html += `<div>${w.temp != null ? Math.round(w.temp)+"°F" : "--"}</div>`;
            html += `<div>💧 ${w.precip != null ? w.precip+"%" : "--"} precip</div>`;
            html += `<div>`;
            html += `${w.wspd != null ? Math.round(w.wspd)+" kt" : "--"} ${w.dirName}`;
            html += ` <span style="color:${w.windRelLabel==='offshore'?'rgba(80,220,120,0.8)':w.windRelLabel==='onshore'?'rgba(220,80,80,0.8)':'rgba(255,200,80,0.8)'};">(${w.windRelLabel})</span></div>`;
            if (waterTempRaw != null) {
              html += `<div>${Math.round(waterTempRaw)}°F water</div>`;
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
      
      // Update collapsed preview — after 6 PM, show tomorrow's score if available
      if (dayCards.length > 0 && dayCards[0].dayLabel === "Today") {
        const afterCutoff = new Date().getHours() >= 18;
        const showDay = (afterCutoff && dayCards.length > 1) ? dayCards[1] : dayCards[0];
        const sl = scoreLabel(showDay.bestScore);
        const dockDayLabelEl = document.getElementById("dockDayLabelCollapsed");
        const dockScoreEl = document.getElementById("dockScoreCollapsed");
        
        if (dockDayLabelEl) dockDayLabelEl.textContent = showDay.dayLabel;
        
        if (dockScoreEl) dockScoreEl.textContent = sl.label + " (" + Math.round(showDay.bestScore * 100) + "/100)";
        
        // Apply gradient class based on score
        const dockCard = document.querySelector('[data-collapse-key="dock_day"]');
        if (dockCard) {
          dockCard.classList.remove('tile-dock-great', 'tile-dock-good', 'tile-dock-marginal', 'tile-dock-poor', 'tile-dock-stayinside');
          if (showDay.bestScore >= 0.80) dockCard.classList.add('tile-dock-great');
          else if (showDay.bestScore >= 0.65) dockCard.classList.add('tile-dock-good');
          else if (showDay.bestScore >= 0.45) dockCard.classList.add('tile-dock-marginal');
          else if (showDay.bestScore >= 0.25) dockCard.classList.add('tile-dock-poor');
          else dockCard.classList.add('tile-dock-stayinside');
        }
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
      

      // Build calendar-style 3-column layout (one column per day)
      const todayISO = new Date().toISOString().split("T")[0];
      const tmrw = new Date(Date.now() + 86400000).toISOString().split("T")[0];

      // Group tides by date, up to 3 days, 4 tides per day
      const byDate = {};
      let tideIdx = 0;
      tides.forEach(t => {
        const d = t.date || todayStr;
        if (!byDate[d]) byDate[d] = [];
        if (byDate[d].length < 4) { byDate[d].push({ ...t, globalIdx: tideIdx }); }
        tideIdx++;
      });
      const dateKeys = Object.keys(byDate).sort().slice(0, 3);

      // Helper: format time 24h -> 12h
      const fmt12 = time => {
        if (!time || !time.includes(":")) return time || "--";
        const [h, m] = time.split(":").map(Number);
        const period = h >= 12 ? "PM" : "AM";
        const h12 = h === 0 ? 12 : h > 12 ? h - 12 : h;
        return `${h12}:${m.toString().padStart(2,"0")} ${period}`;
      };

      // Day label
      const dayLabel = dk =>
        dk === todayISO ? "Today" :
        dk === tmrw ? "Tomorrow" :
        new Date(dk + "T12:00:00").toLocaleDateString("en-US", { weekday:"short", month:"short", day:"numeric" });

      // Calendar container
      const cal = document.createElement("div");
      cal.style.cssText = "display:grid;grid-template-columns:repeat(" + dateKeys.length + ",1fr);gap:10px;margin-bottom:12px;";

      dateKeys.forEach(dk => {
        const col = document.createElement("div");
        col.style.cssText = "display:flex;flex-direction:column;gap:0;";

        // Day header
        const hdr = document.createElement("div");
        hdr.style.cssText = "font-size:0.72rem;font-weight:900;letter-spacing:0.8px;text-transform:uppercase;" +
          "color:var(--muted);padding:0 2px 8px;border-bottom:1px solid var(--border);margin-bottom:8px;";
        hdr.textContent = dayLabel(dk);
        col.appendChild(hdr);

        // Tide entries
        byDate[dk].forEach(t => {
          const isNext = (t.globalIdx === nextIdx);
          const isHigh = t.type === "H";

          const entry = document.createElement("div");
          entry.style.cssText =
            "display:flex;flex-direction:column;gap:1px;padding:9px 10px;border-radius:12px;margin-bottom:7px;" +
            (isNext
              ? "background:rgba(100,200,255,0.12);border:1px solid rgba(100,200,255,0.4);"
              : "background:var(--card-bg,rgba(255,255,255,0.04));border:1px solid var(--border);");

          // Type row
          const typeEl = document.createElement("div");
          typeEl.style.cssText = "display:flex;align-items:center;gap:5px;font-size:0.72rem;font-weight:900;" +
            "letter-spacing:0.5px;text-transform:uppercase;margin-bottom:3px;" +
            (isHigh ? (document.body.classList.contains("theme-light") ? "color:#0055aa;" : "color:rgba(100,200,255,0.9);") : "color:var(--muted);");
          typeEl.innerHTML = (isNext ? "&#9654; " : "") + (isHigh ? "High" : "Low");
          entry.appendChild(typeEl);

          // Time
          const timeEl = document.createElement("div");
          timeEl.style.cssText = "font-size:0.95rem;font-weight:800;color:var(--text);line-height:1.1;";
          timeEl.textContent = fmt12(t.time);
          entry.appendChild(timeEl);

          // Height
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
        
        if (nextTideEl) nextTideEl.textContent = `Next: ${type} Tide`;
        const isTomorrow = (nextTide.date || todayStr) !== todayStr;
        if (nextTideTimeEl) nextTideTimeEl.textContent = time12hr + (isTomorrow ? " (tomorrow)" : "");
        const nextTideHeightEl = document.getElementById("nextTideHeightCollapsed");
        if (nextTideHeightEl) nextTideHeightEl.textContent = height;
        
        // Animate tide water level
        const tideWaterEl = document.getElementById("tideWater");
        if (tideWaterEl && nextIdx >= 0) {
          // Find previous tide to determine direction
          const prevIdx = nextIdx - 1;
          if (prevIdx >= 0 && tides[prevIdx]) {
            const prevTide = tides[prevIdx];
            const prevHeight = parseFloat(prevTide.height) || 0;
            const nextHeight = parseFloat(nextTide.height) || 0;
            
            // Calculate current time as percentage between prev and next tide
            const now = new Date();
            const prevTime = new Date(`${prevTide.date || todayStr}T${prevTide.time || "00:00"}:00`);
            const nextTime = new Date(`${nextTide.date || todayStr}T${nextTide.time || "00:00"}:00`);
            const totalDuration = nextTime - prevTime;
            const elapsed = now - prevTime;
            const progress = Math.max(0, Math.min(1, elapsed / totalDuration));
            
            // Interpolate current height
            const currentHeight = prevHeight + (nextHeight - prevHeight) * progress;
            
            // Convert height to percentage (assume 0-12 ft range for Salem Harbor)
            const minHeight = -2;
            const maxHeight = 12;
            const currentPercent = ((currentHeight - minHeight) / (maxHeight - minHeight)) * 100;
            const prevPercent = ((prevHeight - minHeight) / (maxHeight - minHeight)) * 100;
            
            // Set initial height based on direction
            const isRising = nextHeight > prevHeight;
            tideWaterEl._prevPercent = prevPercent;
            tideWaterEl._targetPercent = currentPercent;
            tideWaterEl.style.height = `${prevPercent}%`;
            
            // Animate to current height after a brief delay
            setTimeout(() => {
              tideWaterEl.style.height = `${Math.max(12, Math.min(95, currentPercent))}%`;

              // Add current tide indicator text inside water
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

    let _selectedForecastDate = null;

    function renderForecast(forecastText, hourlyTimes, hourlyTemps, tempBias, derived) {
      const el = document.getElementById("forecastList");
      if (!el || !Array.isArray(forecastText)) return;
      el.innerHTML = "";

      // Group forecast_text into 10 days (combine day/night periods into single row)
      const days = [];
      const seenDates = new Set();

      // Use corrected daily high/low from collector (single source of truth)
      const _now = new Date();
      const _pad = n => String(n).padStart(2, '0');
      const _dateStr = d => `${d.getFullYear()}-${_pad(d.getMonth()+1)}-${_pad(d.getDate())}`;
      const _todayStr = _dateStr(_now);
      const _tom = new Date(_now); _tom.setDate(_tom.getDate() + 1);
      const _tomorrowStr = _dateStr(_tom);
      const _correctedDays = {};
      if (derived.today_high != null) _correctedDays[_todayStr] = { high: derived.today_high, low: derived.today_low };
      if (derived.tomorrow_high != null) _correctedDays[_tomorrowStr] = { high: derived.tomorrow_high, low: derived.tomorrow_low };
      
      for (const period of forecastText) {
        const dateStr = period.date;
        
        if (seenDates.has(dateStr)) continue;
        seenDates.add(dateStr);
        
        // Find day and night periods for this date
        const dayPeriod = forecastText.find(p => p.date === dateStr && p.is_daytime);
        const nightPeriod = forecastText.find(p => p.date === dateStr && !p.is_daytime);
        
        // For simple dailies, just use the single period
        const isSimple = period.is_simple_daily;
        
        let high = isSimple ? period.temperature : (dayPeriod?.temperature || period.temperature);
        let low = isSimple ? parseInt((period.text || "").match(/low (\d+)/)?.[1] || period.temperature) : (nightPeriod?.temperature || period.temperature);
        // Use corrected hourly high/low for today and tomorrow
        if (_correctedDays[dateStr]) {
          high = Math.round(_correctedDays[dateStr].high);
          low  = Math.round(_correctedDays[dateStr].low);
        }
        
        // Extract precip probability
        const combinedText = isSimple ? period.text : ((dayPeriod?.text || "") + " " + (nightPeriod?.text || ""));
        const precipMatch = (combinedText || "").match(/\((\d+)%\)/);
        const pop = precipMatch ? parseInt(precipMatch[1]) : 0;
        
        const text = (combinedText || "").toLowerCase();
        let emoji = "☀️";
        if (text.includes("thunder")) emoji = "⛈️";
        else if (text.includes("snow")) emoji = "🌨️";
        else if (text.includes("rain")) emoji = "🌧️";
        else if (text.includes("fog")) emoji = "🌥️";
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
            <span style="font-weight:600;min-width:32px;">${d.day}</span>
            <span style="font-size:0.82rem;color:rgba(255,255,255,0.35);">${d.dateNum}</span>
            <span style="font-size:16px;">${d.emoji}</span>
            ${d.pop > 10 ? `<span style="font-size:0.75rem;color:rgba(140,180,255,0.7);font-weight:600;">${d.pop}%</span>` : ""}
          </div>
          <div class="value">${d.high}° <span class="temp-lo" style="opacity:0.4;font-weight:400;">/ ${d.low}°</span></div>`;

        el.appendChild(row);
      }

      updateForecastSelection();

      // Hint
      
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

    // Per-card window state
    let _gustWindowHours = 12;
    let _susWindowHours  = 12;

    function renderWindRisk(data) {
      const hyp   = data.hyperlocal || {};
      const hourly = data.hourly || {};
      const gustPeak = computePeakWorry(hourly, _gustWindowHours, true);
      const susPeak  = computePeakWorry(hourly, _susWindowHours,  false);

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

      // Combined Wind Impact current score
      const cur = data.current || {};
      const curWindSpeed = hyp.corrected_wind_speed ?? cur.wind_speed;
      const curGustSpeed = hyp.corrected_wind_gusts ?? cur.wind_gusts;
      if (cur.wind_direction != null && (curWindSpeed != null || curGustSpeed != null)) {
        const combined = Math.round(combinedWindImpact(curWindSpeed, curGustSpeed, cur.wind_direction));
        const combinedLevel = worryLevel(combined);
        const combinedEl = document.getElementById("windImpactCombinedScore");
        if (combinedEl) combinedEl.innerHTML = `<span class="badge ${combinedLevel.cls}">${combined}</span> (${combinedLevel.label})`;

        const peakCombined = Math.round(gustPeak.score ?? 0);
        const peakLevel = worryLevel(peakCombined);
        const peakEl = document.getElementById("windImpactPeakScore");
        const labelEl = document.getElementById("windImpactScoreLabel");
        if (peakEl) peakEl.innerHTML = `<span class="badge ${peakLevel.cls}">${peakCombined}</span> (${peakLevel.label})`;
        if (labelEl) labelEl.textContent = `Peak impact (next ${_gustWindowHours}h)`;
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

      if (sb.likelihood === undefined || sb.likelihood === null) {
        el.innerHTML = `<div style="text-align:center;color:rgba(255,255,255,0.5);padding:20px;">No sea breeze data available</div>`;
        return;
      }

      const scores = sb.scores || {};
      const hyp = data.hyperlocal || {};
      const buoy = data.buoy_44013 || {};
      const cur = data.current || {};

      let statusColor, statusText;
      if (sb.active) {
        statusColor = "rgba(100,200,120,0.95)";
        statusText = "Active";
      } else if (sb.likelihood >= 40) {
        statusColor = "rgba(220,200,60,0.85)";
        statusText = "Possible";
      } else {
        statusColor = "rgba(150,150,150,0.6)";
        statusText = "Unlikely";
      }

      // Build sea breeze headline
      let sbHeadline;
      if (sb.active) {
        sbHeadline = `Sea breeze active — offshore flow replaced by onshore`;
      } else if (sb.likelihood >= 60) {
        sbHeadline = `Sea breeze likely this afternoon (${sb.likelihood}%)`;
      } else if (sb.likelihood >= 35) {
        sbHeadline = `Sea breeze possible (${sb.likelihood}%) — conditions marginal`;
      } else {
        const windDir = data.current?.wind_direction;
        const compass = windDir != null ? toCompass(windDir) : null;
        sbHeadline = compass
          ? `No sea breeze — ${compass} wind dominates (${sb.likelihood}%)`
          : `No sea breeze — conditions unfavorable (${sb.likelihood}%)`;
      }
      const sbHeadlineColor = sb.active ? "rgba(100,200,120,0.95)" : sb.likelihood >= 40 ? "rgba(220,200,60,0.85)" : "rgba(150,150,150,0.7)";

      const html = `
        <div style="font-size:0.95rem;font-weight:600;color:${sbHeadlineColor};margin-bottom:16px;padding:10px 14px;background:rgba(255,255,255,0.04);border-radius:0;border-left:4px solid ${sbHeadlineColor};">${sbHeadline}</div>
        <div style="text-align:center;margin-bottom:20px;">
          <div style="font-size:2.5rem;color:${statusColor};margin-bottom:8px;">${sb.likelihood}%</div>
          <div style="font-size:1.1rem;opacity:0.9;">${statusText}</div>
          <div style="font-size:0.9rem;opacity:0.7;margin-top:4px;">${sb.reason}</div>
        </div>

        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:20px;">
          <div>
            <div style="opacity:0.7;font-size:0.85rem;margin-bottom:4px;">Temp Differential</div>
            <div style="font-size:1.3rem;">${scores.temp || 0}%</div>
            <div style="opacity:0.6;font-size:0.8rem;margin-top:2px;">Land: ${(hyp.corrected_temp ?? cur.temperature)?.toFixed(1) || "--"}°F | Water: ${buoy.water_temp_f?.toFixed(1) || "--"}°F</div>
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
      
      // Update collapsed preview with new structure
      const seaBreezeCollapsedEl = document.getElementById("seaBreezeCollapsed");
      const seaBreezeLabelEl = document.getElementById("seaBreezeLabel");
      const seaBreezeProbCollapsedEl = document.getElementById("seaBreezeProbCollapsed");
      if (seaBreezeCollapsedEl) {
        seaBreezeCollapsedEl.innerHTML = `${sb.likelihood}<span style="font-size:1.8rem;opacity:0.6;">%</span>`;
      }
      if (seaBreezeLabelEl) seaBreezeLabelEl.textContent = statusText;
      if (seaBreezeProbCollapsedEl) {
        let timeText;
        if (sb.active) {
          timeText = "Active now";
        } else if (sb.likelihood >= 40) {
          timeText = "This afternoon";
        } else {
          const wd = data.current?.wind_direction;
          timeText = wd != null ? `Wind from ${toCompass(wd)}` : "Unfavorable";
        }
        seaBreezeProbCollapsedEl.textContent = timeText;
      }
      
      // Apply gradient class based on likelihood
      const seaBreezeCard = document.querySelector('[data-collapse-key="sea_breeze_detail"]');
      if (seaBreezeCard) {
        seaBreezeCard.classList.remove('tile-seabreeze-unlikely', 'tile-seabreeze-possible', 'tile-seabreeze-likely');
        if (sb.likelihood < 30) seaBreezeCard.classList.add('tile-seabreeze-unlikely');
        else if (sb.likelihood < 60) seaBreezeCard.classList.add('tile-seabreeze-possible');
        else seaBreezeCard.classList.add('tile-seabreeze-likely');
      }
    }

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
      let flType = "Feels Like";
      if (T != null) {
        if (T <= 50 && wind > 3) flType = "Wind Chill";
        else if (T >= 80) flType = "Heat Index";
      }

      // Update tile front
      const valEl = document.getElementById("feelsLikeCardValue");
      const lblEl = document.getElementById("feelsLikeCardLabel");
      const light = isLight();
      if (valEl) valEl.textContent = T != null ? Math.round(feelsLike) + "\u00b0" : "--\u00b0";
      if (lblEl) {
        lblEl.textContent = flType;
        lblEl.style.color = flType === "Wind Chill" ? "rgba(100,180,255,0.9)" :
                            flType === "Heat Index"  ? "rgba(255,140,60,0.9)" :
                            light ? "rgba(0,0,0,0.6)" : "rgba(255,255,255,0.6)";
      }

      // Build 48-hour dataset from HRRR hourly
      const times  = hourly.times       || [];
      const htemps = hourly.corrected_temperature || hourly.temperature || [];
      const hwind  = hourly.wind_speed  || [];
      const hhumid = hourly.corrected_humidity || hourly.humidity    || [];

      function calcFL(ht, hw, hrh) {
        if (ht == null) return null;
        if (ht <= 50 && hw > 3)
          return 35.74 + (0.6215*ht) - (35.75*Math.pow(hw,0.16)) + (0.4275*ht*Math.pow(hw,0.16));
        if (ht >= 80)
          return -42.379 + (2.04901523*ht) + (10.14333127*hrh) - (0.22475541*ht*hrh) -
                 (0.00683783*ht*ht) - (0.05481717*hrh*hrh) + (0.00122874*ht*ht*hrh) +
                 (0.00085282*ht*hrh*hrh) - (0.00000199*ht*ht*hrh*hrh);
        return ht;
      }

      function flTypeFor(ht, hw) {
        if (ht == null) return "Feels Like";
        if (ht <= 50 && hw > 3) return "Wind Chill";
        if (ht >= 80) return "Heat Index";
        return "Feels Like";
      }

      const chartTimes = [], chartFL = [], chartAir = [], chartTypes = [];
      for (let i = 0; i < times.length; i++) {
        const ht  = htemps[i] ?? null;
        const hw  = hwind[i]  ?? 0;
        const hrh = hhumid[i] ?? 50;
        const fl  = calcFL(ht, hw, hrh);
        chartTimes.push(times[i]);
        chartFL.push(fl != null ? Math.round(fl) : null);
        chartAir.push(ht != null ? Math.round(ht) : null);
        chartTypes.push(flTypeFor(ht, hw));
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
        const typ = chartTypes[idx] || "Feels Like";
        timeEl.textContent = timeStr + " \u00b7";
        lineEl.textContent = `${typ}: ${fl} \u00b7 Air: ${air}`;
      }

      const dominantType = chartTypes.find(t => t !== "Feels Like") || "Feels Like";
      const lineColor = dominantType === "Wind Chill" ? "rgba(100,180,255,0.9)"
                      : dominantType === "Heat Index"  ? "rgba(255,140,60,0.9)"
                      : "rgba(180,180,255,0.8)";
      const fillColor = dominantType === "Wind Chill" ? "rgba(100,180,255,0.1)"
                      : dominantType === "Heat Index"  ? "rgba(255,140,60,0.1)"
                      : "rgba(180,180,255,0.05)";

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
              borderColor: "rgba(255,255,255,0.25)",
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

    // ======================================================
    // Birds (eBird recent sightings, 5km radius, 2 days back)
    // Collapsed: top notable species, else species count
    // Expanded: grouped by location, most recent first, all collapsed
    // ======================================================
    function renderBirds(birds) {
      const primaryEl   = document.getElementById("birdsPrimaryCollapsed");
      const secondaryEl = document.getElementById("birdsSecondaryCollapsed");
      const contentEl   = document.getElementById("birdsContent");
      if (!primaryEl || !contentEl) return;

      // Empty / missing data
      if (!birds || !Array.isArray(birds.species) || birds.species.length === 0) {
        primaryEl.textContent = "No recent sightings";
        secondaryEl.textContent = "";
        const days = birds?.back_days ?? 2;
        const km   = birds?.radius_km ?? 5;
        contentEl.innerHTML = `<div style="padding:20px;text-align:center;color:var(--text-secondary);font-size:0.9rem;">No eBird sightings in the last ${days} day${days === 1 ? "" : "s"} within ${km} km.</div>`;
        return;
      }

      const species       = birds.species;
      const speciesCount  = birds.species_count ?? species.length;
      const notables      = species.filter(s => s.notable);
      const totalBirds    = species.reduce((sum, s) => sum + (s.count || 0), 0);

      // --- Collapsed tile ---
      if (notables.length > 0) {
        const topNotable = [...notables].sort((a, b) =>
          (b.last_seen || "").localeCompare(a.last_seen || "")
        )[0];
        primaryEl.textContent = topNotable.name;
        const extra = notables.length - 1;
        secondaryEl.textContent = extra > 0
          ? `+ ${extra} other notable${extra === 1 ? "" : "s"}`
          : "Notable sighting";
      } else {
        primaryEl.textContent = `${speciesCount} species`;
        secondaryEl.textContent = `${totalBirds} bird${totalBirds === 1 ? "" : "s"} · ${birds.radius_km ?? 5} km`;
      }

      // --- Expanded view: theme-aware colors ---
      const light     = isLight();
      const textFaint = light ? "rgba(0,0,0,0.40)"      : "rgba(255,255,255,0.4)";
      const textSub   = light ? "rgba(0,0,0,0.55)"      : "rgba(255,255,255,0.55)";
      const textHead  = light ? "rgba(0,0,0,0.75)"      : "rgba(255,255,255,0.85)";
      const border    = light ? "rgba(0,0,0,0.08)"      : "rgba(255,255,255,0.08)";
      const rowBg     = light ? "rgba(0,0,0,0.02)"      : "rgba(255,255,255,0.03)";
      const notableBg = light ? "rgba(255,140,60,0.15)" : "rgba(255,180,90,0.18)";
      const notableFg = light ? "rgba(200,90,10,0.95)"  : "rgba(255,200,120,0.95)";
      const linkCol   = light ? "rgba(20,80,200,0.9)"   : "rgba(120,190,255,0.9)";

      // Group species by location, then aggregate duplicate species within each location
      const byLocation = new Map();
      species.forEach(s => {
        const key = s.location || "Unknown location";
        if (!byLocation.has(key)) {
          byLocation.set(key, {
            name: key,
            loc_id: s.loc_id,
            loc_private: s.loc_private,
            lat: s.lat,
            lng: s.lng,
            distance_km: s.distance_km,
            last_seen: s.last_seen,
            species: []
          });
        }
        const loc = byLocation.get(key);
        loc.species.push(s);
        if ((s.last_seen || "") > (loc.last_seen || "")) loc.last_seen = s.last_seen;
      });

      const locations = [...byLocation.values()].map(loc => {
        const speciesMap = new Map();

        loc.species.forEach(s => {
          const speciesKey = s.code || s.name || "unknown-species";
          if (!speciesMap.has(speciesKey)) {
            speciesMap.set(speciesKey, { ...s });
            return;
          }

          const existing = speciesMap.get(speciesKey);

          // Sum counts when available
          if (existing.count != null || s.count != null) {
            existing.count = (existing.count || 0) + (s.count || 0);
          }

          // Preserve notable if any sighting is notable
          existing.notable = !!(existing.notable || s.notable);

          // Keep most recent sighting time
          if ((s.last_seen || "") > (existing.last_seen || "")) {
            existing.last_seen = s.last_seen;
          }

          speciesMap.set(speciesKey, existing);
        });

        loc.species = [...speciesMap.values()];

        // Sort species within each location: notable first, then count desc, then name
        loc.species.sort((a, b) => {
          if (a.notable !== b.notable) return a.notable ? -1 : 1;
          const countDiff = (b.count || 0) - (a.count || 0);
          if (countDiff !== 0) return countDiff;
          return (a.name || "").localeCompare(b.name || "");
        });

        loc.hasNotable = loc.species.some(s => s.notable);
        return loc;
      });

      // Sort locations: any hotspot with notable birds first, otherwise by distance from home
      locations.sort((a, b) => {
        if (a.hasNotable !== b.hasNotable) return a.hasNotable ? -1 : 1;
        return (a.distance_km ?? 99) - (b.distance_km ?? 99);
      });

      // Format "2026-04-23 18:49" -> "Apr 23, 6:49 PM"
      const fmtTime = (ts) => {
        if (!ts) return "";
        const [datePart, timePart] = ts.split(" ");
        if (!datePart || !timePart) return ts;
        const [y, mo, d] = datePart.split("-").map(Number);
        const [h, mi]    = timePart.split(":").map(Number);
        const dt = new Date(y, mo - 1, d, h, mi);
        return dt.toLocaleDateString("en-US", { month: "short", day: "numeric" }) +
               ", " +
               dt.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
      };

      const fetchedAt = birds.fetched_at
        ? new Date(birds.fetched_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })
        : null;

      // Header summary
      const notableBadge = notables.length > 0
        ? `<span style="background:${notableBg};color:${notableFg};padding:2px 8px;border-radius:999px;font-size:0.72rem;font-weight:700;margin-left:8px;">${notables.length} notable</span>`
        : "";

      let html = `
        <div style="padding:12px 0 14px;border-bottom:1px solid ${border};margin-bottom:12px;">
          <div style="font-size:1.1rem;font-weight:700;color:${textHead};">
            ${speciesCount} species · ${totalBirds} bird${totalBirds === 1 ? "" : "s"}${notableBadge}
          </div>
          <div style="font-size:0.78rem;color:${textFaint};margin-top:4px;">
            eBird · ${Math.round((birds.radius_km ?? 5) * 0.621371)} miles radius · last ${birds.back_days ?? 2} day${(birds.back_days ?? 2) === 1 ? "" : "s"}${fetchedAt ? ` · updated ${fetchedAt}` : ""}
          </div>
        </div>
      `;

      // Location groups
      locations.forEach((loc, idx) => {
        const groupId = `birdLoc_${idx}`;
        const locNotables = loc.species.filter(s => s.notable).length;
        const locSpeciesCount = loc.species.length;
        const locBirdCount = loc.species.reduce((sum, s) => sum + (s.count || 0), 0);
        const distStr = loc.distance_km != null
  ? `${(loc.distance_km * 0.621371).toFixed(1)} mi`
  : "";

        html += `
          <div style="border:1px solid ${border};border-radius:10px;margin-bottom:8px;overflow:hidden;background:${rowBg};">
            <div onclick="document.getElementById('${groupId}').style.display = document.getElementById('${groupId}').style.display === 'none' ? 'block' : 'none'; this.querySelector('.bird-chev').textContent = document.getElementById('${groupId}').style.display === 'none' ? '▾' : '▴';"
                 style="padding:10px 12px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;gap:8px;">
              <div style="min-width:0;flex:1;">
                <div style="font-weight:700;font-size:0.9rem;color:${textHead};overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">
                  ${loc.loc_id && !loc.loc_private ? `<a href="https://ebird.org/hotspots?hs=${loc.loc_id}" target="_blank" rel="noopener" onclick="event.stopPropagation(); event.preventDefault(); window.__externalLinkOpen = true; window.open('https://ebird.org/hotspots?hs=${loc.loc_id}', '_blank');" style="color:${textHead};text-decoration:none;border-bottom:1px dotted ${textFaint};">${escapeHtml(loc.name)}</a>` : loc.loc_private && loc.lat && loc.lng ? `<a href="https://www.openstreetmap.org/?mlat=${loc.lat}&mlon=${loc.lng}#map=15/${loc.lat}/${loc.lng}" target="_blank" rel="noopener" onclick="event.stopPropagation(); event.preventDefault(); window.__externalLinkOpen = true; window.location.href = 'https://www.openstreetmap.org/?mlat=${loc.lat}&mlon=${loc.lng}#map=15/${loc.lat}/${loc.lng}';" style="color:${textHead};text-decoration:none;border-bottom:1px dotted ${textFaint};">${escapeHtml(loc.name)}</a>` : escapeHtml(loc.name)}${locNotables > 0 ? ` <span style="background:${notableBg};color:${notableFg};padding:1px 6px;border-radius:999px;font-size:0.7rem;font-weight:700;margin-left:4px;">${locNotables}★</span>` : ""}
                </div>
                <div style="font-size:0.75rem;color:${textFaint};margin-top:2px;">
                  ${distStr} · ${locSpeciesCount} species · ${locBirdCount} bird${locBirdCount === 1 ? "" : "s"} · ${fmtTime(loc.last_seen)}
                </div>
              </div>
              <span class="bird-chev" style="color:${textFaint};font-size:0.9rem;flex-shrink:0;">▾</span>
            </div>
            <div id="${groupId}" style="display:none;padding:0 12px 10px;border-top:1px solid ${border};">
              ${loc.species.map(s => {
                const ebirdUrl = `https://ebird.org/species/${s.code}`;
                const isNotable = s.notable;
                const nameStyle = isNotable
                  ? `background:${notableBg};color:${notableFg};padding:1px 6px;border-radius:4px;font-weight:700;`
                  : "";
                return `
                  <div style="display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid ${border};font-size:0.85rem;">
                    <a href="${ebirdUrl}" target="_blank" rel="noopener" onclick="event.stopPropagation(); event.preventDefault(); window.__externalLinkOpen = true; window.open('${ebirdUrl}', '_blank');" style="color:${linkCol};text-decoration:none;flex:1;min-width:0;">
                      <span style="${nameStyle}">${escapeHtml(s.name)}</span>
                    </a>
                    <span style="color:${textSub};margin-left:10px;font-variant-numeric:tabular-nums;flex-shrink:0;">
                      ${s.count > 1 ? `×${s.count}` : "·"}
                    </span>
                  </div>
                `;
              }).join("")}
            </div>
          </div>
        `;
      });

      contentEl.innerHTML = html;
    }

    // Small HTML escaper used by renderBirds (species names are eBird-controlled
    // so very safe, but defense in depth is cheap)
    function escapeHtml(s) {
      if (s == null) return "";
      return String(s)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
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
          if (target === "wind_impact") { _gustWindowHours = hours; _susWindowHours = hours; }
          else if (target === "gust") _gustWindowHours = hours;
          else                        _susWindowHours  = hours;
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
      if (altDeg >= 20)       { status = "Above horizon"; }
      else if (altDeg >= 5)   { status = "Low in sky"; }
      else if (altDeg >= 0)   { status = "Just above horizon"; }
      else if (altDeg >= -6)  { status = "Civil twilight"; }
      else if (altDeg >= -12) { status = "Nautical twilight"; }
      else if (altDeg >= -18) { status = "Astronomical twilight"; }
      else                    { status = "Below horizon (night)"; }

      document.getElementById("sunEmoji").textContent   = emoji;
      document.getElementById("sunStatus").textContent  = status;
      
      // Update collapsed preview - show altitude, arc position, and next event
      const sunStatusCollapsedEl = document.getElementById("sunStatusCollapsed");
      const sunAltitudeCollapsedEl = document.getElementById("sunAltitudeCollapsed");
      
      if (sunStatusCollapsedEl) {
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
        
        sunStatusCollapsedEl.textContent = `${nextEvent} ${nextTime}`;
      }
      
      if (sunAltitudeCollapsedEl) {
        sunAltitudeCollapsedEl.textContent = `${altDeg}° altitude`;
      }
      
      // Position sun dot on arc: x = time progress (sunrise-left to sunset-right), y = altitude
      const sunPositionDot = document.getElementById("sunPositionDot");
      if (sunPositionDot) {
        // Get today's sunrise and sunset times
        const times = SunCalc.getTimes(new Date(), 42.5014, -70.8750);
        const now = Date.now();
        const riseMs = times.sunrise.getTime();
        const setMs = times.sunset.getTime();
        
        // Progress through the day: 0 = sunrise, 1 = sunset
        let progress = (now - riseMs) / (setMs - riseMs);
        progress = Math.max(0, Math.min(1, progress));
        
        // x: left (10) = sunrise, right (110) = sunset
        const x = 10 + (100 * progress);
        // y: use actual altitude for the vertical position
        const normalizedAlt = Math.max(0, altDeg) / 90;
        const y = 55 - (50 * Math.sin(normalizedAlt * Math.PI / 2));
        
        // Hide dot if before sunrise or after sunset
        const visible = now >= riseMs && now <= setMs;
        sunPositionDot.style.display = visible ? '' : 'none';
        
        sunPositionDot.setAttribute('cx', x);
        sunPositionDot.setAttribute('cy', y);
        
        // Update glow circle too
        const glowCircle = sunPositionDot.nextElementSibling;
        if (glowCircle && glowCircle.tagName === 'circle') {
          glowCircle.setAttribute('cx', x);
          glowCircle.setAttribute('cy', y);
          if (glowCircle.style) glowCircle.style.display = visible ? '' : 'none';
        }
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
      function radarBaseTileUrl() {
        const isLight = document.body.classList.contains('theme-light');
        return isLight
          ? "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
          : "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
      }
      function radarApplyBaseTile() {
        if (!radarMap) return;
        if (radarTileLayers._base) radarMap.removeLayer(radarTileLayers._base);
        radarTileLayers._base = L.tileLayer(radarBaseTileUrl(), { maxZoom: 19, attribution: '&copy; <a href="https://carto.com/">CartoDB</a>' });
        radarTileLayers._base.addTo(radarMap);
        radarTileLayers._base.bringToBack();
      }
      radarTileLayers.street = { addTo: () => {} };   // compat stub
      radarTileLayers.satellite = radarTileLayers.street;
      radarApplyBaseTile();
      // Re-apply base tile when theme changes
      const _radarThemeObs = new MutationObserver(() => radarApplyBaseTile());
      _radarThemeObs.observe(document.body, { attributes: true, attributeFilter: ['class'] });


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
      { name: "New Moon", min: 0,     max: 0.025 },
      { name: "Waxing Crescent", min: 0.025, max: 0.235 },
      { name: "First Quarter", min: 0.235, max: 0.265 },
      { name: "Waxing Gibbous", min: 0.265, max: 0.485 },
      { name: "Full Moon", min: 0.485, max: 0.515 },
      { name: "Waning Gibbous", min: 0.515, max: 0.735 },
      { name: "Last Quarter", min: 0.735, max: 0.765 },
      { name: "Waning Crescent", min: 0.765, max: 0.975 },
      { name: "New Moon", min: 0.975, max: 1.0   },
    ];

    /**
     * Draw a canvas-rendered moon phase.
     * @param {string} canvasId - DOM id of the <canvas> element
     * @param {number} phase    - SunCalc illum.phase (0–1, 0=new, 0.5=full)
     * @param {boolean} darkBg  - true = dark background (expanded card), false = transparent (tile)
     */
    function drawMoonCanvas(canvasId, phase, darkBg) {
      const canvas = document.getElementById(canvasId);
      if (!canvas) return;
      const ctx = canvas.getContext("2d");
      const W = canvas.width, H = canvas.height;
      const cx = W / 2, cy = H / 2;
      const R = Math.floor(Math.min(W, H) * 0.31);
      const alpha = phase * 2 * Math.PI; // 0=new, pi=full
      const waxing = alpha < Math.PI;
      const k = Math.cos(alpha); // terminator ellipse param (northern hemisphere)

      ctx.clearRect(0, 0, W, H);

      // Subtle glow
      const glow = ctx.createRadialGradient(cx, cy, R * 0.95, cx, cy, R * 1.6);
      glow.addColorStop(0, "rgba(255,190,110,0.12)");
      glow.addColorStop(1, "rgba(255,190,110,0)");
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(cx, cy, R * 1.6, 0, 2 * Math.PI);
      ctx.fill();

      // Dark disk (unlit side)
      const darkShade = ctx.createRadialGradient(
        cx - R * 0.25, cy - R * 0.25, R * 0.05, cx, cy, R
      );
      darkShade.addColorStop(0, darkBg ? "#17181c" : "rgba(23,24,28,0.85)");
      darkShade.addColorStop(0.6, darkBg ? "#0b0c10" : "rgba(11,12,16,0.85)");
      darkShade.addColorStop(1, darkBg ? "#05060a" : "rgba(5,6,10,0.85)");
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, 2 * Math.PI);
      ctx.fillStyle = darkShade;
      ctx.fill();

      // Clip to moon disk and draw lit side with scanline
      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, 2 * Math.PI);
      ctx.clip();

      const lit = ctx.createRadialGradient(
        cx - R * 0.35, cy - R * 0.35, R * 0.06, cx, cy, R
      );
      lit.addColorStop(0, "#fff2c7");
      lit.addColorStop(0.45, "#ffd27a");
      lit.addColorStop(0.78, "#ffb347");
      lit.addColorStop(1, "#c97e25");
      ctx.fillStyle = lit;

      for (let y = -R; y <= R; y++) {
        const xr = Math.sqrt(R * R - y * y);
        const xt = k * xr;
        let xLeft, xRight;
        if (waxing) { xLeft = xt; xRight = xr; }
        else        { xLeft = -xr; xRight = -xt; }
        ctx.fillRect(cx + xLeft, cy + y, xRight - xLeft, 1);
      }
      ctx.restore();

      // Rim
      ctx.beginPath();
      ctx.arc(cx, cy, R, 0, 2 * Math.PI);
      ctx.strokeStyle = "rgba(255,255,255,0.09)";
      ctx.lineWidth = 1;
      ctx.stroke();
    }

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
      // Draw canvas moon renderings
      drawMoonCanvas("moonCanvasExpanded", illum.phase, false);
      document.getElementById("moonPhaseName").textContent    = phase.name;
      document.getElementById("moonIllumination").textContent = Math.round(illum.fraction * 100) + "% illuminated";
      
      // Update collapsed preview
      drawMoonCanvas("moonCanvasCollapsed", illum.phase, false);
      const moonPhaseCollapsedEl = document.getElementById("moonPhaseCollapsed");
      const moonIllumCollapsedEl = document.getElementById("moonIllumCollapsed");
      
      if (moonPhaseCollapsedEl) {
        moonPhaseCollapsedEl.textContent = phase.name;
      }
      if (moonIllumCollapsedEl) {
        moonIllumCollapsedEl.textContent = Math.round(illum.fraction * 100) + "% illuminated";
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
      body.style.display = isOpen ? "none" : ""; if (preview) preview.style.display = isOpen ? "" : "none"; if (!isOpen) { const bd = document.createElement("div"); bd.className = "modal-backdrop"; bd.id = "modalBackdrop"; bd.style.cssText = "position:fixed;inset:0;z-index:199;background:transparent;"; bd.addEventListener("click", () => toggleCard(key, el)); document.body.appendChild(bd); card.classList.add("card-expanded");

        } else { const shouldReturn = window.__navSource; const bd = document.getElementById("modalBackdrop"); if (bd && !shouldReturn) bd.remove(); if (!shouldReturn) card.classList.remove("card-expanded"); else setTimeout(() => card.classList.remove("card-expanded"), 200); if (window.__navSource) { const src = window.__navSource; window.__navSource = null; requestAnimationFrame(() => { showTab(src.tab); requestAnimationFrame(() => { const rc = document.querySelector(`[data-collapse-key="${src.card}"]`); if (rc && !rc.classList.contains("card-expanded")) rc.click(); }); }); } }
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

    function initCollapsedRadarMap() {
      const mapEl = document.getElementById('radarMapCollapsed');
      if (!mapEl || window._collapsedRadarInitialized) {
        console.log('Exiting - no element or already initialized');
        return;
      }
      
      
      // Initialize mini Leaflet map - zoomed in closer to Marblehead
      const miniMap = L.map('radarMapCollapsed', {
        zoomControl: false,
        attributionControl: false,
        dragging: false,
        scrollWheelZoom: false,
        doubleClickZoom: false,
        touchZoom: false
      }).setView([42.5001, -70.8578], 10);
      
      // Store globally so we can invalidate size on tab switch
      window.collapsedRadarMap = miniMap;
      
      // Use light or dark tiles based on theme
      const isDarkMode = !document.body.classList.contains("theme-light");
      const tileUrl = isDarkMode 
        ? "https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png"
        : "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png";
      L.tileLayer(tileUrl, {
        maxZoom: 19
      }).addTo(miniMap);
      
      // No filter - just use natural light map colors
      const style = document.createElement('style');
      style.textContent = `
        @keyframes radarSweep {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
        @keyframes centerPulse {
          0%, 100% { opacity: 0.6; }
          50% { opacity: 0.3; }
        }
      `;
      document.head.appendChild(style);
      
      // SVG overlay
      const svg = L.svg();
      svg.addTo(miniMap);
      
      
      setTimeout(() => {
        const svgEl = document.querySelector('#radarMapCollapsed svg');
          if (!svgEl) {
          console.log('No SVG element found!');
          return;
        }
        
        // Force map to recalculate size since it was hidden during init
        miniMap.invalidateSize();
        
        const center = miniMap.latLngToLayerPoint([42.5001, -70.8578]);
        
        // Range rings: 15, 30, 60, 90 miles - much lighter
        const ranges = [
          { deg: 0.22, opacity: 0.25, width: '1.5' },
          { deg: 0.43, opacity: 0.2, width: '1.5' },
          { deg: 0.87, opacity: 0.15, width: '1' },
          { deg: 1.3, opacity: 0.1, width: '1' }
        ];
        
        ranges.forEach(range => {
          const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
          circle.setAttribute('cx', center.x);
          circle.setAttribute('cy', center.y);
          circle.setAttribute('r', range.deg * 111 * 3);
          circle.setAttribute('fill', 'none');
          circle.setAttribute('stroke', `rgba(100, 180, 120, ${range.opacity})`);
          circle.setAttribute('stroke-width', range.width);
          circle.setAttribute('stroke-dasharray', '5,4');
          svgEl.appendChild(circle);
        });
        
        // Pulsing glow - very subtle
        const glow = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        glow.setAttribute('cx', center.x);
        glow.setAttribute('cy', center.y);
        glow.setAttribute('r', '10');
        glow.setAttribute('fill', 'rgba(80, 160, 100, 0.15)');
        glow.style.animation = 'centerPulse 2s ease-in-out infinite';
        svgEl.appendChild(glow);
        
        // Center dot - lighter
        const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
        dot.setAttribute('cx', center.x);
        dot.setAttribute('cy', center.y);
        dot.setAttribute('r', '5');
        dot.setAttribute('fill', 'rgba(80, 160, 100, 0.7)');
        dot.setAttribute('stroke', 'white');
        dot.setAttribute('stroke-width', '2');
        svgEl.appendChild(dot);
        
        // Sweep group (animated)
        const sweepGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        sweepGroup.style.transformOrigin = `${center.x}px ${center.y}px`;
        sweepGroup.style.animation = 'radarSweep 4s linear infinite';
        
        // Sweep line - lighter
        const sweep = document.createElementNS('http://www.w3.org/2000/svg', 'line');
        sweep.setAttribute('x1', center.x);
        sweep.setAttribute('y1', center.y);
        sweep.setAttribute('x2', center.x + 150);
        sweep.setAttribute('y2', center.y);
        sweep.setAttribute('stroke', 'rgba(100, 180, 120, 0.3)');
        sweep.setAttribute('stroke-width', '2');
        sweep.setAttribute('stroke-linecap', 'round');
        sweepGroup.appendChild(sweep);
        
        // Trailing wedge glow - very subtle
        const sweepFade = document.createElementNS('http://www.w3.org/2000/svg', 'path');
        const sweepPath = `M ${center.x},${center.y} L ${center.x + 150},${center.y} A 150,150 0 0,1 ${center.x + 106},${center.y + 106} Z`;
        sweepFade.setAttribute('d', sweepPath);
        sweepFade.setAttribute('fill', 'rgba(80, 160, 100, 0.05)');
        sweepGroup.appendChild(sweepFade);
        
        svgEl.appendChild(sweepGroup);
        
        // Grid lines - very subtle
        const gridGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
        gridGroup.setAttribute('opacity', '0.08');
        
        for (let i = 0; i < 5; i++) {
          const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
          line.setAttribute('x1', '0');
          line.setAttribute('y1', i * 50);
          line.setAttribute('x2', '400');
          line.setAttribute('y2', i * 50);
          line.setAttribute('stroke', 'rgba(100, 255, 150, 0.5)');
          line.setAttribute('stroke-width', '0.5');
          gridGroup.appendChild(line);
        }
        
        for (let i = 0; i < 8; i++) {
          const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
          line.setAttribute('x1', i * 50);
          line.setAttribute('y1', '0');
          line.setAttribute('x2', i * 50);
          line.setAttribute('y2', '250');
          line.setAttribute('stroke', 'rgba(100, 255, 150, 0.5)');
          line.setAttribute('stroke-width', '0.5');
          gridGroup.appendChild(line);
        }
        
        svgEl.appendChild(gridGroup);
      }, 800);
      
      window._collapsedRadarInitialized = true;
    }

    function initCollapsibleCards() {
      document.querySelectorAll("[data-collapse-key]").forEach(card => {
        const key     = card.getAttribute("data-collapse-key");
        const openDef = card.getAttribute("data-default-open") !== "false";
        const body    = card.querySelector(".card-body");
        if (!body) return;
        let isOpen = false;  // Always start closed on page load
        body.style.display = isOpen ? "" : "none"; const preview = card.querySelector(".card-collapsed-preview"); if (preview) preview.style.display = isOpen ? "none" : ""; if (card.querySelector(".card-collapsed-preview")) { if (card.dataset.collapseKey !== "hyperlocal") { card.classList.toggle("col-12", isOpen); card.classList.toggle("col-6", !isOpen); } }
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

    function generateForecastSummary(forecasts) {
      const summaryEl = document.getElementById("detailedForecastSummary");
      if (!summaryEl || !forecasts || forecasts.length === 0) return;
      
      // Get first period (should be "Today" or current period)
      const today = forecasts[0];
      if (!today || !today.text) {
        summaryEl.textContent = "Check forecast...";
        return;
      }
      
      // Extract first sentence (up to first period)
      const firstSentence = today.text.split('.')[0].trim();
      
      // Add ellipsis
      summaryEl.textContent = firstSentence + "...";
    }

    function renderHyperlocalForecast(forecasts, hourlyTimes, hourlyTemps, tempBias, derived) {
      const list = document.getElementById("hyperlocalForecastList");
      if (!list || !Array.isArray(forecasts) || forecasts.length === 0) {
        if (list) list.innerHTML = '<div style="color:rgba(255,255,255,0.4);font-size:0.88rem;padding:8px 0;">No forecast available.</div>';
        return;
      }

      // Generate short summary for collapsed preview
      generateForecastSummary(forecasts);

      list.innerHTML = "";
      
      // Use corrected daily high/low from collector (single source of truth)
      const _now = new Date();
      const _pad = n => String(n).padStart(2, "0");
      const _ds = d => `${d.getFullYear()}-${_pad(d.getMonth()+1)}-${_pad(d.getDate())}`;
      const _todayStr = _ds(_now);
      const _tom = new Date(_now); _tom.setDate(_tom.getDate() + 1);
      const _tomorrowStr = _ds(_tom);
      const _fcCorrected = {};
      if (derived.today_high != null) _fcCorrected[_todayStr] = { high: derived.today_high, low: derived.today_low };
      if (derived.tomorrow_high != null) _fcCorrected[_tomorrowStr] = { high: derived.tomorrow_high, low: derived.tomorrow_low };

      forecasts.forEach((p, i) => {
        const row = document.createElement("div");
        row.className = "detailed-period";

        // Use wind data from forecast object
        let windText = p.wind_full || "";

        row.innerHTML =
          '<div class="detailed-period-header">' +
            '<span class="detailed-period-name">' + p.period_name + '</span>' +
            '<span class="detailed-period-temp">' + 
              (p.date && _fcCorrected[p.date] ? Math.round(p.is_daytime ? _fcCorrected[p.date].high : _fcCorrected[p.date].low) : p.temperature) +
            '\u00b0F</span>' +
          '</div>' +
          (windText ? '<div class="detailed-period-wind">' + windText + '</div>' : '') +
          '<div class="detailed-period-narrative">' + p.text + '</div>';

        list.appendChild(row);
      });
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

    // Measure header and tab bar heights, set CSS variables for card modal positioning
    (function measureLayout() {
      function measure() {
        const header = document.querySelector('.app-header') || document.querySelector('header');
        const tabBar = document.querySelector('.bottom-tab-bar');
        if (header) {
          const headerBottom = header.getBoundingClientRect().bottom;
          if (headerBottom > 0) {
            document.documentElement.style.setProperty('--header-bottom', headerBottom + 'px');
          }
        }
        if (tabBar) {
          const tabBarTop = tabBar.getBoundingClientRect().top;
          if (tabBarTop > 0) {
            const tabBarHeight = window.innerHeight - tabBarTop;
            document.documentElement.style.setProperty('--tabbar-height', tabBarHeight + 'px');
          }
        }
      }
      // Measure immediately and again after fonts/layout settle
      measure();
      requestAnimationFrame(() => { measure(); });
      window.addEventListener('resize', measure);
    })();

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
      const waterTemp = data.buoy_44013?.water_temp_f;
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
      
      // Observation-Based Corrections
      // Observation-Based Corrections - simple teaser
      const hyp = data.hyperlocal || {};
      const stationsCount = hyp.stations_used || 0;
      const confidence = hyp.confidence || "Unknown";
      
      setText("correctionsStationsCollapsed", `${stationsCount} stations`);

      // Apply corrections confidence gradient class
      const correctionsCard = document.querySelector('[data-collapse-key="hyperlocal"]');
      if (correctionsCard) {
        correctionsCard.classList.remove('tile-corrections-high', 'tile-corrections-moderate', 'tile-corrections-low');
        if (confidence === 'High') correctionsCard.classList.add('tile-corrections-high');
        else if (confidence === 'Moderate') correctionsCard.classList.add('tile-corrections-moderate');
        else if (confidence === 'Low') correctionsCard.classList.add('tile-corrections-low');
      }
      
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
      }
      
      // Wind Gust Impact - populated by Right Now card data
      // Wind Sustained Impact - populated by Right Now card data
      // Sea Breeze - populated by renderSeaBreezeDetail()
      // Sunset Quality - populated by renderSunsetQuality()
      // Dock Day - populated by renderDockDay()
    }

    // ═══════════════════════════════════════════════════════════════
    // Main Data Load
    // ═══════════════════════════════════════════════════════════════

    // Briefing Tab Renderer
    function renderBriefing(data) {
      if (typeof generateBriefing !== 'function') return;
      const b = generateBriefing(data);
      const now = new Date();
      const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
      const months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
      const dl = document.getElementById('briefDateline');
      if (dl) dl.textContent = days[now.getDay()] + ' · ' + now.getDate() + ' ' + months[now.getMonth()];
      const tl = document.getElementById('briefTimeLabel');
      if (tl) tl.textContent = b.timeLabel;
      const hl = document.getElementById('briefHeadline');
      if (hl) {
        hl.textContent = b.headline;
        hl.style.fontStyle = b.isAI ? 'normal' : 'italic';
      }
      const sm = document.getElementById('briefSummary');
      if (sm) sm.textContent = b.summary;
      const sn = document.getElementById('briefTempNow');
      if (sn) sn.innerHTML = (b.stats.now ?? '--') + '<span class="unit">°</span>';
      const sh = document.getElementById('briefTempHigh');
      if (sh) sh.innerHTML = (b.stats.high ?? '--') + '<span class="unit">°</span>';
      const sr = document.getElementById('briefRain');
      if (sr) sr.innerHTML = (b.stats.rainInches || '0') + '<span class="unit">"</span>';
      // Inject wind impact score into briefing Wind row
      const hyp = data.hyperlocal || {};
      const cur = data.current || {};
      const bWindSpeed = hyp.corrected_wind_speed ?? cur.wind_speed;
      const bGustSpeed = hyp.corrected_wind_gusts ?? cur.wind_gusts;
      const bWindDir = cur.wind_direction;
      if (bWindDir != null && (bWindSpeed != null || bGustSpeed != null)) {
        const bImpact = Math.round(combinedWindImpact(bWindSpeed, bGustSpeed, bWindDir));
        const bLevel = worryLevel(bImpact);
        const windRow = b.todayRows.find(r => r.label === 'Wind');
        if (windRow) {
          windRow.value += ' · Impact: ' + bImpact + ' ' + bLevel.label;
        }
      }
      const cm = { green: 'brief-val-green', orange: 'brief-val-orange', red: 'brief-val-red', blue: 'brief-val-blue' };
      const todayEl = document.getElementById('briefTodayRows');
      if (todayEl) { let html = ''; b.todayRows.forEach(r => { const cls = r.color ? cm[r.color] || '' : ''; html += '<div class="brief-row"><span class="brief-row-label">' + r.label + '</span><span class="brief-row-value ' + cls + '">' + r.value + '</span></div>'; }); todayEl.innerHTML = html; }
      const lifeEl = document.getElementById('briefLifestyleSection');
      if (lifeEl) { if (b.lifestyleRows && b.lifestyleRows.length) { let lh = '<hr class="brief-rule"><div class="brief-section-label">Lifestyle</div><div class="brief-rows">'; b.lifestyleRows.forEach(r => { const cls = r.color ? cm[r.color] || '' : ''; lh += '<div class="brief-row"><span class="brief-row-label">' + r.label + '</span><span class="brief-row-value ' + cls + '">' + r.value + '</span></div>'; }); lh += '</div>'; lifeEl.innerHTML = lh; } else { lifeEl.innerHTML = ''; } }
      const watchEl = document.getElementById('briefWatchSection');
      if (watchEl) { if (b.watchRows && b.watchRows.length) { let wh = '<hr class="brief-rule"><div class="brief-section-label">Watch for</div>'; b.watchRows.forEach(r => { if (r.isAlert) { wh += '<div class="brief-alert-row">⚠ <strong>' + r.value + '</strong>' + (r.detail ? ' — ' + r.detail : '') + '</div>'; } else { const cls = r.color ? cm[r.color] || '' : ''; wh += '<div class="brief-row"><span class="brief-row-label">' + r.label + '</span><span class="brief-row-value ' + cls + '">' + r.value + '</span></div>'; } }); watchEl.innerHTML = wh; } else if (b.priority === 'quiet') { watchEl.innerHTML = '<hr class="brief-rule"><div class="brief-section-label">Watch for</div><div class="brief-quiet-note">No alerts, incoming rain, or frost risk today.</div>'; } else { watchEl.innerHTML = ''; } }
      const tonightEl = document.getElementById('briefTonightSection');
      if (tonightEl) { if (b.tonight) { tonightEl.innerHTML = '<hr class="brief-rule"><div class="brief-section-label">Tonight</div><div class="brief-row"><span class="brief-row-label">Overnight</span><span class="brief-row-value">' + b.tonight + '</span></div>'; } else { tonightEl.innerHTML = ''; } }

      // Cross-card navigation from briefing rows
      var navMap = {
        'Sky': { tab: 'weather', card: '48h_temp_precip' },
        'Wind': { tab: 'weather', card: '48h_wind' },
        'Sea breeze': { tab: 'weather', card: 'sea_breeze_detail' },
        'Fog': { tab: 'weather', card: 'fog_risk' },
        'Rain': { tab: 'weather', card: 'right_now' },
        'Wind chill': { tab: 'weather', card: 'feels_like' },
        'Heat index': { tab: 'weather', card: 'feels_like' },
        'Sun': { tab: 'almanac', card: 'sun' },
        'Tide': { tab: 'almanac', card: 'tides' },
        'Moon': { tab: 'almanac', card: 'moon' },
        'Sunset': { tab: 'hyperlocal', card: 'sunset_quality' },
        'Beach day': { tab: 'hyperlocal', card: 'dock_day' },
        'Hair day': { tab: 'hyperlocal', card: 'hair_day' },
        'Birds': { tab: 'hyperlocal', card: 'birds' },
      };
      var allBriefRows = document.querySelectorAll('#briefTodayRows .brief-row, #briefLifestyleSection .brief-row');
      allBriefRows.forEach(function(row) {
        var labelEl = row.querySelector('.brief-row-label');
        if (!labelEl) return;
        var label = labelEl.textContent.trim();
        var nav = navMap[label];
        if (!nav) return;
        row.style.cursor = 'pointer';
        row.onclick = function(e) {
          e.stopPropagation();
          window.__navSource = { tab: 'briefing', card: null };
          showTab(nav.tab);
          setTimeout(function() {
            var card = document.querySelector('[data-collapse-key="' + nav.card + '"]');
            if (card) card.click();
          }, 100);
        };
      });
    }

    
    // Overhead card: reparent overheadView content into card on first expand
    document.addEventListener('click', function(e) {
      var card = e.target.closest('[data-collapse-key="overhead_card"]');
      if (card && window.__overheadMoved !== true) {
        var src = document.querySelector('#overheadView > .card');
        var dest = document.getElementById('overheadCardBody');
        if (src && dest) {
          dest.appendChild(src);
          window.__overheadMoved = true;
          if (typeof ohInitMap === 'function') setTimeout(function() { ohInitMap(); if (typeof ohRefresh === 'function') ohRefresh(); }, 300);
        }
      }
    });

function loadWeatherData() {
    fetch("https://storage.googleapis.com/myweather-data/weather_data.json?t=" + Date.now())
      .then(r => r.json())
      .then(data => {
        window.__lastWeatherData = data;

        // Apply temperature-based gradient to Right Now card
        const temp = data.hyperlocal?.corrected_temp ?? data.current?.temperature ?? 50;
        const rightNowCard = document.querySelector('[data-collapse-key="right_now"]');
        if (rightNowCard) {
          rightNowCard.classList.remove('tile-temp-cold', 'tile-temp-cool', 'tile-temp-mild', 'tile-temp-warm', 'tile-temp-hot');
          if (temp < 40) rightNowCard.classList.add('tile-temp-cold');
          else if (temp < 55) rightNowCard.classList.add('tile-temp-cool');
          else if (temp < 70) rightNowCard.classList.add('tile-temp-mild');
          else if (temp < 85) rightNowCard.classList.add('tile-temp-warm');
          else rightNowCard.classList.add('tile-temp-hot');
        }

        // Header
        // // document.getElementById("location").textContent    = data.location?.name ?? "Wyman Cove";
        document.getElementById("dataUpdated").textContent = fmtLocal(data.generated_at || data.location?.updated);
        renderSources(data.sources, (data.pws || {}).stale);
        renderFrostTracker(data.frost_log);
        renderBirds(data.birds);
        renderSunsetQuality(data);
        renderDockDay(data);
        renderHairDay(data);
        renderBriefing(data);
        renderSolarSystem();

        // Alerts — consolidated summary bar, panel collapsed by default
        const alertsContainer = document.getElementById("alertsContainer");
        const alertSummaryBar = document.getElementById("alertSummaryBar");
        const alertSummaryText = document.getElementById("alertSummaryText");
        alertsContainer.innerHTML = "";
        // Filter out TEST alerts (NWS transmission tests)
        const _realAlerts = (data.alerts || []).filter(a => {
          const txt = ((a.description || '') + ' ' + (a.headline || '')).toUpperCase();
          return !txt.includes('THIS_MESSAGE_IS_FOR_TEST_PURPOSES_ONLY') && !txt.includes('THIS IS A TEST');
        });
        data.alerts = _realAlerts;
        if (data.alerts && data.alerts.length > 0) {
          const n = data.alerts.length;
          
          // Only show summary bar if there are multiple alerts
          if (alertSummaryBar) {
            alertSummaryBar.style.display = "none"; // alerts shown via badge/modal
          }
          
          if (alertSummaryText) {
            alertSummaryText.textContent = `${n} active alert${n > 1 ? "s" : ""}: ${data.alerts.map(a => a.event || "Alert").join(" · ")}`;
          }
          
          // Single alert — badge handles it, no inline display
          
          alertsContainer.innerHTML = data.alerts.map((a, i) => {
            const id = `alertBody_${i}`;
            return `
            <div class="alert-banner">
              <div class="alert-title" onclick="toggleAlert('${id}')" style="cursor:pointer;display:flex;align-items:center;justify-content:space-between;">
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
        const ctc = document.getElementById("currentTempCollapsed"); 
        if (ctc) {
          const temp = Math.round(data.hyperlocal?.corrected_temp ?? cur.temperature ?? 0);
          ctc.innerHTML = `${temp}<span style="font-size:34px;font-weight:300;color:rgba(0,0,0,0.4);">°</span>`;
          
          // Update thermometer mercury level
          // Tube goes from y=4 (top, 100°F) to y=78 (bottom of tube, 0°F)
          // Bulb top is at y=76
          const mercury = document.getElementById("thermometerMercury");
          if (mercury) {
            const clampedTemp = Math.max(0, Math.min(100, temp));
            // Calculate mercury top position: 100°F = y=4, 0°F = y=76
            const mercuryTop = 76 - (clampedTemp / 100) * 72; // 72px is tube height
            const mercuryHeight = 78 - mercuryTop; // Always extends to bulb connection at y=78
            mercury.setAttribute("y", mercuryTop);
            mercury.setAttribute("height", mercuryHeight);
          }
        }
        
        // Hyperlocal data
        const hyp = data.hyperlocal || {};
        const wu = data.wu_stations || {};
        const der = data.derived || {};
        
        // Calculate corrected Feels Like from corrected temp + wind
        const correctedFeelsLike = der.corrected_feels_like ?? cur.apparent_temperature ?? 0;
        
        document.getElementById("feelsLike").textContent =
          `Feels like ${Math.round(correctedFeelsLike)}°F`;
        const flc = document.getElementById("feelsLikeCollapsed"); if (flc) flc.textContent = `Feels like ${Math.round(correctedFeelsLike)}°`;
        
        // 10-Day collapsed preview - use same calculation as hiLo
        const tenDayHighEl = document.getElementById("tenDayHigh");
        const tenDayLowEl = document.getElementById("tenDayLow");
        if (tenDayHighEl && tenDayLowEl) {
          const der = data.derived || {};
          tenDayHighEl.textContent = der.today_high != null ? `${Math.round(der.today_high)}°` : `--°`;
          tenDayLowEl.textContent = der.today_low != null ? `${Math.round(der.today_low)}°` : `--°`;
        }
        const obsTag = cur.condition_source === "KBVY observed" ? " <span style='font-size:0.75rem;opacity:0.5;'>[obs]</span>" : "";
        document.getElementById("condition").innerHTML = `${emoji} ${desc}${obsTag}`;
        // Removed conditionCollapsed - sky condition now goes in Sky & Precip tile
        
        // Populate Sky & Precip tile preview - with day/night graphics and backgrounds
        const skyConditionEl = document.getElementById("skyConditionCollapsed");
        const skyStatsEl = document.getElementById("skyStatsCollapsed");
        const weatherGraphic = document.getElementById("weatherGraphic");
        const skyPrecipBg = document.getElementById("skyPrecipBg");
        
        if (skyConditionEl) skyConditionEl.textContent = desc;
        if (skyStatsEl) {
          const precipProb = data.hourly?.precipitation_probability?.[0] || 0;
          const cloudCover = data.hourly?.cloud_cover?.[0] || 0;
          
          let skyText = `${precipProb}% precip`;
          if (cloudCover === 100) {
            skyText += ` | 100% clouds`;
          } else if (cloudCover === 0) {
            skyText += ` | Clear`;
          } else {
            skyText += ` | ${Math.round(cloudCover)}% clouds`;
          }
          
          skyStatsEl.textContent = skyText;
        }
        
        // Draw weather graphics and set background based on condition and time of day
        if (weatherGraphic) {
          const skyPrecipCard = document.querySelector('[data-collapse-key="48h_temp_precip"]');
          const condition = desc.toLowerCase();
          
          // Determine if it's day or night
          const now = new Date();
          const sunrise = data.daily?.sunrise?.[0] ? new Date(data.daily.sunrise[0]) : null;
          const sunset = data.daily?.sunset?.[0] ? new Date(data.daily.sunset[0]) : null;
          const isDay = sunrise && sunset ? (now >= sunrise && now < sunset) : true;
          
          let graphicSVG = '';
          let weatherClass = '';
          
          // Clear/Sunny
          if (condition.includes('clear') || condition.includes('sunny')) {
            weatherClass = isDay ? 'weather-clear-day' : 'weather-clear-night';
            if (isDay) {
              // Day: Bright sun
              graphicSVG = `
                <circle cx="75" cy="25" r="18" fill="rgba(255,200,80,0.8)"/>
                <line x1="75" y1="3" x2="75" y2="10" stroke="rgba(255,200,80,0.7)" stroke-width="2" stroke-linecap="round"/>
                <line x1="93" y1="25" x2="100" y2="25" stroke="rgba(255,200,80,0.7)" stroke-width="2" stroke-linecap="round"/>
                <line x1="86" y1="36" x2="91" y2="41" stroke="rgba(255,200,80,0.7)" stroke-width="2" stroke-linecap="round"/>
                <line x1="86" y1="14" x2="91" y2="9" stroke="rgba(255,200,80,0.7)" stroke-width="2" stroke-linecap="round"/>
                <line x1="64" y1="36" x2="59" y2="41" stroke="rgba(255,200,80,0.7)" stroke-width="2" stroke-linecap="round"/>
                <line x1="64" y1="14" x2="59" y2="9" stroke="rgba(255,200,80,0.7)" stroke-width="2" stroke-linecap="round"/>
              `;
            } else {
              // Night: Moon and stars
              graphicSVG = `
                <circle cx="75" cy="25" r="16" fill="rgba(245,245,220,0.8)"/>
                <circle cx="80" cy="20" r="16" fill="rgba(25,25,112,0.6)"/>
                <circle cx="20" cy="15" r="2" fill="rgba(255,255,255,0.8)"/>
                <circle cx="30" cy="25" r="1.5" fill="rgba(255,255,255,0.7)"/>
                <circle cx="45" cy="12" r="1.5" fill="rgba(255,255,255,0.7)"/>
                <circle cx="25" cy="35" r="2" fill="rgba(255,255,255,0.8)"/>
              `;
            }
          }
          // Partly Cloudy
          else if (condition.includes('partly')) {
            weatherClass = isDay ? 'weather-partly-day' : 'weather-partly-night';
            if (isDay) {
              // Day: Sun peeking through clouds
              graphicSVG = `
                <circle cx="60" cy="20" r="12" fill="rgba(255,200,80,0.6)"/>
                <ellipse cx="75" cy="35" rx="20" ry="14" fill="rgba(220,220,220,0.85)"/>
                <ellipse cx="58" cy="40" rx="16" ry="12" fill="rgba(200,200,200,0.85)"/>
              `;
            } else {
              // Night: Moon and clouds
              graphicSVG = `
                <circle cx="60" cy="20" r="11" fill="rgba(245,245,220,0.7)"/>
                <circle cx="64" cy="17" r="11" fill="rgba(47,79,79,0.5)"/>
                <ellipse cx="75" cy="35" rx="20" ry="14" fill="rgba(169,169,169,0.8)"/>
                <ellipse cx="58" cy="40" rx="16" ry="12" fill="rgba(128,128,128,0.8)"/>
              `;
            }
          }
          // Overcast/Cloudy
          else if (condition.includes('overcast') || condition.includes('cloudy')) {
            weatherClass = isDay ? 'weather-cloudy-day' : 'weather-cloudy-night';
            if (isDay) {
              // Day: Gray clouds
              graphicSVG = `
                <ellipse cx="50" cy="28" rx="24" ry="16" fill="rgba(160,160,160,0.8)"/>
                <ellipse cx="75" cy="35" rx="22" ry="15" fill="rgba(150,150,150,0.8)"/>
                <ellipse cx="30" cy="38" rx="20" ry="14" fill="rgba(170,170,170,0.8)"/>
              `;
            } else {
              // Night: Darker clouds
              graphicSVG = `
                <ellipse cx="50" cy="28" rx="24" ry="16" fill="rgba(105,105,105,0.85)"/>
                <ellipse cx="75" cy="35" rx="22" ry="15" fill="rgba(90,90,90,0.85)"/>
                <ellipse cx="30" cy="38" rx="20" ry="14" fill="rgba(115,115,115,0.85)"/>
              `;
            }
          }
          // Rain
          else if (condition.includes('rain') || condition.includes('drizzle') || condition.includes('shower')) {
            weatherClass = isDay ? 'weather-rain-day' : 'weather-rain-night';
            if (isDay) {
              // Day: Rain clouds and raindrops
              graphicSVG = `
                <ellipse cx="50" cy="25" rx="22" ry="14" fill="rgba(100,100,100,0.8)"/>
                <line x1="40" y1="45" x2="36" y2="60" stroke="rgba(100,150,200,0.7)" stroke-width="2.5" stroke-linecap="round"/>
                <line x1="52" y1="45" x2="48" y2="60" stroke="rgba(100,150,200,0.7)" stroke-width="2.5" stroke-linecap="round"/>
                <line x1="64" y1="45" x2="60" y2="60" stroke="rgba(100,150,200,0.7)" stroke-width="2.5" stroke-linecap="round"/>
                <line x1="46" y1="50" x2="42" y2="65" stroke="rgba(100,150,200,0.6)" stroke-width="2" stroke-linecap="round"/>
                <line x1="58" y1="50" x2="54" y2="65" stroke="rgba(100,150,200,0.6)" stroke-width="2" stroke-linecap="round"/>
              `;
            } else {
              // Night: Dark rain
              graphicSVG = `
                <ellipse cx="50" cy="25" rx="22" ry="14" fill="rgba(70,70,70,0.85)"/>
                <line x1="40" y1="45" x2="36" y2="60" stroke="rgba(80,120,160,0.75)" stroke-width="2.5" stroke-linecap="round"/>
                <line x1="52" y1="45" x2="48" y2="60" stroke="rgba(80,120,160,0.75)" stroke-width="2.5" stroke-linecap="round"/>
                <line x1="64" y1="45" x2="60" y2="60" stroke="rgba(80,120,160,0.75)" stroke-width="2.5" stroke-linecap="round"/>
                <line x1="46" y1="50" x2="42" y2="65" stroke="rgba(80,120,160,0.65)" stroke-width="2" stroke-linecap="round"/>
                <line x1="58" y1="50" x2="54" y2="65" stroke="rgba(80,120,160,0.65)" stroke-width="2" stroke-linecap="round"/>
              `;
            }
          }
          // Snow
          else if (condition.includes('snow') || condition.includes('flurr')) {
            weatherClass = isDay ? 'weather-snow-day' : 'weather-snow-night';
            if (isDay) {
              // Day: Snow clouds and snowflakes
              graphicSVG = `
                <ellipse cx="50" cy="25" rx="22" ry="14" fill="rgba(180,180,200,0.8)"/>
                <text x="35" y="55" font-size="18" fill="rgba(150,180,220,0.8)">❄</text>
                <text x="55" y="62" font-size="14" fill="rgba(150,180,220,0.75)">❄</text>
                <text x="48" y="48" font-size="12" fill="rgba(150,180,220,0.7)">❄</text>
              `;
            } else {
              // Night: Dark snow
              graphicSVG = `
                <ellipse cx="50" cy="25" rx="22" ry="14" fill="rgba(90,90,110,0.85)"/>
                <text x="35" y="55" font-size="18" fill="rgba(180,200,230,0.8)">❄</text>
                <text x="55" y="62" font-size="14" fill="rgba(180,200,230,0.75)">❄</text>
                <text x="48" y="48" font-size="12" fill="rgba(180,200,230,0.7)">❄</text>
              `;
            }
          }
          // Mist/Fog
          else if (condition.includes('mist') || condition.includes('fog')) {
            weatherClass = isDay ? 'weather-mist-day' : 'weather-mist-night';
            if (isDay) {
              // Day: Light fog waves
              graphicSVG = `
                <path d="M 20,25 Q 40,20 60,25 T 100,25" stroke="rgba(200,200,200,0.7)" stroke-width="5" fill="none" stroke-linecap="round"/>
                <path d="M 15,40 Q 40,35 65,40 T 105,40" stroke="rgba(210,210,210,0.7)" stroke-width="5" fill="none" stroke-linecap="round"/>
                <path d="M 18,55 Q 40,50 62,55 T 102,55" stroke="rgba(200,200,200,0.65)" stroke-width="5" fill="none" stroke-linecap="round"/>
              `;
            } else {
              // Night: Darker fog
              graphicSVG = `
                <path d="M 20,25 Q 40,20 60,25 T 100,25" stroke="rgba(130,130,130,0.75)" stroke-width="5" fill="none" stroke-linecap="round"/>
                <path d="M 15,40 Q 40,35 65,40 T 105,40" stroke="rgba(140,140,140,0.75)" stroke-width="5" fill="none" stroke-linecap="round"/>
                <path d="M 18,55 Q 40,50 62,55 T 102,55" stroke="rgba(130,130,130,0.7)" stroke-width="5" fill="none" stroke-linecap="round"/>
              `;
            }
          }
          
          weatherGraphic.innerHTML = graphicSVG;
          
          // Apply weather class to card
          if (skyPrecipCard) {
            skyPrecipCard.classList.remove('weather-clear-day', 'weather-clear-night', 'weather-partly-day', 'weather-partly-night', 
              'weather-cloudy-day', 'weather-cloudy-night', 'weather-rain-day', 'weather-rain-night', 
              'weather-snow-day', 'weather-snow-night', 'weather-mist-day', 'weather-mist-night');
            if (weatherClass) {
              skyPrecipCard.classList.add(weatherClass);
            }
          }
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
          
          const scModelWindSpeed = document.getElementById("scModelWindSpeed");
          const scBiasWindSpeed = document.getElementById("scBiasWindSpeed");
          const scCorrectedWindSpeed = document.getElementById("scCorrectedWindSpeed");
          if (scModelWindSpeed) scModelWindSpeed.textContent = hyp.model_wind_speed != null ? Math.round(hyp.model_wind_speed) + " mph" : "--";
          if (scBiasWindSpeed) scBiasWindSpeed.textContent = hyp.bias_wind_speed != null ? (hyp.bias_wind_speed >= 0 ? "+" : "") + hyp.bias_wind_speed.toFixed(1) + " mph" : "--";
          if (scCorrectedWindSpeed) scCorrectedWindSpeed.textContent = hyp.corrected_wind_speed != null ? Math.round(hyp.corrected_wind_speed) + " mph" : "--";
          
          const scModelGusts = document.getElementById("scModelGusts");
          const scBiasGusts = document.getElementById("scBiasGusts");
          const scCorrectedGusts = document.getElementById("scCorrectedGusts");
          if (scModelGusts) scModelGusts.textContent = hyp.model_wind_gusts != null ? Math.round(hyp.model_wind_gusts) + " mph" : "--";
          if (scBiasGusts) scBiasGusts.textContent = hyp.bias_wind_gusts != null ? (hyp.bias_wind_gusts >= 0 ? "+" : "") + hyp.bias_wind_gusts.toFixed(1) + " mph" : "--";
          if (scCorrectedGusts) scCorrectedGusts.textContent = hyp.corrected_wind_gusts != null ? Math.round(hyp.corrected_wind_gusts) + " mph" : "--";
          
          // Dew Point
          const scModelDewpoint = document.getElementById("scModelDewpoint");
          const scBiasDewpoint = document.getElementById("scBiasDewpoint");
          const scCorrectedDewpoint = document.getElementById("scCorrectedDewpoint");
          const modelDewpoint = cur.dew_point;
          if (scModelDewpoint) scModelDewpoint.textContent = modelDewpoint != null ? Math.round(modelDewpoint) + "°F" : "--";
          // Calculate corrected dew point from corrected temp + humidity
          if (scCorrectedDewpoint) {
            const correctedDewpoint = der.corrected_dew_point;
            scCorrectedDewpoint.textContent = correctedDewpoint != null ? Math.round(correctedDewpoint) + "°F" : "--";
            if (scBiasDewpoint && modelDewpoint != null && correctedDewpoint != null) {
              const dewBias = correctedDewpoint - modelDewpoint;
              scBiasDewpoint.textContent = (dewBias >= 0 ? "+" : "") + dewBias.toFixed(1) + "°F";
            }
          } else {
            if (scCorrectedDewpoint) scCorrectedDewpoint.textContent = "--";
            if (scBiasDewpoint) scBiasDewpoint.textContent = "--";
          }
          
          // Wet Bulb Temp
          const scModelWetBulb = document.getElementById("scModelWetBulb");
          const scBiasWetBulb = document.getElementById("scBiasWetBulb");
          const scCorrectedWetBulb = document.getElementById("scCorrectedWetBulb");
          const modelWetBulb = cur.wet_bulb;
          if (scModelWetBulb) scModelWetBulb.textContent = modelWetBulb != null ? Math.round(modelWetBulb) + "°F" : "--";
          const correctedWetBulb = der.corrected_wet_bulb;
          if (scCorrectedWetBulb) scCorrectedWetBulb.textContent = correctedWetBulb != null ? Math.round(correctedWetBulb) + "°F" : "--";
          // Calculate and display bias
          if (scBiasWetBulb && modelWetBulb != null && correctedWetBulb != null) {
            const wbBias = correctedWetBulb - modelWetBulb;
            scBiasWetBulb.textContent = (wbBias >= 0 ? "+" : "") + wbBias.toFixed(1) + "°F";
          } else if (scBiasWetBulb) {
            scBiasWetBulb.textContent = "--";
          }
          
          // Feels Like
          const scModelFeelsLike = document.getElementById("scModelFeelsLike");
          const scBiasFeelsLike = document.getElementById("scBiasFeelsLike");
          const scCorrectedFeelsLike = document.getElementById("scCorrectedFeelsLike");
          // Model feels like from apparent_temperature
          const modelFeelsLike = cur.apparent_temperature;
          if (scModelFeelsLike) scModelFeelsLike.textContent = modelFeelsLike != null ? Math.round(modelFeelsLike) + "°F" : "--";
          // Use corrected feels-like from collector (single source of truth)
          if (scCorrectedFeelsLike) {
            const feelsLike = der.corrected_feels_like;
            scCorrectedFeelsLike.textContent = feelsLike != null ? Math.round(feelsLike) + "°F" : "--";
            if (scBiasFeelsLike && modelFeelsLike != null && feelsLike != null) {
              const flBias = feelsLike - modelFeelsLike;
              scBiasFeelsLike.textContent = (flBias >= 0 ? "+" : "") + flBias.toFixed(1) + "°F";
            }
          } else {
            if (scCorrectedFeelsLike) scCorrectedFeelsLike.textContent = "--";
            if (scBiasFeelsLike) scBiasFeelsLike.textContent = "--";
          }
          
          // Precip Type (only show if precipitation is likely)
          const scModelPrecipType = document.getElementById("scModelPrecipType");
          const scBiasPrecipType = document.getElementById("scBiasPrecipType");
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
              // Bias: show if different from model, otherwise --
              if (scBiasPrecipType) {
                scBiasPrecipType.textContent = (displayType !== modelPType) ? "Changed" : "--";
              }
            } else if (scCorrectedPrecipType) {
              scCorrectedPrecipType.textContent = "--";
              if (scBiasPrecipType) scBiasPrecipType.textContent = "--";
            }
          } else {
            if (scModelPrecipType) scModelPrecipType.textContent = "None";
            if (scCorrectedPrecipType) scCorrectedPrecipType.textContent = "None";
            if (scBiasPrecipType) scBiasPrecipType.textContent = "--";
          }
          
          // Station count and confidence
          const stationsUsedCount = document.getElementById("stationsUsedCount");
          if (stationsUsedCount) stationsUsedCount.textContent = hyp.stations_used ?? "--";
          
          
          const hyperlocalStationsDiag = document.getElementById("hyperlocalStationsDiag");
          if (hyperlocalStationsDiag) hyperlocalStationsDiag.textContent = `${hyp.stations_used ?? "--"} of ${hyp.stations_total ?? "--"} stations used`;
          
          }
        // Today summary
        const daily = data.daily || {};

        const kbos  = data.kbos   || {};
        
        // Use corrected daily high/low from collector (single source of truth)
        const _der = data.derived || {};
        document.getElementById("hiLo").textContent =
          (_der.today_high != null && _der.today_low != null) ? `${Math.round(_der.today_high)}° / ${Math.round(_der.today_low)}°` : "-- / --";
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
        
        // Wind Impact now - combined score (sustained if <15mph, gust otherwise)
        const windImpactNowEl = document.getElementById("windImpactNow");
        if (windImpactNowEl) {
          const windSpeed = hyp.corrected_wind_speed ?? cur.wind_speed;
          const gustValue = hyp.corrected_wind_gusts ?? cur.wind_gusts;
          const windDir   = cur.wind_direction;
          const windDirStr = windDir != null ? degToCompass(windDir) : "";
          
          if (windDir != null && (windSpeed != null || gustValue != null)) {
            const combined = Math.round(combinedWindImpact(windSpeed, gustValue, windDir));
            const level    = worryLevel(combined);
            const spdStr   = windSpeed != null ? `${Math.round(windSpeed)} mph` : "--";
            const gustStr  = gustValue != null ? ` · Gusts ${Math.round(gustValue)} mph` : "";
            windImpactNowEl.innerHTML = `${combined} (${level.label}) · ${windDirStr} ${spdStr}${gustStr}`;
          } else {
            windImpactNowEl.textContent = "--";
          }
        }
        
        // Populate Weather page Wind Impact tile (redesigned)
        const weatherWindSustainedSpeedEl = document.getElementById("weatherWindSustainedSpeed");
        const weatherWindGustsLineEl = document.getElementById("weatherWindGustsLine");
        const weatherWindDirectionIndicatorEl = document.getElementById("weatherWindDirectionIndicator");
        const weatherWindImpactBarEl = document.getElementById("weatherWindImpactBar");
        
        if (weatherWindSustainedSpeedEl && weatherWindGustsLineEl && weatherWindImpactBarEl) {
          const windSpeed = hyp.corrected_wind_speed ?? cur.wind_speed;
          const gustSpeed = hyp.corrected_wind_gusts ?? cur.wind_gusts;
          const windDir = cur.wind_direction;
          
          // Set sustained speed (just number)
          weatherWindSustainedSpeedEl.textContent = windSpeed != null ? Math.round(windSpeed) : '--';
          
          // Set gusts line (one line: "Gusts 21 mph")
          weatherWindGustsLineEl.textContent = gustSpeed != null 
            ? `Gusts ${Math.round(gustSpeed)} mph` 
            : 'Gusts -- mph';
          
          // Rotate direction indicator arrow (add 90° because arrow defaults to north, wind is FROM so show TO)
          if (weatherWindDirectionIndicatorEl && windDir != null) {
            const arrowRotation = (windDir + 90) % 360;
            // Set base rotation, CSS animation adds wobble
            weatherWindDirectionIndicatorEl.style.transformOrigin = '60px 60px';
            weatherWindDirectionIndicatorEl.style.transform = `rotate(${arrowRotation}deg)`;
            weatherWindDirectionIndicatorEl.removeAttribute('transform');
            weatherWindDirectionIndicatorEl.classList.add('wind-wobble');
          }
          
          // Set impact score (combined: sustained if <15mph, gust otherwise)
          const windBarClasses = ['wind-bar-calm','wind-bar-light','wind-bar-moderate','wind-bar-strong','wind-bar-severe'];
          const windTintClasses = ['wind-tint-calm','wind-tint-light','wind-tint-moderate','wind-tint-strong','wind-tint-severe'];
          const windCard = document.querySelector('[data-collapse-key="48h_wind"]');
          weatherWindImpactBarEl.classList.remove(...windBarClasses);
          if (windCard) windCard.classList.remove(...windTintClasses);
          if (windDir != null && (windSpeed != null || gustSpeed != null)) {
            const combined = Math.round(combinedWindImpact(windSpeed, gustSpeed, windDir));
            const combinedLevel = worryLevel(combined);
            weatherWindImpactBarEl.textContent = `Impact: ${combined} ${combinedLevel.label}`;
            const colorCls = combined <= 2 ? 'calm' : combined <= 4 ? 'light' : combined <= 7 ? 'moderate' : combined <= 10 ? 'strong' : 'severe';
            weatherWindImpactBarEl.classList.add(`wind-bar-${colorCls}`);
            if (windCard) windCard.classList.add(`wind-tint-${colorCls}`);
          } else {
            weatherWindImpactBarEl.textContent = 'Impact: --';
          }
        }
        
        // Populate Hyperlocal merged Wind Impact card collapsed tile
        const windImpactCollapsedEl     = document.getElementById("windImpactCollapsed");
        const windImpactLabelEl         = document.getElementById("windImpactLabel");
        const windImpactPeakCollapsedEl = document.getElementById("windImpactPeakCollapsed");

        const windRisk = data.wind_risk || {};

        {
          const cwSpeed = hyp.corrected_wind_speed ?? cur.wind_speed;
          const cwGust  = hyp.corrected_wind_gusts ?? cur.wind_gusts;
          const cwDir   = cur.wind_direction;
          if (windImpactCollapsedEl && cwDir != null) {
            const combined      = Math.round(combinedWindImpact(cwSpeed, cwGust, cwDir));
            const combinedLevel = worryLevel(combined);
            const dirStr        = degToCompass(cwDir);
            windImpactCollapsedEl.textContent = combined.toString();
            if (windImpactLabelEl) windImpactLabelEl.textContent = combinedLevel.label;
            if (windImpactPeakCollapsedEl) windImpactPeakCollapsedEl.textContent =
              `${dirStr} · ${cwSpeed != null ? Math.round(cwSpeed) : '--'} mph · Gusts ${cwGust != null ? Math.round(cwGust) : '--'} mph`;
            const windCard = document.querySelector('[data-collapse-key="wind_impact"]');
            if (windCard) {
              windCard.classList.remove('tile-wind-calm','tile-wind-light','tile-wind-moderate','tile-wind-strong','tile-wind-severe');
              const cls = combined <= 2 ? 'calm' : combined <= 4 ? 'light' : combined <= 7 ? 'moderate' : combined <= 10 ? 'strong' : 'severe';
              windCard.classList.add(`tile-wind-${cls}`);
            }
          }
        }
        
        // Gust Impact expanded detail rows (still populate for expanded body)
        const gustData = windRisk.gust || {};
        if (gustData.worry_score !== undefined) {
          const gustScore = Math.round(gustData.worry_score);
          const gustLevel = worryLevel(gustScore);
          const gustEl = document.getElementById("gustCurrentScore");
          if (gustEl) gustEl.innerHTML = `<span class="badge ${gustLevel.cls}">${gustScore}</span> (${gustLevel.label})`;
          const gustPeakEl = document.getElementById("gustPeak");
          if (gustPeakEl) gustPeakEl.textContent = `${gustData.peak_mph || "--"} mph`;
          const gustDirEl = document.getElementById("gustDir");
          if (gustDirEl) gustDirEl.textContent = gustData.direction_deg != null ? `${gustData.direction_deg}° ${degToCompass(gustData.direction_deg)}` : "--";
          const gustExpEl = document.getElementById("gustExposure");
          if (gustExpEl) gustExpEl.textContent = gustData.exposure_factor != null ? `${(gustData.exposure_factor * 100).toFixed(0)}%` : "--";
          const gustTimeEl = document.getElementById("gustTime");
          if (gustTimeEl) gustTimeEl.textContent = gustData.peak_time ? fmtLocal(gustData.peak_time) : "--";
        }
        
        // Pressure now (with trend inline)
        const pressure = hyp.corrected_pressure_in != null ? hyp.corrected_pressure_in + ' inHg' : (cur.pressure != null ? hpaToInhg(cur.pressure) + ' inHg' : "--");
        const trend = der.pressure_trend || kbos.tendency_label || "";
        const trendShort = der.best_pressure_tend != null 
          ? (der.best_pressure_tend > 0.5 ? "↑" : der.best_pressure_tend < -0.5 ? "↓" : "") 
          : (trend.includes("Rising") ? "↑" : trend.includes("Falling") ? "↓" : "");
        const pressureChange = der.best_pressure_tend != null ? ` ${der.best_pressure_tend > 0 ? '+' : ''}${der.best_pressure_tend.toFixed(1)} hPa` : "";
        const pressureColType = "";
        document.getElementById("pressureNow").textContent = `${pressure} ${trendShort}${pressureChange}${pressureColType}`.trim();
        
        // Humidity now (use corrected if available)
        const displayHumidity = hyp.corrected_humidity ?? cur.humidity;
        document.getElementById("humidityNow").textContent = 
          displayHumidity != null ? `${Math.round(displayHumidity)}%` : "--%";
        
        // Visibility now
        document.getElementById("visibilityNow").textContent = 
          cur.visibility != null ? `${(cur.visibility / 1609.34).toFixed(1)} mi` : "-- mi";

        const _cdp = der.corrected_dew_point ?? cur.dew_point;
        document.getElementById("dewPointNow").textContent = _cdp != null ? `${Math.round(_cdp)}°F` : "--°F";
        
        // Dewpoint depression
        const dewDepEl = document.getElementById("dewPointDepression");
        if (_cdp != null) {
          const depression = (hyp.corrected_temp ?? cur.temperature) - _cdp;
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
              icon = "";
            } else if (likelihood >= 40) {
              icon = "";
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
          fogEl.textContent = fogPct != null ? `${fogLabel} (${fogPct}% chance)` : fogLabel;
          fogEl.style.color = fogLabel === "Likely"     ? "rgba(255,220,80,0.9)"
                            : fogLabel === "Possible"   ? "rgba(255,200,100,0.85)"
                            : fogLabel === "Low chance" ? "rgba(200,200,200,0.7)"
                            : "rgba(255,255,255,0.85)";
        }

       // Sunset Score - read from rendered sunset card
        const sunsetScoreEl = document.getElementById("sunsetScoreNow");
        if (sunsetScoreEl) {
          if (window.__todaySunsetScore) {
            const s = window.__todaySunsetScore;
            sunsetScoreEl.innerHTML = `${s.label} <span style="opacity:0.6;font-size:0.85rem;">(${Math.round(s.score)}/100)</span>`;
            sunsetScoreEl.style.color = s.color;
          } else {
            sunsetScoreEl.textContent = "No data";
          }
        }

        // Dock Day Score - read from renderDockDay()
        const dockDayScoreEl = document.getElementById("dockDayScoreNow");
        if (dockDayScoreEl && window.__todayDockScore) {
          const d = window.__todayDockScore;
          dockDayScoreEl.innerHTML = `${d.label} <span style="opacity:0.6;font-size:0.85rem;">(${Math.round(d.score * 100)}/100)</span>`;
          dockDayScoreEl.style.color = d.color;
        } else if (dockDayScoreEl) {
          dockDayScoreEl.textContent = "No data";
        }

        // Make hyperlocal fields tappable with click handlers
        if (windImpactNowEl) {
          windImpactNowEl.classList.add('hyperlocal-link');
          windImpactNowEl.onclick = (e) => { e.stopPropagation(); window.__navSource = {tab: 'weather', card: 'right_now'}; const card = document.querySelector('[data-collapse-key="wind_impact"]'); if (card) card.click(); };
        }
        if (sbEl) {
          sbEl.classList.add('hyperlocal-link');
          sbEl.onclick = (e) => { e.stopPropagation(); window.__navSource = {tab: 'weather', card: 'right_now'}; const card = document.querySelector('[data-collapse-key="sea_breeze_detail"]'); if (card) card.click(); };
        }
        if (fogEl) {
          fogEl.classList.add('hyperlocal-link');
          fogEl.onclick = (e) => { e.stopPropagation(); window.__navSource = {tab: 'weather', card: 'right_now'}; const card = document.querySelector('[data-collapse-key="fog_risk"]'); if (card) card.click(); };
        }
        if (sunsetScoreEl) {
          sunsetScoreEl.classList.add('hyperlocal-link');
          sunsetScoreEl.onclick = (e) => { e.stopPropagation(); window.__navSource = {tab: 'weather', card: 'right_now'}; showTab('hyperlocal'); setTimeout(() => { const card = document.querySelector('[data-collapse-key="sunset_quality"]'); if (card) card.click(); }, 100); };
        }
        if (dockDayScoreEl) {
          dockDayScoreEl.classList.add('hyperlocal-link');
          dockDayScoreEl.onclick = (e) => { e.stopPropagation(); window.__navSource = {tab: 'weather', card: 'right_now'}; showTab('hyperlocal'); setTimeout(() => { const card = document.querySelector('[data-collapse-key="dock_day"]'); if (card) card.click(); }, 100); };
        }

        // Hair Day Score
        const hairDayNowEl = document.getElementById("hairDayNow");
        if (hairDayNowEl && window.__todayHairScore) {
          const h = window.__todayHairScore;
          hairDayNowEl.innerHTML = `${h.scoreLabel} <span style="opacity:0.6;font-size:0.85rem;">(${h.score}/100)</span>`;
          hairDayNowEl.style.color = h.color;
          hairDayNowEl.classList.add('hyperlocal-link');
          hairDayNowEl.onclick = (e) => { e.stopPropagation(); window.__navSource = {tab: 'weather', card: 'right_now'}; showTab('hyperlocal'); setTimeout(() => { const card = document.querySelector('[data-collapse-key="hair_day"]'); if (card) card.click(); }, 100); };
        } else if (hairDayNowEl) {
          hairDayNowEl.textContent = "No data";
        }

        const feelsLikeEl = document.getElementById("feelsLike");
        if (feelsLikeEl) {
          feelsLikeEl.classList.add("hyperlocal-link");
          feelsLikeEl.onclick = (e) => { e.stopPropagation(); window.__navSource = {tab: "weather", card: "right_now"}; const card = document.querySelector("[data-collapse-key=\"feels_like\"]"); if (card) card.click(); };
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
        const stormFlags = [];
        if (der.pressure_alarm === "falling") stormFlags.push("Pressure falling fast");
        if (der.trough_signal === "Approaching") stormFlags.push("850mb trough approaching");
        const gustWorry = (data.wind_risk?.gust?.level ?? "");
        if (["High","Extreme"].includes(gustWorry)) stormFlags.push(`Gust wind impact: ${gustWorry}`);
        const pop0 = (data.daily?.precipitation_probability_max?.[0] ?? 0);
        if (pop0 >= 60 && der.col_precip_type && der.col_precip_type !== "Rain")
          stormFlags.push(`Precip likely — column type: ${der.col_precip_type}`);
        
        // Add rain intensity flag for moderate/heavy rain
        const dailyPrecip = (data.daily?.precipitation_sum?.[0] ?? 0);
        if (pop0 >= 60 && dailyPrecip >= 0.5)
          stormFlags.push(`Moderate/heavy rain expected (${dailyPrecip.toFixed(1)}")`);

        // Store storm flags globally and refresh alert badge
        window.__stormFlags = stormFlags;
        const badge = document.getElementById("alertBadge");
        if (badge) {
          const dot = badge.querySelector(".alert-badge-dot");
          const container = document.getElementById("alertsContainer");
          const hasAlerts = container && container.innerHTML.trim().length > 0;
          const hasStorm = stormFlags.length >= 2;
          // Badge is always visible — toggle the colored dot for active state
          if (dot) dot.style.display = (hasAlerts || hasStorm) ? "" : "none";
        }
        updatePrecipBadge(data);
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
        const _fcHourly = data.hourly || {};
        const _fcBias = (data.hyperlocal || {}).weighted_bias ?? 0;
        renderForecast(data.forecast_text, _fcHourly.times || [], _fcHourly.temperature || [], _fcBias, data.derived || {});

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
          (hourly.corrected_temperature || hourly.temperature || []).slice(startIdx, startIdx + 48),
          (hourly.precipitation_probability || []).slice(startIdx, startIdx + 48),
          (hourly.corrected_temperature || hourly.temperature || []).map((t, i) => {
            const correctedHumidity = (hourly.corrected_humidity || hourly.humidity || [])[i];
            return calculateWetBulb(t, correctedHumidity);
          }).slice(startIdx, startIdx + 48),
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
        const tempData = (hourly.corrected_temperature || hourly.temperature || []).slice(startIdx, startIdx + 48);
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
        renderFogDetail(data);
        renderFeelsLikeCard(data);
        initWindPills(data);

        const windNowEl      = document.getElementById("windNowWind");
        const windGustsEl    = document.getElementById("windGustsWind");
        const pressureNowEl  = document.getElementById("pressureNowWind");
        const pressureTrendEl= document.getElementById("pressureTrendWind");
        if (windNowEl) windNowEl.textContent =
          (cur.wind_speed != null && cur.wind_direction != null)
            ? `${Math.round(hyp.corrected_wind_speed ?? cur.wind_speed)} mph • ${toCompass(cur.wind_direction)}`
            : "--";
        if (windGustsEl)     windGustsEl.textContent     = cur.wind_gusts != null ? `${Math.round(hyp.corrected_wind_gusts ?? cur.wind_gusts)} mph` : "--";
        if (pressureNowEl)   pressureNowEl.textContent   = hyp.corrected_pressure_in != null ? hyp.corrected_pressure_in + ' inHg' : (cur.pressure != null ? fmtPressure(cur.pressure) : "--");
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
          const sustainedScore = Math.round(worryScore(hyp.corrected_wind_speed ?? cur.wind_speed, exposure));
          const sustainedLevel = worryLevel(sustainedScore);
          if (sustainedImpactEl) {
            sustainedImpactEl.innerHTML = `${sustainedScore} <span style="opacity:0.6;font-size:0.85rem;">(${sustainedLevel.label})</span>`;
          }
        } else if (sustainedImpactEl) {
          sustainedImpactEl.textContent = "N/A";
        }
        
        if (cur.wind_gusts != null && cur.wind_direction != null) {
          const exposure = getExposureFactor(cur.wind_direction);
          const gustScore = Math.round(worryScore(hyp.corrected_wind_gusts ?? cur.wind_gusts, exposure));
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
            if (seaBreeze.active) icon = "";
            else if (seaBreeze.likelihood >= 40) icon = "";
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
          window._currentForecastText = data.forecast_text;
          const _hfHourly = data.hourly || {};
          const _hfBias = (data.hyperlocal || {}).weighted_bias ?? 0;
          renderHyperlocalForecast(data.forecast_text, _hfHourly.times || [], _hfHourly.temperature || [], _hfBias, data.derived || {});
        }
        renderNWSForecast(window._nwsPeriods);

        // Almanac tab
        renderTides(data.tides?.events);
        initCollapsibleCards();
        
        // Initialize collapsed radar map when visible
        const radarPreview = document.querySelector('[data-collapse-key="radar"] .card-collapsed-preview');
        if (radarPreview) {
          // Use MutationObserver to detect when preview becomes visible
          const observer = new MutationObserver(() => {
            if (radarPreview.style.display !== 'none' && !window._collapsedRadarInitialized) {
              console.log('Radar preview is now visible, initializing...');
              setTimeout(initCollapsedRadarMap, 100);
              observer.disconnect();
            }
          });
          observer.observe(radarPreview, { attributes: true, attributeFilter: ['style'] });
          
          // Also try immediately if already visible
          if (radarPreview.style.display !== 'none') {
            setTimeout(initCollapsedRadarMap, 100);
          }
        }
        
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

        const riseDate = daily.sunrise?.[0] ? new Date(daily.sunrise[0]) : null;
        const setDate  = daily.sunset?.[0] ? new Date(daily.sunset[0]) : null;

        const rise = riseDate
          ? riseDate.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })
          : "--";
        const set = setDate
          ? setDate.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" })
          : "--";

        document.getElementById("sunrise").textContent = rise;
        document.getElementById("sunset").textContent  = set;

        // Compute daylight duration
        if (riseDate && setDate) {
          const mins = Math.round((setDate - riseDate) / 60000);
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
    } // end loadWeatherData

    loadWeatherData();

    document.addEventListener('visibilitychange', function() {
      if (document.visibilityState === 'visible') {
        if (window.__externalLinkOpen) {
          window.__externalLinkOpen = false;
          return;
        }
        // Close any open card before refreshing to avoid blank card paint bug
        document.querySelectorAll('.card-expanded').forEach(card => {
          card.classList.remove('card-expanded');
          const body = card.querySelector('.card-body');
          const preview = card.querySelector('.card-collapsed-preview');
          if (body) body.style.display = 'none';
          if (preview) preview.style.display = '';
          const bd = document.getElementById('modalBackdrop');
          if (bd) bd.remove();
        });
        loadWeatherData();
      }
    });

    document.getElementById('refreshBtn').addEventListener('click', function() {
      this.style.transform = 'rotate(360deg)';
      setTimeout(() => { this.style.transform = ''; location.reload(); }, 400);
    });// test comment


// === Bottom tab bar sync ===
(function() {
  const origShowTab = window.showTab;
  window.showTab = function(tab) {
    // Call original
    if (origShowTab) origShowTab(tab);
    // Sync bottom tab bar
    document.querySelectorAll('.bottom-tab').forEach(btn => {
      const label = btn.querySelector('.tab-label').textContent.toLowerCase();
      const isActive = label === tab;
      btn.classList.toggle('active', isActive);
      btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
    });
  };
})();

// Restore active tab after bottom tab bar sync is ready
(function() {
  try {
    const t = localStorage.getItem('activeTab') || 'briefing';
    showTab(t);
  } catch(e) { showTab('weather'); }
})();

// Restore active tab after DOM is ready
document.addEventListener('DOMContentLoaded', function() {
  try { showTab(localStorage.getItem('activeTab') || 'briefing'); } catch(e) { showTab('briefing'); }
});

// === Settings Modal ===
function openSettingsModal() {
  document.getElementById('settingsModal').style.display = 'flex';

  // Swipe-down to dismiss
  const sheet = document.querySelector('#settingsModal .modal-sheet');
  if (sheet && !sheet._swipeInit) {
    sheet._swipeInit = true;
    let startY = 0, isDragging = false;
    sheet.addEventListener('touchstart', e => {
      startY = e.touches[0].clientY;
      isDragging = true;
      sheet.style.transition = 'none';
    }, { passive: true });
    sheet.addEventListener('touchmove', e => {
      if (!isDragging) return;
      const dy = e.touches[0].clientY - startY;
      if (dy > 0) sheet.style.transform = `translateY(${dy}px)`;
    }, { passive: true });
    sheet.addEventListener('touchend', e => {
      isDragging = false;
      const dy = e.changedTouches[0].clientY - startY;
      sheet.style.transition = '';
      if (dy > 80) {
        closeSettingsModal();
      } else {
        sheet.style.transform = '';
      }
    }, { passive: true });

    // Mouse drag-to-dismiss for desktop
    sheet.addEventListener('mousedown', e => {
      startY = e.clientY;
      isDragging = true;
      sheet.style.transition = 'none';
      sheet.style.userSelect = 'none';
    });
    document.addEventListener('mousemove', e => {
      if (!isDragging) return;
      const dy = e.clientY - startY;
      if (dy > 0) sheet.style.transform = `translateY(${dy}px)`;
    });
    document.addEventListener('mouseup', e => {
      if (!isDragging) return;
      isDragging = false;
      sheet.style.transition = '';
      sheet.style.userSelect = '';
      const dy = e.clientY - startY;
      if (dy > 80) {
        closeSettingsModal();
      } else {
        sheet.style.transform = '';
      }
    });
  }
  document.body.style.overflow = 'hidden';
  // Sync data timestamps
  const du = document.getElementById('dataUpdated');
  const pl = document.getElementById('pageLoaded');
  const du2 = document.getElementById('dataUpdated2');
  const pl2 = document.getElementById('pageLoaded2');
  if (du && du2) du2.textContent = du.textContent;
  if (pl && pl2) pl2.textContent = pl.textContent;
}
function closeSettingsModal() {
  const sheet = document.querySelector('#settingsModal .modal-sheet');
  if (sheet) sheet.style.transform = '';
  document.getElementById('settingsModal').style.display = 'none';
  document.body.style.overflow = '';
}

// === Alert Modal ===
function openAlertModal() {
  const sheet = document.querySelector('#alertModal .modal-sheet');
  if (sheet && !sheet._swipeInit) {
    sheet._swipeInit = true;
    let startY = 0, isDragging = false;
    const onTouchStart = e => { startY = e.touches[0].clientY; isDragging = true; sheet.style.transition = 'none'; };
    const onTouchMove = e => { if (!isDragging) return; const dy = e.touches[0].clientY - startY; if (dy > 0) sheet.style.transform = `translateY(${dy}px)`; };
    const onTouchEnd = e => { isDragging = false; const dy = e.changedTouches[0].clientY - startY; sheet.style.transition = ''; if (dy > 80) closeAlertModal(); else sheet.style.transform = ''; };
    const onMouseDown = e => { startY = e.clientY; isDragging = true; sheet.style.transition = 'none'; sheet.style.userSelect = 'none'; };
    const onMouseMove = e => { if (!isDragging) return; const dy = e.clientY - startY; if (dy > 0) sheet.style.transform = `translateY(${dy}px)`; };
    const onMouseUp = e => { if (!isDragging) return; isDragging = false; sheet.style.transition = ''; sheet.style.userSelect = ''; const dy = e.clientY - startY; if (dy > 80) closeAlertModal(); else sheet.style.transform = ''; };
    sheet.addEventListener('touchstart', onTouchStart, { passive: true });
    sheet.addEventListener('touchmove', onTouchMove, { passive: true });
    sheet.addEventListener('touchend', onTouchEnd, { passive: true });
    sheet.addEventListener('mousedown', onMouseDown);
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }
  const container = document.getElementById('alertsContainer');
  const modalBody = document.getElementById('alertModalBody');
  if (!modalBody) return;

  const stormFlags = window.__stormFlags || [];
  const alerts = container ? container.querySelectorAll('.alert-banner') : [];

  modalBody.innerHTML = '';

  // If no alerts, show reassurance instead of refusing to open
  if (alerts.length === 0 && stormFlags.length < 2) {
    modalBody.innerHTML = `
      <div style="padding:32px 16px;text-align:center;color:var(--muted);">
        <div style="font-size:2.5rem;margin-bottom:12px;">✓</div>
        <div style="font-size:1rem;font-weight:500;margin-bottom:4px;color:var(--text-primary);">No active alerts</div>
        <div style="font-size:0.85rem;">No NWS watches, warnings, or advisories for Marblehead.</div>
      </div>`;
    document.getElementById('alertModal').style.display = 'flex';
    document.body.style.overflow = 'hidden';
    return;
  }

  // Storm flags section
  if (stormFlags.length >= 2) {
    const severity = stormFlags.length >= 3 ? 'Storm conditions developing' : 'Active weather developing';
    modalBody.innerHTML += `
      <div class="alert-modal-item" style="border-left:3px solid rgba(255,100,100,0.6);padding-left:12px;">
        <div class="alert-modal-title">${severity}</div>
        <div class="alert-modal-desc">${stormFlags.map(f => '• ' + f).join('<br>')}</div>
      </div>`;
  }

  // NWS alerts section
  alerts.forEach(alert => {
    const titleEl = alert.querySelector('.alert-title span');
    const descEl = alert.querySelector('.alert-desc');
    const title = titleEl ? titleEl.textContent : 'Weather Alert';
    const desc = descEl ? descEl.innerHTML : '';
    modalBody.innerHTML += `
      <div class="alert-modal-item">
        <div class="alert-modal-title">${title}</div>
        <div class="alert-modal-desc">${desc}</div>
      </div>`;
  });

  document.getElementById('alertModal').style.display = 'flex';
  document.body.style.overflow = 'hidden';
}
function closeAlertModal() {
  const sheet = document.querySelector('#alertModal .modal-sheet');
  if (sheet) sheet.style.transform = '';
  document.getElementById('alertModal').style.display = 'none';
  document.body.style.overflow = '';
}

// === Precip Modal ===
function openPrecipModal() {
  const sheet = document.querySelector('#precipModal .modal-sheet');
  if (sheet && !sheet._swipeInit) {
    sheet._swipeInit = true;
    let startY = 0, isDragging = false;
    const onTouchStart = e => { startY = e.touches[0].clientY; isDragging = true; sheet.style.transition = 'none'; };
    const onTouchMove = e => { if (!isDragging) return; const dy = e.touches[0].clientY - startY; if (dy > 0) sheet.style.transform = `translateY(${dy}px)`; };
    const onTouchEnd = e => { isDragging = false; const dy = e.changedTouches[0].clientY - startY; sheet.style.transition = ''; if (dy > 80) closePrecipModal(); else sheet.style.transform = ''; };
    const onMouseDown = e => { startY = e.clientY; isDragging = true; sheet.style.transition = 'none'; sheet.style.userSelect = 'none'; };
    const onMouseMove = e => { if (!isDragging) return; const dy = e.clientY - startY; if (dy > 0) sheet.style.transform = `translateY(${dy}px)`; };
    const onMouseUp = e => { if (!isDragging) return; isDragging = false; sheet.style.transition = ''; sheet.style.userSelect = ''; const dy = e.clientY - startY; if (dy > 80) closePrecipModal(); else sheet.style.transform = ''; };
    sheet.addEventListener('touchstart', onTouchStart, { passive: true });
    sheet.addEventListener('touchmove', onTouchMove, { passive: true });
    sheet.addEventListener('touchend', onTouchEnd, { passive: true });
    sheet.addEventListener('mousedown', onMouseDown);
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }

  const data = window.__lastWeatherData;
  const minutely = data?.pirate_weather?.minutely || [];
  const body = document.getElementById('precipModalBody');
  if (!body) return;

  if (minutely.length === 0) {
    body.innerHTML = '<p style="padding:16px;opacity:0.7;">No minutely data available.</p>';
    document.getElementById('precipModal').style.display = 'flex';
    document.body.style.overflow = 'hidden';
    return;
  }

  // Build summary text
  const now = Math.floor(Date.now() / 1000);

  // Staleness: how many minutes ago was this data fetched
  const dataTime = minutely[0]?.time ?? now;
  const stalenessMin = Math.round((now - dataTime) / 60);

  // First bar clock time label
  const dataDate = new Date(dataTime * 1000);
  const dataHour = dataDate.getHours();
  const dataMin = dataDate.getMinutes();
  const startLabel = `${dataHour % 12 || 12}:${String(dataMin).padStart(2,'0')}${dataHour < 12 ? 'am' : 'pm'}`;

  let firstRainIdx = -1, lastRainIdx = -1;
  let maxIntensity = 0;
  let maxProbability = 0;
  minutely.forEach((pt, i) => {
    const prob = pt.precip_probability ?? 0;
    // Require probability >= 30% — Pirate reports intensity even when probability is 0
    if (pt.precip_intensity > 0.001 && prob >= 0.3) {
      if (firstRainIdx === -1) firstRainIdx = i;
      lastRainIdx = i;
      if (pt.precip_intensity > maxIntensity) maxIntensity = pt.precip_intensity;
    }
    if (prob > maxProbability) maxProbability = prob;
  });

  // Adjust indices for staleness to get minutes-from-now
  const firstRainFromNow = firstRainIdx === -1 ? -1 : firstRainIdx - stalenessMin;
  const lastRainFromNow  = lastRainIdx  === -1 ? -1 : lastRainIdx  - stalenessMin;

  let summaryText = '';
  const maxProbPct = Math.round(maxProbability * 100);
  if (firstRainIdx === -1) {
    // Still show max probability even when no rain gate passes, so user sees what Pirate thinks
    summaryText = maxProbPct > 0
      ? `No precipitation forecast in the next hour. (Peak probability: ${maxProbPct}%)`
      : 'No precipitation in the next hour.';
  } else if (firstRainFromNow <= 0) {
    // Rain already started — NWS intensity: light <0.10, moderate 0.10-0.30, heavy >0.30 in/hr
    const endsIn = Math.max(1, lastRainFromNow + 1);
    const intensity = maxIntensity < 0.10 ? 'Light' : maxIntensity < 0.30 ? 'Moderate' : 'Heavy';
    summaryText = `${intensity} rain now — ending in ~${endsIn} min (${maxProbPct}% probability, ${maxIntensity.toFixed(2)} in/hr)`;
  } else {
    const intensity = maxIntensity < 0.10 ? 'Light' : maxIntensity < 0.30 ? 'Moderate' : 'Heavy';
    const duration = lastRainIdx - firstRainIdx + 1;
    summaryText = `${intensity} rain starting in ~${firstRainFromNow} min, lasting ~${duration} min (${maxProbPct}% probability, ${maxIntensity.toFixed(2)} in/hr)`;
  }

  // Build 60-bar chart
  // Bars with probability < 30% are shown ghosted — Pirate reports intensity
  // even when probability is 0, so without this the chart contradicts the summary.
  const maxI = Math.max(...minutely.map(p => p.precip_intensity), 0.01);
  const bars = minutely.map((pt, i) => {
    const h = Math.max(2, Math.round((pt.precip_intensity / maxI) * 60));
    const prob = pt.precip_probability ?? 0;
    const likely = prob >= 0.3;
    const baseColor = pt.precip_type === 'snow' ? '160,200,255'
                    : pt.precip_type === 'sleet' ? '200,160,255'
                    : '100,160,255';
    // Full opacity if probability gate passes; heavily muted otherwise
    const opacity = likely ? 0.85 : 0.15;
    const color = `rgba(${baseColor},${opacity})`;
    const isNow = i === 0 ? 'border-top:2px solid rgba(255,255,255,0.6);' : '';
    return `<div style="flex:1;display:flex;align-items:flex-end;height:64px;">
      <div style="width:100%;height:${h}px;background:${color};border-radius:2px 2px 0 0;${isNow}"></div>
    </div>`;
  }).join('');

  // Tick marks — first tick is actual clock time, rest are relative
  const ticks = '<div style="display:flex;justify-content:space-between;margin-top:4px;opacity:0.5;font-size:10px;">' +
    [startLabel,'15m','30m','45m','60m'].map(t => `<span>${t}</span>`).join('') + '</div>';

  body.innerHTML = `
    <div style="padding:16px 16px 8px;">
      <div style="font-size:15px;font-weight:500;margin-bottom:14px;">${summaryText}</div>
      <div style="display:flex;align-items:flex-end;gap:1px;height:64px;border-bottom:1px solid rgba(255,255,255,0.15);">
        ${bars}
      </div>
      ${ticks}
    </div>`;

  document.getElementById('precipModal').style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

function closePrecipModal() {
  const sheet = document.querySelector('#precipModal .modal-sheet');
  if (sheet) sheet.style.transform = '';
  document.getElementById('precipModal').style.display = 'none';
  document.body.style.overflow = '';
}

function updatePrecipBadge(data) {
  const badge = document.getElementById('precipBadge');
  if (!badge) return;
  const dot = badge.querySelector('.precip-badge-dot');
  const minutely = data?.pirate_weather?.minutely || [];
  // Require BOTH nonzero intensity AND probability >= 30%.
  // Pirate often reports intensity with probability=0, which means
  // "this is what it would be IF it rained" — not an actual forecast.
  const hasRain = minutely.some(pt => pt.precip_intensity > 0.001 && (pt.precip_probability ?? 0) >= 0.3);
  // Badge is always visible — toggle the colored dot to indicate active state
  if (dot) dot.style.display = hasRain ? '' : 'none';
}

// === Precip Modal ===

// === Alert Badge ===
// Patch the alert rendering to show/hide the header badge
(function() {
  const origRender = null; // We'll observe alertSummaryBar changes
  const observer = new MutationObserver(function() {
    const bar = document.getElementById('alertSummaryBar');
    const badge = document.getElementById('alertBadge');
    if (!badge) return;
    const dot = badge.querySelector('.alert-badge-dot');
    // Show badge if alertSummaryBar has been made visible OR alertsContainer has content
    const container = document.getElementById('alertsContainer');
    const hasAlerts = container && container.innerHTML.trim().length > 0;
    const hasStorm = (window.__stormFlags || []).length >= 2;
    // Badge is always visible — toggle the colored dot to indicate active state
    if (dot) dot.style.display = (hasAlerts || hasStorm) ? '' : 'none';
  });
  
  // Start observing once DOM is ready
  document.addEventListener('DOMContentLoaded', function() {
    const container = document.getElementById('alertsContainer');
    if (container) {
      observer.observe(container, { childList: true, subtree: true, characterData: true });
    }
  });
})();
