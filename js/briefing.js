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
    const highRaw = daily.temperature_max?.[0];
    const bias = hyp.weighted_bias ?? 0;
    const high = Math.round(der.today_high ?? der.high ?? daily.temperature_max?.[0] ?? 0);

    // Low tonight
    const lowRaw = daily.temperature_min?.[0];
    const low = Math.floor(daily.temperature_min?.[0] ?? 0);

    // Sky condition
    const skyCode = cur.weather_code ?? 0;
    const skyDesc = cur.condition_override || cur.weather_description || "";

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

    // Wind band
    let windBand = "calm";
    if (windGust >= 35 || windSpeed >= 25) windBand = "dangerous";
    else if (windGust >= 20 || windSpeed >= 15) windBand = "windy";
    else if (windSpeed >= 10) windBand = "breezy";
    else if (windSpeed >= 5) windBand = "light";

    // Convert wind to knots for display
    const windKt = windSpeed;
    const gustKt = windGust ? Math.round(windGust * 0.868976) : null;

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
      else if (hoursAway <= 48) rainContext = "tomorrow";
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
    let sunsetScore = null;
    let sunsetLabel = null;
    // sunset scoring is done in app-main.js; we'll compute a simple version
    // For now just check if data exists
    const hasSunsetData = sunsetArr.length > 0;

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

    let priority = "quiet";
    if (rainContext === "now") priority = "rain_now";
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
      temp, high, low, windSpeed, windKt, gustKt, windDir, windDeg, humidity,
      skyState, skyDesc, tempBand, windBand, skyTrend,
      rainContext, rainInches, rainStartStr, rainEndStr,
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

    const directional = data?.sunset_directional || [];
    const todayDirectional = directional[0] || null;
    const tomorrowDirectional = directional[1] || null;

    const todaySrc = window.__todaySunsetScore
      ? { score: window.__todaySunsetScore.score, label: window.__todaySunsetScore.label }
      : (todayDirectional ? { score: todayDirectional.score, label: todayDirectional.label } : null);

    const tomorrowSrc = window.__tomorrowSunsetScore
      ? { score: window.__tomorrowSunsetScore.score, label: window.__tomorrowSunsetScore.label }
      : (tomorrowDirectional ? { score: tomorrowDirectional.score, label: tomorrowDirectional.label } : null);

    const src = (useTomorrow && tomorrowSrc) ? tomorrowSrc : todaySrc;
    if (src) {
      return { score: src.score, label: src.label, tomorrow: !!(useTomorrow && tomorrowSrc) };
    }
    return null;
  }

  function getBeachDayScore(data) {
    const cutoffs = getLifestyleCutoffs(data);
    const useTomorrow = !!(cutoffs.beachCutoff && cutoffs.now >= cutoffs.beachCutoff);

    const src = (useTomorrow && window.__tomorrowDockScore) ? window.__tomorrowDockScore : window.__todayDockScore;
    if (src) {
      return { score: Math.round(src.score * 100), label: src.label, tomorrow: useTomorrow && !!window.__tomorrowDockScore };
    }
    return null;
  }

  function getHairDayScore(data) {
    const cutoffs = getLifestyleCutoffs(data);
    const useTomorrow = !!(cutoffs.hairCutoff && cutoffs.now >= cutoffs.hairCutoff);

    const src = (useTomorrow && window.__tomorrowHairScore) ? window.__tomorrowHairScore : window.__todayHairScore;
    if (src) {
      return { score: src.score, label: src.scoreLabel, tomorrow: useTomorrow && !!window.__tomorrowHairScore };
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
        value: `${sunset.label} (${sunset.score}/100)`,
        color: sunset.score >= 70 ? "green" : null,
      });
    }

    // Beach Day — always show (it's why you check the weather)
    const beach = getBeachDayScore(s._data) || estimateBeachDayScore(s);
    if (beach) {
      rows.push({
        label: beach.tomorrow ? "Beach day (tomorrow)" : "Beach day",
        value: `${beach.label} (${beach.score}/100)`,
        color: beach.score >= 75 ? "green" : beach.score >= 58 ? null : beach.score >= 38 ? "orange" : "red",
      });
    }

    // Hair Day — only show if notable (bad or great, not middling)
    const hair = getHairDayScore(s._data) || estimateHairDayScore(s);
    if (hair) {
      rows.push({
        label: hair.tomorrow ? "Hair day (tomorrow)" : "Hair day",
        value: `${hair.label} (${hair.score}/100)`,
        color: hair.score >= 80 ? "green" : "orange",
      });
    }

    // Birds — species count from eBird
    const birds = s._data.birds || {};
    const speciesCount = birds.species_count;
    if (speciesCount) {
      rows.push({ label: "Birds", value: speciesCount + " species nearby", color: null });
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
    const gustStr = s.gustKt ? `, gusts ${s.gustKt}` : "";

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
        c2 = `Rain ongoing${s.rainInches > 0 ? `, ${s.rainInches}" so far` : ""}. Wind ${s.windKt} MPH ${s.windDir}${gustStr}.`;
        break;
      case "rain_soon":
        c2 = `Rain by ${s.rainStartStr}${s.rainInches > 0 ? `, ${s.rainInches}" expected` : ""}. Wind ${s.windKt} MPH ${s.windDir}.`;
        break;
      case "rain_later":
        c2 = `Rain ${s.rainStartStr}–${s.rainEndStr}, ${s.rainInches}". Wind ${s.windKt} MPH ${s.windDir}.`;
        break;
      case "alert":
        c2 = `${s.alerts[0].event}${s.alerts[0].description ? "" : ""}. ${s.windKt} MPH ${s.windDir}${gustStr}.`;
        break;
      case "fog":
        c2 = `Fog probability ${s.fogProb}%. Wind ${s.windKt} MPH ${s.windDir}.`;
        break;
      case "clear_changing":
        c2 = `Cloud cover builds later. Wind ${s.windKt} MPH ${s.windDir}.`;
        break;
      case "sea_breeze":
        c2 = `Sea breeze active (${s.seaBreeze.likelihood}% likelihood). ${s.windKt} MPH ${s.windDir}${gustStr}.`;
        break;
      case "trend":
        c2 = s.skyTrend === "clearing"
          ? `Clearing later. Wind ${s.windKt} MPH ${s.windDir}.`
          : `Clouds building. Wind ${s.windKt} MPH ${s.windDir}.`;
        break;
      case "wind":
        c2 = `Wind ${s.windKt} MPH ${s.windDir}${gustStr}.`;
        break;
      case "temp_extreme":
        c2 = s.tempBand === "hot"
          ? `${s.windKt > 5 ? `Wind ${s.windKt} MPH ${s.windDir}.` : "Barely a breeze."}`
          : `Wind ${s.windKt} MPH ${s.windDir}${gustStr} — feels worse.`;
        break;
      case "frost":
        c2 = `Tonight drops to ${s.low}°. Frost likely by dawn.`;
        break;
      default:
        if (s.rainContext === "tomorrow") {
          c2 = `Next rain: tomorrow. Wind ${s.windKt} MPH ${s.windDir}.`;
        } else {
          c2 = `No rain in sight. Wind ${s.windKt} MPH ${s.windDir}.`;
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
    const gustNote = s.gustKt ? `, gusts ${s.gustKt}` : "";
    rows.push({
      label: "Wind",
      value: `${s.windKt} MPH ${s.windDir}${gustNote}`,
      color: s.windBand === "dangerous" ? "red" : s.windBand === "windy" ? "orange" : null,
    });

    // Sea breeze — only if active with positive delta, or likely
    const sbDeltaRow = parseFloat((sb.reason || "").match(/Δ([-\d.]+)/)?.[1] || "0");
    if (sb.active && sbDeltaRow > 0) {
      rows.push({ label: "Sea breeze", value: `Active — ${sb.reason || "onshore flow"}`, color: "green" });
    } else if ((sb.likelihood ?? 0) >= 40 && sbDeltaRow > 0) {
      rows.push({ label: "Sea breeze", value: `${sb.likelihood}% likely`, color: "orange" });
    }

    // Fog — only if risk
    if (s.hasFog) {
      rows.push({
        label: "Fog",
        value: `${s.fogLabel} — ${s.fogProb}%`,
        color: s.fogProb >= 60 ? "orange" : "blue",
      });
    }

    // Rain — only if coming
    if (s.rainContext === "now") {
      rows.push({ label: "Rain", value: `Now${s.rainInches > 0 ? ` — ${s.rainInches}"` : ""}`, color: "blue" });
    } else if (s.rainContext === "soon") {
      rows.push({ label: "Rain", value: `By ${s.rainStartStr} — ${s.rainInches}"`, color: "blue" });
    } else if (s.rainContext === "later") {
      rows.push({ label: "Rain", value: `${s.rainStartStr}–${s.rainEndStr} — ${s.rainInches}"`, color: "blue" });
    }

    // Feels like — only when cold enough for wind chill or hot enough for heat index
    const feelsLike = Math.round(s._data.current?.apparent_temperature ?? s.temp);
    const feelsDiff = Math.abs(feelsLike - s.temp);
    const showWindChill = feelsLike < s.temp && s.temp <= 40 && feelsDiff >= 5;
    const showHeatIndex = feelsLike > s.temp && s.temp >= 80 && feelsDiff >= 5;
    if (showWindChill) {
      rows.push({ label: "Wind chill", value: feelsLike + "°", color: feelsLike <= 20 ? "red" : feelsLike <= 32 ? "orange" : null });
    } else if (showHeatIndex) {
      rows.push({ label: "Heat index", value: feelsLike + "°", color: feelsLike >= 100 ? "red" : feelsLike >= 90 ? "orange" : null });
    }

    // Humidity — show when notably high or low
    if (s.humidity >= 80) {
      rows.push({ label: "Humidity", value: s.humidity + "%", color: s.humidity >= 90 ? "red" : "orange" });
    } else if (s.humidity <= 25) {
      rows.push({ label: "Humidity", value: s.humidity + "% — very dry", color: "blue" });
    }

    // Sunrise / Sunset
    const daily = s._data.daily || {};
    const todaySunrise = daily.sunrise?.[0];
    const todaySunset = daily.sunset?.[0];
    function fmtTimeShort(iso) {
      if (!iso) return "";
      const d = new Date(iso);
      return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }).toLowerCase();
    }
    if (todaySunrise || todaySunset) {
      rows.push({ label: "Sun", value: "\u2191 " + fmtTimeShort(todaySunrise) + "  \u2193 " + fmtTimeShort(todaySunset), color: null });
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

    // Moon phase (SunCalc is loaded client-side)
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

  function buildWatchRows(s) {
    const rows = [];
    const der = s._data.derived || {};
    const sb = s._data.sea_breeze || {};

    // Wind gusts >= 25 mph or impact score >= 7
    const windImpact = der.wind_impact_score ?? 0;
    const gustMph = Math.round(s._data.current?.wind_gusts ?? (s.gustKt ? s.gustKt / 0.868976 : 0));
    if (gustMph >= 25 || windImpact >= 7) {
      const gustNote = gustMph >= 25 ? "Gusts " + gustMph + " mph" : "Impact " + windImpact + "/10";
      rows.push({ label: "Wind", value: gustNote, color: gustMph >= 35 ? "red" : "orange" });
    }

    // Frost risk: overnight low <= 36
    if (s.low != null && s.low <= 36) {
      rows.push({ label: "Frost risk", value: "Low tonight " + s.low + "°", color: s.low <= 32 ? "red" : "orange" });
    }

    // Sea breeze likelihood >= 60%
    const sbLikelihood = sb.likelihood ?? 0;
    const sbDelta = parseFloat((sb.reason || "").match(/Δ([-\d.]+)/)?.[1] || "0");
    if (sbLikelihood >= 60 && sbDelta > 0) {
      rows.push({ label: "Sea breeze", value: sbLikelihood + "% likely", color: "blue" });
    }

    // Fog probability >= 50%
    const fogProb = der.fog_probability ?? 0;
    if (fogProb >= 50) {
      rows.push({ label: "Fog", value: fogProb + "% probability", color: "orange" });
    }

    // Next rain — only if not today and not none
    if (s.rainContext === "tomorrow") {
      rows.push({ label: "Next rain", value: "Tomorrow", color: "blue" });
    }

    // Alerts
    for (const a of s.alerts) {
      rows.push({
        label: "Alert",
        value: a.event,
        detail: a.description ? a.description.slice(0, 80) : "",
        color: "orange",
        isAlert: true,
      });
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
      },
      todayRows: buildRows(s),
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
