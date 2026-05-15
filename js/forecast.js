// forecast.js — NWS 10-day forecast card


let _selectedForecastDate = null;

function renderForecast(forecastText, hourlyTimes, hourlyTemps, derived) {
  const el = document.getElementById("forecastList");
  if (!el || !Array.isArray(forecastText)) return;
  el.innerHTML = "";

  // Group forecast_text into 10 days (combine day/night periods into single row)
  const days = [];
  const seenDates = new Set();

  // Use corrected daily high/low from collector (single source of truth)
  const _now = new Date();
  const _pad = n => String(n).padStart(2, '0');
  const _dateStr = d => `${d.getFullYear()}-${_pad(d.getMonth()+1)}-${_pad(d.getDate())}`;
  const _todayStr = _dateStr(_now);
  const _tom = new Date(_now); _tom.setDate(_tom.getDate() + 1);
  const _tomorrowStr = _dateStr(_tom);
  const _correctedDays = {};
  if (derived.today_high != null) _correctedDays[_todayStr] = { high: derived.today_high, low: derived.today_low };
  if (derived.tomorrow_high != null) _correctedDays[_tomorrowStr] = { high: derived.tomorrow_high, low: derived.tomorrow_low };
  
  for (const period of forecastText) {
    const dateStr = period.date;
    
    if (seenDates.has(dateStr)) continue;
    seenDates.add(dateStr);
    
    // Find day and night periods for this date
    const dayPeriod = forecastText.find(p => p.date === dateStr && p.is_daytime);
    const nightPeriod = forecastText.find(p => p.date === dateStr && !p.is_daytime);
    
    // For simple dailies, just use the single period
    const isSimple = period.is_simple_daily;
    
    let high = isSimple ? period.temperature : (dayPeriod?.temperature || period.temperature);
    let low = isSimple ? parseInt((period.text || "").match(/low (\d+)/)?.[1] || period.temperature) : (nightPeriod?.temperature || period.temperature);
    // Use corrected hourly high/low for today and tomorrow
    if (_correctedDays[dateStr]) {
      high = Math.round(_correctedDays[dateStr].high);
      low  = Math.round(_correctedDays[dateStr].low);
    }
    
    // Extract precip probability — use structured field, fall back to regex on text
    const combinedText = isSimple ? period.text : ((dayPeriod?.text || "") + " " + (nightPeriod?.text || ""));
    const _dayPop = dayPeriod?.precip_probability ?? null;
    const _nightPop = nightPeriod?.precip_probability ?? null;
    const _simplePop = period.precip_probability ?? null;
    let pop = 0;
    if (isSimple) {
      pop = _simplePop ?? parseInt((combinedText || "").match(/\((\d+)%\)/)?.[1] || "0");
    } else {
      pop = Math.max(_dayPop ?? 0, _nightPop ?? 0);
      if (pop === 0) pop = parseInt((combinedText || "").match(/\((\d+)%\)/)?.[1] || "0");
    }

    const text = (combinedText || "").toLowerCase();
    let emoji = "☀️";
    if (text.includes("thunder")) emoji = "⛈️";
    else if (text.includes("snow")) emoji = "🌨️";
    else if (text.includes("rain")) emoji = "🌧️";
    else if (text.includes("fog")) emoji = "🌥️";
    else if (text.includes("overcast") || text.includes("mostly cloudy")) emoji = "☁️";
    else if (text.includes("partly cloudy")) emoji = "⛅";

    // Wind label — show only when Breezy or worse
    const _windRank = { "Calm": 0, "Light winds": 1, "Breezy": 2, "Windy": 3, "Very windy": 4 };
    let windLabel = "";
    if (!isSimple) {
      const labels = [dayPeriod?.wind_worry_label, nightPeriod?.wind_worry_label].filter(Boolean);
      const worst = labels.reduce((a, b) => (_windRank[b] ?? 0) > (_windRank[a] ?? 0) ? b : a, "Calm");
      if ((_windRank[worst] ?? 0) >= 2) windLabel = worst;
    } else {
      if (text.includes("very windy")) windLabel = "Very windy";
      else if (text.includes("windy")) windLabel = "Windy";
      else if (text.includes("breezy")) windLabel = "Breezy";
    }

    const date = new Date(dateStr + "T00:00:00");
    const day = date.toLocaleDateString("en-US", { weekday: "short" });
    const dateNum = date.toLocaleDateString("en-US", { month:"numeric", day:"numeric" });

    days.push({ dateStr, day, dateNum, high, low, emoji, pop, windLabel });

    if (days.length >= 10) break;
  }

  // Render 10 daily rows
  for (const d of days) {
    const row = document.createElement("div");
    row.className = "forecast-day-row";
    row.dataset.date = d.dateStr;
    row.style.cssText = "display:flex;align-items:flex-start;gap:10px;border-radius:8px;margin:0 -6px;padding:8px 6px;";

    row.innerHTML = `
      <div style="display:flex;align-items:center;gap:6px;min-width:108px;padding-top:2px;">
        <span style="font-weight:600;min-width:32px;">${d.day}</span>
        <span style="font-size:0.82rem;opacity:0.35;">${d.dateNum}</span>
        <span style="font-size:16px;">${d.emoji}</span>
      </div>
      <div style="flex:1;min-width:0;padding-top:5px;">
        <div style="display:flex;align-items:center;gap:6px;">
          <div style="flex:1;height:3px;border-radius:2px;background:var(--fc-bar-track);overflow:hidden;">
            <div class="fc-precip-fill" style="height:100%;width:${d.pop}%;border-radius:2px;"></div>
          </div>
          <span class="fc-pop-pct" style="font-size:0.72rem;font-weight:600;width:34px;text-align:right;">${d.pop > 10 ? d.pop + "%" : ""}</span>
        </div>
        ${d.windLabel ? `<div class="fc-wind-label" style="font-size:0.7rem;opacity:0.45;margin-top:4px;">${d.windLabel}</div>` : ""}
      </div>
      <div style="white-space:nowrap;font-weight:600;padding-top:1px;">${d.high}°<span class="temp-lo" style="opacity:0.4;font-weight:400;"> / ${d.low}°</span></div>`;

    el.appendChild(row);
  }

  updateForecastSelection();

  // Hint
}

function selectForecastDay(dateStr) {
  if (_selectedForecastDate === dateStr) {
    // Deselect — show all periods
    _selectedForecastDate = null;
    filterHyperlocalByDate(null);
  } else {
    _selectedForecastDate = dateStr;
    filterHyperlocalByDate(dateStr);
    // Auto-expand Wyman Cove card
    const card = document.querySelector('[data-collapse-key="hyperlocal_forecast"]');
    if (card) {
      const body = card.querySelector(".card-body");
      const title = card.querySelector(".card-title-collapsible");
      if (body && body.style.display === "none") {
        body.style.display = "";
        if (title) {
          const chev = title.querySelector(".collapse-chevron");
          if (chev) chev.style.transform = "rotate(180deg)";
        }
        try { localStorage.setItem("collapse_hyperlocal_forecast", "open"); } catch(e) {}
      }
      // Scroll into view
      setTimeout(() => card.scrollIntoView({ behavior:"smooth", block:"nearest" }), 100);
    }
  }
  updateForecastSelection();
}

function updateForecastSelection() {
  document.querySelectorAll(".forecast-day-row").forEach(row => {
    const isSelected = row.dataset.date === _selectedForecastDate;
    row.style.background = isSelected ? "rgba(100,160,255,0.12)" : "";
  });

  

}

function filterHyperlocalByDate(dateStr) {
  const list = document.getElementById("hyperlocalForecastList");
  if (!list) return;

  const rows = list.querySelectorAll("div[style*='grid-template-columns']");
  
  if (!dateStr) {
    // No filter - show all rows
    rows.forEach(row => row.style.display = "");
    return;
  }

  // Filter to show only periods matching the selected date
  if (!window._currentForecastText) {
    rows.forEach(row => row.style.display = "");
    return;
  }

  // Get all periods for the selected date
  const matchingPeriods = window._currentForecastText.filter(p => p.date === dateStr);
  const matchingNames = new Set(matchingPeriods.map(p => p.period_name));

  // Show/hide rows based on period name match
  rows.forEach((row, idx) => {
    const period = window._currentForecastText[idx];
    row.style.display = (period && matchingNames.has(period.period_name)) ? "" : "none";
  });
}

function generateForecastSummary(forecasts) {
  const summaryEl = document.getElementById("detailedForecastSummary");
  if (!summaryEl || !forecasts || forecasts.length === 0) return;
  
  // Get first period (should be "Today" or current period)
  const today = forecasts[0];
  if (!today || !today.text) {
    summaryEl.textContent = "Check forecast...";
    return;
  }
  
  // Extract first sentence (up to first period)
  const firstSentence = today.text.split('.')[0].trim();
  
  // Add ellipsis
  summaryEl.textContent = firstSentence + "...";
}

function renderHyperlocalForecast(forecasts, hourlyTimes, hourlyTemps, derived) {
  const list = document.getElementById("hyperlocalForecastList");
  if (!list || !Array.isArray(forecasts) || forecasts.length === 0) {
    if (list) list.innerHTML = '<div style="color:rgba(255,255,255,0.4);font-size:0.88rem;padding:8px 0;">No forecast available.</div>';
    return;
  }

  // Generate short summary for collapsed preview
  generateForecastSummary(forecasts);

  list.innerHTML = "";
  
  // Use corrected daily high/low from collector (single source of truth)
  const _now = new Date();
  const _pad = n => String(n).padStart(2, "0");
  const _ds = d => `${d.getFullYear()}-${_pad(d.getMonth()+1)}-${_pad(d.getDate())}`;
  const _todayStr = _ds(_now);
  const _tom = new Date(_now); _tom.setDate(_tom.getDate() + 1);
  const _tomorrowStr = _ds(_tom);
  const _fcCorrected = {};
  if (derived.today_high != null) _fcCorrected[_todayStr] = { high: derived.today_high, low: derived.today_low };
  if (derived.tomorrow_high != null) _fcCorrected[_tomorrowStr] = { high: derived.tomorrow_high, low: derived.tomorrow_low };

  forecasts.forEach((p, i) => {
    const row = document.createElement("div");
    row.className = "detailed-period";

    // Use wind data from forecast object
    let windText = p.wind_full || "";

    row.innerHTML =
      '<div class="detailed-period-header">' +
        '<span class="detailed-period-name">' + p.period_name + '</span>' +
        '<span class="detailed-period-temp">' + 
          (p.date && _fcCorrected[p.date] ? Math.round(p.is_daytime ? _fcCorrected[p.date].high : _fcCorrected[p.date].low) : p.temperature) +
        '\u00b0F</span>' +
      '</div>' +
      (windText ? '<div class="detailed-period-wind">' + windText + '</div>' : '') +
      '<div class="detailed-period-narrative">' + p.text + '</div>';

    list.appendChild(row);
  });
}
