/**
 * FoodBridge Client-side JavaScript
 * Handlers for Leaflet OpenStreetMap interactive maps, dynamic filtering, and form utilities.
 */

document.addEventListener('DOMContentLoaded', () => {
  // Auto dismiss flash alert messages after 6 seconds
  setTimeout(() => {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
      alert.style.opacity = '0';
      alert.style.transition = 'opacity 0.5s ease';
      setTimeout(() => alert.remove(), 500);
    });
  }, 6000);

  // Initialize features based on current page elements
  initInteractiveMap();
  initLocationPicker();
  initMapViewToggle();
});

/**
 * Initialize Interactive Map view for all food donations list (donations.html)
 */
function initInteractiveMap() {
  const mapElement = document.getElementById('donations-map');
  if (!mapElement) return;

  // Default centered around Bangalore / India (can auto-fit markers)
  const map = L.map('donations-map').setView([12.9716, 77.5946], 12);

  // OpenStreetMap tile layer (Free, fast, no API key needed)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap contributors'
  }).addTo(map);

  // Fetch donation locations from Flask JSON API
  fetch('/api/donations')
    .then(res => res.json())
    .then(donations => {
      if (!donations || donations.length === 0) return;

      const bounds = L.latLngBounds();

      donations.forEach(item => {
        if (item.latitude && item.longitude) {
          const latLng = [item.latitude, item.longitude];
          bounds.extend(latLng);

          // Color badge based on status
          let statusBadgeClass = 'badge-available';
          if (item.status === 'Picked') statusBadgeClass = 'badge-picked';
          if (item.status === 'Delivered') statusBadgeClass = 'badge-delivered';

          const popupContent = `
            <div style="font-family: 'Inter', sans-serif; padding: 4px; min-width: 180px;">
              <span class="badge ${statusBadgeClass}" style="margin-bottom: 6px;">${item.status}</span>
              <h4 style="margin: 4px 0; font-size: 1rem; color: #0f172a;">${item.food_name}</h4>
              <p style="margin: 0; font-size: 0.85rem; color: #64748b;"><strong>Qty:</strong> ${item.quantity}</p>
              <p style="margin: 0 0 8px 0; font-size: 0.85rem; color: #64748b;"><strong>Donor:</strong> ${item.donor_org || item.donor_name}</p>
              <a href="/donations/${item.id}" class="btn btn-primary btn-sm" style="width: 100%; text-align: center; color: white;">View Details</a>
            </div>
          `;

          L.marker(latLng).addTo(map).bindPopup(popupContent);
        }
      });

      if (donations.length > 0) {
        map.fitBounds(bounds, { padding: [40, 40] });
      }
    })
    .catch(err => console.error("Error fetching map donations:", err));
}

/**
 * Initialize Drag-and-Drop Location Picker Map (add_donation.html)
 */
function initLocationPicker() {
  const pickerElement = document.getElementById('location-picker-map');
  if (!pickerElement) return;

  const latInput = document.getElementById('latitude');
  const lngInput = document.getElementById('longitude');
  const addressInput = document.getElementById('location');

  // Default starting position
  const defaultLat = parseFloat(latInput.value) || 12.9716;
  const defaultLng = parseFloat(lngInput.value) || 77.5946;

  const map = L.map('location-picker-map').setView([defaultLat, defaultLng], 13);

  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '© OpenStreetMap contributors'
  }).addTo(map);

  // Draggable Marker
  const marker = L.marker([defaultLat, defaultLng], { draggable: true }).addTo(map);

  function updateCoordinates(lat, lng) {
    latInput.value = lat.toFixed(6);
    lngInput.value = lng.toFixed(6);

    // Optional reverse geocoding via Nominatim API to update address input
    fetch(`https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}`)
      .then(res => res.json())
      .then(data => {
        if (data && data.display_name && (!addressInput.value || addressInput.value.trim() === '')) {
          addressInput.value = data.display_name;
        }
      })
      .catch(() => {});
  }

  // Update on drag end
  marker.on('dragend', function (e) {
    const coord = marker.getLatLng();
    updateCoordinates(coord.lat, coord.lng);
  });

  // Update on map click
  map.on('click', function (e) {
    marker.setLatLng(e.latlng);
    updateCoordinates(e.latlng.lat, e.latlng.lng);
  });
}

/**
 * Toggle between Cards Grid and Map View on donations page
 */
function initMapViewToggle() {
  const toggleBtn = document.getElementById('toggle-view-btn');
  const cardsContainer = document.getElementById('cards-view');
  const mapContainer = document.getElementById('map-view');

  if (!toggleBtn || !cardsContainer || !mapContainer) return;

  let isMapView = false;

  toggleBtn.addEventListener('click', () => {
    isMapView = !isMapView;
    if (isMapView) {
      cardsContainer.style.display = 'none';
      mapContainer.style.display = 'block';
      toggleBtn.innerHTML = '📋 Switch to Card View';
      // Trigger map resize recalculation
      window.dispatchEvent(new Event('resize'));
    } else {
      cardsContainer.style.display = 'grid';
      mapContainer.style.display = 'none';
      toggleBtn.innerHTML = '🗺️ Switch to Map View';
    }
  });
}
