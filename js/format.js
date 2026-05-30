// ======================================================
// Formatting helpers
// ======================================================
// Pure, no DOM, no state. Used by app-main.js and various render
// modules — must load BEFORE app-main.js in index.html.

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

// Single canonical compass function — replaces both old degreesToCompass and degToCompass.
function toCompass(deg, withDeg = true) {
  if (deg == null || isNaN(deg)) return "--";
  const d = ((deg % 360) + 360) % 360;
  const dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];
  const label = dirs[Math.round(d / 22.5) % 16];
  return withDeg ? `${Math.round(d)}° ${label}` : label;
}
