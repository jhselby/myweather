// radar.js — NOAA NEXRAD radar via IEM WMS (Leaflet)

let radarMap       = null;
let radarInited    = false;
let radarPlaying   = false;
let radarTimer     = null;
let radarFrameIdx  = 0;
let radarFrames    = [];
let radarLayers    = {};
let radarLayerType = "radar";

let radarTileLayers  = {};
let radarCurrentTile = "satellite";
const RADAR_CENTER   = [42.5014, -70.8750];
const RADAR_ZOOM     = 7;
const FRAME_DELAY    = 400;
const NEXRAD_FRAMES  = 24;   // 24 frames * 5min = 2 hours of history

function mrmsTimeString(date) {
  const d = new Date(date);
  const minutes = Math.floor(d.getUTCMinutes() / 5) * 5;
  d.setUTCMinutes(minutes, 0, 0);
  return d.toISOString().replace(/\.\d{3}Z$/, 'Z').replace(/:\d{2}Z$/, ':00Z');
}

function generateMRMSFrames() {
  radarFrames = [];
  const now = new Date();
  for (let i = 0; i < NEXRAD_FRAMES; i++) {
    const frameTime = new Date(now - (NEXRAD_FRAMES - 1 - i) * 5 * 60 * 1000);
    radarFrames.push({ ts: frameTime, kind: "past" });
  }

  const scrubber = document.getElementById("radarScrubber");
  if (scrubber) {
    scrubber.max   = radarFrames.length - 1;
    scrubber.value = radarFrames.length - 1;
  }
  const fmt = d => d.toLocaleTimeString("en-US", { hour:"numeric", minute:"2-digit" });
  if (radarFrames.length) {
    const startEl = document.getElementById("radarScrubStart");
    const endEl   = document.getElementById("radarScrubEnd");
    if (startEl) startEl.textContent = fmt(radarFrames[0].ts);
    if (endEl)   endEl.textContent   = fmt(radarFrames[radarFrames.length - 1].ts);
  }

  preloadFrames();
  showFrame(radarFrames.length - 1);
}

function preloadFrames() {
  if (radarLayers._active) {
    radarMap.removeLayer(radarLayers._active);
    radarLayers._active = null;
  }
  radarLayers = {};
}

function showFrame(idx) {
  if (!radarMap || !radarFrames.length) return;
  idx = Math.max(0, Math.min(idx, radarFrames.length - 1));
  radarFrameIdx = idx;
  const frame = radarFrames[idx];

  const timeStr = mrmsTimeString(frame.ts);
  const layer = L.tileLayer.wms("https://mesonet.agron.iastate.edu/cgi-bin/wms/nexrad/n0r-t.cgi", {
    layers: 'nexrad-n0r-wmst',
    format: 'image/png',
    transparent: true,
    opacity: 0.75,
    attribution: '&copy; <a href="https://mesonet.agron.iastate.edu/">IEM NEXRAD</a>',
    time: timeStr
  });

  layer._loaded = false;
  layer._tilesLoading = 0;
  const oldLayer = radarLayers._active;

  layer.on('tileloadstart', () => { layer._tilesLoading++; });
  layer.on('tileload', () => {
    layer._tilesLoading--;
    if (layer._tilesLoading === 0) {
      layer._loaded = true;
      if (oldLayer && radarMap.hasLayer(oldLayer)) radarMap.removeLayer(oldLayer);
    }
  });
  layer.on('tileerror', () => {
    layer._tilesLoading--;
    if (layer._tilesLoading === 0) {
      layer._loaded = true;
      if (oldLayer && radarMap.hasLayer(oldLayer)) radarMap.removeLayer(oldLayer);
    }
  });

  layer.addTo(radarMap);
  radarLayers._active = layer;

  const displayTime = frame.ts.toLocaleTimeString("en-US", { hour:"numeric", minute:"2-digit" });
  document.getElementById("radarTimestamp").textContent = displayTime;
  document.getElementById("radarScrubber").value = idx;

  const curPct = idx / Math.max(radarFrames.length - 1, 1) * 100;
  const scrubber = document.getElementById("radarScrubber");
  if (scrubber) {
    scrubber.style.background = `linear-gradient(to right,
      rgba(100,180,255,0.8) 0%,
      rgba(100,180,255,0.8) ${curPct}%,
      rgba(255,255,255,0.15) ${curPct}%,
      rgba(255,255,255,0.15) 100%)`;
  }
}

function initRadar() {
  if (radarInited) return;
  radarInited = true;

  radarMap = L.map("radarMap", {
    center:  RADAR_CENTER,
    zoom:    RADAR_ZOOM,
    minZoom: 4,
    maxZoom: 12,
    zoomControl: true,
    attributionControl: true,
  });

  function radarBaseTileUrl() {
    const isLight = document.body.classList.contains('theme-light');
    return isLight
      ? "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"
      : "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png";
  }
  function radarApplyBaseTile() {
    if (!radarMap) return;
    if (radarTileLayers._base) radarMap.removeLayer(radarTileLayers._base);
    radarTileLayers._base = L.tileLayer(radarBaseTileUrl(), { maxZoom: 19, attribution: '&copy; <a href="https://carto.com/">CartoDB</a>' });
    radarTileLayers._base.addTo(radarMap);
    radarTileLayers._base.bringToBack();
  }
  radarTileLayers.street = { addTo: () => {} };
  radarTileLayers.satellite = radarTileLayers.street;
  radarApplyBaseTile();

  const _radarThemeObs = new MutationObserver(() => radarApplyBaseTile());
  _radarThemeObs.observe(document.body, { attributes: true, attributeFilter: ['class'] });

  L.circleMarker(RADAR_CENTER, {
    radius: 7, fillColor: "rgba(100,220,255,1)",
    color: "rgba(255,255,255,0.9)", weight: 2, fillOpacity: 1,
    pane: "markerPane",
  }).bindTooltip("Wyman Cove", { permanent: false }).addTo(radarMap);

  setTimeout(() => { if (radarMap) radarMap.invalidateSize(); }, 300);
  generateMRMSFrames();
  setInterval(generateMRMSFrames, 5 * 60 * 1000);
}

function radarTogglePlay() {
  radarPlaying = !radarPlaying;
  const btn = document.getElementById("radarPlayBtn");
  if (radarPlaying) {
    btn.innerHTML = "&#9646;&#9646; Pause";
    radarAdvance();
  } else {
    btn.innerHTML = "&#9654; Play";
    clearTimeout(radarTimer);
  }
}

function radarAdvance() {
  if (!radarPlaying) return;
  if (radarLayers._active && !radarLayers._active._loaded) {
    radarTimer = setTimeout(radarAdvance, 100);
    return;
  }
  let next = radarFrameIdx + 1;
  if (next >= radarFrames.length) {
    next = 0;
    radarTimer = setTimeout(() => { showFrame(next); radarTimer = setTimeout(radarAdvance, FRAME_DELAY); }, 800);
    return;
  }
  showFrame(next);
  radarTimer = setTimeout(radarAdvance, FRAME_DELAY);
}

function radarScrubTo(val) {
  radarPlaying = false;
  document.getElementById("radarPlayBtn").innerHTML = "&#9654; Play";
  clearTimeout(radarTimer);
  showFrame(parseInt(val));
}

function radarToggleMapType() {
  if (!radarMap) return;
  radarMap.removeLayer(radarTileLayers[radarCurrentTile]);
  radarCurrentTile = radarCurrentTile === "street" ? "satellite" : "street";
  radarTileLayers[radarCurrentTile].addTo(radarMap);
  document.getElementById("radarMapBtn").innerHTML =
    radarCurrentTile === "street" ? "🛰 satellite" : "🗺 map";
}

function initCollapsedRadarMap() {
  const mapEl = document.getElementById('radarMapCollapsed');
  if (!mapEl || window._collapsedRadarInitialized) {
    return;
  }
  
  
  // Initialize mini Leaflet map - zoomed in closer to Marblehead
  const miniMap = L.map('radarMapCollapsed', {
    zoomControl: false,
    attributionControl: false,
    dragging: false,
    scrollWheelZoom: false,
    doubleClickZoom: false,
    touchZoom: false
  }).setView([42.5001, -70.8578], 10);
  
  // Store globally so we can invalidate size on tab switch
  window.collapsedRadarMap = miniMap;
  
  // Use light or dark tiles based on theme
  const isDarkMode = !document.body.classList.contains("theme-light");
  const tileUrl = isDarkMode 
    ? "https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png"
    : "https://{s}.basemaps.cartocdn.com/light_nolabels/{z}/{x}/{y}{r}.png";
  L.tileLayer(tileUrl, {
    maxZoom: 19
  }).addTo(miniMap);
  
  // No filter - just use natural light map colors
  const style = document.createElement('style');
  style.textContent = `
    @keyframes radarSweep {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }
    @keyframes centerPulse {
      0%, 100% { opacity: 0.6; }
      50% { opacity: 0.3; }
    }
  `;
  document.head.appendChild(style);
  
  // SVG overlay
  const svg = L.svg();
  svg.addTo(miniMap);
  
  
  setTimeout(() => {
    const svgEl = document.querySelector('#radarMapCollapsed svg');
      if (!svgEl) {
      return;
    }
    
    // Force map to recalculate size since it was hidden during init
    miniMap.invalidateSize();
    
    const center = miniMap.latLngToLayerPoint([42.5001, -70.8578]);
    
    // Range rings: 15, 30, 60, 90 miles - much lighter
    const ranges = [
      { deg: 0.22, opacity: 0.25, width: '1.5' },
      { deg: 0.43, opacity: 0.2, width: '1.5' },
      { deg: 0.87, opacity: 0.15, width: '1' },
      { deg: 1.3, opacity: 0.1, width: '1' }
    ];
    
    ranges.forEach(range => {
      const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      circle.setAttribute('cx', center.x);
      circle.setAttribute('cy', center.y);
      circle.setAttribute('r', range.deg * 111 * 3);
      circle.setAttribute('fill', 'none');
      circle.setAttribute('stroke', `rgba(100, 180, 120, ${range.opacity})`);
      circle.setAttribute('stroke-width', range.width);
      circle.setAttribute('stroke-dasharray', '5,4');
      svgEl.appendChild(circle);
    });
    
    // Pulsing glow - very subtle
    const glow = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    glow.setAttribute('cx', center.x);
    glow.setAttribute('cy', center.y);
    glow.setAttribute('r', '10');
    glow.setAttribute('fill', 'rgba(80, 160, 100, 0.15)');
    glow.style.animation = 'centerPulse 2s ease-in-out infinite';
    svgEl.appendChild(glow);
    
    // Center dot - lighter
    const dot = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    dot.setAttribute('cx', center.x);
    dot.setAttribute('cy', center.y);
    dot.setAttribute('r', '5');
    dot.setAttribute('fill', 'rgba(80, 160, 100, 0.7)');
    dot.setAttribute('stroke', 'white');
    dot.setAttribute('stroke-width', '2');
    svgEl.appendChild(dot);
    
    // Sweep group (animated)
    const sweepGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    sweepGroup.style.transformOrigin = `${center.x}px ${center.y}px`;
    sweepGroup.style.animation = 'radarSweep 4s linear infinite';
    
    // Sweep line - lighter
    const sweep = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    sweep.setAttribute('x1', center.x);
    sweep.setAttribute('y1', center.y);
    sweep.setAttribute('x2', center.x + 150);
    sweep.setAttribute('y2', center.y);
    sweep.setAttribute('stroke', 'rgba(100, 180, 120, 0.3)');
    sweep.setAttribute('stroke-width', '2');
    sweep.setAttribute('stroke-linecap', 'round');
    sweepGroup.appendChild(sweep);
    
    // Trailing wedge glow - very subtle
    const sweepFade = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    const sweepPath = `M ${center.x},${center.y} L ${center.x + 150},${center.y} A 150,150 0 0,1 ${center.x + 106},${center.y + 106} Z`;
    sweepFade.setAttribute('d', sweepPath);
    sweepFade.setAttribute('fill', 'rgba(80, 160, 100, 0.05)');
    sweepGroup.appendChild(sweepFade);
    
    svgEl.appendChild(sweepGroup);
    
    // Grid lines - very subtle
    const gridGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    gridGroup.setAttribute('opacity', '0.08');
    
    for (let i = 0; i < 5; i++) {
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', '0');
      line.setAttribute('y1', i * 50);
      line.setAttribute('x2', '400');
      line.setAttribute('y2', i * 50);
      line.setAttribute('stroke', 'rgba(100, 255, 150, 0.5)');
      line.setAttribute('stroke-width', '0.5');
      gridGroup.appendChild(line);
    }
    
    for (let i = 0; i < 8; i++) {
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', i * 50);
      line.setAttribute('y1', '0');
      line.setAttribute('x2', i * 50);
      line.setAttribute('y2', '250');
      line.setAttribute('stroke', 'rgba(100, 255, 150, 0.5)');
      line.setAttribute('stroke-width', '0.5');
      gridGroup.appendChild(line);
    }
    
    svgEl.appendChild(gridGroup);
  }, 800);
  
  window._collapsedRadarInitialized = true;
}
