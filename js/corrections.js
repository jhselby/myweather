// ─────────────────────────────────────────────────────────────────────────────
// Corrections Card — collapsed preview + expanded table + station bias offsets
// ─────────────────────────────────────────────────────────────────────────────

function renderCorrectionsCard(data) {
  const hyp = data.hyperlocal || {};
  const cur = data.current || {};
  const der = data.derived || {};

  // ── Collapsed preview ────────────────────────────────────────────────────
  const stationsCount = hyp.stations_used || 0;
  const confidence = hyp.confidence || 'Unknown';

  const stationsEl = document.getElementById('correctionsStationsCollapsed');
  if (stationsEl) stationsEl.textContent = stationsCount;

  const confidenceEl = document.getElementById('correctionsConfidenceCollapsed');
  if (confidenceEl) confidenceEl.textContent = confidence !== 'Unknown' ? `${confidence} confidence` : '';

  const correctionsCard = document.querySelector('[data-collapse-key="corrections"]');
  if (correctionsCard) {
    correctionsCard.classList.remove('tile-corrections-high', 'tile-corrections-moderate', 'tile-corrections-low');
    if (confidence === 'High') correctionsCard.classList.add('tile-corrections-high');
    else if (confidence === 'Moderate') correctionsCard.classList.add('tile-corrections-moderate');
    else if (confidence === 'Low') correctionsCard.classList.add('tile-corrections-low');
  }

  // ── Expanded corrections table ───────────────────────────────────────────
  const set = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };

  // Temperature
  set('scModelTemp',     hyp.model_temp != null ? hyp.model_temp.toFixed(1) + '°F' : '--');
  set('scCorrectedTemp', hyp.corrected_temp != null ? Math.round(hyp.corrected_temp) + '°F' : '--');
  const tempBias = (hyp.corrected_temp != null && hyp.model_temp != null)
    ? hyp.corrected_temp - hyp.model_temp
    : (hyp.weighted_bias ?? hyp.bias_temp);
  set('scBiasTemp', tempBias != null ? (tempBias >= 0 ? '+' : '') + tempBias.toFixed(1) + '°F' : '--');

  // Humidity
  set('scModelHumidity',     hyp.model_humidity != null ? Math.round(hyp.model_humidity) + '%' : '--');
  set('scCorrectedHumidity', hyp.corrected_humidity != null ? Math.round(hyp.corrected_humidity) + '%' : '--');
  set('scBiasHumidity', hyp.bias_humidity != null ? (hyp.bias_humidity >= 0 ? '+' : '') + hyp.bias_humidity.toFixed(1) + '%' : '--');

  // Pressure
  set('scModelPressure',     hyp.model_pressure_in != null ? hyp.model_pressure_in.toFixed(2) : '--');
  set('scCorrectedPressure', hyp.corrected_pressure_in != null ? hyp.corrected_pressure_in.toFixed(2) : '--');
  if (hyp.model_pressure_in != null && hyp.corrected_pressure_in != null) {
    const pBias = hyp.corrected_pressure_in - hyp.model_pressure_in;
    set('scBiasPressure', (pBias >= 0 ? '+' : '') + pBias.toFixed(2));
  } else {
    set('scBiasPressure', '--');
  }

  // Wind Speed
  set('scModelWindSpeed',     hyp.model_wind_speed != null ? Math.round(hyp.model_wind_speed) + ' mph' : '--');
  set('scCorrectedWindSpeed', hyp.corrected_wind_speed != null ? Math.round(hyp.corrected_wind_speed) + ' mph' : '--');
  set('scBiasWindSpeed', hyp.bias_wind_speed != null ? (hyp.bias_wind_speed >= 0 ? '+' : '') + hyp.bias_wind_speed.toFixed(1) + ' mph' : '--');

  // Wind Gusts
  set('scModelGusts',     hyp.model_wind_gusts != null ? Math.round(hyp.model_wind_gusts) + ' mph' : '--');
  set('scCorrectedGusts', hyp.corrected_wind_gusts != null ? Math.round(hyp.corrected_wind_gusts) + ' mph' : '--');
  set('scBiasGusts', hyp.bias_wind_gusts != null ? (hyp.bias_wind_gusts >= 0 ? '+' : '') + hyp.bias_wind_gusts.toFixed(1) + ' mph' : '--');

  // Dew Point
  const modelDewpoint = cur.dew_point;
  const correctedDewpoint = der.corrected_dew_point;
  set('scModelDewpoint',     modelDewpoint != null ? Math.round(modelDewpoint) + '°F' : '--');
  set('scCorrectedDewpoint', correctedDewpoint != null ? Math.round(correctedDewpoint) + '°F' : '--');
  if (modelDewpoint != null && correctedDewpoint != null) {
    const dewBias = correctedDewpoint - modelDewpoint;
    set('scBiasDewpoint', (dewBias >= 0 ? '+' : '') + dewBias.toFixed(1) + '°F');
  } else {
    set('scBiasDewpoint', '--');
  }

  // Wet Bulb
  const modelWetBulb = cur.wet_bulb;
  const correctedWetBulb = der.corrected_wet_bulb;
  set('scModelWetBulb',     modelWetBulb != null ? Math.round(modelWetBulb) + '°F' : '--');
  set('scCorrectedWetBulb', correctedWetBulb != null ? Math.round(correctedWetBulb) + '°F' : '--');
  if (modelWetBulb != null && correctedWetBulb != null) {
    set('scBiasWetBulb', (correctedWetBulb - modelWetBulb >= 0 ? '+' : '') + (correctedWetBulb - modelWetBulb).toFixed(1) + '°F');
  } else {
    set('scBiasWetBulb', '--');
  }

  // Feels Like — shade (NWS heat index above 80°F+35% RH, else Australian AT
  // with solar=0). Apples-to-apples with Open-Meteo's apparent_temperature,
  // which is also shade-leaning. Full-sun Steadman lives in the Feels Like card.
  const modelFeelsLike = cur.apparent_temperature;
  let shadeFeels = der.heat_index;
  if (shadeFeels == null) {
    const T = hyp.corrected_temp ?? cur.temperature;
    const RH = hyp.corrected_humidity ?? cur.humidity;
    const ws = hyp.corrected_wind_speed ?? cur.wind_speed ?? 0;
    if (T != null && RH != null) {
      const Tc = (T - 32) * 5 / 9;
      const wsMs = ws * 0.44704;
      const e = (RH / 100) * 6.105 * Math.exp(17.27 * Tc / (237.7 + Tc));
      shadeFeels = (Tc + 0.33 * e - 0.70 * wsMs - 4.00) * 9 / 5 + 32;
    }
  }
  set('scModelFeelsLike',     modelFeelsLike != null ? Math.round(modelFeelsLike) + '°F' : '--');
  set('scCorrectedFeelsLike', shadeFeels != null ? Math.round(shadeFeels) + '°F' : '--');
  if (modelFeelsLike != null && shadeFeels != null) {
    set('scBiasFeelsLike', (shadeFeels - modelFeelsLike >= 0 ? '+' : '') + (shadeFeels - modelFeelsLike).toFixed(1) + '°F');
  } else {
    set('scBiasFeelsLike', '--');
  }

  // Precip Type
  const precipLikely = (cur.precipitation_probability ?? 0) > 20;
  if (precipLikely) {
    const wc = cur.weather_code ?? 0;
    let modelPType = 'None';
    if (wc >= 95) modelPType = 'Thunderstorm';
    else if (wc >= 85 || (wc >= 71 && wc <= 77)) modelPType = 'Snow';
    else if (wc >= 66 && wc <= 67) modelPType = 'Freezing Rain';
    else if (wc >= 51 && wc <= 65) modelPType = 'Rain';
    set('scModelPrecipType', modelPType);
    const correctedPType = der.surface_precip_type;
    if (correctedPType) {
      const displayType = correctedPType === 'freezing_rain' ? 'Freezing Rain' :
        correctedPType.charAt(0).toUpperCase() + correctedPType.slice(1);
      set('scCorrectedPrecipType', displayType);
      set('scBiasPrecipType', displayType !== modelPType ? 'Changed' : '--');
    } else {
      set('scCorrectedPrecipType', '--');
      set('scBiasPrecipType', '--');
    }
  } else {
    set('scModelPrecipType', 'None');
    set('scCorrectedPrecipType', 'None');
    set('scBiasPrecipType', '--');
  }

  // Station count
  set('stationsUsedCount', hyp.stations_used ?? '--');
  set('hyperlocalStationsDiag', `${hyp.stations_used ?? '--'} of ${hyp.stations_total ?? '--'} stations used`);

  // KBVY anchor
  if (hyp.kbvy_temp_f != null && hyp.kbvy_local_delta != null) {
    set('kbvyAnchorLine',
      `KBVY ${hyp.kbvy_temp_f.toFixed(1)}°F · local ${hyp.kbvy_local_delta >= 0 ? '+' : ''}${hyp.kbvy_local_delta.toFixed(1)}°F vs airport`);
  }

  // ── Station bias offsets (adaptive bias correction) ───────────────────────
  _renderStationOffsets(hyp);

  // ── Forecast decay corrections (lead-time-dependent error correction) ────
  _renderDecayCorrections(data);
}


function _renderDecayCorrections(data) {
  const container = document.getElementById('decayCorrectionsSection');
  if (!container) return;

  const dm = data && data.decay_meta;
  if (!dm || typeof dm !== 'object') {
    container.style.display = 'none';
    return;
  }

  // Field key → [display label, unit, decimal places]
  const fieldSpec = {
    t:  ['Temperature',  '°F',    1],
    dp: ['Dew Point',    '°F',    1],
    h:  ['Humidity',     '%',     0],
    ws: ['Wind Speed',   'mph',   1],
    wg: ['Wind Gust',    'mph',   1],
    pa: ['Pressure',     ' inHg', 2],
    cc: ['Cloud Cover',  '%',     0],
    sr: ['Solar Rad',    ' W/m²', 0],
    pp: ['Precip Prob',  '%',     0],
    pr: ['Precip Rate',  ' in/h', 2],
  };

  // v0.6.45: per-field L3/L4 whitelist. Show truthful +24h delta:
  //  - For L3-enabled fields → per_field_24h (the actual L3 correction applied)
  //  - For L2-only fields with bias (t/h/pr) → compute L2 lead-decayed delta
  const l3Fields = new Set(dm.layer_3_fields || []);
  const hourly = (data && data.hourly) || {};
  const per24 = dm.per_field_24h || {};
  const l2Taus = (data.l2_decay_meta && data.l2_decay_meta.tau_hours) || {};

  const delta24 = (correctedKey, rawKey, digits) => {
    const corr = hourly[correctedKey];
    const raw  = hourly[rawKey];
    if (!Array.isArray(corr) || !Array.isArray(raw) || corr.length <= 24 || raw.length <= 24) return null;
    if (corr[24] == null || raw[24] == null) return null;
    return Number((corr[24] - raw[24]).toFixed(digits));
  };

  const rowItems = [];
  const l2Map = {
    t:  ['Temperature', '°F',    2, 'corrected_temperature', 'temperature'],
    h:  ['Humidity',    '%',     1, 'corrected_humidity',    'humidity'],
    pr: ['Pressure',    ' inHg', 3, 'corrected_pressure_in', 'raw_pressure_in'],
  };
  for (const [key, spec] of Object.entries(l2Map)) {
    if (l3Fields.has(key)) continue;
    const d = delta24(spec[3], spec[4], spec[2]);
    if (d == null) continue;
    rowItems.push({ key, label: spec[0], unit: spec[1], digits: spec[2], delta: d, source: 'L2' });
  }
  const l3Order = ['ws', 'wg', 'pp', 'cc', 'sr', 'pa', 'cl', 'cm', 'ch', 'dp'];
  for (const key of l3Order) {
    if (!(key in per24)) continue;
    const [label, unit, digits] = fieldSpec[key] || [key, '', 1];
    rowItems.push({ key, label, unit, digits, delta: Number(per24[key]), source: 'L3' });
  }

  const rows = rowItems.map(x => {
    const v = x.delta;
    const sign = v >= 0 ? '+' : '';
    const color = v > 0 ? 'rgba(239,100,80,0.9)'
                : v < 0 ? 'rgba(80,160,239,0.9)'
                :         'rgba(180,180,180,0.7)';
    let tag = '';
    if (x.source === 'L2') {
      const tau = l2Taus[x.key];
      tag = tau ? ` (L2 τ=${tau >= 1e8 ? '∞' : tau + 'h'})` : ' (L2)';
    } else {
      tag = ' (L3)';
    }
    const display = `${sign}${v.toFixed(x.digits)}${x.unit === '°F' || x.unit === 'mph' ? ' ' + x.unit : x.unit}`;
    return `<div style="display:flex;justify-content:space-between;padding:4px 8px;border-bottom:1px solid rgba(255,255,255,0.05);">
      <span style="opacity:0.7;font-size:0.78rem;">${x.label}<span style="opacity:0.5;">${tag}</span></span>
      <span style="font-weight:700;color:${color};font-size:0.78rem;">${display}</span>
    </div>`;
  }).join('');

  const l3Count = (dm.layer_3_fields || []).length;
  const headerLeft = '+24h forecast adjustment';
  const headerRight = l3Count > 0 ? `L3 on: ${(dm.layer_3_fields || []).join('/')}` : 'L3/L4 paused';
  const footerText = `Applied ${dm.applied_at || '?'} · per-field L3/L4 since v0.6.45 · <a href="/corrections_debug.html" target="_blank" style="color:rgba(120,180,239,0.9);">why →</a>`;
  const title = 'Forecast Corrections at +24h ▾';
  container.innerHTML = `
    <div style="margin-top:14px;">
      <div onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'':'none'"
           style="font-size:0.78rem;font-weight:700;color:rgba(255,255,255,0.5);cursor:pointer;user-select:none;padding:4px 0;">
        ${title}
      </div>
      <div style="display:none;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:8px;overflow:hidden;margin-top:6px;">
        <div style="display:flex;justify-content:space-between;padding:5px 8px;background:rgba(255,255,255,0.05);border-bottom:1px solid rgba(255,255,255,0.1);">
          <span style="font-weight:800;font-size:0.78rem;color:rgba(255,255,255,0.6);">${headerLeft}</span>
          <span style="font-weight:800;font-size:0.78rem;color:rgba(255,255,255,0.6);">${headerRight}</span>
        </div>
        ${rows || `<div style="padding:8px;font-size:0.78rem;opacity:0.5;">No +24h correction data available yet.</div>`}
        <div style="padding:5px 8px;font-size:0.72rem;opacity:0.4;">
          ${footerText}
        </div>
      </div>
    </div>`;
  container.style.display = '';
}


function _renderStationOffsets(hyp) {
  const container = document.getElementById('stationOffsetsSection');
  if (!container) return;

  const offsets = hyp.station_offsets;
  if (!offsets || !offsets.temp || Object.keys(offsets.temp).length === 0) {
    container.style.display = 'none';
    return;
  }

  // Merge temp offsets — prefer day/night split label but show combined value
  const tempOffsets = offsets.temp;

  // Sort by absolute offset descending, show top 8
  const sorted = Object.entries(tempOffsets)
    .sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]))
    .slice(0, 8);

  const rows = sorted.map(([sid, offset]) => {
    const warm = offset > 0;
    const color = warm ? 'rgba(239,100,80,0.9)' : 'rgba(80,160,239,0.9)';
    const sign = offset >= 0 ? '+' : '';
    return `<div style="display:flex;justify-content:space-between;padding:4px 8px;border-bottom:1px solid rgba(255,255,255,0.05);">
      <span style="opacity:0.7;font-size:0.78rem;">${sid}</span>
      <span style="font-weight:700;color:${color};font-size:0.78rem;">${sign}${offset.toFixed(2)}°F</span>
    </div>`;
  }).join('');

  container.innerHTML = `
    <div style="margin-top:14px;">
      <div onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display==='none'?'':'none'"
           style="font-size:0.78rem;font-weight:700;color:rgba(255,255,255,0.5);cursor:pointer;user-select:none;padding:4px 0;">
        Station Calibration Offsets ▾
      </div>
      <div style="display:none;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:8px;overflow:hidden;margin-top:6px;">
        <div style="display:flex;justify-content:space-between;padding:5px 8px;background:rgba(255,255,255,0.05);border-bottom:1px solid rgba(255,255,255,0.1);">
          <span style="font-weight:800;font-size:0.78rem;color:rgba(255,255,255,0.6);">Station</span>
          <span style="font-weight:800;font-size:0.78rem;color:rgba(255,255,255,0.6);">Chronic offset</span>
        </div>
        ${rows}
        <div style="padding:5px 8px;font-size:0.72rem;opacity:0.4;">
          48h rolling average · ${Object.keys(tempOffsets).length} stations calibrated
        </div>
      </div>
    </div>`;
  container.style.display = '';
}
