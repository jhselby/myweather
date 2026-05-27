// outdoor.js — Outside conditions score card

function renderOutdoorConditions(data) {
  const el = document.getElementById("outdoorContent");
  if (!el) return;

  const hourly  = data.hourly || {};
  const htimes  = hourly.times || [];
  const hpop    = hourly.precipitation_probability || [];
  const hprecip = hourly.precipitation || [];
  const hwind   = hourly.wind_speed || [];
  const hgusts  = hourly.wind_gusts || [];
  const hdp     = hourly.corrected_dew_point || hourly.dew_point || [];
  const huv     = hourly.uv_index || [];

  const now = new Date();
  const nowStr = now.toISOString().slice(0, 13); // "2026-05-27T14"

  // Find current hour index
  let nowIdx = htimes.findIndex(t => t && t.slice(0, 13) === nowStr);
  if (nowIdx < 0) nowIdx = 0;

  function scoreRain(idx) {
    // Max POP over current + next 2 hours
    const maxPOP = Math.max(
      hpop[idx] ?? 0,
      hpop[idx + 1] ?? 0,
      hpop[idx + 2] ?? 0
    );
    const raining = (hprecip[idx] ?? 0) > 0.01;
    if (raining) return 5;
    if (maxPOP <= 0)  return 100;
    if (maxPOP <= 15) return 90;
    if (maxPOP <= 30) return 70;
    if (maxPOP <= 50) return 45;
    if (maxPOP <= 70) return 25;
    return 10;
  }

  function scoreWind(idx) {
    const spd = hwind[idx] ?? 0;
    if (spd < 8)  return 100;
    if (spd < 12) return 85;
    if (spd < 18) return 65;
    if (spd < 25) return 40;
    if (spd < 35) return 15;
    return 5;
  }

  function scoreUV(uv) {
    if (uv == null) return 100;
    if (uv < 3)  return 100;
    if (uv < 6)  return 90;
    if (uv < 8)  return 75;
    if (uv < 11) return 55;
    return 35;
  }

  function scoreDewPoint(idx) {
    const dp = hdp[idx] ?? null;
    if (dp == null) return 80;
    if (dp < 45) return 90;
    if (dp < 55) return 100;
    if (dp < 60) return 88;
    if (dp < 65) return 70;
    if (dp < 70) return 45;
    return 20;
  }

  function hourScore(idx) {
    if (idx < 0 || idx >= htimes.length) return 0;
    const r = scoreRain(idx);
    const w = scoreWind(idx);
    const u = scoreUV(uvMax);
    const d = scoreDewPoint(idx);
    return Math.round(r * 0.40 + w * 0.25 + u * 0.15 + d * 0.20);
  }

  function labelFor(score) {
    if (score >= 80) return { label: "Great",       color: "rgba(80,210,120,0.95)"  };
    if (score >= 65) return { label: "Good",         color: "rgba(130,205,80,0.95)"  };
    if (score >= 45) return { label: "Fair",         color: "rgba(220,190,60,0.95)"  };
    if (score >= 25) return { label: "Poor",         color: "rgba(220,130,50,0.95)"  };
    return               { label: "Stay inside",    color: "rgba(200,60,60,0.95)"   };
  }

  function uvLabel(uv) {
    if (uv == null) return null;
    if (uv < 3)  return null;
    if (uv < 6)  return `UV ${uv} — moderate, sunscreen advisable`;
    if (uv < 8)  return `UV ${uv} — high, wear sunscreen`;
    if (uv < 11) return `UV ${uv} — very high, limit midday exposure`;
    return              `UV ${uv} — extreme`;
  }

  function dewLabel(idx) {
    const dp = hdp[idx] ?? null;
    if (dp == null) return "—";
    if (dp < 45) return `${Math.round(dp)}°F · dry`;
    if (dp < 55) return `${Math.round(dp)}°F · comfortable`;
    if (dp < 60) return `${Math.round(dp)}°F · slightly humid`;
    if (dp < 65) return `${Math.round(dp)}°F · humid`;
    if (dp < 70) return `${Math.round(dp)}°F · muggy`;
    return              `${Math.round(dp)}°F · oppressive`;
  }

  function fmtHr(t) {
    if (!t) return "";
    const h = new Date(t).getHours();
    return h === 0 ? "12am" : h < 12 ? h + "am" : h === 12 ? "12pm" : (h - 12) + "pm";
  }

  // Today's peak UV from hourly data (9am–5pm window), fallback to daily
  const todayStr = now.toISOString().slice(0, 10);
  let uvMax = null;
  for (let i = 0; i < htimes.length; i++) {
    if (!htimes[i] || !htimes[i].startsWith(todayStr)) continue;
    const h = new Date(htimes[i]).getHours();
    if (h < 9 || h > 17) continue;
    const v = huv[i];
    if (v != null && (uvMax === null || v > uvMax)) uvMax = v;
  }
  if (uvMax === null) uvMax = data.daily?.uv_index_max?.[0] ?? null;

  // Find best 2h+ window today from now through 8pm
  let bestWindowScore = 0, bestWindowStart = null, bestWindowEnd = null;
  let runStart = null, runScore = 0, runLen = 0;

  for (let i = nowIdx; i < htimes.length; i++) {
    const t = htimes[i];
    if (!t || !t.startsWith(todayStr)) break;
    const h = new Date(t).getHours();
    if (h > 20) break;
    const s = hourScore(i);
    if (s >= 65) {
      if (runStart === null) { runStart = i; runScore = 0; runLen = 0; }
      runScore += s; runLen++;
    } else {
      if (runLen >= 2) {
        const avg = Math.round(runScore / runLen);
        if (avg > bestWindowScore) {
          bestWindowScore = avg;
          bestWindowStart = htimes[runStart];
          bestWindowEnd   = htimes[runStart + runLen - 1];
        }
      }
      runStart = null; runLen = 0; runScore = 0;
    }
  }
  if (runLen >= 2) {
    const avg = Math.round(runScore / runLen);
    if (avg > bestWindowScore) {
      bestWindowScore = avg;
      bestWindowStart = htimes[runStart];
      bestWindowEnd   = htimes[runStart + runLen - 1];
    }
  }

  const currentScore = hourScore(nowIdx);
  const { label, color } = labelFor(currentScore);

  // Update collapsed preview
  const collapsedLabelEl = document.getElementById("outdoorLabelCollapsed");
  const collapsedScoreEl = document.getElementById("outdoorScoreCollapsed");
  if (collapsedLabelEl) { collapsedLabelEl.textContent = label; collapsedLabelEl.style.color = color; }
  if (collapsedScoreEl) collapsedScoreEl.textContent = `Now: ${currentScore}/100`;

  const light = isLight();
  const noteCol = light ? "rgba(0,0,0,0.45)" : "rgba(255,255,255,0.4)";
  const detCol  = light ? "rgba(0,0,0,0.6)"  : "rgba(255,255,255,0.55)";
  const valCol  = light ? "rgba(0,0,0,0.85)" : "rgba(255,255,255,0.9)";
  const scoreCol = color;

  // Sub-factors
  const rainPOP  = Math.max(hpop[nowIdx] ?? 0, hpop[nowIdx+1] ?? 0, hpop[nowIdx+2] ?? 0);
  const windSpd  = Math.round(hwind[nowIdx] ?? 0);
  const windGust = Math.round(hgusts[nowIdx] ?? 0);
  const windStr  = windGust > windSpd + 4 ? `${windSpd} mph · gusts ${windGust}` : `${windSpd} mph`;
  const uvNote   = uvLabel(uvMax);
  const dpStr    = dewLabel(nowIdx);
  const raining  = (hprecip[nowIdx] ?? 0) > 0.01;

  // Headline
  let headline;
  if (currentScore >= 65) {
    headline = `${label} conditions outside`;
  } else if (bestWindowStart) {
    headline = `${label} now — better ${fmtHr(bestWindowStart)}–${fmtHr(bestWindowEnd)}`;
  } else {
    headline = `${label} conditions today`;
  }

  const factors = [
    { label: "Rain",    value: raining ? "Raining now" : `${rainPOP}% next 3h`,  score: scoreRain(nowIdx) },
    { label: "Wind",    value: windStr,                                            score: scoreWind(nowIdx) },
    { label: "Comfort", value: dpStr,                                              score: scoreDewPoint(nowIdx) },
    ...(uvMax != null ? [{ label: "UV", value: `${uvMax} today (peak)`, score: scoreUV(uvMax) }] : []),
  ];

  function barColor(s) {
    return s >= 80 ? "rgba(80,210,120,0.7)" : s >= 55 ? "rgba(220,190,60,0.7)" : "rgba(210,80,60,0.7)";
  }

  let html = `
    <div style="font-size:0.95rem;font-weight:600;color:${scoreCol};margin-bottom:14px;padding:10px 14px;background:rgba(255,255,255,0.04);border-radius:0;border-left:4px solid ${scoreCol};">${headline}</div>
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:18px;padding:0 4px;">
      <div style="text-align:center;">
        <div style="font-size:2.4rem;font-weight:200;line-height:1;color:${scoreCol};">${currentScore}</div>
        <div style="font-size:0.65rem;opacity:0.45;margin-top:2px;">/ 100</div>
      </div>
      <div style="flex:1;">
        <div style="font-size:1.1rem;font-weight:700;color:${scoreCol};margin-bottom:6px;">${label}</div>
        <div style="background:${light ? 'rgba(0,0,0,0.08)' : 'rgba(255,255,255,0.08)'};border-radius:4px;height:6px;overflow:hidden;">
          <div style="width:${currentScore}%;height:100%;background:${scoreCol};border-radius:4px;transition:width 0.4s;"></div>
        </div>
      </div>
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px;">`;

  for (const f of factors) {
    html += `
      <div style="background:${light ? 'rgba(0,0,0,0.03)' : 'rgba(255,255,255,0.04)'};border:1px solid ${light ? 'rgba(0,0,0,0.08)' : 'rgba(255,255,255,0.08)'};border-radius:8px;padding:10px 12px;">
        <div style="font-size:0.7rem;color:${noteCol};margin-bottom:4px;">${f.label}</div>
        <div style="font-size:0.82rem;font-weight:600;color:${valCol};margin-bottom:6px;">${f.value}</div>
        <div style="background:${light ? 'rgba(0,0,0,0.08)' : 'rgba(255,255,255,0.08)'};border-radius:3px;height:3px;overflow:hidden;">
          <div style="width:${f.score}%;height:100%;background:${barColor(f.score)};border-radius:3px;"></div>
        </div>
      </div>`;
  }

  html += `</div>`;

  if (uvNote) {
    html += `<div style="font-size:0.72rem;padding:6px 10px;background:rgba(255,200,80,0.1);border-left:2px solid rgba(255,200,80,0.5);border-radius:0 4px 4px 0;color:${detCol};margin-bottom:10px;">${uvNote}</div>`;
  }

  html += `<div style="font-size:0.72rem;color:${noteCol};margin-top:4px;">Pollen and air quality coming soon.</div>`;

  el.innerHTML = html;
}
