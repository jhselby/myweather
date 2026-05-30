// ======================================================
// Right Now card render
// ======================================================
// Owns every visible field of the Right Now card:
//   - Current temperature + thermometer mercury
//   - Bias confidence indicator
//   - Feels Like (shade) + Full-sun badge
//   - 10-day collapsed preview
//   - Sky condition + Sky/Precip tile + weather graphics
//   - Today summary (hi/lo)
//   - Right Now grid: precip type, wind impact, pressure, humidity,
//     visibility, dew point, UV
//   - Sea breeze now + KBOS observed pressure + KBOS/KBVY temps
//   - Fog risk + lifestyle scores (sunset, beach, hair)
//   - wireHyperlocalLink hookups for tappable fields
//
// Reads `data` only — no shared scope with loadWeatherData. The
// global helpers it depends on are defined elsewhere:
//   wireHyperlocalLink, dim, toCompass, combinedWindImpact, worryLevel,
//   hpaToInhg, fmtPressure, matchWeatherType, WEATHER_GRAPHICS,
//   WEATHER_CLASS_LIST, weatherEmoji, weatherDesc,
//   renderCorrectionsCard, renderWindTile, renderWindImpactCollapsed.

function renderRightNow(data) {
  const cur = data.current || {};
  const der = data.derived || {};
  const hyp = data.hyperlocal || {};
  const daily = data.daily || {};
  const kbos = data.kbos || {};
  const kbvy = data.kbvy || {};
  const seaBreeze = data.sea_breeze || {};
  const code = cur.weather_code;

  // ── Condition emoji + description (with Pirate-minutely override) ──
  const emoji = cur.emoji || weatherEmoji[code] || "&#127777;&#65039;";
  let desc = cur.weather_description || cur.condition_override || weatherDesc[code] || "—";
  if (!/rain|snow|drizzle|sleet|shower/i.test(desc)) {
    const mn2 = window.__precipMinutely || [];
    if (mn2.length) {
      const mn2Now = Math.floor(Date.now() / 1000);
      const mn2Stale = Math.round((mn2Now - (mn2[0]?.time ?? mn2Now)) / 60);
      const mn2Cur = mn2[Math.min(mn2Stale, mn2.length - 1)];
      if (mn2Cur && mn2Cur.precip_intensity > 0.001 && (mn2Cur.precip_probability ?? 0) >= 0.3) {
        const ci2 = mn2Cur.precip_intensity, ct2 = mn2Cur.precip_type || 'rain';
        if (ct2 === 'snow') desc = ci2 < 0.10 ? 'Light Snow' : ci2 < 0.30 ? 'Snow' : 'Heavy Snow';
        else if (ct2 === 'sleet') desc = 'Sleet';
        else desc = ci2 < 0.01 ? 'Drizzle' : ci2 < 0.10 ? 'Light Rain' : ci2 < 0.30 ? 'Moderate Rain' : 'Heavy Rain';
      }
    }
  }

  // ── Current temperature (big number + collapsed-tile temp + thermometer mercury) ──
  document.getElementById("currentTemp").innerHTML =
    `${Math.round(data.hyperlocal?.corrected_temp ?? cur.temperature ?? 0)}<span class="temp-unit">°F</span>`;
  const ctc = document.getElementById("currentTempCollapsed");
  if (ctc) {
    const temp = Math.round(data.hyperlocal?.corrected_temp ?? cur.temperature ?? 0);
    ctc.innerHTML = `${temp}<span style="font-size:34px;font-weight:300;color:rgba(0,0,0,0.4);">°</span>`;
    // Thermometer tube spans y=4 (top, 100°F) to y=78 (bottom, 0°F)
    const mercury = document.getElementById("thermometerMercury");
    if (mercury) {
      const clampedTemp = Math.max(0, Math.min(100, temp));
      const mercuryTop = 76 - (clampedTemp / 100) * 72;
      const mercuryHeight = 78 - mercuryTop;
      mercury.setAttribute("y", mercuryTop);
      mercury.setAttribute("height", mercuryHeight);
    }
  }

  // ── Bias confidence indicator (Low / Moderate trigger the badge) ──
  const confEl = document.getElementById("tempConfidence");
  if (confEl) {
    const conf = hyp.confidence;
    const bias = hyp.weighted_bias;
    if ((conf === "Low" || conf === "Moderate") && bias != null) {
      const sign = bias >= 0 ? "+" : "";
      confEl.textContent = `· ${sign}${bias.toFixed(1)}° correction${conf === "Low" ? " — stations disagree" : ""}`;
      confEl.style.color = conf === "Low" ? "rgba(239,68,68,0.85)" : "rgba(234,179,8,0.85)";
      confEl.style.display = "";
    } else {
      confEl.style.display = "none";
    }
  }

  // ── Feels Like (shade AT primary, full-sun AT badge if > +5°F) ──
  const fullSunFL = der.corrected_feels_like ?? null;
  let _shadeAT = der.heat_index ?? null;
  if (_shadeAT == null) {
    const _T = data.hyperlocal?.corrected_temp ?? cur.temperature;
    const _w = (data.hyperlocal?.corrected_wind_speed ?? cur.wind_speed ?? 0) * 0.44704;
    const _rh = data.hyperlocal?.corrected_humidity ?? cur.humidity ?? 50;
    if (_T != null) {
      const _Tc = (_T - 32) * 5 / 9;
      const _e = (_rh / 100) * 6.105 * Math.exp(17.27 * _Tc / (237.7 + _Tc));
      _shadeAT = Math.round((_Tc + 0.33 * _e - 0.70 * _w - 4.00) * 9 / 5 + 32);
    }
  }
  const heatIndex = _shadeAT ?? cur.apparent_temperature ?? 0;
  const feelsLikeEl = document.getElementById("feelsLike");
  feelsLikeEl.textContent = `Feels like ${Math.round(heatIndex)}°F`;
  const flc = document.getElementById("feelsLikeCollapsed");
  if (flc) flc.textContent = `Feels like ${Math.round(heatIndex)}°F`;
  const fsEl = document.getElementById("feelsLikeFullSun");
  if (fsEl) {
    if (fullSunFL != null && fullSunFL > heatIndex + 5) {
      fsEl.textContent = `☀ Full sun: ${Math.round(fullSunFL)}°F`;
      fsEl.style.display = "";
    } else {
      fsEl.style.display = "none";
    }
  }
  wireHyperlocalLink(feelsLikeEl, 'feels_like');

  // ── 10-Day collapsed preview ──
  const tenDayHighEl = document.getElementById("tenDayHigh");
  const tenDayLowEl = document.getElementById("tenDayLow");
  if (tenDayHighEl && tenDayLowEl) {
    tenDayHighEl.textContent = der.today_high != null ? `${Math.round(der.today_high)}°` : `--°`;
    tenDayLowEl.textContent  = der.today_low  != null ? `${Math.round(der.today_low)}°`  : `--°`;
  }

  // ── Condition label (emoji + desc + [obs] tag if KBVY) ──
  const obsTag = cur.condition_source === "KBVY observed" ? " <span style='font-size:0.75rem;opacity:0.5;'>[obs]</span>" : "";
  const condEl2 = document.getElementById("condition");
  condEl2.innerHTML = `${emoji} ${desc}${obsTag}`;
  condEl2.dataset.emoji = emoji;

  // ── Sky & Precip tile preview ──
  const skyConditionEl = document.getElementById("skyConditionCollapsed");
  const skyStatsEl = document.getElementById("skyStatsCollapsed");
  const weatherGraphic = document.getElementById("weatherGraphic");
  if (skyConditionEl) skyConditionEl.textContent = desc;
  if (skyStatsEl) {
    const precipProb = data.hourly?.precipitation_probability?.[0] || 0;
    const cloudCover = data.hourly?.cloud_cover?.[0] || 0;
    let skyText = `${precipProb}% precip`;
    if (cloudCover === 100)     skyText += ` | 100% clouds`;
    else if (cloudCover === 0)  skyText += ` | Clear`;
    else                        skyText += ` | ${Math.round(cloudCover)}% clouds`;
    skyStatsEl.textContent = skyText;
  }

  // ── Weather graphics + background class on Sky/Precip card ──
  if (weatherGraphic) {
    const skyPrecipCard = document.querySelector('[data-collapse-key="48h_temp_precip"]');
    const condition = desc.toLowerCase();
    const now = new Date();
    const sunrise = data.daily?.sunrise?.[0] ? new Date(data.daily.sunrise[0]) : null;
    const sunset  = data.daily?.sunset?.[0]  ? new Date(data.daily.sunset[0])  : null;
    const isDay = sunrise && sunset ? (now >= sunrise && now < sunset) : true;
    const type = matchWeatherType(condition);
    const dayKey = isDay ? 'day' : 'night';
    const weatherClass = type ? `weather-${type}-${dayKey}` : '';
    weatherGraphic.innerHTML = type ? (WEATHER_GRAPHICS[`${type}_${dayKey}`] || '') : '';
    if (skyPrecipCard) {
      skyPrecipCard.classList.remove(...WEATHER_CLASS_LIST);
      if (weatherClass) skyPrecipCard.classList.add(weatherClass);
    }
  }

  renderCorrectionsCard(data);

  // ── Today summary (high / low) ──
  document.getElementById("hiLo").textContent =
    (der.today_high != null && der.today_low != null)
      ? `${Math.round(der.today_high)}° / ${Math.round(der.today_low)}°`
      : "-- / --";

  // ── Precip type + chance ──
  const todayCode = daily.weather_code?.[0] ?? code;
  let precipType = "None";
  if (todayCode >= 95) precipType = "Thunderstorm";
  else if (todayCode >= 85 || (todayCode >= 71 && todayCode <= 77)) precipType = "Snow";
  else if (todayCode >= 66 && todayCode <= 67) precipType = "Freezing Rain";
  else if (todayCode >= 51 && todayCode <= 65) precipType = "Rain";
  const popMax = daily.precipitation_probability_max?.[0];
  const precipChanceVal = popMax != null ? `${Math.round(popMax)}%` : "--%";
  document.getElementById("precipNow").textContent =
    precipType !== "None" ? `${precipType} ${precipChanceVal}` : precipChanceVal;

  // ── Wind Impact now — combined score (sustained if <15mph, gust otherwise) ──
  const windImpactNowEl = document.getElementById("windImpactNow");
  if (windImpactNowEl) {
    const windSpeed = hyp.corrected_wind_speed ?? cur.wind_speed;
    const gustValue = hyp.corrected_wind_gusts ?? cur.wind_gusts;
    const windDir   = cur.wind_direction;
    const windDirStr = windDir != null ? toCompass(windDir, false) : "";
    if (windDir != null && (windSpeed != null || gustValue != null)) {
      const combined = Math.round(combinedWindImpact(windSpeed, gustValue, windDir));
      const level    = worryLevel(combined);
      const spdStr   = windSpeed != null ? `${Math.round(windSpeed)} mph` : "--";
      const gustStr  = gustValue != null ? ` · Gusts ${Math.round(gustValue)} mph` : "";
      windImpactNowEl.innerHTML = `${combined} (${level.label}) · ${windDirStr} ${spdStr}${gustStr}`;
    } else {
      windImpactNowEl.textContent = "--";
    }
  }
  wireHyperlocalLink(windImpactNowEl, 'wind_impact');

  renderWindTile(data);
  renderWindImpactCollapsed(data);

  // ── Right Now grid: pressure / humidity / visibility / dew point / UV ──
  const pressure = hyp.corrected_pressure_in != null ? hyp.corrected_pressure_in + ' inHg' : (cur.pressure != null ? hpaToInhg(cur.pressure) + ' inHg' : "--");
  const trend = der.pressure_trend || kbos.tendency_label || "";
  const trendShort = der.best_pressure_tend != null
    ? (der.best_pressure_tend > 0.5 ? "↑" : der.best_pressure_tend < -0.5 ? "↓" : "")
    : (trend.includes("Rising") ? "↑" : trend.includes("Falling") ? "↓" : "");
  const pressureChange = der.best_pressure_tend != null ? ` ${der.best_pressure_tend > 0 ? '+' : ''}${der.best_pressure_tend.toFixed(1)} hPa` : "";
  document.getElementById("pressureNow").textContent = `${pressure} ${trendShort}${pressureChange}`.trim();

  const displayHumidity = hyp.corrected_humidity ?? cur.humidity;
  document.getElementById("humidityNow").textContent =
    displayHumidity != null ? `${Math.round(displayHumidity)}%` : "--%";

  document.getElementById("visibilityNow").textContent =
    cur.visibility != null ? `${(cur.visibility / 1609.34).toFixed(1)} mi` : "-- mi";

  const _cdp = der.corrected_dew_point ?? cur.dew_point;
  document.getElementById("dewPointNow").textContent = _cdp != null ? `${Math.round(_cdp)}°F` : "--°F";

  const dewDepEl = document.getElementById("dewPointDepression");
  if (_cdp != null) {
    const depression = (hyp.corrected_temp ?? cur.temperature) - _cdp;
    dewDepEl.textContent = ` (${depression.toFixed(1)}° spread)`;
  } else {
    dewDepEl.textContent = "";
  }

  const modelPressEl = document.getElementById("pressureModel");
  if (modelPressEl && cur.pressure != null) {
    modelPressEl.textContent = fmtPressure(cur.pressure);
  }

  document.getElementById("uvNow").textContent =
    cur.uv_index != null ? cur.uv_index.toFixed(1) : "N/A";

  // ── Sea breeze indicator ──
  const sbEl = document.getElementById("seaBreezeNow");
  if (sbEl) {
    if (seaBreeze.likelihood != null) {
      const likelihood = seaBreeze.likelihood;
      let icon = "";
      if (seaBreeze.active) {
        icon = "";
      } else if (likelihood >= 40) {
        icon = "";
      }
      sbEl.innerHTML = `${icon}${likelihood}% ${dim(seaBreeze.reason || "")}`;
    } else {
      sbEl.textContent = "N/A";
    }
  }
  wireHyperlocalLink(sbEl, 'sea_breeze_detail');

  // ── KBOS observed pressure + tendency ──
  const kbosEl = document.getElementById("pressureKBOS");
  if (kbosEl) {
    if (kbos.pressure_hpa != null) {
      const kbDiff = cur.pressure != null
        ? ` (${(kbos.pressure_hpa - cur.pressure) >= 0 ? "+" : ""}${(kbos.pressure_hpa - cur.pressure).toFixed(1)})`
        : "";
      kbosEl.textContent = fmtPressure(kbos.pressure_hpa) + kbDiff;
      kbosEl.title = "Difference from model";
    } else {
      kbosEl.textContent = "--";
    }
  }

  // ── KBOS / KBVY observed temps ──
  const tempObsEl = document.getElementById("tempObsStations");
  if (tempObsEl) {
    const kbosT = kbos.temp_f != null ? kbos.temp_f.toFixed(1) + "°F" : "--";
    const kbvyT = kbvy.temp_f != null ? kbvy.temp_f.toFixed(1) + "°F" : "--";
    tempObsEl.textContent = `${kbosT} / ${kbvyT}`;
  }

  // ── Fog risk ──
  const fogEl = document.getElementById("fogRiskNow");
  if (fogEl) {
    const fogLabel = der.fog_label ?? "--";
    const fogPct   = der.fog_probability;
    fogEl.textContent = fogPct != null ? `${fogLabel} (${fogPct}% chance)` : fogLabel;
    fogEl.style.color = fogLabel === "Likely"     ? "rgba(255,220,80,0.9)"
                      : fogLabel === "Possible"   ? "rgba(255,200,100,0.85)"
                      : fogLabel === "Low chance" ? "rgba(200,200,200,0.7)"
                      : "rgba(255,255,255,0.85)";
  }
  wireHyperlocalLink(fogEl, 'fog_risk');

  // ── Lifestyle scores (read from globals set by earlier render calls) ──
  const sunsetScoreEl = document.getElementById("sunsetScoreNow");
  if (sunsetScoreEl) {
    if (window.__todaySunsetScore) {
      const s = window.__todaySunsetScore;
      sunsetScoreEl.innerHTML = `${s.label} ${dim(`(${Math.round(s.score)}/100)`)}`;
      sunsetScoreEl.style.color = s.color;
    } else {
      sunsetScoreEl.textContent = "No data";
    }
  }

  const dockDayScoreEl = document.getElementById("swimFloatScoreNow");
  if (dockDayScoreEl && window.__todayDockScore) {
    const dockAfter6 = new Date().getHours() >= 18;
    const d = (dockAfter6 && window.__tomorrowDockScore) ? window.__tomorrowDockScore : window.__todayDockScore;
    dockDayScoreEl.innerHTML = `${d.label} ${dim(`(${Math.round(d.score * 100)}/100)`)}`;
    dockDayScoreEl.style.color = d.color;
  } else if (dockDayScoreEl) {
    dockDayScoreEl.textContent = "No data";
  }

  wireHyperlocalLink(sunsetScoreEl, 'sunset_quality', 'hyperlocal');
  wireHyperlocalLink(dockDayScoreEl, 'swim_float',     'hyperlocal');

  const hairDayNowEl = document.getElementById("hairDayNow");
  if (hairDayNowEl && window.__todayHairScore) {
    const hairAfter6 = new Date().getHours() >= 18;
    const h = (hairAfter6 && window.__tomorrowHairScore) ? window.__tomorrowHairScore : window.__todayHairScore;
    hairDayNowEl.innerHTML = `${h.scoreLabel} ${dim(`(${h.score}/100)`)}`;
    hairDayNowEl.style.color = h.color;
    wireHyperlocalLink(hairDayNowEl, 'hair_day', 'hyperlocal');
  } else if (hairDayNowEl) {
    hairDayNowEl.textContent = "No data";
  }
}
