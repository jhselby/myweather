// modals.js — Settings, alert, and precip modal open/close

// === Settings Modal ===
function openSettingsModal() {
  document.getElementById('settingsModal').style.display = 'flex';

  // Swipe-down to dismiss
  const sheet = document.querySelector('#settingsModal .modal-sheet');
  if (sheet && !sheet._swipeInit) {
    sheet._swipeInit = true;
    let startY = 0, isDragging = false;
    sheet.addEventListener('touchstart', e => {
      startY = e.touches[0].clientY;
      isDragging = true;
      sheet.style.transition = 'none';
    }, { passive: true });
    sheet.addEventListener('touchmove', e => {
      if (!isDragging) return;
      const dy = e.touches[0].clientY - startY;
      if (dy > 0) sheet.style.transform = `translateY(${dy}px)`;
    }, { passive: true });
    sheet.addEventListener('touchend', e => {
      isDragging = false;
      const dy = e.changedTouches[0].clientY - startY;
      sheet.style.transition = '';
      if (dy > 80) {
        closeSettingsModal();
      } else {
        sheet.style.transform = '';
      }
    }, { passive: true });

    // Mouse drag-to-dismiss for desktop
    sheet.addEventListener('mousedown', e => {
      startY = e.clientY;
      isDragging = true;
      sheet.style.transition = 'none';
      sheet.style.userSelect = 'none';
    });
    document.addEventListener('mousemove', e => {
      if (!isDragging) return;
      const dy = e.clientY - startY;
      if (dy > 0) sheet.style.transform = `translateY(${dy}px)`;
    });
    document.addEventListener('mouseup', e => {
      if (!isDragging) return;
      isDragging = false;
      sheet.style.transition = '';
      sheet.style.userSelect = '';
      const dy = e.clientY - startY;
      if (dy > 80) {
        closeSettingsModal();
      } else {
        sheet.style.transform = '';
      }
    });
  }
  document.body.style.overflow = 'hidden';
  // Sync data timestamps
}
function closeSettingsModal() {
  const sheet = document.querySelector('#settingsModal .modal-sheet');
  if (sheet) sheet.style.transform = '';
  // Collapse all subsections and scroll to top
  ['sourcesBody','nerdStuffBody','changelogBody','howItWorksBody','dataPipelineBody','licensesBody'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });
  if (sheet) sheet.scrollTop = 0;
  document.getElementById('settingsModal').style.display = 'none';
  document.body.style.overflow = '';
}

// === Alert Modal ===
function openAlertModal() {
  const sheet = document.querySelector('#alertModal .modal-sheet');
  if (sheet && !sheet._swipeInit) {
    sheet._swipeInit = true;
    let startY = 0, isDragging = false;
    const onTouchStart = e => { startY = e.touches[0].clientY; isDragging = true; sheet.style.transition = 'none'; };
    const onTouchMove = e => { if (!isDragging) return; const dy = e.touches[0].clientY - startY; if (dy > 0) sheet.style.transform = `translateY(${dy}px)`; };
    const onTouchEnd = e => { isDragging = false; const dy = e.changedTouches[0].clientY - startY; sheet.style.transition = ''; if (dy > 80) closeAlertModal(); else sheet.style.transform = ''; };
    const onMouseDown = e => { startY = e.clientY; isDragging = true; sheet.style.transition = 'none'; sheet.style.userSelect = 'none'; };
    const onMouseMove = e => { if (!isDragging) return; const dy = e.clientY - startY; if (dy > 0) sheet.style.transform = `translateY(${dy}px)`; };
    const onMouseUp = e => { if (!isDragging) return; isDragging = false; sheet.style.transition = ''; sheet.style.userSelect = ''; const dy = e.clientY - startY; if (dy > 80) closeAlertModal(); else sheet.style.transform = ''; };
    sheet.addEventListener('touchstart', onTouchStart, { passive: true });
    sheet.addEventListener('touchmove', onTouchMove, { passive: true });
    sheet.addEventListener('touchend', onTouchEnd, { passive: true });
    sheet.addEventListener('mousedown', onMouseDown);
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }
  const container = document.getElementById('alertsContainer');
  const modalBody = document.getElementById('alertModalBody');
  if (!modalBody) return;

  const stormFlags = window.__stormFlags || [];
  const alerts = container ? container.querySelectorAll('.alert-banner') : [];

  modalBody.innerHTML = '';

  const lightningStrike = window.__lightningStrike;

  // If no alerts, show reassurance instead of refusing to open
  if (alerts.length === 0 && stormFlags.length < 2 && !lightningStrike) {
    modalBody.innerHTML = `
      <div style="padding:32px 16px;text-align:center;color:var(--muted);">
        <div style="font-size:2.5rem;margin-bottom:12px;">✓</div>
        <div style="font-size:1rem;font-weight:500;margin-bottom:4px;color:var(--text-primary);">No active alerts</div>
        <div style="font-size:0.85rem;">No NWS watches, warnings, or advisories for Marblehead.</div>
      </div>`;
    document.getElementById('alertModal').style.display = 'flex';
    document.body.style.overflow = 'hidden';
    return;
  }

  // Standalone lightning section (when not already folded into storm flags block)
  if (lightningStrike && stormFlags.length < 2) {
    const distStr = lightningStrike.distKm != null ? ` · closest ${Math.round(lightningStrike.distKm)} km` : "";
    const isClose = lightningStrike.distKm != null && lightningStrike.distKm <= 20;
    modalBody.innerHTML += `
      <div class="alert-modal-item" style="border-left:3px solid ${isClose ? 'rgba(255,80,80,0.7)' : 'rgba(255,160,50,0.7)'};padding-left:12px;">
        <div class="alert-modal-title">⚡ Lightning detected</div>
        <div class="alert-modal-desc">${lightningStrike.count} strike${lightningStrike.count !== 1 ? "s" : ""} in the past hour${distStr}</div>
      </div>`;
  }

  // Storm flags section
  if (stormFlags.length >= 2) {
    const severity = stormFlags.length >= 3 ? 'Storm conditions developing' : 'Active weather developing';
    modalBody.innerHTML += `
      <div class="alert-modal-item" style="border-left:3px solid rgba(255,100,100,0.6);padding-left:12px;">
        <div class="alert-modal-title">${severity}</div>
        <div class="alert-modal-desc">${stormFlags.map(f => '• ' + f).join('<br>')}</div>
      </div>`;
  }

  // NWS alerts section
  alerts.forEach(alert => {
    const titleEl = alert.querySelector('.alert-title span');
    const descEl = alert.querySelector('.alert-desc');
    const title = titleEl ? titleEl.textContent : 'Weather Alert';
    const desc = descEl ? descEl.innerHTML : '';
    modalBody.innerHTML += `
      <div class="alert-modal-item">
        <div class="alert-modal-title">${title}</div>
        <div class="alert-modal-desc">${desc}</div>
      </div>`;
  });

  document.getElementById('alertModal').style.display = 'flex';
  document.body.style.overflow = 'hidden';
}
function closeAlertModal() {
  const sheet = document.querySelector('#alertModal .modal-sheet');
  if (sheet) sheet.style.transform = '';
  document.getElementById('alertModal').style.display = 'none';
  document.body.style.overflow = '';
}

// === Precip Modal ===
function openPrecipModal() {
  const sheet = document.querySelector('#precipModal .modal-sheet');
  if (sheet && !sheet._swipeInit) {
    sheet._swipeInit = true;
    let startY = 0, isDragging = false;
    const onTouchStart = e => { startY = e.touches[0].clientY; isDragging = true; sheet.style.transition = 'none'; };
    const onTouchMove = e => { if (!isDragging) return; const dy = e.touches[0].clientY - startY; if (dy > 0) sheet.style.transform = `translateY(${dy}px)`; };
    const onTouchEnd = e => { isDragging = false; const dy = e.changedTouches[0].clientY - startY; sheet.style.transition = ''; if (dy > 80) closePrecipModal(); else sheet.style.transform = ''; };
    const onMouseDown = e => { startY = e.clientY; isDragging = true; sheet.style.transition = 'none'; sheet.style.userSelect = 'none'; };
    const onMouseMove = e => { if (!isDragging) return; const dy = e.clientY - startY; if (dy > 0) sheet.style.transform = `translateY(${dy}px)`; };
    const onMouseUp = e => { if (!isDragging) return; isDragging = false; sheet.style.transition = ''; sheet.style.userSelect = ''; const dy = e.clientY - startY; if (dy > 80) closePrecipModal(); else sheet.style.transform = ''; };
    sheet.addEventListener('touchstart', onTouchStart, { passive: true });
    sheet.addEventListener('touchmove', onTouchMove, { passive: true });
    sheet.addEventListener('touchend', onTouchEnd, { passive: true });
    sheet.addEventListener('mousedown', onMouseDown);
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  }

  const data = window.__lastWeatherData;
  const minutely = data?.pirate_weather?.minutely || [];
  const body = document.getElementById('precipModalBody');
  if (!body) return;

  if (minutely.length === 0) {
    body.innerHTML = '<p style="padding:16px;opacity:0.7;">No minutely data available.</p>';
    document.getElementById('precipModal').style.display = 'flex';
    document.body.style.overflow = 'hidden';
    return;
  }

  // Build summary text
  const now = Math.floor(Date.now() / 1000);

  // Staleness: how many minutes ago was this data fetched
  const dataTime = minutely[0]?.time ?? now;
  const stalenessMin = Math.round((now - dataTime) / 60);

  // First bar clock time label
  const dataDate = new Date(dataTime * 1000);
  const dataHour = dataDate.getHours();
  const dataMin = dataDate.getMinutes();
  const startLabel = `${dataHour % 12 || 12}:${String(dataMin).padStart(2,'0')}${dataHour < 12 ? 'am' : 'pm'}`;

  let firstRainIdx = -1, lastRainIdx = -1;
  let maxIntensity = 0;
  let maxProbability = 0;
  minutely.forEach((pt, i) => {
    const prob = pt.precip_probability ?? 0;
    // Require probability >= 30% — Pirate reports intensity even when probability is 0
    if (pt.precip_intensity > 0.001 && prob >= 0.3) {
      if (firstRainIdx === -1) firstRainIdx = i;
      lastRainIdx = i;
      if (pt.precip_intensity > maxIntensity) maxIntensity = pt.precip_intensity;
    }
    if (prob > maxProbability) maxProbability = prob;
  });

  // Adjust indices for staleness to get minutes-from-now
  const firstRainFromNow = firstRainIdx === -1 ? -1 : firstRainIdx - stalenessMin;
  const lastRainFromNow  = lastRainIdx  === -1 ? -1 : lastRainIdx  - stalenessMin;

  let summaryText = '';
  const maxProbPct = Math.round(maxProbability * 100);
  if (firstRainIdx === -1) {
    // Still show max probability even when no rain gate passes, so user sees what Pirate thinks
    summaryText = maxProbPct > 0
      ? `No precipitation forecast in the next hour. (Peak probability: ${maxProbPct}%)`
      : 'No precipitation in the next hour.';
  } else if (firstRainFromNow <= 0) {
    // Rain already started — NWS intensity: light <0.10, moderate 0.10-0.30, heavy >0.30 in/hr
    const endsIn = Math.max(1, lastRainFromNow + 1);
    const intensity = maxIntensity < 0.10 ? 'Light' : maxIntensity < 0.30 ? 'Moderate' : 'Heavy';
    summaryText = `${intensity} rain now — ending in ~${endsIn} min (${maxProbPct}% probability, ${maxIntensity.toFixed(2)} in/hr)`;
  } else {
    const intensity = maxIntensity < 0.10 ? 'Light' : maxIntensity < 0.30 ? 'Moderate' : 'Heavy';
    const duration = lastRainIdx - firstRainIdx + 1;
    summaryText = `${intensity} rain starting in ~${firstRainFromNow} min, lasting ~${duration} min (${maxProbPct}% probability, ${maxIntensity.toFixed(2)} in/hr)`;
  }

  // Build 60-bar chart
  // Bars with probability < 30% are shown ghosted — Pirate reports intensity
  // even when probability is 0, so without this the chart contradicts the summary.
  const maxI = Math.max(...minutely.map(p => p.precip_intensity), 0.01);
  const bars = minutely.map((pt, i) => {
    const h = Math.max(2, Math.round((pt.precip_intensity / maxI) * 60));
    const prob = pt.precip_probability ?? 0;
    const likely = prob >= 0.3;
    const baseColor = pt.precip_type === 'snow' ? '160,200,255'
                    : pt.precip_type === 'sleet' ? '200,160,255'
                    : '100,160,255';
    // Full opacity if probability gate passes; heavily muted otherwise
    const opacity = likely ? 0.85 : 0.15;
    const color = `rgba(${baseColor},${opacity})`;
    const isNow = i === 0 ? 'border-top:2px solid rgba(255,255,255,0.6);' : '';
    return `<div style="flex:1;display:flex;align-items:flex-end;height:64px;">
      <div style="width:100%;height:${h}px;background:${color};border-radius:2px 2px 0 0;${isNow}"></div>
    </div>`;
  }).join('');

  // Tick marks — first tick is actual clock time, rest are relative
  const ticks = '<div style="display:flex;justify-content:space-between;margin-top:4px;opacity:0.5;font-size:10px;">' +
    [startLabel,'15m','30m','45m','60m'].map(t => `<span>${t}</span>`).join('') + '</div>';

  body.innerHTML = `
    <div style="padding:16px 16px 8px;">
      <div style="font-size:15px;font-weight:500;margin-bottom:14px;">${summaryText}</div>
      <div style="display:flex;align-items:flex-end;gap:1px;height:64px;border-bottom:1px solid rgba(255,255,255,0.15);">
        ${bars}
      </div>
      ${ticks}
    </div>`;

  document.getElementById('precipModal').style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

function closePrecipModal() {
  const sheet = document.querySelector('#precipModal .modal-sheet');
  if (sheet) sheet.style.transform = '';
  document.getElementById('precipModal').style.display = 'none';
  document.body.style.overflow = '';
}

function updatePrecipBadge(data) {
  const badge = document.getElementById('precipBadge');
  if (!badge) return;
  const dot = badge.querySelector('.precip-badge-dot');
  const minutely = data?.pirate_weather?.minutely || [];
  // Require BOTH nonzero intensity AND probability >= 30%.
  // Pirate often reports intensity with probability=0, which means
  // "this is what it would be IF it rained" — not an actual forecast.
  const hasRain = minutely.some(pt => pt.precip_intensity > 0 && (pt.precip_probability ?? 0) >= 0.3);
  // Badge is always visible — toggle the colored dot to indicate active state
  if (dot) dot.style.display = hasRain ? '' : 'none';
  window.__precipHasRain = hasRain;
  window.__precipMinutely = minutely;
  if (hasRain && window.__lastWeatherData) {
    renderBriefing(window.__lastWeatherData);
    // Also patch Sky & Precip card — it rendered before minutely arrived
    const condEl = document.getElementById('condition');
    if (condEl && !/rain|snow|drizzle|sleet|shower/i.test(condEl.textContent)) {
      const stale = Math.round((Date.now()/1000 - (minutely[0]?.time ?? Date.now()/1000)) / 60);
      const pt = minutely[Math.min(stale, minutely.length - 1)];
      if (pt && pt.precip_intensity > 0.001 && (pt.precip_probability ?? 0) >= 0.3) {
        const ci = pt.precip_intensity, ct = pt.precip_type || 'rain';
        let pwDesc;
        if (ct === 'snow') pwDesc = ci < 0.10 ? 'Light Snow' : ci < 0.30 ? 'Snow' : 'Heavy Snow';
        else if (ct === 'sleet') pwDesc = 'Sleet';
        else pwDesc = ci < 0.01 ? 'Drizzle' : ci < 0.10 ? 'Light Rain' : ci < 0.30 ? 'Moderate Rain' : 'Heavy Rain';
        condEl.innerHTML = `${condEl.dataset.emoji || ''} ${pwDesc}`;
        const skyColEl = document.getElementById('skyConditionCollapsed');
        if (skyColEl) skyColEl.textContent = pwDesc;
      }
    }
  }
}
