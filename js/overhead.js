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
  let selectedAircraftReg = null; // Track selected aircraft registration across refreshes

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
      // selectedAircraftReg preserved across refresh - will re-highlight if still visible

      // Filter: must have position, not on ground
      const visible = aircraft.filter(a =>
        a.lat && a.lon &&
        a.alt_baro && a.alt_baro !== 'ground' &&
        parseInt(a.alt_baro) > 500
      );

      countEl.textContent = `${visible.length} aircraft`;

      visible.forEach(a => {
        const hdg = a.track || 0;
        const reg = a.r || a.hex || a.flight; // Unique identifier
        const isSelected = (reg === selectedAircraftReg);
        const color = isSelected ? '#ec4899' : getPlaneColor(a.alt_baro);

        const planeIcon = L.divIcon({
          html: `<span class="oh-plane-icon" style="color:${color} !important; transform:rotate(${hdg - 90}deg); display:block;">✈︎</span>`,
          className: '',
          iconSize:   [32, 32],
          iconAnchor: [16, 16]
        });

        if (!ohMap) { console.error("ohMap is null when trying to add marker"); return; }
        const marker = L.marker([a.lat, a.lon], { icon: planeIcon }).addTo(ohMap);
        
        // Store aircraft data with marker for later reference
        marker.aircraftData = a;
        marker.aircraftReg = reg;
        
        // Show popup if this was the previously selected aircraft
        if (isSelected) {
          ohShowPopup(a);
        }
        
        marker.on('click', function() { 
          // Update selection
          const oldReg = selectedAircraftReg;
          selectedAircraftReg = reg;
          
          // Refresh all markers to update colors
          ohMarkers.forEach(m => {
            const mData = m.aircraftData;
            const mReg = m.aircraftReg;
            const mHdg = mData.track || 0;
            const mColor = (mReg === reg) ? '#ec4899' : getPlaneColor(mData.alt_baro);
            const mIcon = L.divIcon({
              html: `<span class="oh-plane-icon" style="color:${mColor} !important; transform:rotate(${mHdg - 90}deg); display:block;">✈︎</span>`,
              className: '',
              iconSize:   [32, 32],
              iconAnchor: [16, 16]
            });
            m.setIcon(mIcon);
          });
          
          ohShowPopup(a); 
        });
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

function getStateName(airportName) {
  if (!airportName) return '';
  const stateMatch = airportName.match(/,\s*([A-Z]{2})\s*$/);
  if (stateMatch) return stateMatch[1];
  const states = {
    Alabama: 'AL', Alaska: 'AK', Arizona: 'AZ', Arkansas: 'AR', California: 'CA',
    Colorado: 'CO', Connecticut: 'CT', Delaware: 'DE', Florida: 'FL', Georgia: 'GA',
    Hawaii: 'HI', Idaho: 'ID', Illinois: 'IL', Indiana: 'IN', Iowa: 'IA',
    Kansas: 'KS', Kentucky: 'KY', Louisiana: 'LA', Maine: 'ME', Maryland: 'MD',
    Massachusetts: 'MA', Michigan: 'MI', Minnesota: 'MN', Mississippi: 'MS', Missouri: 'MO',
    Montana: 'MT', Nebraska: 'NE', Nevada: 'NV', 'New Hampshire': 'NH', 'New Jersey': 'NJ',
    'New Mexico': 'NM', 'New York': 'NY', 'North Carolina': 'NC', 'North Dakota': 'ND', Ohio: 'OH',
    Oklahoma: 'OK', Oregon: 'OR', Pennsylvania: 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC',
    'South Dakota': 'SD', Tennessee: 'TN', Texas: 'TX', Utah: 'UT', Vermont: 'VT',
    Virginia: 'VA', Washington: 'WA', 'West Virginia': 'WV', Wisconsin: 'WI', Wyoming: 'WY'
  };
  for (const [state, abbr] of Object.entries(states)) {
    if (airportName.includes(state)) return abbr;
  }
  return '';
}

// Calculate great circle bearing from point1 to point2
function calculateBearing(lat1, lon1, lat2, lon2) {
  const toRad = deg => deg * Math.PI / 180;
  const toDeg = rad => rad * 180 / Math.PI;
  
  const φ1 = toRad(lat1);
  const φ2 = toRad(lat2);
  const Δλ = toRad(lon2 - lon1);
  
  const y = Math.sin(Δλ) * Math.cos(φ2);
  const x = Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ);
  const θ = Math.atan2(y, x);
  
  return (toDeg(θ) + 360) % 360; // Normalize to 0-360
}

// Calculate smallest angular difference between two headings
function angleDiff(a, b) {
  let diff = Math.abs(a - b) % 360;
  return diff > 180 ? 360 - diff : diff;
}

// Calculate great circle distance between two points (in nautical miles)
function haversineDistance(lat1, lon1, lat2, lon2) {
  const toRad = deg => deg * Math.PI / 180;
  const R = 3440.065; // Earth's radius in nautical miles
  
  const φ1 = toRad(lat1);
  const φ2 = toRad(lat2);
  const Δφ = toRad(lat2 - lat1);
  const Δλ = toRad(lon2 - lon1);
  
  const a = Math.sin(Δφ/2) * Math.sin(Δφ/2) +
            Math.cos(φ1) * Math.cos(φ2) *
            Math.sin(Δλ/2) * Math.sin(Δλ/2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
  
  return R * c;
}

// Calculate perpendicular distance from point to great circle route (in nautical miles)
function crossTrackDistance(pointLat, pointLon, routeStartLat, routeStartLon, routeEndLat, routeEndLon) {
  const toRad = deg => deg * Math.PI / 180;
  const toDeg = rad => rad * 180 / Math.PI;
  const R = 3440.065; // Earth's radius in nautical miles
  
  const δ13 = haversineDistance(routeStartLat, routeStartLon, pointLat, pointLon) / R; // angular distance
  const θ13 = toRad(calculateBearing(routeStartLat, routeStartLon, pointLat, pointLon));
  const θ12 = toRad(calculateBearing(routeStartLat, routeStartLon, routeEndLat, routeEndLon));
  
  const δxt = Math.asin(Math.sin(δ13) * Math.sin(θ13 - θ12));
  
  return Math.abs(δxt * R);
}

// Validate if aircraft trajectory matches the claimed route
function validateRoute(aircraftLat, aircraftLon, aircraftHeading, originLat, originLon, destLat, destLon) {
  if (!aircraftHeading || !originLat || !originLon || !destLat || !destLon) {
    return { valid: null, reason: 'insufficient data' };
  }
  
  // Calculate distances to airports
  const distToOrigin = haversineDistance(aircraftLat, aircraftLon, originLat, originLon);
  const distToDest = haversineDistance(aircraftLat, aircraftLon, destLat, destLon);
  const routeLength = haversineDistance(originLat, originLon, destLat, destLon);
  
  // If very close to origin or destination (<100nm), skip validation entirely
  // Departure/arrival patterns make heading and position unreliable
  const nearAirport = distToOrigin < 100 || distToDest < 100;
  if (nearAirport) {
    return { valid: true, reason: 'near airport' };
  }
  
  // Calculate perpendicular distance from aircraft to the route line
  const offTrackDist = crossTrackDistance(
    aircraftLat, aircraftLon,
    originLat, originLon,
    destLat, destLon
  );
  
  // Scale tolerance by route length
  // Short routes (<500nm): 100nm tolerance
  // Medium routes (500-2000nm): 200nm tolerance  
  // Long routes (>2000nm): 300nm tolerance
  let maxOffTrack = 100;
  if (routeLength > 2000) maxOffTrack = 300;
  else if (routeLength > 500) maxOffTrack = 200;
  
  // If aircraft is way off the route line, flag it
  if (offTrackDist > maxOffTrack) {
    return {
      valid: false,
      reason: `${Math.round(offTrackDist)}nm off route (max ${maxOffTrack}nm)`,
      offTrackDist: Math.round(offTrackDist)
    };
  }
  
  // Calculate the expected route bearing from origin to destination
  const routeBearing = calculateBearing(originLat, originLon, destLat, destLon);
  
  // Calculate bearings from aircraft to both airports
  const bearingToOrigin = calculateBearing(aircraftLat, aircraftLon, originLat, originLon);
  const bearingToDest = calculateBearing(aircraftLat, aircraftLon, destLat, destLon);
  
  const diffToOrigin = angleDiff(aircraftHeading, bearingToOrigin);
  const diffToDest = angleDiff(aircraftHeading, bearingToDest);
  const diffToRoute = angleDiff(aircraftHeading, routeBearing);
  
  // Check if aircraft heading aligns with the origin→destination route (within 60°)
  if (diffToRoute <= 60) {
    return { valid: true, reason: 'aligned with route' };
  }
  
  // If heading away from origin AND generally toward destination = departing
  const oppositeOrigin = (bearingToOrigin + 180) % 360;
  const diffFromOppositeOrigin = angleDiff(aircraftHeading, oppositeOrigin);
  if (diffFromOppositeOrigin <= 45 && diffToDest <= 90) {
    return { valid: true, reason: 'departing origin' };
  }
  
  // Heading doesn't match the claimed route
  return { 
    valid: false, 
    reason: `heading ${Math.round(aircraftHeading)}° doesn't align with ${Math.round(routeBearing)}° route`,
    diffToRoute: Math.round(diffToRoute)
  };
}


function ohClosePopup() {
  // Hide the popup
  console.log("ohClosePopup called");
  document.getElementById('oh-popup').style.display = 'none';
  
  // Reset selected aircraft
  const oldReg = selectedAircraftReg;
  selectedAircraftReg = null;
  
  // Refresh all markers to restore altitude-based colors
  ohMarkers.forEach(m => {
    const mData = m.aircraftData;
    const mHdg = mData.track || 0;
    const mColor = getPlaneColor(mData.alt_baro);
    const mIcon = L.divIcon({
      html: `<span class="oh-plane-icon" style="color:${mColor} !important; transform:rotate(${mHdg - 90}deg); display:block;">✈︎</span>`,
      className: '',
      iconAnchor: [16, 16]
    });
    m.setIcon(mIcon);
  });
}
window.ohClosePopup = ohClosePopup;


async function ohShowPopup(a) {
    const flightId = a.flight ? a.flight.trim() : (a.r || 'Unknown');
    document.getElementById('oh-pop-route').textContent = 'looking up route…';
    document.getElementById('oh-pop-flight').textContent = '';
    document.getElementById('oh-pop-airline').textContent = a.desc || a.ownOp || '';
    document.getElementById('oh-pop-alt').textContent =
      a.alt_baro ? `${parseInt(a.alt_baro).toLocaleString()} ft` : '—';
    document.getElementById('oh-pop-spd').textContent =
      a.gs ? `${Math.round(a.gs)} kts` : '—';
    document.getElementById('oh-pop-hdg').textContent =
      a.track ? `${Math.round(a.track)}°` : '—';
    document.getElementById('oh-pop-dist').textContent =
      a.dst ? `${a.dst.toFixed(1)} nm` : '—';
    document.getElementById('oh-pop-vrate').textContent =
      a.geom_rate ? `${a.geom_rate > 0 ? '+' : ''}${Math.abs(a.geom_rate)} fpm` : '—';
    document.getElementById('oh-pop-bearing').textContent =
      a.dir ? `${Math.round(a.dir)}°` : '—';
    document.getElementById('oh-popup').style.display = 'block';

    const callsign = (a.flight || '').trim();
    if (!callsign) {
      document.getElementById('oh-pop-route').textContent = 'Private — no route data';
      return;
    }
    
    // Check if this looks like a commercial flight callsign
    // Commercial: starts with 3-letter airline code (AAL, DAL, UAL) or 2-letter + digits (AA123, DL456)
    // Private/GA: registration format (N12345) or non-standard callsign
    const commercialPattern = /^[A-Z]{3}\d+|^[A-Z]{2}\d+/;
    const isLikelyCommercial = commercialPattern.test(callsign);
    
    try {
      const res  = await fetch(`https://api.adsbdb.com/v0/callsign/${callsign}`);
      if (!res.ok) throw new Error();
      const data = await res.json();
      const r = data?.response?.flightroute;
      if (r) {
        const airline = r.airline?.name || '';
        const callsignDisplay = r.callsign_iata || r.callsign_icao || callsign;
        const headerLine = airline ? `${airline} • ${callsignDisplay}` : callsignDisplay;
        document.getElementById('oh-pop-flight').textContent = headerLine;
        
        const origCity = r.origin?.municipality || '?';
        const origCode = r.origin?.iata_code || r.origin?.icao_code || '?';
        const destCity = r.destination?.municipality || '?';
        const destCode = r.destination?.iata_code || r.destination?.icao_code || '?';
        
        // Validate route using trajectory
        const validation = validateRoute(
          a.lat, a.lon, a.track,
          r.origin?.latitude, r.origin?.longitude,
          r.destination?.latitude, r.destination?.longitude
        );
        
        let routeText = `${origCity} (${origCode}) → ${destCity} (${destCode})`;
        const faLink = ` <a href="https://flightaware.com/live/flight/${callsign}" target="_blank" style="color:#60a5fa; text-decoration:underline;">verify</a>`;
        
        if (validation.valid === false) {
          // Route questionable - add warning and gray it out
          document.getElementById('oh-pop-route').innerHTML = 
            `<span style="color:#888;">${routeText} ⚠️</span>${faLink}`;
        } else {
          // Route validated - show normally with verify link
          document.getElementById('oh-pop-route').innerHTML = `${routeText}${faLink}`;
        }

      } else {
        // No route data returned - could be private or just not in database
        if (isLikelyCommercial) {
          document.getElementById('oh-pop-route').textContent = 'Route unknown';
        } else {
          document.getElementById('oh-pop-flight').textContent = 'Private — no route data';
          document.getElementById('oh-pop-route').textContent = '';
        }
      }
    } catch(e) {
      // API call failed - distinguish between private and commercial
      if (isLikelyCommercial) {
        document.getElementById('oh-pop-route').textContent = 'Route lookup failed';
      } else {
        document.getElementById('oh-pop-flight').textContent = 'Private — no route data';
        document.getElementById('oh-pop-route').textContent = '';
      }
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


  // Toggle live auto-refresh
  window.ohToggleLive = function() {
    if (ohIsPlaying) {
      // Stop auto-refresh
      clearInterval(ohRefreshTimer);
      ohRefreshTimer = null;
      ohIsPlaying = false;
      document.getElementById('oh-live-btn').textContent = 'Live';
    } else {
      // Start auto-refresh
      ohIsPlaying = true;
      document.getElementById('oh-live-btn').textContent = 'Stop';
      ohFetch(); // Fetch immediately
      ohRefreshTimer = setInterval(ohFetch, REFRESH_MS);
    }
  };

  // Stop auto-refresh (called when leaving Overhead tab)
  window.ohStopLive = function() {
    if (ohIsPlaying) {
      clearInterval(ohRefreshTimer);
      ohRefreshTimer = null;
      ohIsPlaying = false;
      document.getElementById('oh-live-btn').textContent = 'Live';
    }
  };

  // Stop auto-refresh when page becomes hidden (lock, minimize, tab switch)
  document.addEventListener('visibilitychange', function() {
    if (document.hidden && ohIsPlaying) {
      clearInterval(ohRefreshTimer);
      ohRefreshTimer = null;
      // Keep ohIsPlaying true so it resumes when visible again
    } else if (!document.hidden && ohIsPlaying && !ohRefreshTimer) {
      ohFetch();
      ohRefreshTimer = setInterval(ohFetch, REFRESH_MS);
    }
  });

})();
