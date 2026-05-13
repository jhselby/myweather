// sky.js — sun, moon, and solar system rendering (SunCalc / VSOP87, no data fetch)

const HOME_LAT = 42.5014;
const HOME_LON = -70.8750;

const MOON_PHASES = [
  { name: "New Moon", min: 0,     max: 0.025 },
  { name: "Waxing Crescent", min: 0.025, max: 0.235 },
  { name: "First Quarter", min: 0.235, max: 0.265 },
  { name: "Waxing Gibbous", min: 0.265, max: 0.485 },
  { name: "Full Moon", min: 0.485, max: 0.515 },
  { name: "Waning Gibbous", min: 0.515, max: 0.735 },
  { name: "Last Quarter", min: 0.735, max: 0.765 },
  { name: "Waning Crescent", min: 0.765, max: 0.975 },
  { name: "New Moon", min: 0.975, max: 1.0   },
];

function fmtTime(date) {
  if (!date || isNaN(date.getTime())) return "--";
  return date.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

function azimuthToSky(azRad) {
  const d = ((azRad * 180 / Math.PI) + 180 + 360) % 360;
  const dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];
  const compass = dirs[Math.round(d / 22.5) % 16];
  return { deg: Math.round(d), compass };
}

function altitudeDescription(altRad) {
  const deg = Math.round(altRad * 180 / Math.PI);
  let text;
  if (deg < 0)  text = "Below horizon";
  else if (deg < 10) text = "Just above horizon";
  else if (deg < 30) text = "Low in sky";
  else if (deg < 60) text = "Mid sky";
  else               text = "High overhead";
  return { deg, text };
}

function daysUntilNextFullMoon() {
  const now = new Date();
  let prev = SunCalc.getMoonIllumination(now).phase;
  for (let d = 1; d <= 30; d++) {
    const candidate = new Date(now.getTime() + d * 86400000);
    const phase = SunCalc.getMoonIllumination(candidate).phase;
    if (prev < 0.5 && phase >= 0.5) return d;
    prev = phase;
  }
  return null;
}

function drawMoonCanvas(canvasId, phase, darkBg) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height;
  const cx = W / 2, cy = H / 2;
  const R = Math.floor(Math.min(W, H) * 0.31);
  const alpha = phase * 2 * Math.PI; // 0=new, pi=full
  const waxing = alpha < Math.PI;
  const k = Math.cos(alpha); // terminator ellipse param (northern hemisphere)

  ctx.clearRect(0, 0, W, H);

  // Subtle glow
  const glow = ctx.createRadialGradient(cx, cy, R * 0.95, cx, cy, R * 1.6);
  glow.addColorStop(0, "rgba(255,190,110,0.12)");
  glow.addColorStop(1, "rgba(255,190,110,0)");
  ctx.fillStyle = glow;
  ctx.beginPath();
  ctx.arc(cx, cy, R * 1.6, 0, 2 * Math.PI);
  ctx.fill();

  // Dark disk (unlit side)
  const darkShade = ctx.createRadialGradient(
    cx - R * 0.25, cy - R * 0.25, R * 0.05, cx, cy, R
  );
  darkShade.addColorStop(0, darkBg ? "#17181c" : "rgba(23,24,28,0.85)");
  darkShade.addColorStop(0.6, darkBg ? "#0b0c10" : "rgba(11,12,16,0.85)");
  darkShade.addColorStop(1, darkBg ? "#05060a" : "rgba(5,6,10,0.85)");
  ctx.beginPath();
  ctx.arc(cx, cy, R, 0, 2 * Math.PI);
  ctx.fillStyle = darkShade;
  ctx.fill();

  // Clip to moon disk and draw lit side with scanline
  ctx.save();
  ctx.beginPath();
  ctx.arc(cx, cy, R, 0, 2 * Math.PI);
  ctx.clip();

  const lit = ctx.createRadialGradient(
    cx - R * 0.35, cy - R * 0.35, R * 0.06, cx, cy, R
  );
  lit.addColorStop(0, "#fff2c7");
  lit.addColorStop(0.45, "#ffd27a");
  lit.addColorStop(0.78, "#ffb347");
  lit.addColorStop(1, "#c97e25");
  ctx.fillStyle = lit;

  for (let y = -R; y <= R; y++) {
    const xr = Math.sqrt(R * R - y * y);
    const xt = k * xr;
    let xLeft, xRight;
    if (waxing) { xLeft = xt; xRight = xr; }
    else        { xLeft = -xr; xRight = -xt; }
    ctx.fillRect(cx + xLeft, cy + y, xRight - xLeft, 1);
  }
  ctx.restore();

  // Rim
  ctx.beginPath();
  ctx.arc(cx, cy, R, 0, 2 * Math.PI);
  ctx.strokeStyle = "rgba(255,255,255,0.09)";
  ctx.lineWidth = 1;
  ctx.stroke();
}

function getMoonPhase(fraction) {
  return MOON_PHASES.find(p => fraction >= p.min && fraction < p.max) || MOON_PHASES[0];
}

function renderMoon() {
  if (typeof SunCalc === "undefined") {
    document.getElementById("moonNote").textContent = "SunCalc library not loaded.";
    return;
  }
  const now   = new Date();
  const illum = SunCalc.getMoonIllumination(now);
  const times = SunCalc.getMoonTimes(now, HOME_LAT, HOME_LON);
  const pos   = SunCalc.getMoonPosition(now, HOME_LAT, HOME_LON);

  const phase = getMoonPhase(illum.phase);
  drawMoonCanvas("moonCanvasExpanded", illum.phase, false);
  document.getElementById("moonPhaseName").textContent    = phase.name;
  document.getElementById("moonIllumination").textContent = Math.round(illum.fraction * 100) + "% illuminated";

  // Update collapsed preview
  drawMoonCanvas("moonCanvasCollapsed", illum.phase, false);
  const moonPhaseCollapsedEl = document.getElementById("moonPhaseCollapsed");
  const moonIllumCollapsedEl = document.getElementById("moonIllumCollapsed");

  if (moonPhaseCollapsedEl) {
    moonPhaseCollapsedEl.textContent = phase.name;
  }
  if (moonIllumCollapsedEl) {
    moonIllumCollapsedEl.textContent = Math.round(illum.fraction * 100) + "% illuminated";
  }

  document.getElementById("moonrise").textContent =
    times.rise ? fmtTime(times.rise) : (times.alwaysUp ? "Up all night" : "Doesn't rise today");
  document.getElementById("moonset").textContent =
    times.set  ? fmtTime(times.set)  : (times.alwaysDown ? "Below horizon all day" : "--");

  const daysToFull = daysUntilNextFullMoon();
  document.getElementById("nextFullMoon").textContent =
    daysToFull === null ? "--" :
    daysToFull === 0    ? "Tonight" :
    daysToFull === 1    ? "Tomorrow" :
    "In " + daysToFull + " days";

  const az  = azimuthToSky(pos.azimuth);
  const alt = altitudeDescription(pos.altitude);
  document.getElementById("moonAzimuth").textContent  = az.deg + "° " + az.compass;
  document.getElementById("moonAltitude").textContent = alt.deg + "° — " + alt.text;
  document.getElementById("moonVisible").textContent  = alt.deg >= 0 ? "Yes" : "No (below horizon)";
  document.getElementById("moonNote").textContent     =
    "Position calculated for " + now.toLocaleTimeString("en-US", { hour:"numeric", minute:"2-digit" }) + " local time.";
}

function renderSun(daily) {
  if (typeof SunCalc === "undefined") return;

  const now  = new Date();
  const pos  = SunCalc.getPosition(now, HOME_LAT, HOME_LON);
  const times= SunCalc.getTimes(now, HOME_LAT, HOME_LON);

  // Altitude and status
  const altDeg = Math.round(pos.altitude * 180 / Math.PI);
  let status, emoji;
  if (altDeg >= 20)       { status = "Above horizon"; }
  else if (altDeg >= 5)   { status = "Low in sky"; }
  else if (altDeg >= 0)   { status = "Just above horizon"; }
  else if (altDeg >= -6)  { status = "Civil twilight"; }
  else if (altDeg >= -12) { status = "Nautical twilight"; }
  else if (altDeg >= -18) { status = "Astronomical twilight"; }
  else                    { status = "Below horizon (night)"; }

  document.getElementById("sunEmoji").textContent   = emoji;
  document.getElementById("sunStatus").textContent  = status;

  // Update collapsed preview - show altitude, arc position, and next event
  const sunStatusCollapsedEl = document.getElementById("sunStatusCollapsed");
  const sunAltitudeCollapsedEl = document.getElementById("sunAltitudeCollapsed");

  if (sunStatusCollapsedEl) {
    const now = new Date();
    const sunrise = times.sunrise;
    const sunset = times.sunset;

    let nextEvent, nextTime;
    if (now < sunrise) {
      nextEvent = "Sunrise";
      nextTime = fmtTime(sunrise);
    } else if (now < sunset) {
      nextEvent = "Sunset";
      nextTime = fmtTime(sunset);
    } else {
      const tomorrow = new Date(now);
      tomorrow.setDate(tomorrow.getDate() + 1);
      const tomorrowTimes = SunCalc.getTimes(tomorrow, HOME_LAT, HOME_LON);
      nextEvent = "Sunrise";
      nextTime = fmtTime(tomorrowTimes.sunrise);
    }

    sunStatusCollapsedEl.textContent = `${nextEvent} ${nextTime}`;
  }

  if (sunAltitudeCollapsedEl) {
    sunAltitudeCollapsedEl.textContent = `${altDeg}° altitude`;
  }

  // Position sun dot on arc: x = time progress (sunrise-left to sunset-right), y = altitude
  const sunPositionDot = document.getElementById("sunPositionDot");
  if (sunPositionDot) {
    const times = SunCalc.getTimes(new Date(), 42.5014, -70.8750);
    const now = Date.now();
    const riseMs = times.sunrise.getTime();
    const setMs = times.sunset.getTime();

    let progress = (now - riseMs) / (setMs - riseMs);
    progress = Math.max(0, Math.min(1, progress));

    const x = 10 + (100 * progress);
    const normalizedAlt = Math.max(0, altDeg) / 90;
    const y = 55 - (50 * Math.sin(normalizedAlt * Math.PI / 2));

    const visible = now >= riseMs && now <= setMs;
    sunPositionDot.style.display = visible ? '' : 'none';

    sunPositionDot.setAttribute('cx', x);
    sunPositionDot.setAttribute('cy', y);

    const glowCircle = sunPositionDot.nextElementSibling;
    if (glowCircle && glowCircle.tagName === 'circle') {
      glowCircle.setAttribute('cx', x);
      glowCircle.setAttribute('cy', y);
      if (glowCircle.style) glowCircle.style.display = visible ? '' : 'none';
    }
  }

  // Azimuth
  const azDeg = Math.round(((pos.azimuth * 180 / Math.PI) + 180 + 360) % 360);
  const dirs  = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];
  const compass = dirs[Math.round(azDeg / 22.5) % 16];
  document.getElementById("sunAzimuth").textContent  = azDeg + "° " + compass;
  document.getElementById("sunAltitude").textContent = altDeg + "°";

  document.getElementById("civilDawn").textContent =
    fmtTime(times.dawn)    || "--";
  document.getElementById("civilDusk").textContent =
    fmtTime(times.dusk)    || "--";

  document.getElementById("goldenHourAM").textContent =
    (times.goldenHourEnd ? fmtTime(times.sunrise) + "–" + fmtTime(times.goldenHourEnd) : "--");
  document.getElementById("goldenHourPM").textContent =
    (times.goldenHour    ? fmtTime(times.goldenHour) + "–" + fmtTime(times.sunset)      : "--");

  document.getElementById("solarNoonLabel").textContent =
    "Solar noon: " + (fmtTime(times.solarNoon) || "--");

  document.getElementById("sunNote").textContent =
    "Position calculated for " +
    now.toLocaleTimeString("en-US", { hour:"numeric", minute:"2-digit" }) + " local time.";
}

function renderSolarSystem() {
  const el = document.getElementById("solarSystemGrid");
  if (!el) return;

  const now   = new Date();
  const jd    = 2440587.5 + now.getTime() / 86400000;
  const T     = (jd - 2451545.0) / 36525.0;

  // Planet orbital elements [L0, L1, a, e0, e1, i0, i1, Om0, Om1, w0, w1]
  const EL = {
    Mercury: [252.250906,149474.0722491,0.387098310,0.20563175, 0.000020407, 7.004986, 0.0018215,48.330893,1.1861883, 77.456119,1.5564776],
    Venus:   [181.979801, 58519.2130302,0.723329820,0.00677188,-0.000047766, 3.394662, 0.0010037,76.679920,0.9011190,131.563703,1.4022288],
    Mars:    [355.433000, 19141.6964471,1.523679342,0.09340062, 0.000090483, 1.849726,-0.0006011,49.558093,0.7720959,336.060234,1.8410449],
    Jupiter: [ 34.351519,  3036.3027748,5.202603209,0.04849485, 0.000163244, 1.303270,-0.0054966,100.464407,1.0209774,14.331207,1.6126352],
    Saturn:  [ 50.077444,  1223.5110686,9.554909192,0.05550825,-0.000346641, 2.488878, 0.0025515,113.665503,0.8770880,93.057237,1.9637613],
  };

  const EMOJIS = { Mercury:"☿", Venus:"♀️", Mars:"♂️", Jupiter:"♃", Saturn:"🪐" };

  // SVG planet functions (40px for collapsed, 60px for expanded)
  const getPlanetSVG = (name, size = 40) => {
    const r = size === 40 ? 16 : 24;
    const cx = size / 2;
    const cy = size / 2;

    if (name === "Mercury") {
      return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
        <defs><radialGradient id="mercury-g-${size}"><stop offset="30%" stop-color="#9D9993"/><stop offset="100%" stop-color="#5C5A57"/></radialGradient></defs>
        <circle cx="${cx}" cy="${cy}" r="${r}" fill="url(#mercury-g-${size})"/>
      </svg>`;
    } else if (name === "Venus") {
      return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
        <defs><radialGradient id="venus-g-${size}"><stop offset="30%" stop-color="#F5E6C8"/><stop offset="100%" stop-color="#D4BE8F"/></radialGradient></defs>
        <circle cx="${cx}" cy="${cy}" r="${r}" fill="url(#venus-g-${size})"/>
      </svg>`;
    } else if (name === "Mars") {
      return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
        <defs><radialGradient id="mars-g-${size}"><stop offset="30%" stop-color="#E27B58"/><stop offset="100%" stop-color="#AD3E1A"/></radialGradient></defs>
        <circle cx="${cx}" cy="${cy}" r="${r}" fill="url(#mars-g-${size})"/>
      </svg>`;
    } else if (name === "Jupiter") {
      return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
        <defs><radialGradient id="jupiter-g-${size}"><stop offset="30%" stop-color="#D4A574"/><stop offset="100%" stop-color="#9E7550"/></radialGradient></defs>
        <circle cx="${cx}" cy="${cy}" r="${r}" fill="url(#jupiter-g-${size})"/>
      </svg>`;
    } else if (name === "Saturn") {
      const ringRx = size === 40 ? 22 : 33;
      const ringRy = size === 40 ? 5 : 7.5;
      const planetR = size === 40 ? 12 : 18;
      return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
        <defs><radialGradient id="saturn-g-${size}"><stop offset="30%" stop-color="#EAE0C8"/><stop offset="100%" stop-color="#BAA888"/></radialGradient></defs>
        <ellipse cx="${cx}" cy="${cy}" rx="${ringRx}" ry="${ringRy}" fill="none" stroke="#C4B69A" stroke-width="${size === 40 ? 1.5 : 2}" opacity="0.5"/>
        <circle cx="${cx}" cy="${cy}" r="${planetR}" fill="url(#saturn-g-${size})"/>
        <ellipse cx="${cx}" cy="${cy}" rx="${ringRx}" ry="${ringRy}" fill="none" stroke="#C4B69A" stroke-width="${size === 40 ? 1.5 : 2}" opacity="0.3" clip-path="inset(50% 0 0 0)"/>
      </svg>`;
    }
    return EMOJIS[name] || "•";
  };

  const COLORS = {
    Mercury:"rgba(180,160,130,0.9)",
    Venus:  "rgba(255,220,100,0.9)",
    Mars:   "rgba(220,80,60,0.9)",
    Jupiter:"rgba(200,160,100,0.9)",
    Saturn: "rgba(210,190,130,0.9)",
  };

  const r2d = r => r * 180 / Math.PI;
  const d2r = d => d * Math.PI / 180;

  // Earth heliocentric position
  const M_e  = d2r(((357.529092 + 35999.0502909*T) % 360 + 360) % 360);
  const e_e  = 0.016708617 - 0.000042037*T;
  let   E_e  = M_e;
  for (let i=0;i<10;i++) E_e -= (E_e - e_e*Math.sin(E_e) - M_e)/(1 - e_e*Math.cos(E_e));
  const w_e  = d2r(102.937348 + 1.7195366*T);
  const xe0  = 1.000001018*(Math.cos(E_e) - e_e);
  const ye0  = 1.000001018*Math.sqrt(1-e_e*e_e)*Math.sin(E_e);
  const xe   = Math.cos(w_e)*xe0 - Math.sin(w_e)*ye0;
  const ye   = Math.sin(w_e)*xe0 + Math.cos(w_e)*ye0;

  // Greenwich Sidereal Time & Local Sidereal Time
  const GMST = ((280.46061837 + 360.98564736629*(jd-2451545.0) + 0.000387933*T*T) % 360 + 360) % 360;
  const LST  = (GMST + HOME_LON + 360) % 360;
  const LAT  = d2r(HOME_LAT);
  const eps  = d2r(23.439291 - 0.013004*T);

  const dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];

  const results = [];

  for (const [name, el] of Object.entries(EL)) {
    const L   = d2r(((el[0] + el[1]*T) % 360 + 360) % 360);
    const a   = el[2];
    const e   = el[3] + el[4]*T;
    const inc = d2r(el[5] + el[6]*T);
    const Om  = d2r(el[7] + el[8]*T);
    const w   = d2r(el[9] + el[10]*T);
    const M   = ((L - w) % (2*Math.PI) + 2*Math.PI) % (2*Math.PI);
    let   E   = M;
    for (let i=0;i<10;i++) E -= (E - e*Math.sin(E) - M)/(1 - e*Math.cos(E));
    const xo  = a*(Math.cos(E) - e);
    const yo  = a*Math.sqrt(1-e*e)*Math.sin(E);
    const cOm=Math.cos(Om),sOm=Math.sin(Om),cw=Math.cos(w-Om),sw=Math.sin(w-Om),ci=Math.cos(inc),si=Math.sin(inc);
    const xh=(cOm*cw-sOm*sw*ci)*xo+(-cOm*sw-sOm*cw*ci)*yo;
    const yh=(sOm*cw+cOm*sw*ci)*xo+(-sOm*sw+cOm*cw*ci)*yo;
    const zh=si*(sw*xo+cw*yo);
    const gx=xh-xe, gy=yh-ye, gz=zh;
    const dist=Math.sqrt(gx*gx+gy*gy+gz*gz);
    // Equatorial
    const xeq=gx, yeq=gy*Math.cos(eps)-gz*Math.sin(eps), zeq=gy*Math.sin(eps)+gz*Math.cos(eps);
    const ra  =((r2d(Math.atan2(yeq,xeq))%360)+360)%360;
    const dec =r2d(Math.asin(zeq/dist));
    // Elongation
    const sx=-xe,sy=-ye,sz=0;
    const sdist=Math.sqrt(sx*sx+sy*sy+sz*sz);
    const dot=Math.max(-1,Math.min(1,(gx*sx+gy*sy+gz*sz)/(dist*sdist)));
    const elong=r2d(Math.acos(dot));
    // Alt/Az
    const HA = d2r(((LST - ra) % 360 + 360) % 360);
    const decR=d2r(dec);
    const alt =r2d(Math.asin(Math.sin(LAT)*Math.sin(decR)+Math.cos(LAT)*Math.cos(decR)*Math.cos(HA)));
    const azR =Math.atan2(-Math.cos(decR)*Math.sin(HA), Math.sin(decR)*Math.cos(LAT)-Math.cos(decR)*Math.cos(HA)*Math.sin(LAT));
    const az  =((r2d(azR)%360)+360)%360;
    const dirIdx=Math.round(az/22.5)%16;

    let state;
    const sunTimes  = (typeof SunCalc !== "undefined") ? SunCalc.getTimes(now, HOME_LAT, HOME_LON) : null;
    const isDark    = sunTimes
      ? (now >= sunTimes.dusk || now <= sunTimes.dawn)
      : false;
    if (alt <= 5)              state = 'below';
    else if (elong <= 15)      state = 'glare';
    else if (!isDark)          state = 'daytime';
    else                       state = 'visible';

    results.push({name, emoji:EMOJIS[name], color:COLORS[name], alt:alt.toFixed(0), az:az.toFixed(0),
                  dir:dirs[dirIdx], dist:dist.toFixed(2), elong:elong.toFixed(0), visible: state === 'visible', state});
  }

  // Sort: visible → daytime → glare → below
  results.sort((a,b) => {
    const rank = { visible:0, daytime:1, glare:2, below:3 };
    if (rank[a.state] !== rank[b.state]) return rank[a.state] - rank[b.state];
    return b.alt - a.alt;
  });

  const trulyVisible = results.filter(r => r.state === 'visible').length;
  const timeStr  = now.toLocaleTimeString("en-US", {hour:"numeric", minute:"2-digit"});

  const light = isLight();
  const subTxt    = light ? "rgba(0,0,0,0.40)" : "rgba(255,255,255,0.4)";
  const dimTxt    = light ? "rgba(0,0,0,0.28)" : "rgba(255,255,255,0.25)";
  const faintTxt  = light ? "rgba(0,0,0,0.35)" : "rgba(255,255,255,0.3)";
  const dirTxt    = light ? "rgba(0,0,0,0.50)" : "rgba(255,255,255,0.5)";
  const visBg     = light ? "rgba(255,255,255,1.0)" : "rgba(255,255,255,0.08)";
  const visShadow = light ? "0 1px 6px rgba(0,0,0,0.10)" : "none";
  const dimBg     = light ? "rgba(0,0,0,0.025)" : "rgba(255,255,255,0.02)";
  const dimBd     = light ? "rgba(0,0,0,0.07)"  : "rgba(255,255,255,0.06)";
  const headerTxt = light ? "rgba(0,0,0,0.45)"  : "rgba(255,255,255,0.4)";
  const glareColor= light ? "rgba(180,110,0,0.85)" : "rgba(255,190,60,0.85)";
  const dayColor  = light ? "rgba(30,90,200,0.80)" : "rgba(140,180,255,0.85)";

  const headerMsg = trulyVisible > 0
    ? `${trulyVisible} planet${trulyVisible!==1?"s":""} visible at ${timeStr}`
    : `No planets visible at ${timeStr}`;

  let html = `<div style="font-size:0.78rem;color:${headerTxt};margin-bottom:12px;">
    ${headerMsg} — geometric position, not naked-eye visibility
  </div>`;

  html += `<div class="solar-grid" style="display:grid;grid-template-columns:repeat(5,1fr);gap:8px;">`;
  for (const p of results) {
    const isVis   = p.state === 'visible';
    const isDay   = p.state === 'daytime';
    const isGlare = p.state === 'glare';
    const isBelow = p.state === 'below';

    const nameColor   = isVis   ? p.color
                      : isDay   ? (light ? "rgba(0,0,0,0.55)" : "rgba(180,200,255,0.7)")
                      : isGlare ? (light ? "rgba(0,0,0,0.50)" : "rgba(200,200,200,0.6)")
                      :           (light ? "rgba(0,0,0,0.32)" : "rgba(150,150,150,0.4)");
    const borderColor = isVis   ? p.color.replace("0.9","0.5")
                      : isDay   ? (light ? "rgba(30,90,200,0.20)" : "rgba(140,180,255,0.18)")
                      : dimBd;
    const bg          = isVis   ? visBg : dimBg;
    const shadow      = isVis   ? visShadow : "none";
    const emojiOp     = isVis   ? "1"
                      : isDay   ? (light ? "0.60" : "0.50")
                      : isGlare ? (light ? "0.50" : "0.40")
                      :           (light ? "0.30" : "0.22");
    const dataOp      = isVis ? "1" : isDay ? "0.80" : isGlare ? "0.70" : "0.50";

    let statusLine;
    if (isVis) {
      statusLine = `<span style="color:rgba(60,180,80,0.9);">${p.alt}° alt · ${p.dir} ${p.az}°</span>`;
    } else if (isDay) {
      statusLine = `<span style="color:${dayColor};">${p.alt}° alt · sky too bright</span>`;
    } else if (isGlare) {
      statusLine = `<span style="color:${glareColor};">solar glare</span>`;
    } else {
      statusLine = `<span style="color:${faintTxt};">below horizon</span>`;
    }

    html += `
      <div style="background:${bg};border:1px solid ${borderColor};border-radius:10px;
                  padding:10px 8px;text-align:center;box-shadow:${shadow};">
        <div style="margin-bottom:4px;opacity:${emojiOp};display:flex;justify-content:center;">${getPlanetSVG(p.name, 60)}</div>
        <div style="font-size:0.82rem;font-weight:900;color:${nameColor};margin-bottom:5px;">${p.name}</div>
        <div style="font-size:0.72rem;margin-bottom:4px;">${statusLine}</div>
        <div style="font-size:0.68rem;color:${faintTxt};opacity:${dataOp};">${p.elong}° from Sun · ${p.dist} AU</div>
      </div>`;
  }
  html += `</div>`;

  el.innerHTML = html;
  document.getElementById("solarSystemNote").textContent =
    "Positions calculated client-side using VSOP87 truncated series. Accurate to ~1°.";

  // Update collapsed preview with visible planets
  const visiblePlanets = results.filter(r => r.state === 'visible');
  const planetsIconsEl = document.getElementById("planetsIconsCollapsed");
  const planetsNamesEl = document.getElementById("planetsNamesCollapsed");

  if (planetsIconsEl && planetsNamesEl) {
    if (visiblePlanets.length > 0) {
      const icons = visiblePlanets.map(p => getPlanetSVG(p.name, 40)).join('');
      const names = visiblePlanets.map(p => p.name).join(', ');
      planetsIconsEl.innerHTML = icons;
      planetsNamesEl.textContent = names; planetsNamesEl.style.fontSize = ''; planetsNamesEl.style.opacity = ''; planetsNamesEl.style.fontWeight = '';
      const labelEl = document.getElementById('planetsVisibleLabel');
      if (labelEl) labelEl.style.display = '';
    } else {
      planetsIconsEl.innerHTML = '';
      planetsNamesEl.textContent = 'None visible now';
      planetsNamesEl.style.fontSize = '20px';
      planetsNamesEl.style.opacity = '0.75';
      planetsNamesEl.style.fontWeight = '400';
      const labelEl2 = document.getElementById('planetsVisibleLabel');
      if (labelEl2) labelEl2.style.display = 'none';
    }
  }
}
