// Frontal-passage card. Hidden when state=quiet; shows compact summary
// when active or recent. Cause-attribution detail is here so users can
// understand WHY the weather feels different rather than just see numbers.

function _frontalRelative(tsLocal) {
  if (!tsLocal) return "";
  // tsLocal is "YYYY-MM-DDTHH:MM" in America/New_York
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
  const block = weatherData && weatherData.frontal;
  if (!block || block.state === "quiet" || !block.event) {
    card.style.display = "none";
    return;
  }

  const ev = block.event;
  const isActive = block.state === "active";
  const typeLabel = _frontalTypeLabel(ev.type);

  // Card becomes visible
  card.style.display = "";

  // Title + tile label
  const titleText = isActive ? "Front Passing" : "Front Passed";
  const titleEl = document.getElementById("frontalTitleText");
  const tileLabel = document.getElementById("frontalTileLabel");
  if (titleEl) titleEl.textContent = titleText;
  if (tileLabel) tileLabel.textContent = titleText;

  // Collapsed preview
  const collapsedHead = document.getElementById("frontalCollapsedHeadline");
  const collapsedWhen = document.getElementById("frontalCollapsedWhen");
  const collapsedDetail = document.getElementById("frontalCollapsedDetails");
  if (collapsedHead) collapsedHead.textContent = isActive ? "⚡ Active" : "🌬 " + typeLabel;
  if (collapsedWhen) collapsedWhen.textContent = isActive
    ? `${typeLabel}, started ${_frontalRelative(ev.ts)}`
    : `${_frontalRelative(ev.ts)}`;

  const bits = [];
  if (ev.dp_drop_f != null) bits.push(`dewpoint ${ev.dp_drop_f > 0 ? "−" : "+"}${Math.abs(ev.dp_drop_f).toFixed(0)}°F`);
  if (ev.wd_from_oct && ev.wd_to_oct) bits.push(`wind ${ev.wd_from_oct} → ${ev.wd_to_oct}`);
  if (collapsedDetail) collapsedDetail.textContent = bits.join(" · ");

  // Expanded body
  const setT = (id, val) => { const e = document.getElementById(id); if (e) e.textContent = val ?? "--"; };
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
