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
    function fmtRelAge(dt) {
      if (!dt) return "--";
      const d = new Date(dt);
      if (isNaN(d.getTime())) return "--";
      const mins = Math.round((Date.now() - d.getTime()) / 60000);
      if (mins < 1)  return "just now";
      if (mins < 60) return mins + "m ago";
      return Math.round(mins / 60) + "h ago";
    }
    window.fmtRelAge = fmtRelAge;

    // Single canonical compass function — replaces both old degreesToCompass and degToCompass
    function toCompass(deg, withDeg = true) {
      if (deg == null || isNaN(deg)) return "--";
      const d = ((deg % 360) + 360) % 360;
      const dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];
      const label = dirs[Math.round(d / 22.5) % 16];
      return withDeg ? `${Math.round(d)}° ${label}` : label;
    }

    // Tear down the modal state of the currently-expanded card without firing
    // toggleCard's "return to source" logic. Used when one expanded card
    // navigates to another — we want to dismiss the source cleanly so the
    // outsideHandler doesn't eat the synthetic click on the target.
    function _dismissExpandedCard(card) {
      if (!card || !card.classList.contains('card-expanded')) return;
      const body = card.querySelector('.card-body');
      const preview = card.querySelector('.card-collapsed-preview');
      const chev = card.querySelector('.collapse-chevron');
      if (body) body.style.display = 'none';
      if (preview) preview.style.display = '';
      if (chev) { chev.style.display = ''; chev.style.transform = 'rotate(-90deg)'; }
      card.classList.remove('card-expanded');
      const bd = document.getElementById('modalBackdrop');
      if (bd) bd.remove();
      document.body.classList.remove('card-modal-open');
      if (window.__cardOutsideHandler) {
        document.removeEventListener('touchstart', window.__cardOutsideHandler, true);
        document.removeEventListener('click', window.__cardOutsideHandler, true);
        window.__cardOutsideHandler = null;
      }
    }

    // Wire a "Right Now" tile field to expand its detail card on tap.
    // If the source card is currently expanded, dismisses it first so the
    // outsideHandler doesn't eat the synthetic click on the target.
    // __navSource is set AFTER the dismiss so it only fires when the user
    // closes the target (returning them to the source).
    function wireHyperlocalLink(el, cardKey, targetTab) {
      if (!el) return;
      el.classList.add('hyperlocal-link');
      el.onclick = (e) => {
        e.stopPropagation();
        _dismissExpandedCard(el.closest('.card-expanded'));
        window.__navSource = { tab: 'weather', card: 'right_now' };
        const openCard = () => {
          const card = document.querySelector(`[data-collapse-key="${cardKey}"]`);
          if (card) card.click();
        };
        if (targetTab) {
          showTab(targetTab);
          setTimeout(openCard, 100);
        } else {
          openCard();
        }
      };
    }

    // Dim suffix span used after the primary value in many card displays.
    function dim(text) {
      return `<span style="opacity:0.6;font-size:0.85rem;">${text}</span>`;
    }

    // ======================================================
    // Right Now weather-art SVG dispatch
    // ======================================================
    // Inline SVG inner-markup for the Right Now art, keyed by `${type}_${day|night}`.
    const WEATHER_GRAPHICS = {
      clear_day: `
                <circle cx="75" cy="25" r="18" fill="rgba(255,200,80,0.8)"/>
                <line x1="75" y1="3" x2="75" y2="10" stroke="rgba(255,200,80,0.7)" stroke-width="2" stroke-linecap="round"/>
                <line x1="93" y1="25" x2="100" y2="25" stroke="rgba(255,200,80,0.7)" stroke-width="2" stroke-linecap="round"/>
                <line x1="86" y1="36" x2="91" y2="41" stroke="rgba(255,200,80,0.7)" stroke-width="2" stroke-linecap="round"/>
                <line x1="86" y1="14" x2="91" y2="9" stroke="rgba(255,200,80,0.7)" stroke-width="2" stroke-linecap="round"/>
                <line x1="64" y1="36" x2="59" y2="41" stroke="rgba(255,200,80,0.7)" stroke-width="2" stroke-linecap="round"/>
                <line x1="64" y1="14" x2="59" y2="9" stroke="rgba(255,200,80,0.7)" stroke-width="2" stroke-linecap="round"/>
              `,
      clear_night: `
                <circle cx="75" cy="25" r="16" fill="rgba(245,245,220,0.8)"/>
                <circle cx="80" cy="20" r="16" fill="rgba(25,25,112,0.6)"/>
                <circle cx="20" cy="15" r="2" fill="rgba(255,255,255,0.8)"/>
                <circle cx="30" cy="25" r="1.5" fill="rgba(255,255,255,0.7)"/>
                <circle cx="45" cy="12" r="1.5" fill="rgba(255,255,255,0.7)"/>
                <circle cx="25" cy="35" r="2" fill="rgba(255,255,255,0.8)"/>
              `,
      partly_day: `
                <circle cx="60" cy="20" r="12" fill="rgba(255,200,80,0.6)"/>
                <ellipse cx="75" cy="35" rx="20" ry="14" fill="rgba(220,220,220,0.85)"/>
                <ellipse cx="58" cy="40" rx="16" ry="12" fill="rgba(200,200,200,0.85)"/>
              `,
      partly_night: `
                <circle cx="60" cy="20" r="11" fill="rgba(245,245,220,0.7)"/>
                <circle cx="64" cy="17" r="11" fill="rgba(47,79,79,0.5)"/>
                <ellipse cx="75" cy="35" rx="20" ry="14" fill="rgba(169,169,169,0.8)"/>
                <ellipse cx="58" cy="40" rx="16" ry="12" fill="rgba(128,128,128,0.8)"/>
              `,
      cloudy_day: `
                <ellipse cx="50" cy="28" rx="24" ry="16" fill="rgba(160,160,160,0.8)"/>
                <ellipse cx="75" cy="35" rx="22" ry="15" fill="rgba(150,150,150,0.8)"/>
                <ellipse cx="30" cy="38" rx="20" ry="14" fill="rgba(170,170,170,0.8)"/>
              `,
      cloudy_night: `
                <ellipse cx="50" cy="28" rx="24" ry="16" fill="rgba(105,105,105,0.85)"/>
                <ellipse cx="75" cy="35" rx="22" ry="15" fill="rgba(90,90,90,0.85)"/>
                <ellipse cx="30" cy="38" rx="20" ry="14" fill="rgba(115,115,115,0.85)"/>
              `,
      rain_day: `
                <ellipse cx="50" cy="25" rx="22" ry="14" fill="rgba(100,100,100,0.8)"/>
                <line x1="40" y1="45" x2="36" y2="60" stroke="rgba(100,150,200,0.7)" stroke-width="2.5" stroke-linecap="round"/>
                <line x1="52" y1="45" x2="48" y2="60" stroke="rgba(100,150,200,0.7)" stroke-width="2.5" stroke-linecap="round"/>
                <line x1="64" y1="45" x2="60" y2="60" stroke="rgba(100,150,200,0.7)" stroke-width="2.5" stroke-linecap="round"/>
                <line x1="46" y1="50" x2="42" y2="65" stroke="rgba(100,150,200,0.6)" stroke-width="2" stroke-linecap="round"/>
                <line x1="58" y1="50" x2="54" y2="65" stroke="rgba(100,150,200,0.6)" stroke-width="2" stroke-linecap="round"/>
              `,
      rain_night: `
                <ellipse cx="50" cy="25" rx="22" ry="14" fill="rgba(70,70,70,0.85)"/>
                <line x1="40" y1="45" x2="36" y2="60" stroke="rgba(80,120,160,0.75)" stroke-width="2.5" stroke-linecap="round"/>
                <line x1="52" y1="45" x2="48" y2="60" stroke="rgba(80,120,160,0.75)" stroke-width="2.5" stroke-linecap="round"/>
                <line x1="64" y1="45" x2="60" y2="60" stroke="rgba(80,120,160,0.75)" stroke-width="2.5" stroke-linecap="round"/>
                <line x1="46" y1="50" x2="42" y2="65" stroke="rgba(80,120,160,0.65)" stroke-width="2" stroke-linecap="round"/>
                <line x1="58" y1="50" x2="54" y2="65" stroke="rgba(80,120,160,0.65)" stroke-width="2" stroke-linecap="round"/>
              `,
      snow_day: `
                <ellipse cx="50" cy="25" rx="22" ry="14" fill="rgba(180,180,200,0.8)"/>
                <text x="35" y="55" font-size="18" fill="rgba(150,180,220,0.8)">❄</text>
                <text x="55" y="62" font-size="14" fill="rgba(150,180,220,0.75)">❄</text>
                <text x="48" y="48" font-size="12" fill="rgba(150,180,220,0.7)">❄</text>
              `,
      snow_night: `
                <ellipse cx="50" cy="25" rx="22" ry="14" fill="rgba(90,90,110,0.85)"/>
                <text x="35" y="55" font-size="18" fill="rgba(180,200,230,0.8)">❄</text>
                <text x="55" y="62" font-size="14" fill="rgba(180,200,230,0.75)">❄</text>
                <text x="48" y="48" font-size="12" fill="rgba(180,200,230,0.7)">❄</text>
              `,
      mist_day: `
                <path d="M 20,25 Q 40,20 60,25 T 100,25" stroke="rgba(200,200,200,0.7)" stroke-width="5" fill="none" stroke-linecap="round"/>
                <path d="M 15,40 Q 40,35 65,40 T 105,40" stroke="rgba(210,210,210,0.7)" stroke-width="5" fill="none" stroke-linecap="round"/>
                <path d="M 18,55 Q 40,50 62,55 T 102,55" stroke="rgba(200,200,200,0.65)" stroke-width="5" fill="none" stroke-linecap="round"/>
              `,
      mist_night: `
                <path d="M 20,25 Q 40,20 60,25 T 100,25" stroke="rgba(130,130,130,0.75)" stroke-width="5" fill="none" stroke-linecap="round"/>
                <path d="M 15,40 Q 40,35 65,40 T 105,40" stroke="rgba(140,140,140,0.75)" stroke-width="5" fill="none" stroke-linecap="round"/>
                <path d="M 18,55 Q 40,50 62,55 T 102,55" stroke="rgba(130,130,130,0.7)" stroke-width="5" fill="none" stroke-linecap="round"/>
              `,
    };

    // Condition substrings → weather type, checked in this order (first match wins).
    const WEATHER_TYPE_MATCHERS = [
      { type: 'clear',  patterns: ['clear', 'sunny'] },
      { type: 'partly', patterns: ['partly'] },
      { type: 'cloudy', patterns: ['overcast', 'cloudy'] },
      { type: 'rain',   patterns: ['rain', 'drizzle', 'shower'] },
      { type: 'snow',   patterns: ['snow', 'flurr'] },
      { type: 'mist',   patterns: ['mist', 'fog'] },
    ];

    const WEATHER_CLASS_LIST = WEATHER_TYPE_MATCHERS.flatMap(
      ({ type }) => [`weather-${type}-day`, `weather-${type}-night`]
    );

    function matchWeatherType(condition) {
      for (const { type, patterns } of WEATHER_TYPE_MATCHERS) {
        if (patterns.some(p => condition.includes(p))) return type;
      }
      return null;
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
    fetch("https://data.wymancove.com/weather_data.json?t=" + Date.now())
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
        window._combinedWindImpact = combinedWindImpact;
        window._worryLevel = worryLevel;

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
        var _duEl = document.getElementById("dataUpdated2"); if (_duEl) _duEl.textContent = fmtRelAge(data.generated_at || data.location?.updated);
        renderSources(data.sources, (data.pws || {}).stale);
        renderFrostTracker(data.frost_log);
        renderBirds(data.birds);
        renderSunsetQuality(data);
        renderDockDay(data);
        renderHairDay(data);
        renderOutdoorConditions(data);
        renderBriefing(data);
        renderSolarSystem();

        // NWS alerts panel — see js/alerts.js
        renderAlerts(data);

        // Right Now card — see js/right_now.js (incremental extraction in progress)
        renderRightNow(data);

        // Right Now card fully extracted — see js/right_now.js
        // Locals also referenced by downstream code (forecast, wind tab, almanac):
        const cur       = data.current     || {};
        const der       = data.derived     || {};
        const hyp       = data.hyperlocal  || {};
        const daily     = data.daily       || {};
        const seaBreeze = data.sea_breeze  || {};

        // Pressure alarm banner + storm-mode badge — see js/alarms.js
        renderPressureAlarm(data);
        renderStormMode(data);
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
          ssHour,
          (hourly.precipitation || []).slice(startIdx, startIdx + 48)
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
        renderThunderstormCard(data);
        window.__thunderstorm = (data.derived?.thunderstorm?.severity && data.derived.thunderstorm.severity !== 'clear')
          ? data.derived.thunderstorm : null;
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
            sustainedImpactEl.innerHTML = `${sustainedScore} ${dim(`(${sustainedLevel.label})`)}`;
          }
        } else if (sustainedImpactEl) {
          sustainedImpactEl.textContent = "N/A";
        }
        
        if (cur.wind_gusts != null && cur.wind_direction != null) {
          const exposure = getExposureFactor(cur.wind_direction);
          const gustScore = Math.round(worryScore(hyp.corrected_wind_gusts ?? cur.wind_gusts, exposure));
          const gustLevel = worryLevel(gustScore);
          if (gustImpactEl) {
            gustImpactEl.innerHTML = `${gustScore} ${dim(`(${gustLevel.label})`)}`;
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
            sbWindEl.innerHTML = `${icon}${seaBreeze.likelihood}% ${dim(seaBreeze.reason || "")}`;
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

        // Observed history chart
        const obsEntries = (data.obs_temp_log?.entries) || [];
        if (obsEntries.length > 0) {
          buildObsChart(obsEntries);
          renderObsChartCollapsedPreview(obsEntries);
        }

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
        renderOutdoorConditions(_d);
        renderBriefing(_d);
        renderCorrectionsCard(_d);
        populateCollapsedPreviews(_d);
        const _duEl = document.getElementById('dataUpdated2');
        if (_duEl) {
          const _dt = _d.generated_at || _d.location?.updated;
          if (_dt) {
            const _d2 = new Date(_dt);
            if (!isNaN(_d2.getTime())) _duEl.textContent = fmtRelAge(_dt);
          }
        }
      } catch(e) {}
    })();

    loadWeatherData();

    // Version update detection + refresh-on-return: see js/version_check.js


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
    const hasTs = !!window.__thunderstorm;
    // Badge is always visible — toggle the colored dot to indicate active state
    if (dot) dot.style.display = (hasAlerts || hasStorm || hasTs) ? '' : 'none';
    // Briefing tab alert dot
    const tabDot = document.getElementById('briefingTabAlertDot');
    if (tabDot) tabDot.style.display = (hasAlerts || hasStorm || hasTs) ? '' : 'none';
  });
  
  // Start observing once DOM is ready
  document.addEventListener('DOMContentLoaded', function() {
    const container = document.getElementById('alertsContainer');
    if (container) {
      observer.observe(container, { childList: true, subtree: true, characterData: true });
    }
  });
})();

// Pull-to-refresh: see js/pull_refresh.js

// cache bust
