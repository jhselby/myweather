// ======================================================
// Tab navigation
// ======================================================
// Owns the four pieces that together make tab switching work:
//   1. showTab(which) — the core switcher. Hides/shows tab views,
//      applies directional slide animation, manages per-tab scroll
//      position, refixes Leaflet maps and tide animation when
//      relevant tabs become visible.
//   2. Swipe-navigation IIFE — touchstart/touchend listeners that
//      call showTab for left/right swipes (mobile gesture nav).
//   3. Bottom-tab-bar sync IIFE — monkey-patches window.showTab so
//      every tab switch also updates the active state + tab-pop
//      animation on the bottom navigation bar. MUST run after
//      showTab is defined.
//   4. Tab-restore IIFE — reads `activeTab` from localStorage and
//      invokes the now-wrapped showTab to set the initial tab.
//      MUST run after the sync wrapper.
//
// Load order in index.html: this file must load BEFORE app-main.js
// (app-main.js references showTab from wireHyperlocalLink + the
// visibilitychange listener, both expecting window.showTab to exist).

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

// ── Swipe navigation between tabs ──
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

// ── Bottom tab bar sync ──
// Monkey-patches window.showTab so every switch also paints the
// bottom-bar active state + tab-pop animation.
(function() {
  const origShowTab = window.showTab;
  window.showTab = function(tab) {
    if (origShowTab) origShowTab(tab);
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

// ── Restore active tab after the sync wrapper is in place ──
// URL ?tab=<name> takes precedence over localStorage (used by deep links
// from Instagram bio / shared URLs to land directly on a specific tab).
(function() {
  try {
    const validTabs = ['briefing', 'weather', 'hyperlocal', 'almanac', 'overhead'];
    const urlTab = new URLSearchParams(window.location.search).get('tab');
    const stored = localStorage.getItem('activeTab');
    const t = (urlTab && validTabs.includes(urlTab))
      ? urlTab
      : (stored || 'briefing');
    showTab(t);
  } catch(e) { showTab('weather'); }
})();
