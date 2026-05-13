// seabreeze.js — Sea breeze forecast card

function renderSeaBreezeDetail(data) {
  const sb = data.sea_breeze || {};
  const el = document.getElementById("seaBreezeDetail");
  if (!el) return;

  if (sb.likelihood === undefined || sb.likelihood === null) {
    el.innerHTML = `<div style="text-align:center;color:rgba(255,255,255,0.5);padding:20px;">No sea breeze data available</div>`;
    return;
  }

  const scores = sb.scores || {};
  const hyp = data.hyperlocal || {};
  const buoy = data.buoy_44013 || {};
  const cur = data.current || {};

  let statusColor, statusText;
  if (sb.active) {
    statusColor = "rgba(100,200,120,0.95)";
    statusText = "Active";
  } else if (sb.likelihood >= 40) {
    statusColor = "rgba(220,200,60,0.85)";
    statusText = "Possible";
  } else {
    statusColor = "rgba(150,150,150,0.6)";
    statusText = "Unlikely";
  }

  // Build sea breeze headline
  let sbHeadline;
  if (sb.active) {
    sbHeadline = `Sea breeze active — offshore flow replaced by onshore`;
  } else if (sb.likelihood >= 60) {
    sbHeadline = `Sea breeze likely this afternoon (${sb.likelihood}%)`;
  } else if (sb.likelihood >= 35) {
    sbHeadline = `Sea breeze possible (${sb.likelihood}%) — conditions marginal`;
  } else {
    const windDir = data.current?.wind_direction;
    const compass = windDir != null ? toCompass(windDir) : null;
    sbHeadline = compass
      ? `No sea breeze — ${compass} wind dominates (${sb.likelihood}%)`
      : `No sea breeze — conditions unfavorable (${sb.likelihood}%)`;
  }
  const sbHeadlineColor = sb.active ? "rgba(100,200,120,0.95)" : sb.likelihood >= 40 ? "rgba(220,200,60,0.85)" : "rgba(150,150,150,0.7)";

  const html = `
    <div style="font-size:0.95rem;font-weight:600;color:${sbHeadlineColor};margin-bottom:16px;padding:10px 14px;background:rgba(255,255,255,0.04);border-radius:0;border-left:4px solid ${sbHeadlineColor};">${sbHeadline}</div>
    <div style="text-align:center;margin-bottom:20px;">
      <div style="font-size:2.5rem;color:${statusColor};margin-bottom:8px;">${sb.likelihood}%</div>
      <div style="font-size:1.1rem;opacity:0.9;">${statusText}</div>
      <div style="font-size:0.9rem;opacity:0.7;margin-top:4px;">${sb.reason}</div>
    </div>

    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:16px;margin-bottom:20px;">
      <div>
        <div style="opacity:0.7;font-size:0.85rem;margin-bottom:4px;">Temp Differential</div>
        <div style="font-size:1.3rem;">${scores.temp || 0}%</div>
        <div style="opacity:0.6;font-size:0.8rem;margin-top:2px;">Land: ${(hyp.corrected_temp ?? cur.temperature)?.toFixed(1) || "--"}°F | Water: ${buoy.water_temp_f?.toFixed(1) || "--"}°F</div>
      </div>
      <div>
        <div style="opacity:0.7;font-size:0.85rem;margin-bottom:4px;">Wind Speed</div>
        <div style="font-size:1.3rem;">${scores.wind_speed || 0}%</div>
        <div style="opacity:0.6;font-size:0.8rem;margin-top:2px;">${(hyp.corrected_wind_speed ?? cur.wind_speed)?.toFixed(1) || "--"} mph</div>
      </div>
      <div>
        <div style="opacity:0.7;font-size:0.85rem;margin-bottom:4px;">Direction</div>
        <div style="font-size:1.3rem;">${scores.direction || 0}%</div>
        <div style="opacity:0.6;font-size:0.8rem;margin-top:2px;">${cur.wind_direction ? Math.round(cur.wind_direction) + "° " + toCompass(cur.wind_direction) : "--"}</div>
      </div>
      <div>
        <div style="opacity:0.7;font-size:0.85rem;margin-bottom:4px;">Time of Day</div>
        <div style="font-size:1.3rem;">${scores.time || 0}%</div>
        <div style="opacity:0.6;font-size:0.8rem;margin-top:2px;">${new Date().toLocaleTimeString("en-US", {hour: "numeric", minute: "2-digit"})}</div>
      </div>
    </div>

    <div style="opacity:0.7;font-size:0.85rem;line-height:1.5;">
      <strong>Calculation:</strong> Likelihood = (Temp × 40%) + (Direction × 30%) + (Wind Speed × 20%) + (Time × 10%)<br>
      = (${scores.temp || 0} × 0.4) + (${scores.direction || 0} × 0.3) + (${scores.wind_speed || 0} × 0.2) + (${scores.time || 0} × 0.1) = ${sb.likelihood}%
    </div>
  `;

  el.innerHTML = html;
  
  // Update collapsed preview with new structure
  const seaBreezeCollapsedEl = document.getElementById("seaBreezeCollapsed");
  const seaBreezeLabelEl = document.getElementById("seaBreezeLabel");
  const seaBreezeProbCollapsedEl = document.getElementById("seaBreezeProbCollapsed");
  if (seaBreezeCollapsedEl) {
    seaBreezeCollapsedEl.innerHTML = `${sb.likelihood}<span style="font-size:1.8rem;opacity:0.6;">%</span>`;
  }
  if (seaBreezeLabelEl) seaBreezeLabelEl.textContent = statusText;
  if (seaBreezeProbCollapsedEl) {
    let timeText;
    if (sb.active) {
      timeText = "Active now";
    } else if (sb.likelihood >= 40) {
      timeText = "This afternoon";
    } else {
      const wd = data.current?.wind_direction;
      timeText = wd != null ? `Wind from ${toCompass(wd)}` : "Unfavorable";
    }
    seaBreezeProbCollapsedEl.textContent = timeText;
  }
  
  // Apply gradient class based on likelihood
  const seaBreezeCard = document.querySelector('[data-collapse-key="sea_breeze_detail"]');
  if (seaBreezeCard) {
    seaBreezeCard.classList.remove('tile-seabreeze-unlikely', 'tile-seabreeze-possible', 'tile-seabreeze-likely');
    if (sb.likelihood < 30) seaBreezeCard.classList.add('tile-seabreeze-unlikely');
    else if (sb.likelihood < 60) seaBreezeCard.classList.add('tile-seabreeze-possible');
    else seaBreezeCard.classList.add('tile-seabreeze-likely');
  }
}
