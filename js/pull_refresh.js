// ======================================================
// Pull-to-refresh
// ======================================================
// iOS-style drag-down-from-top gesture that reloads the page.
// Only arms when scrolled to the top AND no card is expanded (so
// gestures inside an expanded card don't accidentally reload).
// Reload threshold is 72px of vertical pull.

(function initPullToRefresh() {
  const THRESHOLD = 72;
  let startY = 0;
  let pulling = false;
  let indicator = null;

  function getIndicator() {
    if (!indicator) {
      const headerBottom = (document.querySelector('header') || {getBoundingClientRect: () => ({bottom: 110})}).getBoundingClientRect().bottom;
      indicator = document.createElement('div');
      indicator.id = 'ptrIndicator';
      indicator.style.top = (headerBottom + 12) + 'px';
      indicator.innerHTML = '<div class="ptr-arc"></div>';
      document.body.appendChild(indicator);
    }
    return indicator;
  }

  function removeIndicator() {
    if (indicator) {
      indicator.style.transition = 'transform 0.25s ease, opacity 0.25s ease';
      indicator.style.opacity = '0';
      indicator.style.transform = 'translateX(-50%) translateY(-48px)';
      setTimeout(() => { indicator && indicator.remove(); indicator = null; }, 260);
    }
  }

  document.addEventListener('touchstart', function(e) {
    if (window.scrollY === 0 && !document.querySelector('.card-expanded')) {
      startY = e.touches[0].clientY;
      pulling = true;
    }
  }, { passive: true });

  document.addEventListener('touchmove', function(e) {
    if (!pulling) return;
    const dy = e.touches[0].clientY - startY;
    if (dy <= 0) { pulling = false; removeIndicator(); return; }
    const ind = getIndicator();
    const progress = Math.min(dy / THRESHOLD, 1);
    ind.style.transition = 'none';
    ind.style.opacity = String(Math.min(progress * 2, 1));
    ind.style.transform = `translateX(-50%) translateY(${-48 + progress * 48}px)`;
    const arc = ind.querySelector('.ptr-arc');
    if (arc && !ind.classList.contains('ptr-loading')) arc.style.transform = `rotate(${progress * 270}deg)`;
    ind.classList.toggle('ptr-ready', dy >= THRESHOLD);
  }, { passive: true });

  document.addEventListener('touchend', function(e) {
    if (!pulling) return;
    pulling = false;
    const dy = e.changedTouches[0].clientY - startY;
    if (dy >= THRESHOLD && indicator) {
      indicator.classList.remove('ptr-ready');
      indicator.classList.add('ptr-loading');
      indicator.style.transition = 'none';
      indicator.style.transform = 'translateX(-50%) translateY(0px)';
      setTimeout(() => { removeIndicator(); location.reload(); }, 400);
    } else {
      removeIndicator();
    }
  }, { passive: true });
})();
