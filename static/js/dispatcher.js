document.addEventListener("DOMContentLoaded", () => {
  const mapElement = document.getElementById("dispatch-map");
  const statusElement = document.getElementById("map-status");
  if (!mapElement) return;
  if (!window.L) {
    statusElement.textContent = "The map library did not load. Check the connection and reload.";
    return;
  }
  const map = L.map(mapElement).setView([20.5937, 78.9629], 5);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  const markers = new Map();
  const updateMarker = (location) => {
    let marker = markers.get(location.id);
    if (location.latitude === null || location.longitude === null) {
      if (marker) {
        map.removeLayer(marker);
        markers.delete(location.id);
      }
      return;
    }

    const coordinates = [location.latitude, location.longitude];
    if (!marker) {
      marker = L.marker(coordinates).addTo(map);
      markers.set(location.id, marker);
    } else {
      marker.setLatLng(coordinates);
    }
    const popup = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = location.vehicle_number;
    const driver = document.createElement("div");
    driver.textContent = location.driver;
    const state = document.createElement("div");
    state.textContent = `${location.availability} · Patient ${location.patient_status}`;
    const updated = document.createElement("div");
    updated.textContent = `Last update: ${new Date(location.updated_at).toLocaleString()}`;
    popup.append(title, driver, state, updated);
    marker.bindPopup(popup);
  };

  const fetchLocations = async () => {
    try {
      const response = await fetch(mapElement.dataset.locationsUrl, {
        headers: { Accept: "application/json" },
      });
      if (!response.ok) throw new Error(`Location request failed (${response.status}).`);
      const data = await response.json();
      const seen = new Set();
      data.locations.forEach((location) => {
        seen.add(location.id);
        updateMarker(location);
      });
      markers.forEach((marker, id) => {
        if (!seen.has(id)) {
          map.removeLayer(marker);
          markers.delete(id);
        }
      });
      statusElement.textContent = `${data.locations.length} ambulance location(s) available.`;
    } catch (error) {
      statusElement.textContent = `Unable to refresh locations: ${error.message}`;
    }
  };

  const connect = () => {
    const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${scheme}//${window.location.host}/ws/locations/`);
    socket.onopen = () => {
      statusElement.textContent = "Live ambulance locations connected.";
    };
    socket.onmessage = (event) => {
      try {
        updateMarker(JSON.parse(event.data));
        statusElement.textContent = "Live ambulance locations connected.";
      } catch (error) {
        statusElement.textContent = `Unable to read a location update: ${error.message}`;
      }
    };
    socket.onclose = (event) => {
      if (event.code === 4403) {
        statusElement.textContent = "Live location access ended. Sign in again.";
        return;
      }
      statusElement.textContent = "Live connection lost; reconnecting…";
      window.setTimeout(connect, 5000);
    };
    socket.onerror = () => socket.close();
  };

  fetchLocations();
  connect();
  window.setInterval(fetchLocations, 30000);
});
