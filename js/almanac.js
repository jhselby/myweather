// almanac.js — Today almanac card (sunrise, sunset, daylight, moon)

function renderTodayAlmanac(daily) {
  const el = document.getElementById("todayAlmanacContent");
  if (!el) return;

  const now    = new Date();
  const light  = isLight();

  // ── Date basics ──────────────────────────────────────────
  const fullDate = now.toLocaleDateString("en-US", {
    weekday:"long", year:"numeric", month:"long", day:"numeric"
  });
  const startOfYear = new Date(now.getFullYear(), 0, 0);
  const dayOfYear   = Math.floor((now - startOfYear) / 86400000);
  const isLeap      = (now.getFullYear() % 4 === 0 && now.getFullYear() % 100 !== 0) || now.getFullYear() % 400 === 0;
  const daysInYear  = isLeap ? 366 : 365;
  const weekNum     = Math.ceil(dayOfYear / 7);

  // ── Season ────────────────────────────────────────────────
  // Meteorological seasons (Dec 1, Mar 1, Jun 1, Sep 1)
  const yr = now.getFullYear();
  const seasons = [
    { name:"Winter",  start: new Date(yr-1, 11, 1), next: new Date(yr, 2, 1),  nextName:"Spring" },
    { name:"Spring",  start: new Date(yr, 2, 1),    next: new Date(yr, 5, 1),  nextName:"Summer" },
    { name:"Summer",  start: new Date(yr, 5, 1),    next: new Date(yr, 8, 1),  nextName:"Fall"   },
    { name:"Fall",    start: new Date(yr, 8, 1),    next: new Date(yr, 11, 1), nextName:"Winter" },
  ];
  let season = seasons[0];
  for (const s of seasons) {
    if (now >= s.start) season = s;
  }
  const daysToNext  = Math.ceil((season.next - now) / 86400000);

  // ── Daylight ──────────────────────────────────────────────
  let daylightStr = "--";
  let daylightMins = null;
  if (typeof SunCalc !== "undefined") {
    const times0    = SunCalc.getTimes(now, HOME_LAT, HOME_LON);
    const riseMs    = times0.sunrise?.getTime();
    const setMs     = times0.sunset?.getTime();
    if (riseMs && setMs) {
      daylightMins = Math.round((setMs - riseMs) / 60000);
      const h = Math.floor(daylightMins / 60);
      const m = daylightMins % 60;
      daylightStr = `${h}h ${m}m`;
    }
  }

  // Daylight change vs yesterday
  let changeStr = "";
  if (typeof SunCalc !== "undefined" && daylightMins !== null) {
    const yesterday = new Date(now.getTime() - 86400000);
    const ty = SunCalc.getTimes(yesterday, HOME_LAT, HOME_LON);
    if (ty.sunrise && ty.sunset) {
      const yMins = Math.round((ty.sunset - ty.sunrise) / 60000);
      const diff  = daylightMins - yMins;
      const sign  = diff >= 0 ? "+" : "−";
      const absDiff = Math.abs(diff);
      const diffM = Math.floor(absDiff / 60);
      const diffS = absDiff % 60;  // diff is in minutes — get seconds from fractional
      // Actually SunCalc gives millisecond precision — redo in seconds
      const tyMs   = ty.sunset.getTime() - ty.sunrise.getTime();
      const t0Ms   = SunCalc.getTimes(now, HOME_LAT, HOME_LON);
      const todayMs2 = t0Ms.sunset?.getTime() - t0Ms.sunrise?.getTime();
      if (todayMs2 && tyMs) {
        const diffSec = Math.round((todayMs2 - tyMs) / 1000);
        const dSign   = diffSec >= 0 ? "+" : "−";
        const dAbs    = Math.abs(diffSec);
        const dM      = Math.floor(dAbs / 60);
        const dS      = dAbs % 60;
        const dColor  = diffSec >= 0
          ? (light ? "rgba(20,140,60,0.9)" : "rgba(100,220,120,0.9)")
          : (light ? "rgba(180,60,20,0.9)" : "rgba(220,100,80,0.9)");
        changeStr = `<span style="color:${dColor};font-weight:800;">${dSign}${dM > 0 ? dM+"m " : ""}${dS}s vs yesterday</span>`;
      }
    }
  }

  // ── Sunrise / Sunset ──────────────────────────────────────
  let riseStr = "--", setStr = "--";
  if (typeof SunCalc !== "undefined") {
    const t = SunCalc.getTimes(now, HOME_LAT, HOME_LON);
    if (t.sunrise) riseStr = fmtTime(t.sunrise);
    if (t.sunset)  setStr  = fmtTime(t.sunset);
  }

  // ── Moon ──────────────────────────────────────────────────
  let moonPhase = "", moonIllum = "";
  if (typeof SunCalc !== "undefined") {
    const mi = SunCalc.getMoonIllumination(now);
    const phases = [
      [0.025, "New Moon"],      [0.25,  "Waxing Crescent"],
      [0.275, "First Quarter"], [0.5,   "Waxing Gibbous"],
      [0.525, "Full Moon"],     [0.75,  "Waning Gibbous"],
      [0.775, "Last Quarter"],  [1.0,   "Waning Crescent"],
    ];
    moonPhase = phases.find(([t]) => mi.phase < t)?.[1] ?? "New Moon";
    moonIllum = Math.round(mi.fraction * 100) + "% illuminated";
  }

  // ── Render ────────────────────────────────────────────────
  const labelCol = light ? "rgba(0,0,0,0.50)"  : "rgba(255,255,255,0.65)";
  const valCol   = light ? "rgba(0,0,0,0.88)"  : "rgba(255,255,255,0.92)";
  const dimCol   = light ? "rgba(0,0,0,0.38)"  : "rgba(255,255,255,0.50)";
  const divCol   = light ? "rgba(0,0,0,0.06)"  : "rgba(255,255,255,0.08)";

  // Use pure inline styles — no .label/.value classes to avoid !important conflicts
  const rowStyle  = `display:flex;justify-content:flex-start;align-items:baseline;` +
                    `padding:9px 0;border-bottom:1px solid ${divCol};gap:12px;`;
  const lblStyle  = `font-size:0.82rem;color:${labelCol};flex-shrink:0;`;
  const valStyle  = `font-size:0.88rem;font-weight:700;color:${valCol};text-align:right;margin-left:auto;`;
  const subStyle  = `font-size:0.72rem;color:${dimCol};margin-top:1px;font-weight:400;`;

  const row = (label, value, sub = "") => `
    <div style="${rowStyle}">
      <div style="${lblStyle}">${label}</div>
      <div style="${valStyle}">${value}${sub ? `<div style="${subStyle}">${sub}</div>` : ""}</div>
    </div>`;

  el.innerHTML = `
    <div style="font-size:1.05rem;font-weight:900;color:${valCol};margin-bottom:14px;">${fullDate}</div>
    ${row("Day of year",    `${dayOfYear} of ${daysInYear}`, `Week ${weekNum}`)}
    ${row("Season (meteorological)",`${season.name}`, `${daysToNext} days until ${season.nextName}`)}
    ${row("Sunrise",        riseStr)}
    ${row("Sunset",         setStr)}
    ${row("Daylight",       daylightStr, changeStr)}
    ${row("Moon",           moonPhase, moonIllum)}
  `;
}
