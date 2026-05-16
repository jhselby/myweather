// hair.js — Hair day forecast card
function wineScaleHair(raw) { return Math.max(50, Math.min(100, Math.round(50 + 50 * Math.pow(Math.max(0, raw) / 100, 0.6)))); }

function renderHairDay(data) {
  window.__lastWeatherData = data;
  const el = document.getElementById("hairDayContent");
  if (!el) return;

  const hourly  = data.hourly || {};
  const htimes  = hourly.times || [];
  const hhumid  = hourly.corrected_humidity || hourly.humidity || [];
  const htemp   = hourly.corrected_temperature || hourly.temperature || [];
  const hdp     = hourly.corrected_dew_point || hourly.dew_point || [];
  const hah     = hourly.corrected_absolute_humidity || [];
  const hwind   = hourly.wind_gusts || [];  // gusts rip styled hair; sustained just moves it
  const hprecip = hourly.precipitation_probability || [];
  const hcode   = hourly.weather_code || [];
  const hpamt   = hourly.precipitation || [];



  // --- Precip type from WMO weather code ---
  function precipType(code) {
    if (code == null) return null;
    if ((code >= 71 && code <= 77) || code === 85 || code === 86) return "Snow";
    if (code === 66 || code === 67) return "Freezing rain";
    if (code >= 51 && code <= 67) return "Rain";
    if (code >= 80 && code <= 84) return "Showers";
    if (code >= 95) return "Thunderstorm";
    return null;
  }


  // --- Hair type profiles ---
  const HAIR_PROFILES = {
    straight: {
      label: "Straight",
      // Straight hair goes limp in humidity, static in dry air
      scoreAH(ah) {
        if (ah == null) return 70;
        if (ah < 2)    return 45;  // static, flyaways
        if (ah < 4)    return 85;
        if (ah < 5)    return 95;  // sweet spot
        if (ah < 6)    return 90;
        if (ah < 7)    return 80;
        if (ah < 10)   return 65;  // getting limp
        if (ah < 14)   return 45;
        if (ah < 17)   return 30;
        return 15;
      },
      windThreshold: 28,  // straight hair handles wind better
      weights: { ah: 0.55, precip: 0.30, wind: 0.15 },
      dryWarning: "Very dry — static and flyaways likely",
      humidWarning: "High humidity — hair may fall flat"
    },
    wavy: {
      label: "Wavy",
      scoreAH(ah) {
        if (ah == null) return 70;
        if (ah < 2)    return 55;
        if (ah < 4)    return 82;
        if (ah < 5)    return 92;
        if (ah < 6)    return 85;
        if (ah < 7)    return 75;
        if (ah < 10)   return 55;
        if (ah < 14)   return 30;
        if (ah < 17)   return 15;
        return 5;
      },
      windThreshold: 22,
      weights: { ah: 0.60, precip: 0.25, wind: 0.15 },
      dryWarning: "Very dry — waves may lose definition",
      humidWarning: "Humid — frizz and puffiness likely"
    },
    curly: {
      label: "Curly",
      scoreAH(ah) {
        if (ah == null) return 70;
        if (ah < 2)    return 50;
        if (ah < 4)    return 72;
        if (ah < 5)    return 88;
        if (ah < 6)    return 80;
        if (ah < 7)    return 68;
        if (ah < 10)   return 45;
        if (ah < 14)   return 22;
        if (ah < 17)   return 10;
        return 5;
      },
      windThreshold: 20,
      weights: { ah: 0.70, precip: 0.20, wind: 0.10 },
      dryWarning: "Very dry — curls may lose definition and frizz",
      humidWarning: "Humid — frizz and volume expansion likely"
    },
    coily: {
      label: "Coily",
      // Coily hair needs moisture — dry air is the enemy
      scoreAH(ah) {
        if (ah == null) return 70;
        if (ah < 2)    return 25;  // very bad — shrinkage, breakage
        if (ah < 4)    return 55;
        if (ah < 5)    return 75;
        if (ah < 6)    return 88;
        if (ah < 7)    return 92;  // sweet spot is higher
        if (ah < 10)   return 85;
        if (ah < 14)   return 70;
        if (ah < 17)   return 55;
        return 40;
      },
      windThreshold: 18,  // more fragile
      weights: { ah: 0.75, precip: 0.15, wind: 0.10 },
      dryWarning: "Very dry — risk of breakage and excess shrinkage",
      humidWarning: "Humid but manageable — seal ends well"
    }
  };

  function getHairType() {
    try { return localStorage.getItem("hairType") || "curly"; } catch(e) { return "curly"; }
  }
  function setHairType(t) {
    try { localStorage.setItem("hairType", t); } catch(e) {}
  }
  const hairProfile = HAIR_PROFILES[getHairType()];

  // --- AH-based scoring (inverted U — sweet spot 4-5 g/m³) ---
  // Too dry (<2) = flyaways/static. Too humid (>14) = frizz.
  // Based on curly hair expert consensus: dew point 35-50°F is optimal.
  function scoreAH(ah) {
    if (ah == null) return 70;
    if (ah < 2)    return 60;  // very dry — flyaways, static
    if (ah < 4)    return 78;  // dry but okay
    if (ah < 5)    return 95;  // sweet spot
    if (ah < 6)    return 88;
    if (ah < 7)    return 80;
    if (ah < 10)   return 60;
    if (ah < 14)   return 35;
    if (ah < 17)   return 15;
    return 5;                  // tropical, brutal
  }

  // --- Precip scoring — type matters ---
  // Snow/freezing rain penalized more heavily than rain
  function scorePrecip(pop, type, amtMm) {
    if (pop == null) return 80;
    let typeMultiplier = 1.0;
    if (type === "Snow" || type === "Freezing rain") typeMultiplier = 1.4;
    const intensity = amtMm != null && amtMm > 5 ? 1.2 : 1.0; // heavy precip extra penalty
    const baseScore = pop < 10  ? 100 :
                      pop < 25  ? 78  :
                      pop < 50  ? 50  :
                      pop < 75  ? 25  : 8;
    return Math.max(5, Math.round(baseScore / (typeMultiplier * intensity)));
  }

  // --- Wind scoring — tuned for curly hair ---
  // Score based on how late in the day wind first crosses threshold.
  // Later bad wind = better score (more of the day happens before ruin).
  // badStartHour is the first hour (6-20) where sustained wind >= 15 mph.
  // Returns null-equivalent 100 if wind stays calm all day.
  const WIND_THRESHOLD_MPH = hairProfile.windThreshold;  // gust threshold (sustained-equivalent ~14-15 mph)
  function scoreWind(badStartHour) {
    if (badStartHour == null) return 100;   // calm all day
    if (badStartHour >= 18)    return 95;   // late evening — day was fine
    if (badStartHour >= 13)    return 80;   // afternoon — morning was good
    if (badStartHour >= 10)    return 60;   // mid-morning — styling window was clean
    if (badStartHour >= 7)     return 35;   // early morning — day ruined from start
    return 20;                              // windy from wake-up
  }

  function labelFor(score) {
    if (score >= 88) return { label: "Great hair day", emoji: "💁",  color: "rgba(100,220,130,0.95)" };
    if (score >= 74) return { label: "Good hair day",  emoji: "😊",  color: "rgba(130,210,100,0.95)" };
    if (score >= 58) return { label: "Manageable",     emoji: "🤷",  color: "rgba(200,190,80,0.95)"  };
    if (score >= 40) return { label: "Frizz risk",     emoji: "😬",  color: "rgba(220,150,60,0.95)"  };
    if (score >= 25) return { label: "Bad hair day",   emoji: "😤",  color: "rgba(220,100,60,0.95)"  };
    return             { label: "Stay inside",         emoji: "🙈",  color: "rgba(200,60,60,0.95)"   };
  }

  // --- Hour weight for morning-biased aggregation ---
  function hourWeight(hr) {
    if (hr >= 6  && hr < 10) return 3.0;  // styling window
    if (hr >= 10 && hr < 14) return 1.0;
    if (hr >= 14 && hr <= 20) return 0.5;
    return 0;
  }

  function aggregateDay(dateStr) {
    let sumDp = 0, sumAH = 0, sumRH = 0, sumTemp = 0;
    let sumPrecip = 0, sumPrecipAmt = 0, totalW = 0;
    let peakMorningDp = null;
    let peakWind = 0;
    let morningWindSum = 0, morningWindW = 0;
    let dominantCode = null, maxCodeW = 0;

    for (let i = 0; i < htimes.length; i++) {
      if (!htimes[i] || !htimes[i].startsWith(dateStr)) continue;
      const hr = new Date(htimes[i]).getHours();
      const w  = hourWeight(hr);
      if (w === 0) continue;

      const dp  = hdp[i] ?? null;
      const ah  = hah[i] ?? null;

      if (dp   != null) { sumDp   += dp   * w; }
      if (ah   != null) { sumAH   += ah   * w; }
      if (hhumid[i] != null) { sumRH   += hhumid[i] * w; }
      if (htemp[i]  != null) { sumTemp  += htemp[i]  * w; }
      totalW += w;

      if (hprecip[i] != null) sumPrecip    += hprecip[i] * w;
      if (hpamt[i]   != null) sumPrecipAmt += hpamt[i]   * w;

      // Dominant weather code by weight
      if (hcode[i] != null && w > maxCodeW) { dominantCode = hcode[i]; maxCodeW = w; }

      const wind = hwind[i];
      if (wind != null) {
        if (wind > peakWind) peakWind = wind;
        if (hr >= 6 && hr < 10) { morningWindSum += wind; morningWindW++; }
      }

      if (hr >= 6 && hr < 10 && dp != null) {
        if (peakMorningDp === null || dp > peakMorningDp) peakMorningDp = dp;
      }
    }

    if (totalW === 0) return null;

    const avgDp       = sumDp    / totalW;
    const avgAH       = sumAH    / totalW;
    const avgRH       = sumRH    / totalW;
    const avgPrecip   = sumPrecip / totalW;
    const avgPrecipAmt= sumPrecipAmt / totalW;
    const morningGust = morningWindW > 0 ? morningWindSum / morningWindW : peakWind;
    const pType       = precipType(dominantCode);

    // --- Walk hours 6-20 to find wind crossover and restyle window ---
    let badStartHour = null;
    const hoursOfDay = [];  // [{hr, wind}] for 6-20 on this date
    for (let i = 0; i < htimes.length; i++) {
      if (!htimes[i] || !htimes[i].startsWith(dateStr)) continue;
      const hr = new Date(htimes[i]).getHours();
      if (hr < 6 || hr > 20) continue;
      hoursOfDay.push({ hr, wind: hwind[i] });
    }
    hoursOfDay.sort((a, b) => a.hr - b.hr);

    for (const h of hoursOfDay) {
      if (h.wind != null && h.wind >= WIND_THRESHOLD_MPH) { badStartHour = h.hr; break; }
    }

    // Restyle window: 2+ consecutive calm hours after badStart, before 7pm
    let restyleWindow = null;
    if (badStartHour != null) {
      let winStart = null, winEnd = null;
      for (const h of hoursOfDay) {
        if (h.hr <= badStartHour || h.hr >= 19) continue;
        if (h.wind != null && h.wind < WIND_THRESHOLD_MPH) {
          if (winStart == null) winStart = h.hr;
          winEnd = h.hr;
        } else {
          if (winStart != null && (winEnd - winStart) >= 1) break;  // had a window, it ended
          winStart = null; winEnd = null;
        }
      }
      if (winStart != null && winEnd != null && (winEnd - winStart) >= 1) {
        restyleWindow = { start: winStart, end: winEnd };
      }
    }

    return { avgDp, avgAH, avgRH, avgPrecip, avgPrecipAmt, pType,
             peakMorningDp, morningGust, peakGust: peakWind,
             badStartHour, restyleWindow };
  }

  // --- Build day objects ---
  const now = new Date();
  const days = [];

  for (let d = 0; d <= 2; d++) {
    const date = new Date(now);
    date.setDate(date.getDate() + d);
    const dateStr   = `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`;
    const dayName   = d === 0 ? "Today" : d === 1 ? "Tomorrow"
                    : date.toLocaleDateString("en-US", { weekday: "long" });
    const dateLabel = date.toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric" });

    const agg = aggregateDay(dateStr);
    if (!agg) continue;

    const ahScore     = hairProfile.scoreAH(agg.avgAH);
    const precipScore = scorePrecip(agg.avgPrecip, agg.pType, agg.avgPrecipAmt);
    const windScore   = scoreWind(agg.badStartHour);
    const rhPenalty    = agg.avgRH == null ? 1.0 : agg.avgRH > 90 ? 0.65 : agg.avgRH > 80 ? 0.80 : agg.avgRH > 70 ? 0.92 : 1.0;
    const score       = Math.round((ahScore * hairProfile.weights.ah + precipScore * hairProfile.weights.precip + windScore * hairProfile.weights.wind) * rhPenalty);
    const lf          = labelFor(score);

    // Flags
    const morningWarning = agg.peakMorningDp != null && agg.peakMorningDp >= 60
      ? `Dew point peaks ${Math.round(agg.peakMorningDp)}°F in morning — style before going out`
      : (agg.avgAH != null && agg.avgAH < 2
      ? hairProfile.dryWarning
      : null);

    // --- Composed wind flag ---
    function fmtHr(h) {
      const ampm = h >= 12 ? "pm" : "am";
      const h12  = h === 0 ? 12 : h > 12 ? h - 12 : h;
      return `${h12}${ampm}`;
    }
    let windFlag = null;
    if (agg.badStartHour != null) {
      if (agg.restyleWindow) {
        windFlag = `Windy from ${fmtHr(agg.badStartHour)}, calms ${fmtHr(agg.restyleWindow.start)}–${fmtHr(agg.restyleWindow.end)} — restyle opportunity`;
      } else if (agg.badStartHour >= 13) {
        windFlag = `Wind picks up after ${fmtHr(agg.badStartHour)}`;
      } else {
        windFlag = `Windy from ${fmtHr(agg.badStartHour)} — tough day for hair`;
      }
    }

    days.push({
      label: dayName, dateLabel,
      avgAH: agg.avgAH, avgRH: agg.avgRH, avgDp: agg.avgDp,
      avgPrecip: agg.avgPrecip, pType: agg.pType,
      morningGust: agg.morningGust,
      score, scoreLabel: lf.label, emoji: lf.emoji, color: lf.color,
      morningWarning, windFlag
    });
  }

  if (!days.length) { el.innerHTML = '<div style="opacity:0.5;">No forecast data available</div>'; return; }

  // Store today and tomorrow for Right Now / Briefing cards
  window.__todayHairScore = days[0];
  if (days.length > 1) window.__tomorrowHairScore = days[1];

  // Update collapsed preview — after 6 PM show tomorrow
  const hairNow = new Date(); const hairSunsetStr = data.daily?.sunset?.[0]; const afterCutoff = hairSunsetStr ? hairNow > new Date(new Date(hairSunsetStr).getTime() + 2 * 3600000) : hairNow.getHours() >= 18;
  const showDay = (afterCutoff && days.length > 1) ? days[1] : days[0];
  const showDayLabel = (afterCutoff && days.length > 1) ? "Tomorrow" : "Today";
  const emojiEl = document.getElementById("hairDayEmojiCollapsed");
  const labelEl = document.getElementById("hairDayLabelCollapsed");
  const scoreEl = document.getElementById("hairDayScoreCollapsed");
  if (emojiEl) emojiEl.textContent = showDay.emoji;
  if (labelEl) { labelEl.textContent = showDay.scoreLabel; labelEl.style.color = showDay.color; }
  if (scoreEl) scoreEl.textContent = `${showDayLabel}: ${wineScaleHair(showDay.score)}/100`;

  // --- Headline ---
  function hairHeadline(day) {
    const ah = day.avgAH;
    let reason;
    if (ah == null)     reason = "";
    else if (ah < 2)    reason = " — very dry, watch for static";
    else if (ah < 5)    reason = " — dry air, great conditions";
    else if (ah < 7)    reason = " — comfortable moisture";
    else if (ah < 10)   reason = " — humidity building";
    else if (ah < 14)   reason = " — humid, frizz likely";
    else                reason = " — very humid, frizz certain";
    return `${day.scoreLabel}${reason}`;
  }

  // --- Day card ---
  function dayCard(day, isToday) {
    const ahVal   = day.avgAH   != null ? day.avgAH.toFixed(1) + " g/m³"  : "--";
    const rhVal   = day.avgRH   != null ? Math.round(day.avgRH) + "%"               : "--";
    const rainVal = day.avgPrecip != null
      ? Math.round(day.avgPrecip) + "%" + (day.pType ? " · " + day.pType : "")
      : "--";
    const gustVal = day.morningGust != null ? Math.round(day.morningGust) + " mph"  : "--";

    // AH bar: 0–20 g/m³ range, peak (green) at 4-5 g/m³
    const ahBarPct = day.avgAH != null ? Math.max(0, Math.min(100, Math.round(day.score))) : 50;
    const ahBarColor = ahBarPct >= 80 ? "rgba(100,210,120,0.7)" : ahBarPct >= 55 ? "rgba(200,180,60,0.7)" : "rgba(210,80,60,0.7)";

    const flags = [day.morningWarning, day.windFlag].filter(Boolean);
    const flagsHtml = flags.length
      ? flags.map(f => `<div style="font-size:0.68rem;margin-top:6px;padding:4px 8px;background:rgba(255,200,80,0.1);border-left:2px solid rgba(255,200,80,0.5);border-radius:0 4px 4px 0;opacity:0.85;">${f}</div>`).join("")
      : "";

    return `
      <div style="background:rgba(255,255,255,${isToday ? "0.06" : "0.03"});border:1px solid rgba(255,255,255,${isToday ? "0.14" : "0.07"});border-radius:10px;padding:12px 10px;display:flex;flex-direction:column;align-items:center;min-width:0;">
        <div style="font-size:0.78rem;font-weight:700;margin-bottom:2px;opacity:${isToday ? "1" : "0.7"};">${day.label}</div>
        <div style="font-size:0.68rem;opacity:0.45;margin-bottom:6px;">${day.dateLabel}</div>
        <div style="font-size:2rem;line-height:1;margin-bottom:4px;">${day.emoji}</div>
        <div style="font-size:0.8rem;font-weight:600;color:${day.color};text-align:center;margin-bottom:8px;">${day.scoreLabel}</div>
        <div style="font-size:1.4rem;font-weight:300;margin-bottom:6px;">${wineScaleHair(day.score)}<span style="font-size:0.65rem;opacity:0.5;">/100</span></div>
        <div style="width:100%;display:flex;align-items:center;gap:4px;margin-bottom:12px;">
          <span style="font-size:0.6rem;opacity:0.3;flex-shrink:0;">0</span>
          <div style="flex:1;background:rgba(255,255,255,0.08);border-radius:3px;height:4px;overflow:hidden;">
            <div style="width:${day.score}%;height:100%;background:${day.color};border-radius:3px;"></div>
          </div>
          <span style="font-size:0.6rem;opacity:0.3;flex-shrink:0;">100</span>
        </div>
        <div style="width:100%;font-size:0.7rem;display:grid;grid-template-columns:auto 1fr;gap:3px 0;">
          <span style="opacity:0.5;">RH</span><span style="font-weight:600;text-align:right;">${rhVal}</span>
          <span style="opacity:0.5;">AH</span><span style="font-weight:600;text-align:right;">${ahVal}</span>
          <span style="opacity:0.5;">Rain</span><span style="font-weight:600;text-align:right;">${rainVal}</span>
          <span style="opacity:0.5;line-height:1.3;">Morning<br>Gust</span><span style="font-weight:600;text-align:right;">${gustVal}</span>
        </div>
        ${flagsHtml}
      </div>`;
  }

  const today = days[0];
  const headline = hairHeadline(today);
  const currentType = getHairType();
  const selectorHtml = `<div style="display:flex;gap:6px;margin-bottom:14px;justify-content:center;">` +
    Object.keys(HAIR_PROFILES).map(k => {
      const p = HAIR_PROFILES[k];
      const active = k === currentType;
      return `<button onclick="event.stopPropagation(); localStorage.setItem('hairType','${k}'); renderHairDay(window.__lastWeatherData);"
        style="padding:5px 12px;border-radius:999px;border:1px solid ${active ? 'rgba(255,255,255,0.4)' : 'rgba(255,255,255,0.12)'};
        background:${active ? 'rgba(255,255,255,0.15)' : 'rgba(255,255,255,0.04)'};
        color:${active ? 'rgba(255,255,255,0.95)' : 'rgba(255,255,255,0.5)'};
        font-size:0.72rem;font-weight:${active ? '700' : '500'};cursor:pointer;
        transition:all 0.2s;">${p.label}</button>`;
    }).join("") + `</div>`;
  el.innerHTML =
    selectorHtml +
    `<div style="font-size:0.95rem;font-weight:600;color:${today.color};margin-bottom:14px;padding:10px 14px;background:rgba(255,255,255,0.04);border-radius:0;border-left:4px solid ${today.color};">${headline}</div>` +
    `<div style="display:grid;grid-template-columns:repeat(${days.length},1fr);gap:8px;margin-bottom:12px;">` +
    days.map((d, i) => dayCard(d, i === 0)).join("") +
    `</div>`;
}
