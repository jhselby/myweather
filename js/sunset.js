// sunset.js — Sunset quality forecast card
// Uses SunCalc sunset times + cloud data fetched by collector

// ======================================================
// Sunset Quality Forecast
// Algorithm based on SunsetWx methodology:
//   Score = mid_cloud × (1 - low_cloud_penalty) × humidity_factor
// Best sunsets: 30-70% mid/high cloud, <20% low cloud, dry air
// ======================================================
function renderSunsetQuality(data) {
  const el = document.getElementById("sunsetQualityContent");
  if (!el) return;

  const sunsetDir = data.sunset_directional || [];
  
  if (!sunsetDir.length) {
    el.innerHTML = `<div style="color:rgba(255,255,255,0.4);font-size:0.85rem;">Sunset data unavailable</div>`;
    return;
  }

  const scores = [];
  
  for (const day of sunsetDir) {
    const clouds = day.clouds || {};
    const cloud10 = clouds['10mi'];
    const cloud25 = clouds['25mi'];
    const cloud50 = clouds['50mi'];
    
    // Need at least one distance to calculate score
    if (!cloud10 && !cloud25 && !cloud50) continue;
    
    // Use the first available cloud data for timing
    const timeSource = cloud25 || cloud50 || cloud10;
    const sunsetTime = new Date(day.sunset_time);
    const sunsetIdx = timeSource.times.findIndex(t => new Date(t).getTime() >= sunsetTime.getTime());
    
    if (sunsetIdx < 0) continue;
    
    // Window: sunset-1h, sunset, sunset+1h
    // Forward-weighted [0.15, 0.50, 0.35] — what matters is conditions AT and just AFTER sunset,
    // not an hour before. Equal weighting buries clearing trends.
    const wi = [sunsetIdx - 1, sunsetIdx, sunsetIdx + 1].filter(
      i => i >= 0 && i < timeSource.times.length
    );
    const FW = [0.15, 0.50, 0.35].slice(3 - wi.length); // drop early weights if window is short
    function avgWindow(source, field, weights) {
      if (!source) return null;
      const w = weights || FW;
      let sum = 0, wsum = 0;
      wi.forEach((i, j) => {
        const v = source[field][i];
        if (v != null) { sum += v * w[j]; wsum += w[j]; }
      });
      return wsum ? sum / wsum : 0;
    }

    // Use available data, estimate missing with nearby values
    const low10 = avgWindow(cloud10, 'cloud_low')
                  ?? avgWindow(cloud25, 'cloud_low') ?? 0;
    const mid25 = avgWindow(cloud25, 'cloud_mid')
                  ?? avgWindow(cloud50, 'cloud_mid')
                  ?? avgWindow(cloud10, 'cloud_mid') ?? 0;
    const mid50 = avgWindow(cloud50, 'cloud_mid')
                  ?? avgWindow(cloud25, 'cloud_mid') ?? mid25;
    const high25 = avgWindow(cloud25, 'cloud_high')
                   ?? avgWindow(cloud50, 'cloud_high')
                   ?? avgWindow(cloud10, 'cloud_high') ?? 0;
    const high50 = avgWindow(cloud50, 'cloud_high')
                   ?? avgWindow(cloud25, 'cloud_high') ?? high25;
    const hum25 = avgWindow(cloud25 || cloud50 || cloud10, 'humidity') ?? 50;
    
    const totalCloud = (low10 + mid25 + high25) / 3;
    
    if (totalCloud < 15) {
      const dayLabel = day.day === 0 ? "Today" : day.day === 1 ? "Tomorrow"
        : sunsetTime.toLocaleDateString("en-US", { weekday:"short", month:"short", day:"numeric" });
      const timeLabel = sunsetTime.toLocaleTimeString("en-US", { hour:"numeric", minute:"2-digit" });
      
      scores.push({
        dayLabel, timeLabel,
        score: 45,
        label: "Good",
        color: "rgba(255,220,100,0.9)",
        avgLow: low10.toFixed(0),
        avgMid: mid25.toFixed(0),
        avgHigh: high25.toFixed(0),
        avgHum: hum25.toFixed(0),
        note: "Clear sky"
      });
      continue;
    }
    
    if (low10 > 75) {
      const dayLabel = day.day === 0 ? "Today" : day.day === 1 ? "Tomorrow"
        : sunsetTime.toLocaleDateString("en-US", { weekday:"short", month:"short", day:"numeric" });
      const timeLabel = sunsetTime.toLocaleTimeString("en-US", { hour:"numeric", minute:"2-digit" });
      
      scores.push({
        dayLabel, timeLabel,
        score: 10,
        label: "Poor",
        color: "rgba(120,120,120,0.6)",
        avgLow: low10.toFixed(0),
        avgMid: mid25.toFixed(0),
        avgHigh: high25.toFixed(0),
        avgHum: hum25.toFixed(0),
        note: "Overcast"
      });
      continue;
    }
    
    const midCloudAvg = mid25 * 0.7 + mid50 * 0.3;

    const midScore = midCloudAvg <= 70
      ? midCloudAvg / 70
      : Math.max(0.3, (100 - midCloudAvg) / 40);

    const highBonus = Math.min((high25 + high50) / 2, 60) / 60 * 0.3;
    const lowPenalty = Math.min(low10 / 80, 1.0);
    // Humidity penalty: meaningful above 70% (not 60%) — coastal air is naturally humid
    const humFactor = 1 - Math.max(0, (hum25 - 70)) / 90;
    // Partial low clouds at the horizon catch color from below — treat as a contribution,
    // not just a blocker. Peak opportunity around 20-50% low cloud coverage.
    const lowCloudColor = (low10 > 8 && low10 < 72)
      ? Math.sin((low10 - 8) / 64 * Math.PI) * 0.35
      : 0;

    let score = (midScore * 0.7 + highBonus + lowCloudColor) * (1 - lowPenalty * 0.55) * humFactor;
    score = Math.max(1, Math.min(100, Math.round(score * 100)));
    
    let label, color;
    if (score >= 75)      { label = "Spectacular";  color = "rgba(255,160,40,0.95)";  ; }
    else if (score >= 55) { label = "Very Good";    color = "rgba(255,200,60,0.95)";  ; }
    else if (score >= 35) { label = "Good";         color = "rgba(255,220,100,0.9)"; }
    else if (score >= 18) { label = "Fair";         color = "rgba(180,180,180,0.8)"; }
    else                    { label = "Poor";         color = "rgba(120,120,120,0.6)"; }
    
    const dayLabel = day.day === 0 ? "Today" : day.day === 1 ? "Tomorrow"
      : sunsetTime.toLocaleDateString("en-US", { weekday:"short", month:"short", day:"numeric" });
    const timeLabel = sunsetTime.toLocaleTimeString("en-US", { hour:"numeric", minute:"2-digit" });
    
    scores.push({
      dayLabel, timeLabel, score, label, color,
      avgLow: low10.toFixed(0),
      avgMid: midCloudAvg.toFixed(0),
      avgHigh: ((high25 + high50) / 2).toFixed(0),
      avgHum: hum25.toFixed(0)
    });
    

  }

  // Store today sunset score for Right Now card
  const todayScore = scores.find(s => s.dayLabel === "Today");
  if (todayScore) window.__todaySunsetScore = {score: todayScore.score, label: todayScore.label, color: todayScore.color};
  const tomorrowScore = scores.find(s => s.dayLabel === "Tomorrow");
  if (tomorrowScore) window.__tomorrowSunsetScore = {score: tomorrowScore.score, label: tomorrowScore.label, color: tomorrowScore.color};

  if (!scores.length) {
    el.innerHTML = `<div style="color:${isLight() ? 'rgba(0,0,0,0.4)' : 'rgba(255,255,255,0.4)'};font-size:0.85rem;">No sunset data in forecast window</div>`;
    return;
  }

  const light = isLight();
  const tileBg   = light ? "rgba(0,0,0,0.03)"   : "rgba(255,255,255,0.04)";
  const tileBd   = light ? "rgba(0,0,0,0.09)"   : "rgba(255,255,255,0.08)";
  const dayCol   = light ? "rgba(0,0,0,0.75)"   : "rgba(255,255,255,0.6)";
  const timeCol  = light ? "rgba(0,0,0,0.50)"   : "rgba(255,255,255,0.35)";
  const barBg    = light ? "rgba(0,0,0,0.10)"   : "rgba(255,255,255,0.1)";
  const detCol   = light ? "rgba(0,0,0,0.55)"   : "rgba(255,255,255,0.4)";
  const noteCol  = light ? "rgba(0,0,0,0.50)"   : "rgba(255,255,255,0.3)";

  // Adjust score colors for light mode readability
  function adjustScoreColor(color) {
    if (!light) return color;
    if (color.includes("120,120,120")) return "rgba(0,0,0,0.7)";     // Poor: darker gray
    if (color.includes("180,180,180")) return "rgba(60,60,60,0.9)";     // Fair: darker gray
    if (color.includes("255,220,100")) return "rgba(180,140,0,0.95)";      // Good: dark gold
    if (color.includes("255,200,60"))  return "rgba(180,130,0,0.95)";      // Very Good: dark gold
    if (color.includes("255,160,40"))  return "rgba(200,100,0,0.95)";      // Spectacular: dark orange
    return color;
  }

  let html = ``;

  // Headline from today's (or next available) sunset score
  if (scores.length > 0) {
    const ts = scores[0];
    const scoreCol = adjustScoreColor(ts.color);
    let sunsetHL;
    const mid = parseInt(ts.avgMid);
    const low = parseInt(ts.avgLow);
    if (ts.note === "Clear sky") {
      sunsetHL = `Good sunset tonight — clear horizon, low humidity`;
    } else if (ts.label === "Spectacular" || ts.label === "Very Good") {
      sunsetHL = `${ts.label} sunset tonight — mid-level clouds at distance (${mid}%)`;
    } else if (ts.label === "Good") {
      sunsetHL = `Decent sunset tonight — some color likely`;
    } else if (ts.label === "Fair") {
      sunsetHL = `Fair sunset tonight — limited color expected`;
    } else if (low > 60) {
      sunsetHL = `Poor sunset tonight — overcast blocks the horizon`;
    } else {
      sunsetHL = `Poor sunset tonight — clouds limit color`;
    }
    html += `<div style="font-size:0.95rem;font-weight:600;color:${scoreCol};margin-bottom:14px;padding:10px 14px;background:rgba(255,255,255,0.04);border-radius:0;border-left:4px solid ${scoreCol};">${sunsetHL}</div>`;
  }

  html += `<div class="scroll-day-grid" style="display:grid;grid-template-columns:repeat(${scores.length},1fr);gap:10px;margin-bottom:12px;">`;
  for (const s of scores) {
    const barW = Math.round(s.score * 100);
    const scoreCol = adjustScoreColor(s.color);
    const noteHtml = s.note ? `<div style="font-size:0.72rem;color:${noteCol};margin-top:4px;">${s.note}</div>` : '';
    html += `
      <div style="background:${tileBg};border:1px solid ${tileBd};
                  border-radius:10px;padding:16px 12px;text-align:center;">
        <div style="font-size:0.9rem;font-weight:800;color:${dayCol};margin-bottom:6px;">${s.dayLabel}</div>
        
        <div style="font-size:1.05rem;font-weight:900;color:${scoreCol};margin-bottom:6px;">${s.label} <span style="font-size:0.8rem;opacity:0.7;">(${Math.round(s.score)})</span></div>
        <div style="font-size:0.8rem;color:${timeCol};margin-bottom:10px;">Sunset ${s.timeLabel}</div>
        <div style="height:5px;background:${barBg};border-radius:3px;overflow:hidden;margin-bottom:10px;">
          <div style="height:100%;width:${barW}%;background:${scoreCol};border-radius:3px;transition:width 0.4s;"></div>
        </div>
        <div style="font-size:0.78rem;color:${detCol};line-height:2;">
          <span>Low ${s.avgLow}%</span> ·
          <span>Mid ${s.avgMid}%</span> ·
          <span>High ${s.avgHigh}%</span>
        </div>
        ${noteHtml}
      </div>`;
  }
  html += `</div>`;
  html += `<div style="font-size:0.78rem;color:${noteCol};margin-top:4px;">
    Clouds sampled 10-50 miles west along actual sunset direction (not overhead).
    Best sunsets: 30-70% mid clouds at distance, clear horizon nearby, dry air. Clear skies with low humidity score "Good".
  </div>`;

  el.innerHTML = html;
  
  // Update collapsed preview with next sunset's data
  // Determine if we should show today or tomorrow based on current time vs civil dusk
  const now = new Date();
  let nextSunset = scores.length > 0 ? scores[0] : null;
  
  // Check if we're past civil dusk - if so, show tomorrow
  const civilDuskStr = data.sun?.civil_dusk;
  if (civilDuskStr && nextSunset) {
    const civilDusk = new Date(civilDuskStr);
    if (now > civilDusk && scores.length > 1) {
      nextSunset = scores[1]; // Show tomorrow
    }
  }
  
  if (nextSunset) {
    const sunsetDayEl = document.getElementById("sunsetDayCollapsed");
    const sunsetIconEl = document.getElementById("sunsetIconCollapsed");
    const sunsetScoreEl = document.getElementById("sunsetScoreCollapsed");
    
    if (sunsetDayEl) sunsetDayEl.textContent = nextSunset.dayLabel;
    
    if (sunsetScoreEl) sunsetScoreEl.innerHTML = `${nextSunset.label} <span style="font-size:0.85rem;opacity:0.7;">(${nextSunset.score}/100)</span>`;
    
    // Apply gradient class based on score
    const sunsetCard = document.querySelector('[data-collapse-key="sunset_quality"]');
    if (sunsetCard) {
      sunsetCard.classList.remove('tile-sunset-poor', 'tile-sunset-fair', 'tile-sunset-good', 'tile-sunset-verygood', 'tile-sunset-spectacular');
      if (nextSunset.score < 20) sunsetCard.classList.add('tile-sunset-poor');
      else if (nextSunset.score < 35) sunsetCard.classList.add('tile-sunset-fair');
      else if (nextSunset.score < 55) sunsetCard.classList.add('tile-sunset-good');
      else if (nextSunset.score < 75) sunsetCard.classList.add('tile-sunset-verygood');
      else sunsetCard.classList.add('tile-sunset-spectacular');
    }
  }
}
