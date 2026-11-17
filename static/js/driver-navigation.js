document.addEventListener("DOMContentLoaded", () => {
  const mapElement = document.getElementById("driver-navigation-map");
  const statusElement = document.getElementById("navigation-map-status");
  const tracker = document.querySelector("[data-gps-tracker]");
  if (!mapElement || !statusElement || !tracker) return;

  if (!window.L) {
    statusElement.textContent = "The map library did not load. Check the connection and reload.";
    return;
  }

  const readCoordinate = (value, minimum, maximum) => {
    if (value === "") return null;
    const coordinate = Number(value);
    return Number.isFinite(coordinate) && coordinate >= minimum && coordinate <= maximum
      ? coordinate
      : null;
  };
  const destination = {
    latitude: readCoordinate(mapElement.dataset.destinationLatitude, -90, 90),
    longitude: readCoordinate(mapElement.dataset.destinationLongitude, -180, 180),
  };
  if (destination.latitude === null || destination.longitude === null) {
    statusElement.textContent = "The confirmed destination coordinates are unavailable.";
    return;
  }

  const destinationLatLng = [destination.latitude, destination.longitude];
  const map = L.map(mapElement).setView(destinationLatLng, 14);
  L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 19,
    attribution: 'Sources: <a href="https://goto.arcgisonline.com/maps/World_Street_Map">Esri</a>, HERE, Garmin, USGS, Intermap, INCREMENT P, NRCan, Esri Japan, METI, Esri China (Hong Kong), Esri Korea, Esri (Thailand), NGCC, &copy; OpenStreetMap contributors, and the GIS User Community',
  }).addTo(map);

  const destinationIcon = L.divIcon({
    className: "driver-navigation-marker",
    html: '<span class="driver-navigation-destination" aria-label="Patient destination">!</span>',
    iconSize: [32, 38],
    iconAnchor: [16, 36],
  });
  L.marker(destinationLatLng, { icon: destinationIcon })
    .addTo(map)
    .bindTooltip("Confirmed patient destination", { direction: "top", offset: [0, -30] });

  const ambulanceIcon = L.divIcon({
    className: "driver-navigation-marker",
    html: '<span class="driver-navigation-ambulance" aria-label="Live ambulance GPS">🚑</span>',
    iconSize: [40, 40],
    iconAnchor: [20, 20],
  });
  const start = {
    latitude: readCoordinate(mapElement.dataset.startLatitude, -90, 90),
    longitude: readCoordinate(mapElement.dataset.startLongitude, -180, 180),
  };
  let latestPosition = (
    start.latitude !== null && start.longitude !== null
      ? { latitude: start.latitude, longitude: start.longitude }
      : null
  );
  let ambulanceMarker = null;
  let startMarker = null;
  if (latestPosition) {
    const startLatLng = [latestPosition.latitude, latestPosition.longitude];
    startMarker = L.circleMarker(startLatLng, {
      radius: 6,
      color: "#0f6b46",
      fillColor: "#fff",
      fillOpacity: 1,
      weight: 3,
    }).addTo(map).bindTooltip("Starting point (last verified GPS)");
    ambulanceMarker = L.marker(startLatLng, { icon: ambulanceIcon })
      .addTo(map)
      .bindTooltip("Latest verified ambulance GPS");
    map.fitBounds(L.latLngBounds([startLatLng, destinationLatLng]).pad(0.2), { maxZoom: 15 });
  } else {
    statusElement.textContent =
      "Showing the confirmed destination only. Start navigation to get a live GPS position.";
  }

  let routeLayer = null;
  let fallbackLayer = null;
  let routeGeometry = [];
  let routeDistanceMeters = 0;
  let routeDurationSeconds = 0;
  let routeOrigin = null;
  let lastRouteRequestAt = 0;
  let routeRequestId = 0;
  let routeInFlight = false;
  let followAmbulance = true;
  const rerouteDistanceMeters = 250;
  const rerouteAfterMs = 90000;
  const routeUrl = tracker.dataset.routeUrl;

  const distanceMeters = (left, right) => {
    const radians = (degrees) => degrees * Math.PI / 180;
    const latitudeDelta = radians(right.latitude - left.latitude);
    const longitudeDelta = radians(right.longitude - left.longitude);
    const firstLatitude = radians(left.latitude);
    const secondLatitude = radians(right.latitude);
    const value = Math.sin(latitudeDelta / 2) ** 2
      + Math.cos(firstLatitude) * Math.cos(secondLatitude)
      * Math.sin(longitudeDelta / 2) ** 2;
    return 6371000 * 2 * Math.atan2(Math.sqrt(value), Math.sqrt(1 - value));
  };

  const remainingAlongRoute = (point) => {
    if (routeGeometry.length < 2) return null;
    let nearestSegment = 0;
    let nearestFraction = 0;
    let nearestDistanceSquared = Infinity;
    for (let index = 0; index < routeGeometry.length - 1; index += 1) {
      const first = routeGeometry[index];
      const second = routeGeometry[index + 1];
      const scale = Math.cos((point.latitude + first.latitude + second.latitude) / 3 * Math.PI / 180);
      const firstX = first.longitude * scale;
      const firstY = first.latitude;
      const deltaX = (second.longitude - first.longitude) * scale;
      const deltaY = second.latitude - first.latitude;
      const lengthSquared = deltaX * deltaX + deltaY * deltaY;
      const fraction = lengthSquared === 0
        ? 0
        : Math.max(0, Math.min(1, (
          (point.longitude * scale - firstX) * deltaX
          + (point.latitude - firstY) * deltaY
        ) / lengthSquared));
      const offsetX = point.longitude * scale - (firstX + fraction * deltaX);
      const offsetY = point.latitude - (firstY + fraction * deltaY);
      const distanceSquared = offsetX * offsetX + offsetY * offsetY;
      if (distanceSquared < nearestDistanceSquared) {
        nearestDistanceSquared = distanceSquared;
        nearestSegment = index;
        nearestFraction = fraction;
      }
    }

    let remaining = distanceMeters(
      {
        latitude: routeGeometry[nearestSegment].latitude
          + (routeGeometry[nearestSegment + 1].latitude - routeGeometry[nearestSegment].latitude) * nearestFraction,
        longitude: routeGeometry[nearestSegment].longitude
          + (routeGeometry[nearestSegment + 1].longitude - routeGeometry[nearestSegment].longitude) * nearestFraction,
      },
      routeGeometry[nearestSegment + 1],
    );
    for (let index = nearestSegment + 1; index < routeGeometry.length - 1; index += 1) {
      remaining += distanceMeters(routeGeometry[index], routeGeometry[index + 1]);
    }
    return remaining;
  };

  const updateRouteStatus = () => {
    if (!routeGeometry.length || !latestPosition) return;
    const remaining = remainingAlongRoute(latestPosition);
    if (remaining === null) return;
    const remainingKm = (remaining / 1000).toFixed(1);
    const remainingMinutes = routeDistanceMeters > 0
      ? Math.round(routeDurationSeconds * remaining / routeDistanceMeters)
      : 0;
    statusElement.textContent =
      `Road route: ${remainingKm} km remaining · about ${remainingMinutes} min by OSRM estimate. Not traffic-aware.`;
  };

  const showStraightLineFallback = () => {
    if (!latestPosition) {
      statusElement.textContent = "Road route unavailable. Start GPS tracking to show the ambulance position.";
      return;
    }
    if (fallbackLayer) map.removeLayer(fallbackLayer);
    if (routeLayer) {
      map.removeLayer(routeLayer);
      routeLayer = null;
    }
    fallbackLayer = L.polyline(
      [[latestPosition.latitude, latestPosition.longitude], destinationLatLng],
      { color: "#a65b00", weight: 4, dashArray: "8 8", opacity: .8 },
    ).addTo(map);
    const directKm = (distanceMeters(latestPosition, destination) / 1000).toFixed(1);
    statusElement.textContent =
      `OSRM road route unavailable. Showing a ${directKm} km straight-line fallback; this is not a road route or ETA.`;
  };

  const requestRoute = async (force = false) => {
    if (!latestPosition || !routeUrl || tracker.dataset.routeAvailable !== "true") {
      if (!latestPosition) {
        statusElement.textContent = "Start navigation to get a live GPS position and route.";
      } else {
        statusElement.textContent = "A road route is not available for the current journey status.";
      }
      return;
    }
    if (routeInFlight) return;
    if (!force && routeOrigin) {
      const moved = distanceMeters(routeOrigin, latestPosition);
      if (moved < rerouteDistanceMeters && Date.now() - lastRouteRequestAt < rerouteAfterMs) {
        if (routeGeometry.length) updateRouteStatus();
        else if (fallbackLayer) showStraightLineFallback();
        return;
      }
    }

    routeInFlight = true;
    const requestId = ++routeRequestId;
    const requestedOrigin = { ...latestPosition };
    lastRouteRequestAt = Date.now();
    statusElement.textContent = "Loading road route from OSRM…";
    const controller = typeof AbortController === "undefined" ? null : new AbortController();
    const timeoutId = window.setTimeout(() => {
      if (controller) controller.abort();
    }, 10000);
    try {
      const url = `${routeUrl}${requestedOrigin.longitude},${requestedOrigin.latitude};${destination.longitude},${destination.latitude}?overview=full&geometries=geojson&steps=false`;
      const requestOptions = { headers: { Accept: "application/json" } };
      if (controller) requestOptions.signal = controller.signal;
      const response = await fetch(url, requestOptions);
      if (!response.ok) throw new Error(`Routing service returned ${response.status}.`);
      const data = await response.json();
      if (requestId !== routeRequestId) return;
      if (data.code !== "Ok" || !data.routes || !data.routes.length) {
        throw new Error(data.message || "No road route was returned.");
      }
      const route = data.routes[0];
      if (
        !route.geometry
        || route.geometry.type !== "LineString"
        || !Array.isArray(route.geometry.coordinates)
        || route.geometry.coordinates.length < 2
        || !route.geometry.coordinates.every((coordinate) => (
          Array.isArray(coordinate)
          && Number.isFinite(Number(coordinate[0]))
          && Number.isFinite(Number(coordinate[1]))
          && Number(coordinate[0]) >= -180
          && Number(coordinate[0]) <= 180
          && Number(coordinate[1]) >= -90
          && Number(coordinate[1]) <= 90
        ))
        || !Number.isFinite(Number(route.distance))
        || Number(route.distance) <= 0
        || !Number.isFinite(Number(route.duration))
        || Number(route.duration) < 0
      ) {
        throw new Error("The routing service returned invalid route geometry.");
      }
      if (routeLayer) map.removeLayer(routeLayer);
      if (fallbackLayer) {
        map.removeLayer(fallbackLayer);
        fallbackLayer = null;
      }
      routeLayer = L.geoJSON(route.geometry, {
        style: { color: "#1769aa", weight: 5, opacity: .82 },
      }).addTo(map);
      routeGeometry = route.geometry.coordinates.map(([longitude, latitude]) => ({
        latitude,
        longitude,
      }));
      routeDistanceMeters = Number(route.distance) || 0;
      routeDurationSeconds = Number(route.duration) || 0;
      routeOrigin = requestedOrigin;
      updateRouteStatus();
    } catch (error) {
      if (requestId !== routeRequestId) return;
      routeGeometry = [];
      routeOrigin = requestedOrigin;
      showStraightLineFallback();
      statusElement.textContent += ` (${error.message})`;
    } finally {
      window.clearTimeout(timeoutId);
      routeInFlight = false;
      if (
        latestPosition
        && routeOrigin
        && distanceMeters(routeOrigin, latestPosition) >= rerouteDistanceMeters
      ) {
        requestRoute();
      }
    }
  };

  map.on("dragstart zoomstart", () => {
    followAmbulance = false;
  });
  const recenterButton = tracker.querySelector("[data-map-recenter]");
  if (recenterButton) {
    recenterButton.addEventListener("click", () => {
      followAmbulance = true;
      if (latestPosition) {
        map.setView([latestPosition.latitude, latestPosition.longitude], Math.max(map.getZoom(), 15));
      }
    });
  }

  window.addEventListener("driver:gps-position", (event) => {
    const point = {
      latitude: event.detail.latitude,
      longitude: event.detail.longitude,
    };
    latestPosition = point;
    const latLng = [point.latitude, point.longitude];
    if (!startMarker) {
      startMarker = L.circleMarker(latLng, {
        radius: 6,
        color: "#0f6b46",
        fillColor: "#fff",
        fillOpacity: 1,
        weight: 3,
      }).addTo(map).bindTooltip("Journey start point");
    }
    if (!ambulanceMarker) {
      ambulanceMarker = L.marker(latLng, { icon: ambulanceIcon })
        .addTo(map)
        .bindTooltip("Live ambulance GPS");
    } else {
      ambulanceMarker.setLatLng(latLng);
    }
    if (followAmbulance) map.panTo(latLng);
    if (!routeOrigin) requestRoute(true);
    else requestRoute();
  });

  if (latestPosition) requestRoute(true);
});
