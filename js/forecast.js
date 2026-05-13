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
    
    // Extract precip probability
    const combinedText = isSimple ? period.text : ((dayPeriod?.text || "") + " " + (nightPeriod?.text || ""));
    const precipMatch = (combinedText || "").match(/\((\d+)%\)/);
    const pop = precipMatch ? parseInt(precipMatch[1]) : 0;
    
    const text = (combinedText || "").toLowerCase();
    let emoji = "☀️";
    if (text.includes("thunder")) emoji = "⛈️";
    else if (text.includes("snow")) emoji = "🌨️";
    else if (text.includes("rain")) emoji = "🌧️";
    else if (text.includes("fog")) emoji = "🌥️";
    else if (text.includes("overcast") || text.includes("mostly cloudy")) emoji = "☁️";
    else if (text.includes("partly cloudy")) emoji = "⛅";
    
    const date = new Date(dateStr + "T00:00:00");
    const day = date.toLocaleDateString("en-US", { weekday: "short" });
    const dateNum = date.toLocaleDateString("en-US", { month:"numeric", day:"numeric" });
    
    days.push({ dateStr, day, dateNum, high, low, emoji, pop });
    
    if (days.length >= 10) break;
  }

  // Render 10 daily rows
  for (const d of days) {
    const row = document.createElement("div");
    row.className = "row forecast-day-row";
    row.dataset.date = d.dateStr;
    row.style.cssText = "border-radius:8px;margin:0 -6px;padding:7px 6px;";

    // Click handler removed - days are no longer clickable

    row.innerHTML = `
      <div class="label" style="display:flex;align-items:center;gap:8px;">
        <span style="font-weight:600;min-width:32px;">${d.day}</span>
        <span style="font-size:0.82rem;color:rgba(255,255,255,0.35);">${d.dateNum}</span>
        <span style="font-size:16px;">${d.emoji}</span>
        ${d.pop > 10 ? `<span style="font-size:0.75rem;color:rgba(140,180,255,0.7);font-weight:600;">${d.pop}%</span>` : ""}
      </div>
      <div class="value">${d.high}° <span class="temp-lo" style="opacity:0.4;font-weight:400;">/ ${d.low}°</span></div>`;

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
