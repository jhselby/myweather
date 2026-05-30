// ======================================================
// NWS alerts panel
// ======================================================
// Populates the inline alerts container with one expandable banner per
// active alert. Also filters out NWS test transmissions in-place on
// `data.alerts` so downstream code (briefing, badge, etc.) only sees
// real alerts. The summary bar itself stays hidden — alerts now surface
// via the alert badge in the header, which opens the modal.
//
// Depends on toggleAlert() from js/ui.js being globally available
// (referenced from the inline onclick handlers we generate here).

function renderAlerts(data) {
  const alertsContainer  = document.getElementById("alertsContainer");
  const alertSummaryBar  = document.getElementById("alertSummaryBar");
  const alertSummaryText = document.getElementById("alertSummaryText");
  if (!alertsContainer) return;

  alertsContainer.innerHTML = "";

  // Filter out TEST alerts (NWS transmission tests) — mutates data.alerts.
  const realAlerts = (data.alerts || []).filter(a => {
    const txt = ((a.description || "") + " " + (a.headline || "")).toUpperCase();
    return !txt.includes("THIS_MESSAGE_IS_FOR_TEST_PURPOSES_ONLY") && !txt.includes("THIS IS A TEST");
  });
  data.alerts = realAlerts;

  if (!realAlerts.length) return;

  const n = realAlerts.length;

  // Summary bar stays hidden — badge + modal handle this now.
  if (alertSummaryBar) alertSummaryBar.style.display = "none";

  if (alertSummaryText) {
    alertSummaryText.textContent =
      `${n} active alert${n > 1 ? "s" : ""}: ${realAlerts.map(a => a.event || "Alert").join(" · ")}`;
  }

  alertsContainer.innerHTML = realAlerts.map((a, i) => {
    const id = `alertBody_${i}`;
    return `
    <div class="alert-banner">
      <div class="alert-title" onclick="toggleAlert('${id}')" style="cursor:pointer;display:flex;align-items:center;justify-content:space-between;">
        <span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;min-width:0;">&#9888;&#65039; ${a.event || a.headline?.split(" issued")[0] || "Weather Alert"}</span>
        <span id="alertChevron_${i}" style="font-size:0.8rem;color:rgba(255,255,255,0.5);margin-left:8px;">&#9660; Show</span>
      </div>
      <div id="${id}" class="alert-desc" style="display:none;margin-top:8px;">${a.description || ""}
        ${a.url ? `<div style="margin-top:8px;"><a href="${a.url}" target="_blank" style="color:rgba(100,200,255,0.8);font-size:0.82rem;">Full details &#8599;</a></div>` : ""}
      </div>
    </div>`;
  }).join("");
}
