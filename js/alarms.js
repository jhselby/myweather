// ======================================================
// Pressure alarm + Storm mode
// ======================================================
// Two related displays that both react to the collector's derived
// alarm fields, plus other signals (wind, precip type, lightning):
//
//   renderPressureAlarm(data) — paints the #pressureAlarmBanner with the
//     collector's pressure_alarm classification ("falling"/etc.) or a
//     dim "Pressure: Normal (+0.2 hPa)" line when no alarm is firing.
//
//   renderStormMode(data) — builds the composite stormFlags list
//     (pressure dropping, approaching trough, high gusts, frozen precip
//     likely, heavy rain, lightning), stores it on window for briefing
//     consumption, re-renders the briefing, and toggles the colored dot
//     on the alert badge.
//
// Both depend on the renderBriefing() function from js/briefing.js
// being globally available (only renderStormMode actually calls it).

function renderPressureAlarm(data) {
  const alarmBanner = document.getElementById("pressureAlarmBanner");
  if (!alarmBanner) return;
  const der = data.derived || {};
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

function renderStormMode(data) {
  const der = data.derived || {};
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
  if (pop0 >= 60 && dailyPrecip >= 0.5) {
    stormFlags.push(`Heavy rain expected — ${dailyPrecip.toFixed(1)}"`);
  }

  const tempestStations = data.tempest?.stations || [];
  const lightningCount1hr = Math.max(0, ...tempestStations.map(st => st.lightning_count_1hr || 0));
  const lightningDists = tempestStations.map(st => st.lightning_last_distance_km).filter(d => d != null && d > 0);
  const lightningMinDist = lightningDists.length > 0 ? Math.min(...lightningDists) : null;
  const lightningActive = lightningCount1hr >= 3 || (lightningCount1hr >= 1 && lightningMinDist != null && lightningMinDist <= 20);
  if (lightningActive) {
    stormFlags.push(`Lightning detected — ${lightningCount1hr} strike${lightningCount1hr !== 1 ? "s" : ""} in past hour`);
  }
  window.__lightningStrike = lightningActive ? { count: lightningCount1hr, distKm: lightningMinDist } : null;

  // Publish storm flags + refresh briefing so it can render them
  window.__stormFlags = stormFlags;
  renderBriefing(data);

  // Toggle the colored dot on the always-visible alert badge
  const badge = document.getElementById("alertBadge");
  if (badge) {
    const dot = badge.querySelector(".alert-badge-dot");
    const container = document.getElementById("alertsContainer");
    const hasAlerts = container && container.innerHTML.trim().length > 0;
    const hasStorm = stormFlags.length >= 2;
    if (dot) dot.style.display = (hasAlerts || hasStorm || !!window.__lightningStrike || !!window.__thunderstorm) ? "" : "none";
  }
}
