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
