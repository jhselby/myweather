// ======================================================
// Theme + pressure-unit display helpers
// ======================================================
// Provides:
//   - setTheme / applyTheme / updateSettingBtns / isLight — light/dark/system
//   - chartTextColor / chartGridColor — Chart.js color helpers used by every
//     chart-rendering module (tempchart, wind, obschart, feelslike, thunderstorm)
//   - hpaToInhg / fmtPressure — pressure unit formatting
//   - rerenderPressure — re-paints existing pressure DOM after a unit change
//   - On-load IIFE: applies stored theme and watches for system color-scheme changes
//
// Must load BEFORE app-main.js (which used to host this block) and before any
// render modules that read theme state at boot. Other modules read these
// helpers when their render functions execute, so late loading would still
// work; positioning early just keeps the boot sequence clean.

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

function updateSettingBtns() {
  const theme = localStorage.getItem('theme') || 'system';
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

// Re-render all pressure fields using last fetched data (called when units change)
function rerenderPressure() {
  const data = window.__lastWeatherData;
  if (!data) return;
  const h = data.hourly || {};

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

// Apply theme on load + watch for system color-scheme changes
(function() {
  applyTheme(localStorage.getItem('theme') || 'system');
  window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
    if ((localStorage.getItem('theme') || 'system') === 'system') applyTheme('system');
  });
})();
