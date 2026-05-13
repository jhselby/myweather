// ======================================================
    // Utility Functions
    // ======================================================
    
    /**
     * Calculate wet bulb temperature using Stull's formula
     * @param {number} t_f - Temperature in °F
     * @param {number} rh_pct - Relative humidity in %
     * @returns {number|null} - Wet bulb temperature in °F, or null if invalid
     */


    // ======================================================
    // Menu drawer functions
    // ======================================================
    
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
      ['themeLight','themeDark','themeSystem'].forEach(id => {
        document.getElementById(id)?.classList.remove('active');
      });
      const themeMap = { light:'themeLight', dark:'themeDark', system:'themeSystem' };
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
   

    let WIND_EXPOSURE_TABLE = [
      [  0,  25, 1.00],
      [ 25,  45, 0.70],
      [ 45, 100, 0.25],
      [100, 200, 0.08],
      [200, 260, 0.10],
      [260, 290, 0.40],
      [290, 320, 0.75],
      [320, 360, 1.00],
    ];
    const WORRY_NOTICEABLE  =  5;
    const WORRY_NOTABLE     = 12;
    const WORRY_SIGNIFICANT = 20;
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


    let _selectedForecastDate = null;

    function renderForecast(forecastText, hourlyTimes, hourlyTemps, derived) {
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

    // ======================================================
    // Birds (eBird recent sightings, 5km radius, 2 days back)
    // Collapsed: top notable species, else species count
    // Expanded: grouped by location, most recent first, all collapsed
    // ======================================================
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

    // ======================================================
    // Sun (SunCalc)
    // ======================================================

    // Radar — NOAA NEXRAD via IEM WMS
    // 5-minute archive interval (vs RainViewer's 10-minute)
    // WMS endpoint: https://mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0r-t.cgi
    // Layer: nexrad-n0r-wmst (time-enabled NEXRAD base reflectivity composite)
    // Time format: YYYY-MM-DDTHH:MM:00Z
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

    function renderHyperlocalForecast(forecasts, hourlyTimes, hourlyTemps, derived) {
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
      // Inject wind impact score into briefing Wind row
      const hyp = data.hyperlocal || {};
      const cur = data.current || {};
      const sc = document.getElementById('briefConditions');
      const scl = document.getElementById('briefConditionsLabel');
      if (sc) {
        const raw = cur.weather_description || cur.condition_override || '--';
        // Override with Pirate Weather radar if it shows current precip and HRRR doesn't
        let displayCondition = raw;
        if (!/rain|snow|drizzle|sleet|shower/i.test(raw)) {
          const mn = window.__precipMinutely || [];
          if (mn.length) {
            const mnNow = Math.floor(Date.now() / 1000);
            const mnStale = Math.round((mnNow - (mn[0]?.time ?? mnNow)) / 60);
            const mnCur = mn[Math.min(mnStale, mn.length - 1)];
            if (mnCur && mnCur.precip_intensity > 0.001 && (mnCur.precip_probability ?? 0) >= 0.3) {
              const ci = mnCur.precip_intensity;
              const ct = mnCur.precip_type || 'rain';
              if (ct === 'snow') displayCondition = ci < 0.10 ? 'Light Snow' : ci < 0.30 ? 'Snow' : 'Heavy Snow';
              else if (ct === 'sleet') displayCondition = 'Sleet';
              else displayCondition = ci < 0.01 ? 'Drizzle' : ci < 0.10 ? 'Light Rain' : ci < 0.30 ? 'Moderate Rain' : 'Heavy Rain';
            }
          }
        }
        const parts = displayCondition.split(/,\s*|(?<=\S)\s+and\s+/i);
        sc.textContent = parts[0];
        if (scl) scl.textContent = parts[1] ? parts[1].toLowerCase() : 'sky';
        const fitSizes = ['2.4rem','2.0rem','1.7rem','1.4rem','1.15rem','0.95rem','0.82rem'];
        const maxW = sc.parentElement ? sc.parentElement.offsetWidth - 8 : 999;
        sc.style.fontSize = fitSizes[0];
        for (const s of fitSizes) {
          sc.style.fontSize = s;
          if (sc.scrollWidth <= maxW) break;
        }
      }
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
      const almanacEl = document.getElementById('briefAlmanacSection');
      if (almanacEl) { if (b.almanacRows && b.almanacRows.length) { let ah = '<hr class="brief-rule"><div class="brief-section-label">Almanac</div><div class="brief-rows">'; b.almanacRows.forEach(r => { const cls = r.color ? cm[r.color] || '' : ''; ah += '<div class="brief-row"><span class="brief-row-label">' + r.label + '</span><span class="brief-row-value ' + cls + '">' + r.value + '</span></div>'; }); ah += '</div>'; almanacEl.innerHTML = ah; } else { almanacEl.innerHTML = ''; } }
      const lifeEl = document.getElementById('briefLifestyleSection');
      if (lifeEl) { if (b.lifestyleRows && b.lifestyleRows.length) { let lh = '<hr class="brief-rule"><div class="brief-section-label">Lifestyle</div><div class="brief-rows">'; b.lifestyleRows.forEach(r => { const cls = r.color ? cm[r.color] || '' : ''; lh += '<div class="brief-row"><span class="brief-row-label">' + r.label + '</span><span class="brief-row-value ' + cls + '">' + r.value + '</span></div>'; }); lh += '</div>'; lifeEl.innerHTML = lh; } else { lifeEl.innerHTML = ''; } }
      const watchEl = document.getElementById('briefWatchSection');
      const hasWatchContent = b.watchRows && b.watchRows.length > 0;

      if (watchEl) { if (b.watchRows && b.watchRows.length) { let wh = '<div class="brief-section-label">Watch for</div>'; b.watchRows.forEach(r => { if (r.isHtml) { wh += r.html; } else if (r.isAlert) { wh += '<div class="brief-alert-row" onclick="openAlertModal()" style="cursor:pointer;">⚠ <strong>' + r.value + '</strong>' + (r.detail ? '<div style="font-size:0.78rem;margin-top:3px;opacity:0.72;">' + r.detail + '</div>' : '') + '</div>'; } else { const cls = r.color ? cm[r.color] || '' : ''; wh += '<div class="brief-row"><span class="brief-row-label">' + r.label + '</span><span class="brief-row-value ' + cls + '">' + r.value + '</span></div>'; } }); wh += '<hr class="brief-rule" style="margin-top:14px;">'; watchEl.innerHTML = wh; } else { watchEl.innerHTML = ''; } }
      const tonightEl = document.getElementById('briefTonightSection');
      if (tonightEl) {
        if (b.tonight) {
          const ft = data.forecast_text || [];
          const tonightFc = ft.find(p => p.period_name === 'Tonight');
          let th = '<hr class="brief-rule"><div class="brief-section-label">Tonight</div>';
          th += '<div class="brief-row"><span class="brief-row-label">Overnight</span><span class="brief-row-value">' + b.tonight + '</span></div>';
          if (tonightFc && tonightFc.text) {
            th += '<div style="font-size:0.88rem;opacity:0.7;padding:6px 0 2px;line-height:1.5;">' + tonightFc.text + '</div>';
          }
          tonightEl.innerHTML = th;
        } else { tonightEl.innerHTML = ''; }
      }

      // Cross-card navigation from briefing rows
      var navMap = {
        'Sky': { tab: 'weather', card: '48h_temp_precip' },
        'Wind': { tab: 'weather', card: '48h_wind' },
        'Sea breeze': { tab: 'weather', card: 'sea_breeze_detail' },
        'Fog': { tab: 'weather', card: 'fog_risk' },
        'Rain': { tab: 'weather', card: '48h_temp_precip' },
        'Next rain': { tab: 'weather', card: '48h_temp_precip' },
        'Wind chill': { tab: 'weather', card: 'feels_like' },
        'Heat index': { tab: 'weather', card: 'feels_like' },
        'Sun': { tab: 'almanac', card: 'sun' },
        'Tide': { tab: 'almanac', card: 'tides' },
        'Moon': { tab: 'almanac', card: 'moon' },
        'Sunset': { tab: 'hyperlocal', card: 'sunset_quality' },
        'Beach day': { tab: 'hyperlocal', card: 'swim_float' },
        'Hair day': { tab: 'hyperlocal', card: 'hair_day' },
        'Birds': { tab: 'hyperlocal', card: 'birds' },
      };
      var allBriefRows = document.querySelectorAll('#briefTodayRows .brief-row, #briefAlmanacSection .brief-row, #briefLifestyleSection .brief-row, #briefWatchSection .brief-row');
      allBriefRows.forEach(function(row) {
        var labelEl = row.querySelector('.brief-row-label');
        if (!labelEl) return;
        var label = labelEl.textContent.trim().replace(/ \(tomorrow\)/, '');
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

    
    // Return to source tab on PWA resume after any cross-tab clickthrough
    document.addEventListener('visibilitychange', function() {
      if (!document.hidden && window.__navSource) {
        var src = window.__navSource;
        window.__navSource = null;
        showTab(src.tab);
      }
    });

    // Overhead card: reparent overheadView content into card on first expand
    document.addEventListener('click', function(e) {
      var card = e.target.closest('[data-collapse-key="overhead_card"]');
      if (card && window.__overheadMoved !== true) {
        window.__overheadMoved = true;
        function reparentAndInit() {
          var src = document.querySelector('#overheadView > .card');
          var dest = document.getElementById('overheadCardBody');
          if (src && dest) {
            dest.appendChild(src);
            setTimeout(function() { if (typeof ohInitMap === 'function') ohInitMap(); setTimeout(function() { if (typeof ohFetch === 'function') ohFetch(); else if (typeof ohRefresh === 'function') ohRefresh(); }, 500); }, 300);
          }
        }
        if (typeof ohInitMap === 'function') {
          reparentAndInit();
        } else {
          var s = document.createElement('script');
          s.src = 'js/overhead.js?v=83b33af2';
          s.onload = reparentAndInit;
          document.body.appendChild(s);
        }
      }
    });

function loadWeatherData() {
    fetch("https://storage.googleapis.com/myweather-data/weather_data.json?t=" + Date.now())
      .then(r => { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
      .then(data => {
        window.__lastWeatherData = data;

        // Use exposure table from data if available (single source of truth with collector)
        if (Array.isArray(data.wind_exposure_table) && data.wind_exposure_table.length > 0) {
          WIND_EXPOSURE_TABLE = data.wind_exposure_table;
        }

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
        var _duEl = document.getElementById("dataUpdated2"); if (_duEl) _duEl.textContent = fmtLocal(data.generated_at || data.location?.updated);
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
        let desc  = cur.weather_description || cur.condition_override || weatherDesc[code] || "—";
        if (!/rain|snow|drizzle|sleet|shower/i.test(desc)) {
          const mn2 = window.__precipMinutely || [];
          if (mn2.length) {
            const mn2Now = Math.floor(Date.now() / 1000);
            const mn2Stale = Math.round((mn2Now - (mn2[0]?.time ?? mn2Now)) / 60);
            const mn2Cur = mn2[Math.min(mn2Stale, mn2.length - 1)];
            if (mn2Cur && mn2Cur.precip_intensity > 0.001 && (mn2Cur.precip_probability ?? 0) >= 0.3) {
              const ci2 = mn2Cur.precip_intensity, ct2 = mn2Cur.precip_type || 'rain';
              if (ct2 === 'snow') desc = ci2 < 0.10 ? 'Light Snow' : ci2 < 0.30 ? 'Snow' : 'Heavy Snow';
              else if (ct2 === 'sleet') desc = 'Sleet';
              else desc = ci2 < 0.01 ? 'Drizzle' : ci2 < 0.10 ? 'Light Rain' : ci2 < 0.30 ? 'Moderate Rain' : 'Heavy Rain';
            }
          }
        }
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
        
        // Bias confidence indicator
        const confEl = document.getElementById("tempConfidence");
        if (confEl) {
          const conf = hyp.confidence;
          const bias = hyp.weighted_bias;
          if ((conf === "Low" || conf === "Moderate") && bias != null) {
            const sign = bias >= 0 ? "+" : "";
            confEl.textContent = `· ${sign}${bias.toFixed(1)}° correction${conf === "Low" ? " — stations disagree" : ""}`;
            confEl.style.color = conf === "Low" ? "rgba(239,68,68,0.85)" : "rgba(234,179,8,0.85)";
            confEl.style.display = "";
          } else {
            confEl.style.display = "none";
          }
        }

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
        const condEl2 = document.getElementById("condition");
        condEl2.innerHTML = `${emoji} ${desc}${obsTag}`;
        condEl2.dataset.emoji = emoji;
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

        renderCorrectionsCard(data);
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
          const windDirStr = windDir != null ? toCompass(windDir, false) : "";
          
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
        
        renderWindTile(data);
        renderWindImpactCollapsed(data);
        
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

        // Beach Day Score - read from renderDockDay()
        const dockDayScoreEl = document.getElementById("swimFloatScoreNow");
        if (dockDayScoreEl && window.__todayDockScore) {
          const dockAfter6 = new Date().getHours() >= 18; const d = (dockAfter6 && window.__tomorrowDockScore) ? window.__tomorrowDockScore : window.__todayDockScore;
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
          dockDayScoreEl.onclick = (e) => { e.stopPropagation(); window.__navSource = {tab: 'weather', card: 'right_now'}; showTab('hyperlocal'); setTimeout(() => { const card = document.querySelector('[data-collapse-key="swim_float"]'); if (card) card.click(); }, 100); };
        }

        // Hair Day Score
        const hairDayNowEl = document.getElementById("hairDayNow");
        if (hairDayNowEl && window.__todayHairScore) {
          const hairAfter6 = new Date().getHours() >= 18; const h = (hairAfter6 && window.__tomorrowHairScore) ? window.__tomorrowHairScore : window.__todayHairScore;
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
        if (der.pressure_alarm === "falling") stormFlags.push("Pressure dropping");
        if (der.trough_signal === "Approaching") stormFlags.push("Weather system approaching");
        const gustWorry = (data.wind_risk?.gust?.level ?? "");
        if (["High","Extreme"].includes(gustWorry)) stormFlags.push(`${gustWorry} wind gusts expected`);
        const pop0 = (data.daily?.precipitation_probability_max?.[0] ?? 0);
        if (pop0 >= 60 && der.surface_precip_type && der.surface_precip_type !== "rain") {
          const typeMap = { snow: "Snow", "freezing rain": "Freezing rain", sleet: "Sleet", mixed: "Mixed precip" };
          const surfLabel = typeMap[der.surface_precip_type] || der.surface_precip_type;
          stormFlags.push(`${surfLabel} likely`);
        }

        const dailyPrecip = (data.daily?.precipitation_sum?.[0] ?? 0);
        if (pop0 >= 60 && dailyPrecip >= 0.5)
          stormFlags.push(`Heavy rain expected — ${dailyPrecip.toFixed(1)}"`);

        const tempestStations = data.tempest?.stations || [];
        const lightningCount1hr = tempestStations.reduce((sum, st) => sum + (st.lightning_count_1hr || 0), 0);
        const lightningDists = tempestStations.map(st => st.lightning_last_distance_km).filter(d => d != null && d > 0);
        const lightningMinDist = lightningDists.length > 0 ? Math.min(...lightningDists) : null;
        const lightningActive = lightningCount1hr >= 3 || (lightningCount1hr >= 1 && lightningMinDist != null && lightningMinDist <= 20);
        if (lightningActive) {
          stormFlags.push(`Lightning detected — ${lightningCount1hr} strike${lightningCount1hr !== 1 ? "s" : ""} in past hour`);
        }
        window.__lightningStrike = lightningActive ? { count: lightningCount1hr, distKm: lightningMinDist } : null;

        // Store storm flags globally and refresh alert badge
        window.__stormFlags = stormFlags;
        renderBriefing(data); // Re-render now that storm flags are available
        const badge = document.getElementById("alertBadge");
        if (badge) {
          const dot = badge.querySelector(".alert-badge-dot");
          const container = document.getElementById("alertsContainer");
          const hasAlerts = container && container.innerHTML.trim().length > 0;
          const hasStorm = stormFlags.length >= 2;
          // Badge is always visible — toggle the colored dot for active state
          if (dot) dot.style.display = (hasAlerts || hasStorm || !!window.__lightningStrike) ? "" : "none";
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
        renderForecast(data.forecast_text, _fcHourly.times || [], _fcHourly.corrected_temperature || _fcHourly.temperature || [], data.derived || {});

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
          (hourly.corrected_wet_bulb || hourly.wet_bulb || []).slice(startIdx, startIdx + 48),
          (hourly.temperature_850hPa || []).slice(startIdx, startIdx + 48),
          (hourly.cloud_cover_low || []).slice(startIdx, startIdx + 48),
          (hourly.cloud_cover_mid || []).slice(startIdx, startIdx + 48),
          (hourly.cloud_cover_high || []).slice(startIdx, startIdx + 48),
          (hourly.cloud_cover || []).slice(startIdx, startIdx + 48),
          srHour,
          ssHour
        );

        renderWindChart(data);

        // Initialize temp/precip data bar with hour 0 data
        const tempData = (hourly.corrected_temperature || hourly.temperature || []).slice(startIdx, startIdx + 48);
        const popData = (hourly.precipitation_probability || []).slice(startIdx, startIdx + 48);
        const wbData = (hourly.corrected_wet_bulb || hourly.wet_bulb || []).slice(startIdx, startIdx + 48);
        const t850Data = (hourly.temperature_850hPa || []).slice(startIdx, startIdx + 48);
        const cloudLowData = (hourly.cloud_cover_low || []).slice(startIdx, startIdx + 48);
        const cloudMidData = (hourly.cloud_cover_mid || []).slice(startIdx, startIdx + 48);
        const cloudHighData = (hourly.cloud_cover_high || []).slice(startIdx, startIdx + 48);
        const cloudTotalData = (hourly.cloud_cover || []).slice(startIdx, startIdx + 48);

        updateTempPrecipDataBar(0, times, tempData, popData, wbData, t850Data, cloudLowData, cloudMidData, cloudHighData, cloudTotalData);

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


        // Hyperlocal forecast
        if (data.forecast_text) {
          window._currentForecastText = data.forecast_text;
          const _hfHourly = data.hourly || {};
          renderHyperlocalForecast(data.forecast_text, _hfHourly.times || [], _hfHourly.corrected_temperature || _hfHourly.temperature || [], data.derived || {});
        }

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

        const waterTempF = data.salem_water_temp_f ?? buoy.water_temp_f;
        setEl("buoyWaterTemp", waterTempF != null ? waterTempF.toFixed(1) + "°F" : "--");
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
        console.error("Weather fetch failed:", err); document.getElementById("condition").textContent = "Data unavailable";
        // // document.getElementById("location").textContent = "Error loading weather_data.json";
      });
    } // end loadWeatherData

    loadWeatherData();

    // Version update detection — light up refresh button if a new deploy is available
    // setTimeout(0) defers until after the full DOM is parsed (appVersion element exists)
    function checkForUpdate() {
      const loadedVersion = document.getElementById('appVersion')?.textContent?.trim();
      if (!loadedVersion) return;
      fetch('version.json?_=' + Date.now())
        .then(r => r.json())
        .then(d => {
          const dot = document.getElementById('refreshAlertDot');
          if (dot) dot.style.display = (d.version && d.version !== loadedVersion) ? 'block' : 'none';
        })
        .catch(() => {});
    }
    setTimeout(checkForUpdate, 0);
    setInterval(checkForUpdate, 5 * 60 * 1000);

    // Track when user leaves the app for briefing-on-return logic
    document.addEventListener('visibilitychange', function() {
      if (document.hidden) {
        window.__lastHiddenAt = Date.now();
      }
    });

    // refreshOnReturn: fires on tab-switch (visibilitychange) AND app-switch (window focus).
    // Debounced so both events triggering together only cause one reload.
    let __lastRefresh = 0;
    function refreshOnReturn() {
      const now = Date.now();
      if (now - __lastRefresh < 2000) return;
      __lastRefresh = now;

      if (window.__externalLinkOpen) {
        window.__externalLinkOpen = false;
        return;
      }
      // Return to briefing tab if away for 5+ minutes
      if (window.__lastHiddenAt && (now - window.__lastHiddenAt) > 5 * 60 * 1000) {
        showTab('briefing');
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

    document.addEventListener('visibilitychange', function() {
      if (document.visibilityState === 'visible') refreshOnReturn();
    });
    window.addEventListener('focus', refreshOnReturn);

    document.getElementById('refreshBtn').addEventListener('click', function() {
      this.style.transform = 'rotate(360deg)';
      const updatePending = document.getElementById('refreshAlertDot')?.style.display !== 'none';
      setTimeout(() => {
        this.style.transform = '';
        if (updatePending) {
          window.location.href = window.location.pathname + '?_=' + Date.now();
        } else {
          location.reload();
        }
      }, 400);
    });


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
  // Always start on briefing — it's the landing page for fresh opens
  var _plEl = document.getElementById("pageLoaded2"); if (_plEl) _plEl.textContent = new Date().toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  try { showTab('briefing'); } catch(e) { showTab('briefing'); }
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
}
function closeSettingsModal() {
  const sheet = document.querySelector('#settingsModal .modal-sheet');
  if (sheet) sheet.style.transform = '';
  // Collapse all subsections and scroll to top
  ['sourcesBody','nerdStuffBody','changelogBody','howItWorksBody','dataPipelineBody','licensesBody'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });
  if (sheet) sheet.scrollTop = 0;
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

  const lightningStrike = window.__lightningStrike;

  // If no alerts, show reassurance instead of refusing to open
  if (alerts.length === 0 && stormFlags.length < 2 && !lightningStrike) {
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

  // Standalone lightning section (when not already folded into storm flags block)
  if (lightningStrike && stormFlags.length < 2) {
    const distStr = lightningStrike.distKm != null ? ` · closest ${Math.round(lightningStrike.distKm)} km` : "";
    const isClose = lightningStrike.distKm != null && lightningStrike.distKm <= 20;
    modalBody.innerHTML += `
      <div class="alert-modal-item" style="border-left:3px solid ${isClose ? 'rgba(255,80,80,0.7)' : 'rgba(255,160,50,0.7)'};padding-left:12px;">
        <div class="alert-modal-title">⚡ Lightning detected</div>
        <div class="alert-modal-desc">${lightningStrike.count} strike${lightningStrike.count !== 1 ? "s" : ""} in the past hour${distStr}</div>
      </div>`;
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
  const hasRain = minutely.some(pt => pt.precip_intensity > 0 && (pt.precip_probability ?? 0) >= 0.3);
  // Badge is always visible — toggle the colored dot to indicate active state
  if (dot) dot.style.display = hasRain ? '' : 'none';
  window.__precipHasRain = hasRain;
  window.__precipMinutely = minutely;
  if (hasRain && window.__lastWeatherData) {
    renderBriefing(window.__lastWeatherData);
    // Also patch Sky & Precip card — it rendered before minutely arrived
    const condEl = document.getElementById('condition');
    if (condEl && !/rain|snow|drizzle|sleet|shower/i.test(condEl.textContent)) {
      const stale = Math.round((Date.now()/1000 - (minutely[0]?.time ?? Date.now()/1000)) / 60);
      const pt = minutely[Math.min(stale, minutely.length - 1)];
      if (pt && pt.precip_intensity > 0.001 && (pt.precip_probability ?? 0) >= 0.3) {
        const ci = pt.precip_intensity, ct = pt.precip_type || 'rain';
        let pwDesc;
        if (ct === 'snow') pwDesc = ci < 0.10 ? 'Light Snow' : ci < 0.30 ? 'Snow' : 'Heavy Snow';
        else if (ct === 'sleet') pwDesc = 'Sleet';
        else pwDesc = ci < 0.01 ? 'Drizzle' : ci < 0.10 ? 'Light Rain' : ci < 0.30 ? 'Moderate Rain' : 'Heavy Rain';
        condEl.innerHTML = `${condEl.dataset.emoji || ''} ${pwDesc}`;
        const skyColEl = document.getElementById('skyConditionCollapsed');
        if (skyColEl) skyColEl.textContent = pwDesc;
      }
    }
  }
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
// cache bust
