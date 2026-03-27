// ========== OVERHEAD (FLIGHT TRACKER) ==========
(function() {
  const HOME_LAT   = 42.4973;
  const HOME_LNG   = -70.8661;
  const RADIUS_NM  = 200;
  const REFRESH_MS = 30000;
  const API_URL    = `https://api.airplanes.live/v2/point/${HOME_LAT}/${HOME_LNG}/${RADIUS_NM}`;

  let ohMap = null;
  let ohMarkers = [];
  let ohRefreshTimer = null;
  let lastFetchTime = null;
  let ohTileLayers = {};
  let ohCurrentTile = 'satellite';
  let ohIsPlaying = false;

  // Initialize map (lazy, on first tab switch to overhead)
  function getPlaneColor(altitude) {
    const alt = parseInt(altitude, 10);
    if (isNaN(alt) || alt <= 0) return "#60a5fa";
    if (alt < 5000) return "#fbbf24";
    if (alt < 20000) return "#34d399";
    return "#60a5fa";
  }

  function ohInitMap() {
    if (ohMap) return; // Already initialized

    ohMap = L.map('overheadMap', {
      center: [HOME_LAT, HOME_LNG],
      zoom: 12,
      zoomControl: true,
      attributionControl: false
    });
    window.ohMap = ohMap; // Expose to global scope

    ohTileLayers.street = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 18 });
    ohTileLayers.satellite = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 19 });
    ohTileLayers.satellite.addTo(ohMap);

    // Home marker
    const homeIcon = L.divIcon({
      html: '<span class="oh-home-icon" style="color:#f87171">⌂</span>',
      className: '',
      iconSize: [20, 20],
      iconAnchor: [10, 10]
    });
    L.marker([HOME_LAT, HOME_LNG], { icon: homeIcon }).addTo(ohMap);

    ohMap.on('moveend', ohUpdateCount);
  }

  function ohUpdateCount() {
    if (!ohMap) return;
    const bounds = ohMap.getBounds();
    const inView = ohMarkers.filter(m => bounds.contains(m.getLatLng()));
    const countEl = document.getElementById('oh-count');
    countEl.textContent = `${inView.length} visible`;
  }

  async function ohFetch() {
    const statusEl = document.getElementById('oh-status');
    const countEl  = document.getElementById('oh-count');
    statusEl.textContent = 'updating…';
    statusEl.style.color = '#888';

    try {
      const res  = await fetch(API_URL);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const aircraft = data.ac || [];

      // Clear old markers
      ohMarkers.forEach(m => ohMap.removeLayer(m));
      ohMarkers = [];

      // Filter: must have position, not on ground
      const visible = aircraft.filter(a =>
        a.lat && a.lon &&
        a.alt_baro && a.alt_baro !== 'ground' &&
        parseInt(a.alt_baro) > 500
      );

      countEl.textContent = `${visible.length} aircraft`;

      visible.forEach(a => {
        const hdg = a.track || 0;
        const color = getPlaneColor(a.alt_baro);

        const planeIcon = L.divIcon({
          html: `<span class="oh-plane-icon" style="color:${color} !important; transform:rotate(${hdg}deg); display:block;">✈︎</span>`,
          className: '',
          iconSize:   [32, 32],
          iconAnchor: [16, 16]
        });

        if (!ohMap) { console.error("ohMap is null when trying to add marker"); return; }
        const marker = L.marker([a.lat, a.lon], { icon: planeIcon }).addTo(ohMap);
        marker.on('click', function() { ohShowPopup(a); });
        ohMarkers.push(marker);
      });

      ohUpdateCount();

      lastFetchTime = Date.now();
      statusEl.textContent = "just now";
      statusEl.style.color = "#4ade80";
      // Update relative time every 30 seconds
      setInterval(() => {
        const elapsed = Math.floor((Date.now() - lastFetchTime) / 1000);
        if (elapsed < 60) statusEl.textContent = "just now";
        else if (elapsed < 3600) statusEl.textContent = Math.floor(elapsed / 60) + "m ago";
        else statusEl.textContent = Math.floor(elapsed / 3600) + "h ago";
      }, 30000);

    } catch(err) {
      statusEl.textContent = 'fetch failed';
      statusEl.style.color = '#f87171';
      countEl.textContent  = '— see console';
      console.error('Overhead tracker error:', err);
    }
  }

  async function ohShowPopup(a) {
    const flightId = a.flight ? a.flight.trim() : (a.r || 'Unknown');
    document.getElementById('oh-pop-flight').textContent = flightId;
    document.getElementById('oh-pop-route').textContent = 'looking up route…';
    document.getElementById('oh-pop-airline').textContent = a.desc || a.ownOp || '';
    document.getElementById('oh-pop-alt').textContent =
      a.alt_baro ? `${parseInt(a.alt_baro).toLocaleString()} ft` : '—';
    document.getElementById('oh-pop-spd').textContent =
      a.gs ? `${Math.round(a.gs)} kts` : '—';
    document.getElementById('oh-pop-hdg').textContent =
      a.track ? `${Math.round(a.track)}°` : '—';
    document.getElementById('oh-popup').style.display = 'block';

    const callsign = (a.flight || '').trim();
    if (!callsign) {
      document.getElementById('oh-pop-route').textContent = 'No callsign';
      return;
    }
    try {
      const res  = await fetch(`https://api.adsbdb.com/v0/callsign/${callsign}`);
      if (!res.ok) throw new Error();
      const data = await res.json();
      const r = data?.response?.flightroute;
      if (r) {
        const orig = r.origin?.iata_code      || r.origin?.icao_code      || '?';
        const dest = r.destination?.iata_code || r.destination?.icao_code || '?';
        const airline = r.airline?.name || '';
        document.getElementById('oh-pop-route').textContent = `${orig} → ${dest}`;
        if (airline && !document.getElementById('oh-pop-airline').textContent) {
          document.getElementById('oh-pop-airline').textContent = airline;
        }
      } else {
        document.getElementById('oh-pop-route').textContent = 'Route unknown';
      }
    } catch(e) {
      document.getElementById('oh-pop-route').textContent = 'Route lookup failed';
    }
  }


  window.ohRefresh = function() {
    if (!ohMap) {
      alert('Switch to Overhead tab first');
      return;
    }
    ohFetch();
  };

  window.ohToggleMapType = function() {
    if (!ohMap) return;
    ohMap.removeLayer(ohTileLayers[ohCurrentTile]);
    ohCurrentTile = ohCurrentTile === 'street' ? 'satellite' : 'street';
    ohTileLayers[ohCurrentTile].addTo(ohMap);
    document.getElementById('oh-map-btn').textContent =
      ohCurrentTile === 'street' ? '🛰 satellite' : '🗺 map';
  };

    // Expose to global scope for showTab to call
  window.ohInitMap = ohInitMap;
  window.ohMap = null; // Will be set by ohInitMap

})();