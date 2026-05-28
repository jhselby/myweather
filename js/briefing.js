/**
 * briefing.js — Wyman Cove Weather Briefing Tab
 * 
 * Generates editorial-style briefing content from weather_data.json.
 * Vibes headline (impressionistic) + specific summary (numbers).
 * All template-driven, no API calls.
 */

(function () {
  "use strict";

  // ── Lexicon: synonym pools for natural variation ──

  const LEX = {
    sky: {
      clear:    ["clear", "bright", "sunny", "blue"],
      fair:     ["fair", "mostly clear", "pretty clear"],
      cloudy:   ["cloudy", "gray", "overcast"],
      overcast: ["overcast", "gray", "heavy cloud", "leaden"],
      fog:      ["foggy", "murky", "soupy"],
      rain:     ["wet", "rainy"],
      hazy:     ["hazy", "milky", "washed out"],
      snow:     ["snowy", "wintry"],
    },
    temp: {
      frigid: ["bitter", "brutally cold", "frigid"],
      cold:   ["cold", "chilly", "raw"],
      cool:   ["cool", "crisp", "brisk"],
      mild:   ["mild", "comfortable", "pleasant"],
      warm:   ["warm", "nice", "balmy"],
      hot:    ["hot", "sweltering", "scorching"],
    },
    wind: {
      calm:      ["calm", "still", "dead calm"],
      light:     ["a light breeze", "light wind", "barely a breeze"],
      breezy:    ["breezy", "a bit gusty"],
      windy:     ["windy", "gusty", "blowing"],
      dangerous: ["howling", "violent gusts", "screaming"],
    },
  };

  function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }
  function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s; }

  // ── Compass helper ──

  function toCompass(deg) {
    if (deg == null) return "";
    const dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSW","SW","WSW","W","WNW","NW","NNW"];
    return dirs[Math.round(deg / 22.5) % 16];
  }

  // ── Step 1: Interpret — reduce raw data to semantic states ──

  function interpret(data) {
    const cur = data.current || {};
    const hyp = data.hyperlocal || {};
    const der = data.derived || {};
    const hourly = data.hourly || {};
    const daily = data.daily || {};
    const sb = data.sea_breeze || {};

    // Current values (prefer hyperlocal-corrected)
    const temp = Math.round(hyp.corrected_temp ?? cur.temperature ?? 0);
    const windSpeed = Math.round(hyp.corrected_wind_speed ?? cur.wind_speed ?? 0);
    const windGust = Math.round(hyp.corrected_wind_gusts ?? cur.wind_gusts ?? 0);
    const windDeg = cur.wind_direction;
    const windDir = toCompass(windDeg);
    const humidity = Math.round(hyp.corrected_humidity ?? cur.humidity ?? 0);

    // High temp today
    const high = Math.round(der.today_high ?? der.high ?? daily.temperature_max?.[0] ?? 0);

    // Low tonight
    const low = Math.round(der.today_low ?? daily.temperature_min?.[0] ?? 0);

    // Sky condition
    const skyCode = cur.weather_code ?? 0;
    let skyDesc = cur.weather_description || cur.condition_override || "";
    if (!/rain|snow|drizzle|sleet|shower/i.test(skyDesc)) {
      const mn = window.__precipMinutely || [];
      if (mn.length) {
        const mnStale = Math.round((Date.now()/1000 - (mn[0]?.time ?? Date.now()/1000)) / 60);
        const mnPt = mn[Math.min(mnStale, mn.length - 1)];
        if (mnPt && mnPt.precip_intensity > 0.001 && (mnPt.precip_probability ?? 0) >= 0.3) {
          const ci = mnPt.precip_intensity, ct = mnPt.precip_type || 'rain';
          if (ct === 'snow') skyDesc = ci < 0.10 ? 'Light Snow' : ci < 0.30 ? 'Snow' : 'Heavy Snow';
          else if (ct === 'sleet') skyDesc = 'Sleet';
          else skyDesc = ci < 0.01 ? 'Drizzle' : ci < 0.10 ? 'Light Rain' : ci < 0.30 ? 'Moderate Rain' : 'Heavy Rain';
        }
      }
    }

    let skyState = "clear";
    if (skyCode >= 95) skyState = "rain"; // thunderstorm
    else if (skyCode >= 71) skyState = "snow";
    else if (skyCode >= 61) skyState = "rain";
    else if (skyCode >= 51) skyState = "rain"; // drizzle
    else if (skyCode >= 48) skyState = "fog";
    else if (skyCode >= 3) skyState = "cloudy";
    else if (skyCode >= 2) skyState = "fair";

    // Temperature band
    let tempBand = "mild";
    if (high != null) {
      if (high <= 32) tempBand = "frigid";
      else if (high <= 45) tempBand = "cold";
      else if (high <= 58) tempBand = "cool";
      else if (high <= 72) tempBand = "mild";
      else if (high <= 85) tempBand = "warm";
      else tempBand = "hot";
    }

    // Wind band — from impact score (accounts for local exposure), not raw speed
    const _expTable = [[0,25,1],[25,45,.7],[45,100,.25],[100,200,.08],[200,260,.1],[260,290,.4],[290,320,.75],[320,360,1]];
    const _dir = cur.wind_direction;
    let _ef = 0.5;
    if (_dir != null) {
      const _d = ((_dir % 360) + 360) % 360;
      for (const [a, b, f] of _expTable) { if (a <= b ? (_d >= a && _d < b) : (_d >= a || _d < b)) { _ef = f; break; } }
    }
    const _ws = (s) => s * Math.pow(_ef, 1.5);
    const _impact = windSpeed < 15 ? _ws(windSpeed) : _ws(windGust);
    let windBand = "calm";
    if (_impact >= 30) windBand = "dangerous";
    else if (_impact >= 16) windBand = "windy";
    else if (_impact >= 10) windBand = "breezy";
    else if (_impact >= 5) windBand = "light";

    // Wind for display — use the same corrected mph values as the wind card
    const windMph = windSpeed;
    const gustMph = windGust || null;

    // Rain in next 48h — scan hourly precip probability
    const popArr = hourly.precipitation_probability || [];
    const precipArr = hourly.precipitation || [];
    const timeArr = hourly.times || [];
    let rainTiming = null;
    let rainAmount = 0;
    let rainStart = null;
    let rainEnd = null;

    // Sum total precip next 48h
    for (let i = 0; i < Math.min(precipArr.length, 48); i++) {
      rainAmount += (precipArr[i] || 0);
    }
    rainAmount = Math.round(rainAmount * 100) / 100; // mm
    const rainInches = Math.round(rainAmount / 25.4 * 10) / 10; // convert mm to inches

    // Find first/last hour with pop > 40%
    for (let i = 0; i < Math.min(popArr.length, 48); i++) {
      if (popArr[i] >= 40) {
        if (!rainStart && timeArr[i]) rainStart = new Date(timeArr[i]);
        if (timeArr[i]) rainEnd = new Date(timeArr[i]);
      }
    }

    const now = new Date();
    let rainContext = "none";
    if (rainStart) {
      const hoursAway = (rainStart.getTime() - now.getTime()) / 3600000;
      if (hoursAway <= 0) rainContext = "now";
      else if (hoursAway <= 3) rainContext = "soon";
      else if (hoursAway <= 12) rainContext = "later";
      else if (hoursAway <= 48) {
        rainContext = rainStart.toLocaleDateString("en-US", { weekday: "long" });
      }
    }

    // Minutely overrides hourly: if Pirate Weather minutely shows rain within 60 min,
    // upgrade rainContext so a stale far-off day label doesn't contradict imminent rain.
    {
      const minutely = window.__precipMinutely || [];
      if (minutely.length) {
        const nowSec = Math.floor(Date.now() / 1000);
        const dataTime = minutely[0]?.time ?? nowSec;
        const stalenessMin = Math.round((nowSec - dataTime) / 60);
        let firstRainIdx = -1;
        for (let i = 0; i < minutely.length; i++) {
          const pt = minutely[i];
          if (pt.precip_intensity > 0.001 && (pt.precip_probability ?? 0) >= 0.3) {
            firstRainIdx = i; break;
          }
        }
        if (firstRainIdx !== -1) {
          const minAway = firstRainIdx - stalenessMin;
          if (minAway <= 0 && rainContext !== "now") rainContext = "now";
          else if (minAway <= 60 && !["now", "soon"].includes(rainContext)) rainContext = "soon";
        }
      }
    }

    function fmtHour(d) {
      if (!d) return "";
      return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }).toLowerCase();
    }
    const rainStartStr = fmtHour(rainStart);
    const rainEndStr = fmtHour(rainEnd);

    // Fog
    const fogProb = der.fog_probability ?? 0;
    const fogLabel = der.fog_label ?? "No risk";
    // Fog only dominates the headline if it's actually foggy right now (code >= 45)
    // or the probability is very high (>= 70). Otherwise it's just a data row.
    const hasFog = fogProb >= 50;
    const fogIsHeadline = (skyCode >= 45 && skyCode <= 49) || fogProb >= 70;

    // Sea breeze
    // Sea breeze: only meaningful when land is warmer than water (positive delta)
    const sbDelta = parseFloat((sb.reason || "").match(/Δ([-\d.]+)/)?.[1] || "0");
    const seaBreeze = {
      active: (sb.active || false) && sbDelta > 0,
      likelihood: sb.likelihood ?? 0,
      reason: sb.reason || "",
    };

    // Sunset quality — find today's score
    const sunsetArr = data.sunset_directional || [];
    // sunset scoring is done in app-main.js; briefing uses that when available

    // Alerts
    const alerts = data.alerts || [];

    // Frost risk
    const frostRisk = low != null && low <= 32;

    // Time of day
    const hour = now.getHours();
    let timeOfDay = "morning";
    if (hour < 6) timeOfDay = "overnight";
    else if (hour < 12) timeOfDay = "morning";
    else if (hour < 17) timeOfDay = "afternoon";
    else if (hour < 21) timeOfDay = "evening";
    else timeOfDay = "tonight";

    // Time of day label for section header
    const timeLabels = {
      overnight: "tonight",
      morning: "this morning",
      afternoon: "this afternoon",
      evening: "this evening",
      tonight: "tonight",
    };

    // Sky trend — check if cloud cover increases/decreases over next 12h
    // Use a high threshold (40+ point swing) so minor changes don't override reality
    const cloudArr = hourly.cloud_cover || [];
    let skyTrend = "steady";
    if (cloudArr.length >= 12) {
      const nowCloud = cloudArr[0] ?? 50;
      const laterCloud = cloudArr[11] ?? 50;
      if (laterCloud - nowCloud > 40) skyTrend = "clouding";
      else if (nowCloud - laterCloud > 40) skyTrend = "clearing";
    }

    // Month name
    const monthNames = ["January","February","March","April","May","June","July","August","September","October","November","December"];
    const month = monthNames[now.getMonth()];

    // ── Step 2: Prioritize ──
    // Rule: current reality beats model predictions.
    // "Clear now but clouds later" is not the same as "cloudy."

    const isClearNow = skyCode <= 2; // clear, mostly clear, partly cloudy

    const criticalAlert = alerts.find(a => a.severity === "Extreme" || a.severity === "Severe");

    let priority = "quiet";
    if (criticalAlert) priority = "alert";
    else if (rainContext === "now") priority = "rain_now";
    else if (rainContext === "soon") priority = "rain_soon";
    else if (alerts.length > 0) priority = "alert";
    else if (fogIsHeadline) priority = "fog";
    else if (rainContext === "later") priority = "rain_later";
    else if (seaBreeze.active) priority = "sea_breeze";
    else if (isClearNow && skyTrend === "clouding") priority = "clear_changing";
    else if (!isClearNow && skyTrend !== "steady") priority = "trend";
    else if (windBand === "windy" || windBand === "dangerous") priority = "wind";
    else if (tempBand === "hot" || tempBand === "frigid") priority = "temp_extreme";
    else if (frostRisk) priority = "frost";

    return {
      temp, high, low, windSpeed, windMph, gustMph, windDir, windDeg, humidity,
      skyState, skyDesc, tempBand, windBand, skyTrend,
      rainContext, rainInches, rainAmount, rainStartStr, rainEndStr,
      fogProb, fogLabel, hasFog,
      seaBreeze, alerts, frostRisk,
      timeOfDay, timeLabel: timeLabels[timeOfDay] || "today",
      month, priority,
      // Pass through for data rows
      _data: data,
    };
  }

  // ── Lifestyle score helpers ──

  function getLifestyleCutoffs(data) {
    const now = new Date();
    const daily = data?.daily || {};
    const todaySunsetIso = daily.sunset?.[0] || null;
    const todaySunset = todaySunsetIso ? new Date(todaySunsetIso) : null;

    let civilDusk = null;
    if (typeof SunCalc !== "undefined") {
      try {
        const scTimes = SunCalc.getTimes(now, 42.5014, -70.8750);
        civilDusk = scTimes?.dusk || null;
      } catch (e) {}
    }

    // Fallback: civil dusk is roughly 30 minutes after sunset if SunCalc is unavailable
    if (!civilDusk && todaySunset) {
      civilDusk = new Date(todaySunset.getTime() + 30 * 60 * 1000);
    }

    const beachCutoff = todaySunset;
    const hairCutoff = todaySunset ? new Date(todaySunset.getTime() + 2 * 60 * 60 * 1000) : null;

    return {
      now,
      civilDusk,
      beachCutoff,
      hairCutoff,
    };
  }

  function getSunsetScore(data) {
    const cutoffs = getLifestyleCutoffs(data);
    const useTomorrow = !!(cutoffs.civilDusk && cutoffs.now >= cutoffs.civilDusk);
    const todaySrc = window.__todaySunsetScore || null;
    const tomorrowSrc = window.__tomorrowSunsetScore || null;
    const src = (useTomorrow && tomorrowSrc) ? tomorrowSrc : todaySrc;
    if (src && src.score != null) {
      return { score: src.score, label: src.label, color: src.color, tomorrow: !!(useTomorrow && tomorrowSrc) };
    }
    return null;
  }

  function getBeachDayScore(data) {
    const cutoffs = getLifestyleCutoffs(data);
    const useTomorrow = !!(cutoffs.beachCutoff && cutoffs.now >= cutoffs.beachCutoff);

    const src = (useTomorrow && window.__tomorrowDockScore) ? window.__tomorrowDockScore : window.__todayDockScore;
    if (src) {
      const displayScore = typeof wineScaleDock === 'function' ? wineScaleDock(src.score) : Math.round(src.score * 100);
      return { score: displayScore, label: src.label, color: src.color, tomorrow: useTomorrow && !!window.__tomorrowDockScore };
    }
    return null;
  }

  function getHairDayScore(data) {
    const cutoffs = getLifestyleCutoffs(data);
    const useTomorrow = !!(cutoffs.hairCutoff && cutoffs.now >= cutoffs.hairCutoff);

    const src = (useTomorrow && window.__tomorrowHairScore) ? window.__tomorrowHairScore : window.__todayHairScore;
    if (src) {
      const displayScore = typeof wineScaleHair === 'function' ? wineScaleHair(src.score) : src.score;
      return { score: displayScore, label: src.scoreLabel, color: src.color, tomorrow: useTomorrow && !!window.__tomorrowHairScore };
    }
    return null;
  }

  // Simplified sunset estimate for standalone preview (no app-main globals)
  function estimateSunsetScore(data) {
    const cloudArr = data.hourly?.cloud_cover || [];
    // Rough: check cloud cover around hour 18-20 (sunset time in NE)
    const sunsetClouds = cloudArr.slice(12, 16); // approximate
    if (!sunsetClouds.length) return null;
    const avgCloud = sunsetClouds.reduce((a, b) => a + b, 0) / sunsetClouds.length;
    // Best sunsets: 30-70% cloud cover. Clear = boring, overcast = no color.
    let score;
    if (avgCloud >= 30 && avgCloud <= 70) score = 70 + Math.round((1 - Math.abs(avgCloud - 50) / 20) * 20);
    else if (avgCloud < 30) score = 30 + Math.round(avgCloud);
    else score = Math.max(10, 60 - Math.round((avgCloud - 70) * 0.8));
    
    let label;
    if (score >= 75) label = "Great";
    else if (score >= 55) label = "Good";
    else if (score >= 35) label = "Fair";
    else label = "Poor";
    return { score, label };
  }

  // Simplified beach day estimate for standalone preview
  function estimateBeachDayScore(s) {
    if (s.high == null) return null;
    let score = 50;
    if (s.high >= 70) score += 20;
    else if (s.high >= 60) score += 10;
    else if (s.high <= 50) score -= 20;
    if (s.windBand === "calm" || s.windBand === "light") score += 15;
    else if (s.windBand === "windy") score -= 20;
    else if (s.windBand === "dangerous") score -= 40;
    if (s.rainContext === "now" || s.rainContext === "soon") score -= 30;
    else if (s.rainContext === "later") score -= 10;
    score = Math.max(0, Math.min(100, score));
    
    let label;
    if (score >= 75) label = "Great day";
    else if (score >= 58) label = "Good day";
    else if (score >= 38) label = "Marginal";
    else if (score >= 20) label = "Poor";
    else label = "Stay inside";
    return { score, label };
  }

  // Simplified hair day estimate for standalone preview
  function estimateHairDayScore(s) {
    let score = 70;
    if (s.humidity >= 80) score -= 25;
    else if (s.humidity >= 65) score -= 10;
    if (s.windBand === "windy" || s.windBand === "dangerous") score -= 20;
    else if (s.windBand === "breezy") score -= 5;
    if (s.rainContext === "now" || s.rainContext === "soon") score -= 20;
    score = Math.max(0, Math.min(100, score));
    
    let label;
    if (score >= 88) label = "Great hair day";
    else if (score >= 74) label = "Good hair day";
    else if (score >= 58) label = "Manageable";
    else if (score >= 40) label = "Frizz risk";
    else if (score >= 25) label = "Bad hair day";
    else label = "Stay inside";
    return { score, label };
  }

  // ── Build lifestyle rows ──

  function buildLifestyleRows(s) {
    const rows = [];

    // Sunset — only show if Good or better
    const sunset = getSunsetScore(s._data) || estimateSunsetScore(s._data);
    if (sunset) {
      rows.push({
        label: sunset.tomorrow ? "Sunset (tomorrow)" : "Sunset",
        value: sunset.label,
        color: ["Spectacular","Very Good"].includes(sunset.label) ? "orange" : sunset.label === "Good" ? "green" : null,
      });
    }

    // Beach Day — always show (it's why you check the weather)
    const beach = getBeachDayScore(s._data) || estimateBeachDayScore(s);
    if (beach) {
      rows.push({
        label: beach.tomorrow ? "Beach day (tomorrow)" : "Beach day",
        value: beach.label,
        color: beach.label === "Great day" ? "green" : beach.label === "Good day" ? null : beach.label === "Stay inside" ? "red" : "orange",
      });
    }

    // Hair Day — only show if notable (bad or great, not middling)
    const hair = getHairDayScore(s._data) || estimateHairDayScore(s);
    if (hair) {
      rows.push({
        label: hair.tomorrow ? "Hair day (tomorrow)" : "Hair day",
        value: hair.label,
        color: ["Great hair day","Good hair day"].includes(hair.label) ? "green" : ["Bad hair day","Stay inside"].includes(hair.label) ? "red" : ["Frizz risk"].includes(hair.label) ? "orange" : null,
      });
    }

    // Birds — species count from eBird
    const birds = s._data.birds || {};
    const speciesCount = birds.species_count;
    if (speciesCount) {
      rows.push({ label: "Birds", value: speciesCount + " species spotted nearby · Last 48h", color: null });
    }

    return rows;
  }

  // ── Step 3: Generate vibes headline ──

  function vibesHeadline(s) {
    const skyW = pick(LEX.sky[s.skyState] || ["quiet"]);
    const tempW = pick(LEX.temp[s.tempBand] || ["mild"]);
    const windW = pick(LEX.wind[s.windBand] || ["calm"]);

    const pools = {
      rain_now: [
        "It's already raining.",
        "Rain is here.",
        "Wet out there right now.",
        "Raining — not going anywhere soon.",
      ],
      rain_soon: [
        "Rain is close.",
        "It won't stay dry for long.",
        "Grab what you need — rain's coming.",
        "The dry window is closing.",
      ],
      rain_later: [
        "Dry for now, rain later.",
        "Nice start, wetter later.",
        "Enjoy the dry stretch while it lasts.",
        `${cap(skyW)} now — won't last.`,
        "You'll get the dry part first.",
      ],
      alert: [
        "There's an advisory up.",
        "Not a great day to push it.",
        `${cap(windW)} — advisory in effect.`,
        "The weather service wants your attention.",
      ],
      fog: [
        "Fog is the whole story.",
        "A murky start.",
        "Visibility could get weird for a bit.",
        "Soupy early, clearing later.",
      ],
      sea_breeze: [
        "Sea breeze is running.",
        "The onshore flow is here.",
        `${cap(tempW)}, with a sea breeze making itself known.`,
        "Wind shifted onshore.",
      ],
      clear_changing: [
        `${cap(skyW)} now, but clouds are coming.`,
        `${cap(tempW)} and ${skyW} — enjoy it while it lasts.`,
        "The nice part comes first.",
        `${cap(skyW)} start, grayer later.`,
        `${cap(tempW)} ${skyW} morning. Clouds build later.`,
      ],
      trend: s.skyTrend === "clearing" ? [
        "It gets better later.",
        "The sky opens up as the day goes.",
        "Gray early, nicer later.",
        "Clouds pull back — patience pays off.",
      ] : [
        "The brighter part comes first.",
        "More clouds as the day goes on.",
        `${cap(skyW)} now, but it won't last.`,
        "Gets grayer later.",
      ],
      wind: [
        `${cap(windW)} out there.`,
        "The wind is the story today.",
        `${cap(tempW)}, but windy.`,
        "The breeze has some edge to it.",
      ],
      temp_extreme: s.tempBand === "hot" ? [
        "A hot one.",
        `${cap(tempW)} — not much relief.`,
        "Going to cook out there.",
        `${cap(tempW)} and sticky.`,
      ] : [
        `${cap(tempW)} today.`,
        `A ${tempW} one.`,
        "Not exactly comfortable out there.",
        `${cap(tempW)} and raw.`,
      ],
      frost: [
        "Frost tonight — cover anything tender.",
        "Cold enough for frost by morning.",
        "Clear and cold tonight.",
      ],
      quiet: [
        "Not much going on.",
        "Pretty quiet out.",
        `${cap(tempW)} and easy.`,
        `${cap(skyW)} and not much else.`,
        "Hard to complain about that.",
        `${cap(skyW)}, ${tempW}. Done.`,
        "A simple weather day.",
        "Kind of an easy one.",
        `A ${tempW} ${s.month} ${s.timeOfDay === "morning" ? "morning" : "day"}.`,
        `${cap(skyW)} and ${tempW} — about right for ${s.month}.`,
        `${cap(tempW)}. ${cap(skyW)}. Nothing else to report.`,
      ],
    };

    return pick(pools[s.priority] || pools.quiet);
  }

  // ── Step 4: Generate specific summary ──

  function specificSummary(s) {
    const gustStr = s.gustMph ? `, gusts ${s.gustMph}` : "";

    // Clause 1: current conditions
    const c1Pool = [
      `${s.temp}° now, high of ${s.high}°.`,
      `${s.temp}° and ${s.skyDesc.toLowerCase() || "quiet"}, heading to ${s.high}°.`,
      `Currently ${s.temp}°, high ${s.high}°.`,
    ];
    const c1 = pick(c1Pool);

    // Clause 2: the priority detail
    let c2 = "";
    switch (s.priority) {
      case "rain_now":
        c2 = `Rain ongoing${s.rainInches > 0 ? `, ${s.rainInches}" so far` : ""}. Wind ${s.windMph} mph ${s.windDir}${gustStr}.`;
        break;
      case "rain_soon":
        c2 = `Rain by ${s.rainStartStr}${s.rainInches > 0 ? `, ${s.rainInches}" expected` : ""}. Wind ${s.windMph} mph ${s.windDir}.`;
        break;
      case "rain_later":
        c2 = `Rain ${s.rainStartStr}–${s.rainEndStr}, ${s.rainInches}". Wind ${s.windMph} mph ${s.windDir}.`;
        break;
      case "alert":
        c2 = `${s.alerts[0].event}${s.alerts[0].description ? "" : ""}. ${s.windMph} mph ${s.windDir}${gustStr}.`;
        break;
      case "fog":
        c2 = `Fog probability ${s.fogProb}%. Wind ${s.windMph} mph ${s.windDir}.`;
        break;
      case "clear_changing":
        c2 = `Cloud cover builds later. Wind ${s.windMph} mph ${s.windDir}.`;
        break;
      case "sea_breeze":
        c2 = `Sea breeze active (${s.seaBreeze.likelihood}% likelihood). ${s.windMph} mph ${s.windDir}${gustStr}.`;
        break;
      case "trend":
        c2 = s.skyTrend === "clearing"
          ? `Clearing later. Wind ${s.windMph} mph ${s.windDir}.`
          : `Clouds building. Wind ${s.windMph} mph ${s.windDir}.`;
        break;
      case "wind":
        c2 = `Wind ${s.windMph} mph ${s.windDir}${gustStr}.`;
        break;
      case "temp_extreme":
        c2 = s.tempBand === "hot"
          ? `${s.windMph > 5 ? `Wind ${s.windMph} mph ${s.windDir}.` : "Barely a breeze."}`
          : `Wind ${s.windMph} mph ${s.windDir}${gustStr} — feels worse.`;
        break;
      case "frost":
        c2 = `Tonight drops to ${s.low}°. Frost likely by dawn.`;
        break;
      default:
        if (s.rainContext && s.rainContext !== "none") {
          c2 = `Next rain: ${s.rainContext}. Wind ${s.windMph} mph ${s.windDir}.`;
        } else {
          c2 = `No rain in sight. Wind ${s.windMph} mph ${s.windDir}.`;
        }
    }

    return `${c1} ${c2}`;
  }

  // ── Step 5: Build data rows for TODAY section ──

  function buildRows(s) {
    const rows = [];
    const der = s._data.derived || {};
    const sb = s._data.sea_breeze || {};

    // Sky — always show
    let skyValue = cap(s.skyDesc || s.skyState);
    if (s.skyTrend === "clearing") skyValue += " — clearing later";
    else if (s.skyTrend === "clouding") skyValue += " — clouding up later";
    rows.push({ label: "Sky", value: skyValue, color: null });

    // Wind — always show
    const gustNote = s.gustMph ? `, gusts ${s.gustMph}` : "";
    rows.push({
      label: "Wind",
      value: `${s.windMph} mph ${s.windDir}${gustNote}`,
      color: s.windBand === "dangerous" ? "red" : s.windBand === "windy" ? "orange" : null,
    });

    // High / Low
    if (s.high != null && s.low != null) {
      rows.push({ label: "High / Low", value: s.high + "° / " + s.low + "°", color: null });
    }

    // Sea breeze — only if active with positive delta, or likely
    const sbDeltaRow = parseFloat((sb.reason || "").match(/Δ([-\d.]+)/)?.[1] || "0");
    if (sb.active && sbDeltaRow > 0) {
      rows.push({ label: "Sea breeze", value: `Active — ${sb.reason || "onshore flow"}`, color: "green" });
    } else if ((sb.likelihood ?? 0) >= 40 && sbDeltaRow > 0) {
      rows.push({ label: "Sea breeze", value: `${sb.likelihood}% likely`, color: "orange" });
    }

    // Feels like — compute from s.temp (today's high) so feelsDiff comparison is meaningful
    let feelsLike = s.temp;
    if (s.temp != null) {
      const T = s.temp;
      const wind = s.windMph ?? 0;
      const RH = s.humidity;

      if (T <= 50 && wind > 3) {
        feelsLike = 35.74 + (0.6215 * T) - (35.75 * Math.pow(wind, 0.16)) + (0.4275 * T * Math.pow(wind, 0.16));
      } else if (T >= 80 && RH != null) {
        feelsLike =
          -42.379 +
          2.04901523 * T +
          10.14333127 * RH -
          0.22475541 * T * RH -
          0.00683783 * T * T -
          0.05481717 * RH * RH +
          0.00122874 * T * T * RH +
          0.00085282 * T * RH * RH -
          0.00000199 * T * T * RH * RH;
      } else {
        feelsLike = s._data.current?.apparent_temperature ?? T;
      }
    }

    feelsLike = Math.round(feelsLike);
    const feelsDiff = Math.abs(feelsLike - s.temp);
    const showWindChill = feelsLike < s.temp && s.temp <= 40 && feelsDiff >= 5;
    const showHeatIndex = feelsLike > s.temp && s.temp >= 80 && feelsDiff >= 3;
    if (showWindChill) {
      rows.push({ label: "Wind chill", value: feelsLike + "°", color: feelsLike <= 20 ? "red" : feelsLike <= 32 ? "orange" : null });
    } else if (showHeatIndex) {
      const derivedHI = s._data?.derived?.heat_index;
      const displayHI = derivedHI != null ? Math.round(derivedHI) : feelsLike;
      const fullSun = s._data?.derived?.corrected_feels_like;
      const fullSunRounded = fullSun != null ? Math.round(fullSun) : null;
      const hiValue = fullSunRounded != null && fullSunRounded > displayHI + 3
        ? `${displayHI}° in shade · ${fullSunRounded}° in full sun`
        : displayHI + "°";
      rows.push({ label: "Heat index", value: hiValue, color: displayHI >= 100 ? "red" : displayHI >= 90 ? "orange" : null });
    }

    // Humidity — show when notably high or low
    if (s.humidity >= 80) {
      rows.push({ label: "Humidity", value: s.humidity + "%", color: s.humidity >= 90 ? "red" : "orange" });
    } else if (s.humidity <= 25) {
      rows.push({ label: "Humidity", value: s.humidity + "% — very dry", color: "blue" });
    }

    return rows;
  }

  function buildAlmanacRows(s) {
    const rows = [];

    function fmtTimeShort(iso) {
      if (!iso) return "";
      const d = new Date(iso);
      return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }).toLowerCase();
    }

    // Sun
    const daily = s._data.daily || {};
    const todaySunrise = daily.sunrise?.[0];
    const todaySunset = daily.sunset?.[0];
    if (todaySunrise || todaySunset) {
      rows.push({ label: "Sun", value: "↑ " + fmtTimeShort(todaySunrise) + "  ↓ " + fmtTimeShort(todaySunset), color: null });
    }

    // Next tide
    const tideEvents = (s._data.tides || {}).events || [];
    const nowMs = Date.now();
    const nextTide = tideEvents.find(function(e) {
      return new Date(e.date + "T" + e.time).getTime() >= nowMs;
    });
    if (nextTide) {
      const typeStr = nextTide.type === "H" ? "High" : "Low";
      const ht = parseFloat(nextTide.height).toFixed(1);
      rows.push({ label: "Tide", value: typeStr + " " + fmtTimeShort(nextTide.date + "T" + nextTide.time) + " (" + ht + " ft)", color: null });
    }

    // Moon
    if (typeof SunCalc !== "undefined") {
      const mi = SunCalc.getMoonIllumination(new Date());
      const phases = [[0.025,"New Moon"],[0.25,"Waxing Crescent"],[0.275,"First Quarter"],[0.5,"Waxing Gibbous"],[0.525,"Full Moon"],[0.75,"Waning Gibbous"],[0.775,"Last Quarter"],[1.0,"Waning Crescent"]];
      const moonName = phases.find(function(p) { return mi.phase < p[0]; })?.[1] ?? "New Moon";
      const illum = Math.round(mi.fraction * 100);
      rows.push({ label: "Moon", value: moonName + " (" + illum + "%)", color: null });
    }

    return rows;
  }

  // ── Step 6: Build WATCH FOR rows ──

  function buildPrecipMiniBar() {
    const minutely = window.__precipMinutely || [];
    if (!minutely.length) return null;
    const now = Math.floor(Date.now() / 1000);
    const dataTime = minutely[0]?.time ?? now;
    const stalenessMin = Math.round((now - dataTime) / 60);
    let firstRainIdx = -1, lastRainIdx = -1, maxIntensity = 0;
    minutely.forEach((pt, i) => {
      const prob = pt.precip_probability ?? 0;
      if (pt.precip_intensity > 0.001 && prob >= 0.3) {
        if (firstRainIdx === -1) firstRainIdx = i;
        lastRainIdx = i;
        if (pt.precip_intensity > maxIntensity) maxIntensity = pt.precip_intensity;
      }
    });
    const firstRainFromNow = firstRainIdx === -1 ? -1 : firstRainIdx - stalenessMin;
    const lastRainFromNow  = lastRainIdx  === -1 ? -1 : lastRainIdx  - stalenessMin;
    const peakIntensity = maxIntensity < 0.10 ? 'Light' : maxIntensity < 0.30 ? 'Moderate' : 'Heavy';
    const curIdx = Math.min(stalenessMin, minutely.length - 1);
    const curI = minutely[curIdx]?.precip_intensity || 0;
    const nowIntensity = curI < 0.10 ? 'Light' : curI < 0.30 ? 'Moderate' : 'Heavy';
    let summaryText = '';
    if (firstRainFromNow <= 0) {
      summaryText = `${nowIntensity} rain now — ending in ~${Math.max(1, lastRainFromNow + 1)} min`;
    } else {
      const duration = lastRainIdx - firstRainIdx + 1;
      summaryText = `${peakIntensity} rain in ~${firstRainFromNow} min, lasting ~${duration} min`;
    }
    const maxI = Math.max(...minutely.map(p => p.precip_intensity), 0.01);
    const bars = minutely.map((pt, i) => {
      const h = Math.max(1, Math.round((pt.precip_intensity / maxI) * 28));
      const prob = pt.precip_probability ?? 0;
      const likely = prob >= 0.3;
      const baseColor = pt.precip_type === 'snow' ? '160,200,255' : pt.precip_type === 'sleet' ? '200,160,255' : '100,160,255';
      const opacity = likely ? 0.85 : 0.15;
      return `<div style="flex:1;display:flex;align-items:flex-end;height:28px;"><div style="width:100%;height:${h}px;background:rgba(${baseColor},${opacity});border-radius:1px 1px 0 0;"></div></div>`;
    }).join('');
    return `<div onclick="openPrecipModal()" style="cursor:pointer;padding:8px 0 4px;">
      <div style="font-size:0.88rem;margin-bottom:6px;opacity:0.85;">🌧 ${summaryText}</div>
      <div style="display:flex;align-items:flex-end;gap:1px;height:28px;">${bars}</div>
    </div>`;
  }

  function buildWatchRows(s) {
    const rows = [];
    const der = s._data.derived || {};
    const sb = s._data.sea_breeze || {};

    // 1. NWS alerts (highest urgency)
    for (const a of s.alerts) {
      rows.push({
        label: "Alert",
        value: a.event,
        detail: a.description ? a.description.slice(0, 120) : "",
        color: "red",
        isAlert: true,
      });
    }

    // 2. Storm flags — derive title from the most specific flag, show rest as detail
    const stormFlags = window.__stormFlags || [];
    if (stormFlags.length >= 2) {
      const titlePriority = [
        f => f.includes("Freezing rain") && f,
        f => f.includes("Snow") && f,
        f => f.includes("Heavy rain") && f,
        f => f.includes("Mixed precip") && f,
        f => f.includes("Rain likely") && f,
        f => f.includes("gusts") && f,
        f => f.includes("system approaching") && f,
        f => f.includes("Pressure") && f,
      ];
      let title = null;
      for (const test of titlePriority) {
        title = stormFlags.map(test).find(Boolean) || null;
        if (title) break;
      }
      if (!title) title = stormFlags[0];
      const detail = stormFlags.filter(f => f !== title).join(" · ");
      rows.push({
        label: "Storm",
        value: title,
        detail,
        color: "orange",
        isAlert: true,
      });
    }

    // 3. Thunderstorm / lightning — active always shows; watch only shows at Moderate risk or higher
    const ts = der.thunderstorm;
    if (ts && ts.active) {
      const distStr = ts.min_distance_km != null ? ` · closest ${ts.min_distance_km} km` : "";
      const label = ts.severity === "severe" ? "Severe Thunderstorm" : "Thunderstorm";
      rows.push({
        label,
        value: `${ts.lightning_count} strike${ts.lightning_count !== 1 ? "s" : ""}/hr${distStr}`,
        color: ts.severity === "severe" ? "red" : "orange",
        isAlert: true,
      });
    } else if (ts && ts.severity === "watch" && ts.cape_label !== "Weak") {
      const riskDesc = ts.cape_label === "Extreme" ? "Extreme risk" :
                       ts.cape_label === "High"    ? "High risk" :
                                                     "Moderate risk";
      rows.push({
        label: "Thunderstorm risk",
        value: riskDesc,
        color: "orange",
        isAlert: false,
      });
    }

    // 4. Precip mini bar (current/imminent rain)
    if (window.__precipHasRain) {
      const miniBar = buildPrecipMiniBar();
      if (miniBar) rows.push({ isHtml: true, html: miniBar });
    }

    // 5. Next rain
    if (s.rainContext && !["none","now","soon","later"].includes(s.rainContext)) {
      rows.push({ label: "Next rain", value: s.rainContext, color: "blue" });
    }

    // 6. Wind
    const windImpact = der.wind_impact_score ?? 0;
    const gustMph = Math.round(s._data.hyperlocal?.corrected_wind_gusts ?? s._data.current?.wind_gusts ?? s.gustMph ?? 0);
    if (windImpact >= 7) {
      let windValue = "Impact " + windImpact + "/10";
      if (gustMph >= 25) windValue += " · Gusts " + gustMph + " mph";
      rows.push({ label: "Wind", value: windValue, color: windImpact >= 9 ? "red" : "orange" });
    }

    // 7. Fog
    const fogProb = der.fog_probability ?? 0;
    if (fogProb >= 50) {
      rows.push({ label: "Fog", value: fogProb + "% probability", color: "orange", dim: fogProb < 70 });
    }

    // 8. Frost risk
    if (s.low != null && s.low <= 36) {
      rows.push({ label: "Frost risk", value: "Low tonight " + s.low + "°", color: s.low <= 32 ? "red" : "orange" });
    }

    // 9. Sea breeze
    const sbLikelihood = sb.likelihood ?? 0;
    const sbDelta = parseFloat((sb.reason || "").match(/Δ([-\d.]+)/)?.[1] || "0");
    if (sbLikelihood >= 60 && sbDelta > 0) {
      rows.push({ label: "Sea breeze", value: sbLikelihood + "% likely", color: "blue", dim: true });
    }

    // 10. Heat stress (WBGT)
    {
      const hTemps  = s._data.hourly?.corrected_temperature || s._data.hourly?.temperature || [];
      const hWb     = s._data.hourly?.corrected_wet_bulb    || s._data.hourly?.wet_bulb    || [];
      const hRad    = s._data.hourly?.direct_radiation || [];
      const hTimes  = s._data.hourly?.times || [];
      const todayStr = new Date().toLocaleDateString("en-US");
      let peakWBGT = 0, peakHour = null;
      hTimes.forEach((t, i) => {
        const dt = new Date(t);
        if (dt.toLocaleDateString("en-US") !== todayStr) return;
        const h = dt.getHours();
        if (h < 9 || h > 18) return;
        const T  = hTemps[i] ?? null;
        const Tw = hWb[i]    ?? null;
        if (T == null || Tw == null) return;
        const wbgt = 0.7 * Tw + 0.3 * T + 0.002 * (hRad[i] ?? 0);
        if (wbgt > peakWBGT) { peakWBGT = wbgt; peakHour = dt; }
      });
      if (peakWBGT >= 80) {
        const risk  = peakWBGT >= 88 ? "High risk" : peakWBGT >= 83 ? "Moderate" : "Caution";
        const color = peakWBGT >= 88 ? "red" : "orange";
        const dim   = peakWBGT < 83;
        const timeStr = peakHour ? " · peaks " + peakHour.toLocaleTimeString("en-US", { hour: "numeric" }) : "";
        rows.push({ label: "Heat stress", value: `WBGT ${Math.round(peakWBGT)}°F · ${risk}${timeStr}`, color, dim });
      }
    }

    // 11. UV index — only when high or above, and only during the UV window
    {
      const hUV    = s._data.hourly?.uv_index || [];
      const hTimes = s._data.hourly?.times || [];
      const todayISO = new Date().toISOString().slice(0, 10);
      const nowHour = new Date().getHours();
      let uvPeak = null;
      hTimes.forEach((t, i) => {
        if (!t || !t.startsWith(todayISO)) return;
        const h = new Date(t).getHours();
        if (h < nowHour || h > 17) return;   // only current hour onward, within UV window
        const v = hUV[i];
        if (v != null && (uvPeak === null || v > uvPeak)) uvPeak = v;
      });
      if (uvPeak != null && uvPeak >= 6) {
        const uv = Math.round(uvPeak);
        const value = uv >= 11 ? `UV ${uv} — extreme` :
                      uv >= 8  ? `UV ${uv} — very high, limit midday exposure` :
                                 `UV ${uv} — high, wear sunscreen`;
        rows.push({ label: "UV", value, color: "orange" });
      }
    }

    return rows;
  }

  // ── Step 7: Tonight row ──

  function buildTonightRow(s) {
    const parts = [];
    if (s.low != null) parts.push(`Low ${s.low}°`);
    if (s.frostRisk) parts.push("frost likely");
    return parts.length ? parts.join(", ") : null;
  }

  // ── Main export: generate full briefing ──

  function generateBriefing(data) {
    const s = interpret(data);

    // Use AI-generated headline/subheadline if available, fall back to templates
    const aiBriefing = data.briefing || {};
    const headline = aiBriefing.headline || vibesHeadline(s);
    const summary = aiBriefing.subheadline || specificSummary(s);

    return {
      timeLabel: s.timeLabel,
      headline: headline,
      summary: summary,
      stats: {
        now: s.temp,
        high: s.high,
        rainInches: s.rainInches,
        rainAmount: s.rainAmount,
        rainContext: s.rainContext,
      },
      todayRows: buildRows(s),
      almanacRows: buildAlmanacRows(s),
      lifestyleRows: buildLifestyleRows(s),
      watchRows: buildWatchRows(s),
      tonight: buildTonightRow(s),
      priority: s.priority,
      isAI: !!aiBriefing.headline,
    };
  }

  // Expose globally
  window.generateBriefing = generateBriefing;

})();

// Briefing Tab Renderer
function renderBriefing(data) {
  if (typeof generateBriefing !== 'function') return;
  const b = generateBriefing(data);
  const now = new Date();
  const days = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
  const months = ['January','February','March','April','May','June','July','August','September','October','November','December'];
  const dl = document.getElementById('briefDateline');
  if (dl) {
    const dateStr = days[now.getDay()] + ' · ' + now.getDate() + ' ' + months[now.getMonth()];
    const genAt = data.generated_at ? new Date(data.generated_at) : null;
    const ageMin = genAt ? Math.round((now - genAt) / 60000) : null;
    const ageStr = ageMin != null ? (ageMin < 1 ? 'just now' : ageMin + 'm ago') : '';
    dl.innerHTML = '<span>' + dateStr + '</span>' + (ageStr ? '<span class="brief-dateline-age">' + ageStr + '</span>' : '');
  }
  const tl = document.getElementById('briefTimeLabel');
  if (tl) tl.textContent = b.timeLabel;
  const hl = document.getElementById('briefHeadline');
  if (hl) {
    hl.textContent = b.headline;
    hl.style.fontStyle = b.isAI ? 'normal' : 'italic';
  }
  const staleEl = document.getElementById('briefHeadlineStale');
  if (staleEl) {
    const cachedAt = data.briefing?.cached_at ? new Date(data.briefing.cached_at) : null;
    const headlineAge = cachedAt ? Math.round((now - cachedAt) / 60000) : null;
    if (b.isAI && headlineAge != null && headlineAge >= 90) {
      const hStr = headlineAge >= 120 ? Math.round(headlineAge / 60) + 'h' : headlineAge + 'm';
      staleEl.textContent = 'headline from ' + hStr + ' ago';
      staleEl.style.display = '';
    } else {
      staleEl.style.display = 'none';
    }
  }
  const sm = document.getElementById('briefSummary');
  if (sm) sm.textContent = b.summary;
  const sn = document.getElementById('briefTempNow');
  if (sn) sn.innerHTML = (b.stats.now ?? '--') + '<span class="unit">°</span>';
  const sh = document.getElementById('briefTempHigh');
  if (sh) sh.innerHTML = (b.stats.high ?? '--') + '<span class="unit">°</span>';
  // Inject wind impact score into briefing Wind row
  const hyp = data.hyperlocal || {};
  const cur = data.current || {};
  const sc = document.getElementById('briefConditions');
  const scl = document.getElementById('briefConditionsLabel');
  if (sc) {
    const raw = cur.weather_description || cur.condition_override || '--';
    // Override with Pirate Weather radar if it shows current precip and HRRR doesn't
    let displayCondition = raw;
    if (!/rain|snow|drizzle|sleet|shower/i.test(raw)) {
      const mn = window.__precipMinutely || [];
      if (mn.length) {
        const mnNow = Math.floor(Date.now() / 1000);
        const mnStale = Math.round((mnNow - (mn[0]?.time ?? mnNow)) / 60);
        const mnCur = mn[Math.min(mnStale, mn.length - 1)];
        if (mnCur && mnCur.precip_intensity > 0.001 && (mnCur.precip_probability ?? 0) >= 0.3) {
          const ci = mnCur.precip_intensity;
          const ct = mnCur.precip_type || 'rain';
          if (ct === 'snow') displayCondition = ci < 0.10 ? 'Light Snow' : ci < 0.30 ? 'Snow' : 'Heavy Snow';
          else if (ct === 'sleet') displayCondition = 'Sleet';
          else displayCondition = ci < 0.01 ? 'Drizzle' : ci < 0.10 ? 'Light Rain' : ci < 0.30 ? 'Moderate Rain' : 'Heavy Rain';
        }
      }
    }
    const parts = displayCondition.split(/,\s*|(?<=\S)\s+and\s+/i);
    sc.textContent = parts[0];
    if (scl) scl.textContent = parts[1] ? parts[1].toLowerCase() : 'sky';
    const fitSizes = ['2.4rem','2.0rem','1.7rem','1.4rem','1.15rem','0.95rem','0.82rem'];
    const fitSkyText = () => {
      const maxW = sc.parentElement ? sc.parentElement.offsetWidth - 8 : 999;
      for (const s of fitSizes) {
        sc.style.fontSize = s;
        if (sc.scrollWidth <= maxW) break;
      }
    };
    sc.style.fontSize = fitSizes[0];
    fitSkyText();
    if (document.fonts && document.fonts.ready) {
      document.fonts.ready.then(fitSkyText);
    }
  }
  const bWindSpeed = hyp.corrected_wind_speed ?? cur.wind_speed;
  const bGustSpeed = hyp.corrected_wind_gusts ?? cur.wind_gusts;
  const bWindDir = cur.wind_direction;
  if (bWindDir != null && (bWindSpeed != null || bGustSpeed != null)) {
    const bImpact = Math.round(combinedWindImpact(bWindSpeed, bGustSpeed, bWindDir));
    const bLevel = worryLevel(bImpact);
    const windRow = b.todayRows.find(r => r.label === 'Wind');
    if (windRow) {
      const gustPart = bGustSpeed != null ? `, gusts ${Math.round(bGustSpeed)}` : '';
      windRow.value = `${bLevel.label} at the cove (${Math.round(bWindSpeed)} mph ${toCompass(bWindDir)}${gustPart})`;
      windRow.color = bLevel.cls === 'severe' ? 'red' : bLevel.cls === 'significant' ? 'orange' : null;
    }
  }
  const cm = { green: 'brief-val-green', orange: 'brief-val-orange', red: 'brief-val-red', blue: 'brief-val-blue' };
  const todayEl = document.getElementById('briefTodayRows');
  if (todayEl) { let html = ''; b.todayRows.forEach(r => { const cls = r.color ? cm[r.color] || '' : ''; html += '<div class="brief-row"><span class="brief-row-label">' + r.label + '</span><span class="brief-row-value ' + cls + '">' + r.value + '</span></div>'; }); todayEl.innerHTML = html; }
  const almanacEl = document.getElementById('briefAlmanacSection');
  if (almanacEl) { if (b.almanacRows && b.almanacRows.length) { let ah = '<hr class="brief-rule"><div class="brief-section-label">Almanac</div><div class="brief-rows">'; b.almanacRows.forEach(r => { const cls = r.color ? cm[r.color] || '' : ''; ah += '<div class="brief-row"><span class="brief-row-label">' + r.label + '</span><span class="brief-row-value ' + cls + '">' + r.value + '</span></div>'; }); ah += '</div>'; almanacEl.innerHTML = ah; } else { almanacEl.innerHTML = ''; } }
  const lifeEl = document.getElementById('briefLifestyleSection');
  if (lifeEl) { if (b.lifestyleRows && b.lifestyleRows.length) { let lh = '<hr class="brief-rule"><div class="brief-section-label">Lifestyle</div><div class="brief-rows">'; b.lifestyleRows.forEach(r => { const cls = r.color ? cm[r.color] || '' : ''; lh += '<div class="brief-row"><span class="brief-row-label">' + r.label + '</span><span class="brief-row-value ' + cls + '">' + r.value + '</span></div>'; }); lh += '</div>'; lifeEl.innerHTML = lh; } else { lifeEl.innerHTML = ''; } }
  const watchEl = document.getElementById('briefWatchSection');
  const hasWatchContent = b.watchRows && b.watchRows.length > 0;

  if (watchEl) { if (b.watchRows && b.watchRows.length) { let wh = '<div class="brief-section-label">Watch for</div><div class="brief-rows">'; b.watchRows.forEach(r => { if (r.isHtml) { wh += r.html; } else if (r.isAlert) { const redCls = r.color === 'red' ? ' brief-alert-row--red' : ''; wh += '<div class="brief-alert-row' + redCls + '" onclick="openAlertModal()" style="cursor:pointer;">⚠ <strong>' + r.value + '</strong>' + (r.detail ? '<div style="font-size:0.78rem;margin-top:3px;opacity:0.72;">' + r.detail + '</div>' : '') + '</div>'; } else { const cls = r.color ? cm[r.color] || '' : ''; const dimCls = r.dim ? ' brief-row--dim' : ''; wh += '<div class="brief-row' + dimCls + '"><span class="brief-row-label">' + r.label + '</span><span class="brief-row-value ' + cls + '">' + r.value + '</span></div>'; } }); wh += '</div><hr class="brief-rule" style="margin-top:14px;">'; watchEl.innerHTML = wh; } else { watchEl.innerHTML = ''; } }
  const tonightEl = document.getElementById('briefTonightSection');
  if (tonightEl) {
    if (b.tonight) {
      const ft = data.forecast_text || [];
      const tonightFc = ft.find(p => p.period_name === 'Tonight');
      let th = '<hr class="brief-rule"><div class="brief-section-label">Tonight</div>';
      th += '<div class="brief-row"><span class="brief-row-label">Overnight</span><span class="brief-row-value">' + b.tonight + '</span></div>';
      if (tonightFc && tonightFc.text) {
        th += '<div style="font-size:0.88rem;opacity:0.7;padding:6px 0 2px;line-height:1.5;">' + tonightFc.text + '</div>';
      }
      tonightEl.innerHTML = th;
    } else { tonightEl.innerHTML = ''; }
  }

  // Cross-card navigation from briefing rows
  var navMap = {
    'Sky': { tab: 'weather', card: '48h_temp_precip' },
    'Wind': { tab: 'weather', card: '48h_wind' },
    'Sea breeze': { tab: 'weather', card: 'sea_breeze_detail' },
    'Fog': { tab: 'weather', card: 'fog_risk' },
    'Thunderstorm': { tab: 'weather', card: 'thunderstorm' },
    'Severe Thunderstorm': { tab: 'weather', card: 'thunderstorm' },
    'Thunderstorm risk': { tab: 'weather', card: 'thunderstorm' },
    'Rain': { tab: 'weather', card: '48h_temp_precip' },
    'Next rain': { tab: 'weather', card: '48h_temp_precip' },
    'Wind chill': { tab: 'weather', card: 'feels_like' },
    'Heat index': { tab: 'weather', card: 'feels_like' },
    'High / Low': { tab: 'weather', card: 'hyperlocal_forecast' },
    'Overnight': { tab: 'weather', card: 'hyperlocal_forecast' },
    'Sun': { tab: 'almanac', card: 'sun' },
    'Tide': { tab: 'almanac', card: 'tides' },
    'Moon': { tab: 'almanac', card: 'moon' },
    'Sunset': { tab: 'hyperlocal', card: 'sunset_quality' },
    'Beach day': { tab: 'hyperlocal', card: 'swim_float' },
    'Hair day': { tab: 'hyperlocal', card: 'hair_day' },
    'Birds': { tab: 'hyperlocal', card: 'birds' },
    'UV': { tab: 'hyperlocal', card: 'outdoor_conditions' },
    'Heat stress': { tab: 'hyperlocal', card: 'outdoor_conditions' },
  };
  var allBriefRows = document.querySelectorAll('#briefTodayRows .brief-row, #briefAlmanacSection .brief-row, #briefLifestyleSection .brief-row, #briefWatchSection .brief-row, #briefTonightSection .brief-row');
  allBriefRows.forEach(function(row) {
    var labelEl = row.querySelector('.brief-row-label');
    if (!labelEl) return;
    var label = labelEl.textContent.trim().replace(/ \(tomorrow\)/, '');
    var nav = navMap[label];
    if (!nav) return;
    row.style.cursor = 'pointer';
    row.onclick = function(e) {
      e.stopPropagation();
      window.__navSource = { tab: 'briefing', card: null };
      showTab(nav.tab);
      setTimeout(function() {
        var card = document.querySelector('[data-collapse-key="' + nav.card + '"]');
        if (card) card.click();
      }, 100);
    };
  });

  // Stat box click-throughs
  var statLinks = [
    { id: 'briefTempNow',    tab: 'weather', card: 'right_now' },
    { id: 'briefTempHigh',   tab: 'weather', card: 'ten_day' },
    { id: 'briefConditions', tab: 'weather', card: '48h_temp_precip' },
  ];
  statLinks.forEach(function(sl) {
    var el = document.getElementById(sl.id);
    var box = el && el.closest('.brief-stat');
    if (!box) return;
    box.style.cursor = 'pointer';
    box.onclick = function(e) {
      e.stopPropagation();
      window.__navSource = { tab: 'briefing', card: null };
      showTab(sl.tab);
      setTimeout(function() {
        var card = document.querySelector('[data-collapse-key="' + sl.card + '"]');
        if (card) card.click();
      }, 100);
    };
  });
}
