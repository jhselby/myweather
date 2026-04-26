#!/usr/bin/env python3
"""Replace old PWA prompt with iOS action sheet style prompt"""

NEW_PROMPT = '''  <!-- PWA Install Prompt — iOS Action Sheet Style -->
  <style>
    .pwa-overlay {
      display: none;
      position: fixed;
      inset: 0;
      z-index: 99999;
      background: rgba(0,0,0,0.45);
      -webkit-tap-highlight-color: transparent;
      opacity: 0;
      transition: opacity 0.3s ease;
    }
    .pwa-overlay.visible { opacity: 1; }

    .pwa-sheet {
      position: fixed;
      bottom: 0;
      left: 0;
      right: 0;
      z-index: 100000;
      display: none;
      transform: translateY(100%);
      transition: transform 0.35s cubic-bezier(0.4, 0, 0.2, 1);
      padding: 0 8px calc(8px + env(safe-area-inset-bottom, 0px));
    }
    .pwa-sheet.visible { transform: translateY(0); }

    .pwa-sheet-inner {
      background: rgba(242,242,247,0.97);
      border-radius: 14px;
      overflow: hidden;
      -webkit-backdrop-filter: saturate(180%) blur(20px);
      backdrop-filter: saturate(180%) blur(20px);
    }

    .pwa-header {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 16px;
      border-bottom: 0.5px solid rgba(0,0,0,0.1);
    }

    .pwa-app-icon {
      width: 48px;
      height: 48px;
      border-radius: 10px;
      flex-shrink: 0;
    }

    .pwa-header-text h3 {
      margin: 0;
      font-size: 0.95rem;
      font-weight: 600;
      color: #000;
      font-family: -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .pwa-header-text p {
      margin: 2px 0 0;
      font-size: 0.78rem;
      color: rgba(0,0,0,0.45);
      font-family: -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .pwa-body {
      padding: 16px;
      font-family: -apple-system, BlinkMacSystemFont, sans-serif;
      font-size: 0.85rem;
      color: rgba(0,0,0,0.55);
      line-height: 1.45;
      border-bottom: 0.5px solid rgba(0,0,0,0.1);
    }

    .pwa-steps {
      padding: 0;
      margin: 0;
      list-style: none;
    }

    .pwa-step {
      display: flex;
      align-items: center;
      gap: 12px;
      padding: 14px 16px;
      font-family: -apple-system, BlinkMacSystemFont, sans-serif;
      font-size: 0.88rem;
      color: #000;
      border-bottom: 0.5px solid rgba(0,0,0,0.1);
    }

    .pwa-step:last-child { border-bottom: none; }

    .pwa-step-icon {
      width: 28px;
      height: 28px;
      flex-shrink: 0;
      display: flex;
      align-items: center;
      justify-content: center;
    }

    .pwa-step-icon svg { width: 22px; height: 22px; }

    .pwa-cancel {
      background: rgba(242,242,247,0.97);
      border-radius: 14px;
      margin-top: 8px;
      -webkit-backdrop-filter: saturate(180%) blur(20px);
      backdrop-filter: saturate(180%) blur(20px);
    }

    .pwa-cancel-btn {
      display: block;
      width: 100%;
      padding: 16px;
      border: none;
      background: none;
      font-family: -apple-system, BlinkMacSystemFont, sans-serif;
      font-size: 1.05rem;
      font-weight: 600;
      color: #007AFF;
      cursor: pointer;
      -webkit-tap-highlight-color: transparent;
      text-align: center;
    }

    .pwa-cancel-btn:active {
      background: rgba(0,0,0,0.05);
      border-radius: 14px;
    }

    .pwa-arrow {
      position: fixed;
      bottom: calc(env(safe-area-inset-bottom, 0px) + 2px);
      left: 50%;
      transform: translateX(-50%);
      z-index: 100001;
      display: none;
    }
    .pwa-arrow.visible { display: block; }

    body:not(.theme-light) .pwa-sheet-inner {
      background: rgba(44,44,46,0.97);
    }
    body:not(.theme-light) .pwa-header {
      border-bottom-color: rgba(255,255,255,0.08);
    }
    body:not(.theme-light) .pwa-header-text h3 { color: #fff; }
    body:not(.theme-light) .pwa-header-text p { color: rgba(255,255,255,0.45); }
    body:not(.theme-light) .pwa-body {
      color: rgba(255,255,255,0.55);
      border-bottom-color: rgba(255,255,255,0.08);
    }
    body:not(.theme-light) .pwa-step {
      color: #fff;
      border-bottom-color: rgba(255,255,255,0.08);
    }
    body:not(.theme-light) .pwa-cancel {
      background: rgba(44,44,46,0.97);
    }
    body:not(.theme-light) .pwa-cancel-btn:active {
      background: rgba(255,255,255,0.05);
    }
    body:not(.theme-light) .pwa-arrow polygon {
      fill: rgba(44,44,46,0.97);
    }
  </style>

  <div class="pwa-overlay" id="pwaOverlay"></div>
  <div class="pwa-sheet" id="pwaSheet">
    <div class="pwa-sheet-inner">
      <div class="pwa-header">
        <img class="pwa-app-icon" src="icon-192.png" alt="Wyman Cove Weather">
        <div class="pwa-header-text">
          <h3>Add to Home Screen</h3>
          <p>Wyman Cove Weather</p>
        </div>
      </div>
      <div class="pwa-body">
        Get quick access to Wyman Cove conditions in full screen, without the browser toolbar.
      </div>
      <ol class="pwa-steps">
        <li class="pwa-step">
          <span class="pwa-step-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="#007AFF" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 12v7a2 2 0 002 2h12a2 2 0 002-2v-7"/>
              <polyline points="16 6 12 2 8 6"/>
              <line x1="12" y1="2" x2="12" y2="15"/>
            </svg>
          </span>
          <span>Tap <strong>Share</strong> in the toolbar below</span>
        </li>
        <li class="pwa-step">
          <span class="pwa-step-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="#007AFF" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="3"/>
              <line x1="12" y1="8" x2="12" y2="16"/>
              <line x1="8" y1="12" x2="16" y2="12"/>
            </svg>
          </span>
          <span>Tap <strong>Add to Home Screen</strong></span>
        </li>
      </ol>
    </div>
    <div class="pwa-cancel">
      <button class="pwa-cancel-btn" id="pwaCancelBtn">Cancel</button>
    </div>
  </div>
  <svg class="pwa-arrow" id="pwaArrow" width="24" height="16" viewBox="0 0 24 16">
    <polygon points="0,0 24,0 12,16" fill="rgba(242,242,247,0.97)"/>
  </svg>

  <script>
  (function() {
    if (window.matchMedia('(display-mode: standalone)').matches || navigator.standalone === true) return;

    var isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;

    if (!isIOS) {
      var deferredPrompt = null;
      window.addEventListener('beforeinstallprompt', function(e) {
        e.preventDefault();
        deferredPrompt = e;
        var visits = parseInt(localStorage.getItem('pwa-visit-count') || '0') + 1;
        localStorage.setItem('pwa-visit-count', visits.toString());
        if (visits < 3) return;
        var dismissed = localStorage.getItem('pwa-prompt-dismissed');
        if (dismissed && (Date.now() - parseInt(dismissed)) < 30 * 24 * 60 * 60 * 1000) return;
        deferredPrompt.prompt();
        deferredPrompt.userChoice.then(function() { deferredPrompt = null; });
      });
      return;
    }

    var dismissed = localStorage.getItem('pwa-prompt-dismissed');
    if (dismissed && (Date.now() - parseInt(dismissed)) < 30 * 24 * 60 * 60 * 1000) return;

    var visits = parseInt(localStorage.getItem('pwa-visit-count') || '0') + 1;
    localStorage.setItem('pwa-visit-count', visits.toString());
    if (visits < 3) return;

    var overlay = document.getElementById('pwaOverlay');
    var sheet = document.getElementById('pwaSheet');
    var arrow = document.getElementById('pwaArrow');
    var cancelBtn = document.getElementById('pwaCancelBtn');
    if (!overlay || !sheet || !cancelBtn) return;

    function showPrompt() {
      overlay.style.display = 'block';
      sheet.style.display = 'block';
      void sheet.offsetHeight;
      overlay.classList.add('visible');
      sheet.classList.add('visible');
      arrow.classList.add('visible');
    }

    function hidePrompt() {
      overlay.classList.remove('visible');
      sheet.classList.remove('visible');
      arrow.classList.remove('visible');
      localStorage.setItem('pwa-prompt-dismissed', Date.now().toString());
      setTimeout(function() {
        overlay.style.display = 'none';
        sheet.style.display = 'none';
      }, 350);
    }

    overlay.addEventListener('click', hidePrompt);
    cancelBtn.addEventListener('click', hidePrompt);

    setTimeout(showPrompt, 2000);
  })();
  </script>'''

with open("index.html", "rb") as f:
    c = f.read().decode()

marker = '<!-- PWA Install Prompt'
start = c.find(marker)
if start == -1:
    print("ERROR: Could not find old PWA prompt marker")
    exit(1)

body_end = c.find('</body>', start)
last_script_end = c.rfind('</script>', start, body_end) + len('</script>')

old_block = c[start:last_script_end]
print(f"Removing old block: {len(old_block)} chars")

c = c[:start] + NEW_PROMPT + c[last_script_end:]

with open("index.html", "wb") as f:
    f.write(c.encode())

print("SUCCESS")
