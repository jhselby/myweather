/* Scorecard rows: ours vs the bar, per field. Shared by model.html (full table) and index.html (summary)
   so the two pages cannot disagree. Truth rule (plan Step 3.1, 11-22): t, dp, ws, wg on URMA; h on the
   Mesonet at 6-47 h; everything else on the model-blended logged truth (labelled weak/mix on /model).
   tc = truth_compare.json, pf = per_field_scoring.json "7d" per_field block. */
(function (root) {
const FIELDS = [
  // key, name, plain description, unit, decimals
  ["t",  "Temperature",    "air temperature",               "°F",   1],
  ["h",  "Humidity",       "relative humidity",             "% RH", 1],
  ["dp", "Dew point",      "how much moisture is in the air","°F",  1],
  ["ws", "Wind speed",     "sustained wind",                "mph",  1],
  ["wg", "Gusts",          "peak gusts",                    "mph",  1],
  ["wd", "Wind direction", "where the wind comes from",     "°",    0],
  ["sr", "Sunshine",       "solar radiation at the ground", "W/m²", 0],
  ["cc", "Cloud cover",    "how much of the sky is covered","%",    1],
  ["pp", "Rain chance",    "probability of rain that hour", "pts",  1],
  ["pa", "Rain amount",    "inches that hour",              "in",   3],
  ["cl", "Low cloud",      "cloud below ~6,500 ft",         "%",    1],
  ["cm", "Mid cloud",      "cloud ~6,500–20,000 ft",        "%",    1],
  ["ch", "High cloud",     "cloud above ~20,000 ft",        "%",    1],
];
const pct = (us, them) => (them ? (them - us) / them * 100 : null);

function computeScorecard(tc, pf) {
  pf = pf || {};
  const rows = [];
  for (const [k, name, desc, unit, dec] of FIELDS) {
    let us = null, them = null, src = "NBM", truth = null, n = null;
    // Truth rule (plan Step 3.1, 11-22): t, dp, ws, wg on URMA (the Mesonet did not qualify for t / dp;
    // wind stays on URMA); h on the Mesonet at 6-47 h (the only field that qualified).
    const fld = tc && tc.fields && tc.fields[k];
    const two = fld ? (k === "h" ? fld.lead_6h_plus : fld.lead_2h_plus) : null;
    if (["t", "dp", "ws", "wg"].includes(k) && two && two.n_urma > 500) {
      us = two.served_mae_urma; them = two.public_mae_urma; truth = "urma"; n = two.n_urma;
    } else if (k === "h" && two && two.n > 500) {
      us = two.served_mae_stations; them = two.public_mae_stations; truth = "stn"; n = two.n;
    } else if (k === "cc" && tc && tc.cc_urma && tc.cc_urma.bands) {
      let s = 0, p = 0, m = 0;   // leads 6-47h, matching the 2h+ rows above as closely as the bands allow
      for (const [b, v] of Object.entries(tc.cc_urma.bands)) { if (v && b !== "0-5") { s += v.served_mae_urma * v.n; p += v.public_mae_urma * v.n; m += v.n; } }
      if (m) { us = s / m; them = p / m; truth = "urma"; n = m; }
    }
    if (us == null && pf[k]) {
      const x = pf[k];
      us = x.prod_current_config_mae ?? x.prod_mae;
      const nbm = x.nbm_raw_mae;
      if (x.in_nbm_scope || ((k === "pp" || k === "pa") && nbm != null)) { them = nbm; src = "NBM"; }
      else { them = x.hrrr_raw_mae; src = "HRRR"; }
      truth = (k === "cl" || k === "cm" || k === "ch") ? "weak" : "mix"; n = x.n_prod;
    }
    if (us == null || them == null) continue;
    // weather.gov becomes the bar only where it has enough scored rows: a bar built on one day (wg, 15 rows) or a
    // few hours is not a result. Below MIN_NWS_ROWS the NBM/HRRR bar stays until the weather.gov rows fill in (~12-06).
    const MIN_NWS_ROWS = 500;
    let nws = null, nNws = 0;
    if (two && truth === "urma" && two.lift_vs_nws_urma_pct != null) { nws = two.lift_vs_nws_urma_pct; nNws = two.n_nws_urma || 0; }
    else if (two && truth === "stn" && two.lift_vs_nws_stations_pct != null) { nws = two.lift_vs_nws_stations_pct; nNws = two.n_nws || 0; }
    else if (tc && tc.nws_shrunk && tc.nws_shrunk[k]) { nws = tc.nws_shrunk[k].lift_vs_nws_pct; nNws = tc.nws_shrunk[k].n || 0; }
    if (nNws < MIN_NWS_ROWS) nws = null;
    // The bar: NWS forecast (weather.gov) where it carries the field, else NBM/HRRR.
    let bUs = us, bThem = them, bSrc = src;
    if (nws != null) {
      let nu = null, nt = null;
      if (two && truth === "urma" && two.nws_mae_urma != null) { nu = two.served_mae_urma_nwsrows; nt = two.nws_mae_urma; }
      else if (two && truth === "stn" && two.nws_mae_stations != null) { nu = two.served_mae_stations_nwsrows; nt = two.nws_mae_stations; }
      else if (tc && tc.nws_shrunk && tc.nws_shrunk[k]) { nu = tc.nws_shrunk[k].served_mae; nt = tc.nws_shrunk[k].nws_mae; }
      if (nu != null && nt != null) { bUs = nu; bThem = nt; bSrc = "weather.gov"; }
    }
    rows.push({ k, name, desc, unit, dec, us, them, src, truth, n, nws, bUs, bThem, bSrc, bar: pct(bUs, bThem), lift: pct(us, them) });
  }
  const main = rows.filter(r => !["cl", "cm", "ch"].includes(r.k));
  return {
    rows,
    W: main.filter(r => r.bar > 2),
    L: main.filter(r => r.bar < -2),
    T: main.filter(r => Math.abs(r.bar) <= 2),
  };
}
root.computeScorecard = computeScorecard;
root.SCORECARD_PCT = pct;
})(window);
