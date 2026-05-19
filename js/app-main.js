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
    const _tabScrollPos = {};
    function showTab(which) {
      const tabOrder = ['briefing', 'weather', 'hyperlocal', 'almanac'];
      const views = { briefing: "briefingView", weather: "weatherView", almanac: "almanacView", overhead: "overheadView", hyperlocal: "hyperlocalView" };

      // Determine slide direction before updating localStorage
      const current = localStorage.getItem('activeTab') || 'briefing';
      const fromIdx = tabOrder.indexOf(current);
      const toIdx = tabOrder.indexOf(which);

      // Save scroll position of the tab being left
      if (current !== which) _tabScrollPos[current] = window.scrollY;

      Object.keys(views).forEach(k => {
        const v = document.getElementById(views[k]);
        if (v) v.style.display = (k === which) ? "" : "none";
      });

      // Apply directional slide to incoming view
      if (fromIdx !== -1 && toIdx !== -1 && fromIdx !== toIdx) {
        const v = document.getElementById(views[which]);
        if (v) {
          const cls = toIdx > fromIdx ? 'slide-in-right' : 'slide-in-left';
          v.classList.remove('slide-in-left', 'slide-in-right');
          void v.offsetWidth;
          v.classList.add(cls);
        }
      }

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

      // Restore scroll position when switching tabs (not on initial same-tab load)
      if (fromIdx !== toIdx) {
        const savedScroll = _tabScrollPos[which] ?? 0;
        window.scrollTo({ top: savedScroll, behavior: "instant" });
      }
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
        } else if (dx > 0 && idx > 0) {
          showTab(tabOrder[idx - 1]);
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
    // Main Data Load
    // ═══════════════════════════════════════════════════════════════


    
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

        // If the data schema is newer than this JS knows about, stop rendering and ask for a refresh
        const EXPECTED_SCHEMA = "1.2";
        if (data.schema_version && data.schema_version !== EXPECTED_SCHEMA) {
          const el = document.getElementById("dataUpdated2");
          if (el) el.textContent = "App update required — tap refresh";
          const btn = document.getElementById("refreshBtn");
          if (btn) btn.classList.add("has-update");
          return;
        }

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

        // Feels like: shade AT as primary, full-sun AT as secondary badge
        const fullSunFL = der.corrected_feels_like ?? null;
        let _shadeAT = der.heat_index ?? null;
        if (_shadeAT == null) {
          const _T = data.hyperlocal?.corrected_temp ?? cur.temperature;
          const _w = (data.hyperlocal?.corrected_wind_speed ?? cur.wind_speed ?? 0) * 0.44704;
          const _rh = data.hyperlocal?.corrected_humidity ?? cur.humidity ?? 50;
          if (_T != null) {
            const _Tc = (_T - 32) * 5 / 9;
            const _e = (_rh / 100) * 6.105 * Math.exp(17.27 * _Tc / (237.7 + _Tc));
            _shadeAT = Math.round((_Tc + 0.33 * _e - 0.70 * _w - 4.00) * 9 / 5 + 32);
          }
        }
        const heatIndex = _shadeAT ?? cur.apparent_temperature ?? 0;

        document.getElementById("feelsLike").textContent =
          `Feels like ${Math.round(heatIndex)}°F`;
        const flc = document.getElementById("feelsLikeCollapsed"); if (flc) flc.textContent = `Feels like ${Math.round(heatIndex)}°`;
        const fsEl = document.getElementById("feelsLikeFullSun");
        if (fsEl) {
          if (fullSunFL != null && fullSunFL > heatIndex + 5) {
            fsEl.textContent = `☀ Full sun: ${Math.round(fullSunFL)}°F`;
            fsEl.style.display = "";
          } else {
            fsEl.style.display = "none";
          }
        }
        
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
        const lightningCount1hr = Math.max(0, ...tempestStations.map(st => st.lightning_count_1hr || 0));
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
        try { localStorage.setItem('lastWeatherData', JSON.stringify(data)); } catch(e) {}
      })
      .catch(err => {
        console.error("Weather fetch failed:", err); document.getElementById("condition").textContent = "Data unavailable";
        // // document.getElementById("location").textContent = "Error loading weather_data.json";
      });
    } // end loadWeatherData

    // Stale-while-revalidate: render last cached data immediately so the page
    // isn't blank while the network fetch is in flight.
    (function() {
      try {
        const _raw = localStorage.getItem('lastWeatherData');
        if (!_raw) return;
        const _d = JSON.parse(_raw);
        if (!_d || _d.schema_version !== '1.2') return;
        window.__lastWeatherData = _d;
        renderFrostTracker(_d.frost_log);
        renderBirds(_d.birds);
        renderSunsetQuality(_d);
        renderDockDay(_d);
        renderHairDay(_d);
        renderBriefing(_d);
        renderCorrectionsCard(_d);
        populateCollapsedPreviews(_d);
        const _duEl = document.getElementById('dataUpdated2');
        if (_duEl) {
          const _dt = _d.generated_at || _d.location?.updated;
          if (_dt) {
            const _d2 = new Date(_dt);
            if (!isNaN(_d2.getTime())) _duEl.textContent = _d2.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
          }
        }
      } catch(e) {}
    })();

    loadWeatherData();

    // Version update detection — light up refresh button if a new deploy is available
    // setTimeout(0) defers until after the full DOM is parsed (appVersion element exists)
    function checkForUpdate() {
      // If we just reloaded due to an update, suppress the check for 30s — GitHub Pages CDN
      // ignores query params for HTML, so the old index.html may still be served for a bit.
      const justUpdated = sessionStorage.getItem('_updateReload');
      if (justUpdated && Date.now() - parseInt(justUpdated) < 30000) return;
      sessionStorage.removeItem('_updateReload');
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
          sessionStorage.setItem('_updateReload', Date.now());
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
      const isActive = (btn.dataset.tab || btn.querySelector('.tab-label').textContent.toLowerCase()) === tab;
      const wasActive = btn.classList.contains('active');
      btn.classList.toggle('active', isActive);
      btn.setAttribute('aria-selected', isActive ? 'true' : 'false');
      if (isActive && !wasActive) {
        btn.classList.remove('tab-pop');
        void btn.offsetWidth;
        btn.classList.add('tab-pop');
        btn.addEventListener('animationend', () => btn.classList.remove('tab-pop'), { once: true });
      }
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

// Move notice — show once only to users referred from old GitHub Pages URL
(function() {
  try {
    if (!localStorage.getItem('moveNotice2025') && document.referrer.includes('jhselby.github.io')) {
      const el = document.getElementById('moveNoticeBanner');
      if (el) el.style.display = '';
      if (window.goatcounter) goatcounter.count({ path: '/event/move-notice-shown', title: 'Move Notice Shown', event: true });
    }
  } catch(e) {}
})();

// Set page-loaded timestamp
document.addEventListener('DOMContentLoaded', function() {
  window._pageLoadTime = new Date();
});


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
    // Briefing tab alert dot
    const tabDot = document.getElementById('briefingTabAlertDot');
    if (tabDot) tabDot.style.display = (hasAlerts || hasStorm) ? '' : 'none';
  });
  
  // Start observing once DOM is ready
  document.addEventListener('DOMContentLoaded', function() {
    const container = document.getElementById('alertsContainer');
    if (container) {
      observer.observe(container, { childList: true, subtree: true, characterData: true });
    }
  });
})();

// Pull-to-refresh
(function initPullToRefresh() {
  const THRESHOLD = 72;
  let startY = 0;
  let pulling = false;
  let indicator = null;

  function getIndicator() {
    if (!indicator) {
      const headerBottom = (document.querySelector('header') || {getBoundingClientRect: () => ({bottom: 110})}).getBoundingClientRect().bottom;
      indicator = document.createElement('div');
      indicator.id = 'ptrIndicator';
      indicator.style.top = (headerBottom + 12) + 'px';
      indicator.innerHTML = '<div class="ptr-arc"></div>';
      document.body.appendChild(indicator);
    }
    return indicator;
  }

  function removeIndicator() {
    if (indicator) {
      indicator.style.transition = 'transform 0.25s ease, opacity 0.25s ease';
      indicator.style.opacity = '0';
      indicator.style.transform = 'translateX(-50%) translateY(-48px)';
      setTimeout(() => { indicator && indicator.remove(); indicator = null; }, 260);
    }
  }

  document.addEventListener('touchstart', function(e) {
    if (window.scrollY === 0 && !document.querySelector('.card-expanded')) {
      startY = e.touches[0].clientY;
      pulling = true;
    }
  }, { passive: true });

  document.addEventListener('touchmove', function(e) {
    if (!pulling) return;
    const dy = e.touches[0].clientY - startY;
    if (dy <= 0) { pulling = false; removeIndicator(); return; }
    const ind = getIndicator();
    const progress = Math.min(dy / THRESHOLD, 1);
    ind.style.transition = 'none';
    ind.style.opacity = String(Math.min(progress * 2, 1));
    ind.style.transform = `translateX(-50%) translateY(${-48 + progress * 48}px)`;
    const arc = ind.querySelector('.ptr-arc');
    if (arc && !ind.classList.contains('ptr-loading')) arc.style.transform = `rotate(${progress * 270}deg)`;
    ind.classList.toggle('ptr-ready', dy >= THRESHOLD);
  }, { passive: true });

  document.addEventListener('touchend', function(e) {
    if (!pulling) return;
    pulling = false;
    const dy = e.changedTouches[0].clientY - startY;
    if (dy >= THRESHOLD && indicator) {
      indicator.classList.remove('ptr-ready');
      indicator.classList.add('ptr-loading');
      indicator.style.transition = 'none';
      indicator.style.transform = 'translateX(-50%) translateY(0px)';
      setTimeout(() => { removeIndicator(); location.reload(); }, 400);
    } else {
      removeIndicator();
    }
  }, { passive: true });
})();

// cache bust
