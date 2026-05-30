// ======================================================
// Version update detection + refresh-on-return
// ======================================================
// Two related responsibilities that both fire when the user comes back
// to the app or a new deploy lands:
//   1. checkForUpdate() — polls version.json every 5 min and lights the
//      red dot on the refresh button when the loaded JS version is older
//      than what's now on the server.
//   2. refreshOnReturn() — on tab-switch + window-focus, reloads weather
//      data (debounced 2s) and snaps back to the briefing tab if the
//      user was away 5+ minutes.
// The refresh-button click handler ties the two together: if the dot is
// lit it does a cache-busting reload, otherwise a plain location.reload.
//
// Depends on globals defined in app-main.js: showTab, loadWeatherData.
// Must therefore be loaded AFTER app-main.js in index.html.

(function() {
  // ── checkForUpdate: poll version.json for new deploys ──
  function checkForUpdate() {
    // If we just reloaded due to an update, suppress the check for 30s — GitHub Pages CDN
    // ignores query params for HTML, so the old index.html may still be served for a bit.
    const justUpdated = sessionStorage.getItem('_updateReload');
    if (justUpdated && Date.now() - parseInt(justUpdated) < 30000) {
      const dot = document.getElementById('refreshAlertDot');
      if (dot) dot.style.display = 'none';
      return;
    }
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

  // ── Track when user leaves the app (for briefing-on-return logic) ──
  document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
      window.__lastHiddenAt = Date.now();
    }
  });

  // ── refreshOnReturn: debounced reload on visibility / focus ──
  // Fires on tab-switch (visibilitychange) AND app-switch (window focus).
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

  // ── Refresh button: cache-bust reload if update pending, else plain reload ──
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
})();
