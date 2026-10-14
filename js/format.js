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

// v0.7.51 — observed precip when the model's weather code says dry. The model
// description stays primary when it shows precip (intensity, 0e646222); when it
// misses rain entirely, KBVY's present weather or the WU network take over.
// Tempest is left out: its precip_rate_in is a 1-minute accumulation.
const WET_RE = /rain|snow|drizzle|sleet|shower|thunder|storm|freezing|ice pellets|hail/i;
function observedPrecipDesc(data) {
  const ov = (data.current || {}).condition_override || "";
  if (/snow|sleet|freezing|ice pellets|hail|thunder/i.test(ov)) return ov;
  // Stations within 1.5 mi, fresh readings only, rates in in/hr.
  // WU: drop rows >10 min older than the newest WU report (stale rows read 0).
  // Tempest: precip_rate_in is a 1-minute accumulation, so x60.
  const NEAR_MI = 1.5;
  const wu = (((data.wu_stations || {}).stations) || [])
    .filter(s => s.precip_rate_in != null && s.distance_mi != null && s.distance_mi <= NEAR_MI && s.timestamp);
  const wuT = wu.map(s => Date.parse(s.timestamp.replace(" ", "T")));
  const newest = Math.max(...wuT.filter(t => !isNaN(t)));
  const rates = wu.filter((s, i) => !(newest - wuT[i] > 10 * 60000)).map(s => s.precip_rate_in);
  ((data.tempest || {}).stations || [])
    .filter(s => s.valid !== false && s.precip_rate_in != null && s.distance_mi != null
      && s.distance_mi <= NEAR_MI && !(s.age_minutes > 10))
    .forEach(s => rates.push(s.precip_rate_in * 60));
  const pos = rates.filter(r => r > 0).sort((a, b) => a - b);
  if (pos.length >= 3 && pos.length >= 0.25 * rates.length) {
    const med = pos[Math.floor(pos.length / 2)];
    return med < 0.01 ? "Drizzle" : med < 0.10 ? "Light Rain" : med < 0.30 ? "Moderate Rain" : "Heavy Rain";
  }
  return WET_RE.test(ov) ? ov : null;
}
window.observedPrecipDesc = observedPrecipDesc;

// Single canonical compass function — replaces both old degreesToCompass and degToCompass.
function toCompass(deg, withDeg = true) {
  if (deg == null || isNaN(deg)) return "--";
  const d = ((deg % 360) + 360) % 360;
  const dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];
  const label = dirs[Math.round(d / 22.5) % 16];
  return withDeg ? `${Math.round(d)}° ${label}` : label;
}
