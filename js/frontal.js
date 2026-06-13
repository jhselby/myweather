// Frontal-passage card. Always visible, content changes by state.
// - quiet:  "No recent passage" + last-passage summary if any
// - recent: "Front Passed" with cause attribution (last 12h)
// - active: "Front Passing" with in-progress signature

function _frontalRelative(tsLocal) {
  if (!tsLocal) return "";
  const ev = new Date(tsLocal.replace(" ", "T"));
  const diffMin = Math.round((Date.now() - ev.getTime()) / 60000);
  if (diffMin < 0) return "moments ago";
  if (diffMin < 90) return `${diffMin} min ago`;
  const diffH = Math.round(diffMin / 60);
  if (diffH < 24) return `${diffH}h ago`;
  return `${Math.round(diffH / 24)}d ago`;
}

function _frontalTypeLabel(t) {
  return {
    cold:       "Cold front",
    warm:       "Warm front",
    sea_breeze: "Sea-breeze front",
    unknown:    "Front",
  }[t] || "Front";
}

function renderFrontal(weatherData) {
  const card = document.getElementById("frontalCard");
  if (!card) return;

  const block = (weatherData && weatherData.frontal) || {};
  const state = block.state || "quiet";
  const ev = block.event || null;
  const recentEvents = block.recent_events || [];
  const lastPast = recentEvents.length ? recentEvents[recentEvents.length - 1] : null;

  card.style.display = "";

  const setT = (id, val) => { const e = document.getElementById(id); if (e) e.textContent = val ?? "--"; };
  const titleEl = document.getElementById("frontalTitleText");
  const tileLabel = document.getElementById("frontalTileLabel");
  const collapsedHead = document.getElementById("frontalCollapsedHeadline");
  const collapsedWhen = document.getElementById("frontalCollapsedWhen");
  const collapsedDetail = document.getElementById("frontalCollapsedDetails");

  if (state === "quiet") {
    if (titleEl) titleEl.textContent = "Front";
    if (tileLabel) tileLabel.textContent = "Front";
    if (collapsedHead) collapsedHead.textContent = "No recent passage";
    if (collapsedWhen) collapsedWhen.textContent = lastPast
      ? `Last front: ${_frontalRelative(lastPast.ts)}`
      : "Watching for boundary shifts";
    if (collapsedDetail) collapsedDetail.textContent = lastPast
      ? `${_frontalTypeLabel(lastPast.type)} · ${lastPast.wd_from_oct || "?"} → ${lastPast.wd_to_oct || "?"}`
      : "";

    setT("frontalStatusBadge", "Quiet");
    setT("frontalTypeValue", lastPast ? `${_frontalTypeLabel(lastPast.type)} (last)` : "--");
    setT("frontalWhenValue", lastPast ? _frontalRelative(lastPast.ts) : "no passages logged yet");
    setT("frontalConfidenceValue", "--");
    setT("frontalDewpointValue", lastPast?.dp_drop_f != null
      ? `${lastPast.dp_drop_f > 0 ? "dropped" : "rose"} ${Math.abs(lastPast.dp_drop_f).toFixed(1)}°F`
      : "--");
    setT("frontalWindValue", (lastPast?.wd_from_oct && lastPast?.wd_to_oct)
      ? `${lastPast.wd_from_oct} → ${lastPast.wd_to_oct}`
      : "--");
    setT("frontalPressureValue", "--");
    return;
  }

  const isActive = state === "active";
  const typeLabel = _frontalTypeLabel(ev.type);
  const titleText = isActive ? "Front Passing" : "Front Passed";
  if (titleEl) titleEl.textContent = titleText;
  if (tileLabel) tileLabel.textContent = titleText;

  if (collapsedHead) collapsedHead.textContent = isActive ? "⚡ Active" : "🌬 " + typeLabel;
  if (collapsedWhen) collapsedWhen.textContent = isActive
    ? `${typeLabel}, started ${_frontalRelative(ev.ts)}`
    : `${_frontalRelative(ev.ts)}`;

  const bits = [];
  if (ev.dp_drop_f != null) bits.push(`dewpoint ${ev.dp_drop_f > 0 ? "−" : "+"}${Math.abs(ev.dp_drop_f).toFixed(0)}°F`);
  if (ev.wd_from_oct && ev.wd_to_oct) bits.push(`wind ${ev.wd_from_oct} → ${ev.wd_to_oct}`);
  if (collapsedDetail) collapsedDetail.textContent = bits.join(" · ");

  setT("frontalStatusBadge", isActive ? "Passing now" : "Recently passed");
  setT("frontalTypeValue", typeLabel);
  setT("frontalWhenValue", _frontalRelative(ev.ts));
  setT("frontalConfidenceValue", ev.confidence ? `${ev.confidence}%` : "--");

  const dpStr = ev.dp_drop_f == null
    ? "--"
    : (ev.dp_drop_f > 0
        ? `dropped ${ev.dp_drop_f.toFixed(1)}°F`
        : `rose ${Math.abs(ev.dp_drop_f).toFixed(1)}°F`);
  setT("frontalDewpointValue", dpStr);

  const wdStr = (ev.wd_from_oct && ev.wd_to_oct)
    ? `${ev.wd_from_oct} (${ev.wd_from}°) → ${ev.wd_to_oct} (${ev.wd_to}°)`
    : "--";
  setT("frontalWindValue", wdStr);

  const pStr = (ev.p_min_inhg != null && ev.p_now_inhg != null)
    ? `bottomed ${ev.p_min_inhg.toFixed(2)}″, now ${ev.p_now_inhg.toFixed(2)}″`
    : "--";
  setT("frontalPressureValue", pStr);
}

window.renderFrontal = renderFrontal;
