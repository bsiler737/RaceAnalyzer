/**
 * Leaflet map initialization for HTMX-swapped content.
 */
function initMap(el) {
  const coordsAttr = el.getAttribute('data-leaflet-coords');
  const climbsAttr = el.getAttribute('data-leaflet-climbs');
  if (!coordsAttr) return;

  try {
    const coords = JSON.parse(coordsAttr);
    if (!coords || coords.length < 2) return;

    // Destroy existing map instance if any
    if (el._leafletMap) {
      el._leafletMap.remove();
    }

    const center = coords[Math.floor(coords.length / 2)];
    const map = L.map(el, {scrollWheelZoom: false}).setView(center, 13);
    el._leafletMap = map;

    L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
      attribution: '&copy; OpenStreetMap contributors &copy; CARTO',
      maxZoom: 19
    }).addTo(map);

    // Main route polyline
    L.polyline(coords, {color: '#2563EB', weight: 4, opacity: 0.85}).addTo(map);

    // Start marker
    L.marker(coords[0], {
      icon: L.divIcon({className: 'leaflet-start-marker', html: '<div style="background:#22c55e;width:12px;height:12px;border-radius:50%;border:2px solid white;"></div>'})
    }).addTo(map);

    // Finish marker
    L.marker(coords[coords.length - 1], {
      icon: L.divIcon({className: 'leaflet-finish-marker', html: '<div style="background:#ef4444;width:12px;height:12px;border-radius:50%;border:2px solid white;"></div>'})
    }).addTo(map);

    // Climb overlays
    if (climbsAttr) {
      const climbs = JSON.parse(climbsAttr);
      climbs.forEach(function(climb) {
        if (climb.coords && climb.coords.length >= 2) {
          const color = climb.grade < 5 ? '#FFC107' : climb.grade < 8 ? '#FF5722' : '#B71C1C';
          L.polyline(climb.coords, {color: color, weight: 7, opacity: 0.9}).addTo(map);
        }
      });
    }

    // Fit bounds
    const bounds = L.latLngBounds(coords);
    map.fitBounds(bounds, {padding: [20, 20]});

  } catch (e) {
    console.error('Map init failed:', e);
  }
}

document.addEventListener('DOMContentLoaded', function() {
  document.querySelectorAll('[data-leaflet-coords]').forEach(initMap);
});

document.body.addEventListener('htmx:afterSwap', function(event) {
  event.detail.target.querySelectorAll('[data-leaflet-coords]').forEach(initMap);
});
