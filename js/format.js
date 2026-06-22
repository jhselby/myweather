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

// C1 confidence-band suffix. Reads data.confidence.cells[field][band].displayed_mae
// and returns ` ±N` styled with dim text. Returns empty string when:
//   - confidence layer not applied (gated off)
//   - cell missing / null displayed_mae
//   - half-range suppression: when displayed_mae > 0.5 × cellRange (e.g. ±30 on
//     a 0-100% scale), we suppress because the band is louder than the value.
//
// Stage 4b (v0.6.181): rendered live even when applied=false, because the
// cells are stamped today and the visual sanity-check is the whole point of
// a live preview. Final ENABLED flip in the Fitter doesn't change the markup.
function c1Band(data, field, band, opts = {}) {
  const cell = data?.confidence?.cells?.[field]?.[band];
  if (!cell) return "";
  const mae = cell.displayed_mae;
  if (mae == null) return "";
  const halfRange = opts.halfRange ?? null;
  if (halfRange != null && mae > halfRange) return "";
  const txt = mae < 10 ? mae.toFixed(1) : Math.round(mae).toString();
  return ` <span style="opacity:0.45;font-size:0.65em;font-weight:400;">±${txt}</span>`;
}
window.c1Band = c1Band;

// Single canonical compass function — replaces both old degreesToCompass and degToCompass.
function toCompass(deg, withDeg = true) {
  if (deg == null || isNaN(deg)) return "--";
  const d = ((deg % 360) + 360) % 360;
  const dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];
  const label = dirs[Math.round(d / 22.5) % 16];
  return withDeg ? `${Math.round(d)}° ${label}` : label;
}
