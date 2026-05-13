// ui.js — Card toggle, tab navigation helpers, alert panel

function navigateToHyperlocalCard(cardKey) {
  // Close any open modal cards and remove backdrop
  const openCards = document.querySelectorAll(".card-expanded");
  openCards.forEach(c => c.classList.remove("card-expanded"));
  const backdrop = document.getElementById("modalBackdrop");
  if (backdrop) backdrop.remove();
  
  // Switch to Hyperlocal tab
  
  showTab('hyperlocal');
  
  const rnCard = document.querySelector("[data-collapse-key=\"right_now\"]");
  // Find the card and open it if closed
  const card = document.querySelector(`[data-collapse-key="${cardKey}"]`);
  if (!card) return;
  
  const body = card.querySelector('.card-body');
  if (!body) return;
  
  // Open the card if it's closed
  if (body.style.display === 'none') {
    const titleEl = card.querySelector('.card-title-collapsible');
    if (titleEl) {
      toggleCard(cardKey, titleEl);
    }
  }
  
  // Scroll the card into view with some padding
  setTimeout(() => {
    card.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 100);
}

function toggleCard(key, el) {
  // Close all other cards first
  // Remove any existing backdrop first
  const existingBackdrop = document.getElementById("modalBackdrop");
  if (existingBackdrop) existingBackdrop.remove();
  
  document.querySelectorAll("[data-collapse-key]").forEach(otherCard => {
  const allCards = document.querySelectorAll("[data-collapse-key]");
  allCards.forEach(c => {
    const k = c.getAttribute("data-collapse-key");
    const b = c.querySelector(".card-body");
  });
    const otherKey = otherCard.getAttribute("data-collapse-key");
    if (otherKey !== key) {
      const otherBody = otherCard.querySelector(".card-body");
      const otherPreview = otherCard.querySelector(".card-collapsed-preview");
      const otherChev = otherCard.querySelector(".collapse-chevron");
      if (otherBody && otherBody.style.display !== "none") {
        otherBody.style.display = "none";
        if (otherPreview) otherPreview.style.display = "";
        otherCard.classList.remove("card-expanded");
        const otherClose = otherCard.querySelector(".card-close-btn");
        if (otherClose) otherClose.style.display = "none";
        if (otherChev) {
          otherChev.style.display = "";
          otherChev.style.transform = "rotate(-90deg)";
        }
      }
    }
  });
  
  const card  = el.closest(".card");
  const body  = card.querySelector(".card-body");
  const preview = card.querySelector(".card-collapsed-preview");
  const chev  = el.querySelector(".collapse-chevron");
  if (!body) return;
  const isOpen = body.style.display !== "none";
  body.style.display = isOpen ? "none" : ""; if (preview) preview.style.display = isOpen ? "" : "none"; if (!isOpen) { const bd = document.createElement("div"); bd.className = "modal-backdrop"; bd.id = "modalBackdrop"; bd.style.cssText = "position:fixed;inset:0;z-index:199;background:transparent;"; bd.addEventListener("click", () => toggleCard(key, el)); document.body.appendChild(bd); card.classList.add("card-expanded");

    } else { const shouldReturn = window.__navSource; const bd = document.getElementById("modalBackdrop"); if (bd && !shouldReturn) bd.remove(); if (!shouldReturn) card.classList.remove("card-expanded"); else setTimeout(() => card.classList.remove("card-expanded"), 200); if (window.__navSource) { const src = window.__navSource; window.__navSource = null; requestAnimationFrame(() => { showTab(src.tab); requestAnimationFrame(() => { const rc = document.querySelector(`[data-collapse-key="${src.card}"]`); if (rc && !rc.classList.contains("card-expanded")) rc.click(); }); }); } }
  const closeBtn = card.querySelector(".card-close-btn"); if (closeBtn) closeBtn.style.display = isOpen ? "none" : "flex"; if (chev) { if (card.querySelector(".card-close-btn")) { chev.style.display = "none"; } else { chev.style.display = isOpen ? "" : "none"; chev.style.transform = isOpen ? "rotate(-90deg)" : ""; } }
  try { localStorage.setItem("card_" + key, isOpen ? "0" : "1"); } catch(e) {}
  
  // Initialize radar when radar card is opened
  if (key === "radar" && !isOpen) {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        initRadar();
        if (radarMap) radarMap.invalidateSize();
      });
    });
  }
}


function initCollapsibleCards() {
  document.querySelectorAll("[data-collapse-key]").forEach(card => {
    const key     = card.getAttribute("data-collapse-key");
    const openDef = card.getAttribute("data-default-open") !== "false";
    const body    = card.querySelector(".card-body");
    if (!body) return;
    let isOpen = false;  // Always start closed on page load
    body.style.display = isOpen ? "" : "none"; const preview = card.querySelector(".card-collapsed-preview"); if (preview) preview.style.display = isOpen ? "none" : ""; if (card.querySelector(".card-collapsed-preview")) { if (card.dataset.collapseKey !== "hyperlocal") { card.classList.toggle("col-12", isOpen); card.classList.toggle("col-6", !isOpen); } }
    const chev = card.querySelector(".collapse-chevron");
    if (chev) { chev.style.transform = isOpen ? "" : "rotate(-90deg)"; if (card.querySelector(".card-close-btn")) chev.style.display = "none"; }
  });
}

function toggleAlert(id) {
  const body = document.getElementById(id);
  if (!body) return;
  const idx = id.replace("alertBody_", "");
  const chevron = document.getElementById("alertChevron_" + idx);
  const isOpen = body.style.display !== "none";
  body.style.display = isOpen ? "none" : "block";
  if (chevron) chevron.innerHTML = isOpen ? "&#9660; Show" : "&#9650; Hide";
}

function collapseAllAlerts() {
  document.querySelectorAll("[id^='alertBody_']").forEach((body, i) => {
    body.style.display = "none";
    const chev = document.getElementById("alertChevron_" + i);
    if (chev) chev.innerHTML = "&#9660; Show";
  });
}

  

  function toggleAlertPanel() {
  const panel = document.getElementById("alertsContainer");
  const chev  = document.getElementById("alertSummaryChev");
  if (!panel) return;
  const isOpen = panel.style.display !== "none";
  panel.style.display = isOpen ? "none" : "";
  if (chev) chev.innerHTML = isOpen ? "&#9660; Show" : "&#9650; Hide";
  
  // If opening panel and there's only 1 alert, auto-expand it
  if (!isOpen) {
const alertBodies = panel.querySelectorAll('[id^="alertBody_"]');
if (alertBodies.length === 1) {
  const firstAlertId = alertBodies[0].id;
  toggleAlert(firstAlertId);
}
  }
}
