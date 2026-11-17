document.addEventListener("DOMContentLoaded", () => {
  const mapElement = document.getElementById("dispatch-map");
  if (!mapElement) return;

  const statusElement = document.getElementById("map-status");
  const routeStatusElement = document.getElementById("route-status");
  const emergencyList = document.getElementById("emergency-list");
  const detailsElement = document.getElementById("selection-details");
  const routeUrl = mapElement.dataset.routeUrl;
  const refreshInterval = 5000;

  if (!window.L) {
    statusElement.textContent = "The map library did not load. Check the connection and reload.";
    return;
  }

  const map = L.map(mapElement).setView([17.6868, 83.2185], 11);
  L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}", {
    maxZoom: 19,
    attribution: 'Sources: <a href="https://goto.arcgisonline.com/maps/World_Street_Map">Esri</a>, HERE, Garmin, USGS, Intermap, INCREMENT P, NRCan, Esri Japan, METI, Esri China (Hong Kong), Esri Korea, Esri (Thailand), NGCC, &copy; OpenStreetMap contributors, and the GIS User Community',
  }).addTo(map);

  const ambulanceMarkers = new Map();
  const patientMarkers = new Map();
  let emergencies = [];
  let locations = [];
  let selectedBookingId = null;
  let routeLayer = null;
  let routeKey = "";
  let routeRequestId = 0;
  let routeOrigin = null;
  let routeGeometry = null;
  let routeDistanceMeters = 0;
  let routeDurationSeconds = 0;
  let lastRouteRequestAt = 0;

  const formatDate = (value) => {
    if (!value) return "No GPS update";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? "Unknown" : date.toLocaleString();
  };

  const hasCoordinates = (latitude, longitude) => (
    latitude !== null
    && longitude !== null
    && latitude !== undefined
    && longitude !== undefined
    && Number.isFinite(Number(latitude))
    && Number.isFinite(Number(longitude))
    && Number(latitude) >= -90
    && Number(latitude) <= 90
    && Number(longitude) >= -180
    && Number(longitude) <= 180
  );

  const distanceMeters = (left, right) => {
    if (!left || !right) return Infinity;
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

  const appendDetail = (list, label, value, className = "") => {
    const term = document.createElement("dt");
    term.textContent = label;
    const description = document.createElement("dd");
    description.textContent = value || "Not available";
    if (className) description.className = className;
    list.append(term, description);
  };

  const ambulanceIcon = (location, selected) => {
    const classes = ["ambulance-marker"];
    if (location.availability !== "Available" || location.patient_status === "ON") {
      classes.push("is-busy");
    }
    if (location.gps_stale) classes.push("is-stale");
    if (selected) classes.push("is-selected");
    return L.divIcon({
      className: "dispatch-div-icon",
      html: `<div class="${classes.join(" ")}" aria-label="Ambulance ${location.vehicle_number}">🚑</div>`,
      iconSize: [36, 36],
      iconAnchor: [18, 18],
      popupAnchor: [0, -18],
    });
  };

  const patientIcon = (selected) => L.divIcon({
    className: "dispatch-div-icon",
    html: `<div class="patient-marker${selected ? " is-selected" : ""}" aria-label="Emergency patient"><span>!</span></div>`,
    iconSize: [36, 36],
    iconAnchor: [18, 30],
    popupAnchor: [0, -30],
  });

  const popupDetails = (titleText, rows) => {
    const wrapper = document.createElement("div");
    const title = document.createElement("strong");
    title.textContent = titleText;
    wrapper.append(title);
    rows.forEach(([label, value]) => {
      const row = document.createElement("div");
      row.textContent = `${label}: ${value || "Not available"}`;
      wrapper.append(row);
    });
    return wrapper;
  };

  const updateAmbulanceMarker = (location) => {
    let marker = ambulanceMarkers.get(location.id);
    if (!hasCoordinates(location.latitude, location.longitude)) {
      if (marker) {
        map.removeLayer(marker);
        ambulanceMarkers.delete(location.id);
      }
      return;
    }

    const coordinates = [Number(location.latitude), Number(location.longitude)];
    const selected = emergencies.some(
      (booking) => booking.id === selectedBookingId && booking.ambulance_id === location.id,
    );
    if (!marker) {
      marker = L.marker(coordinates).addTo(map);
      ambulanceMarkers.set(location.id, marker);
    } else {
      marker.setLatLng(coordinates);
    }
    marker.setIcon(ambulanceIcon(location, selected));
    const activeBooking = emergencies.find((booking) => booking.id === location.active_booking_id);
    marker.bindPopup(popupDetails(location.vehicle_number, [
      ["Driver", location.driver],
      ["Contact", location.driver_phone],
      ["Availability", location.availability],
      ["Patient status", location.patient_status],
      ["Coordinates", `${Number(location.latitude).toFixed(5)}, ${Number(location.longitude).toFixed(5)}`],
      ["GPS accuracy", location.accuracy_meters == null ? "Not available" : `±${Number(location.accuracy_meters).toFixed(0)} m`],
      ["Last GPS update", formatDate(location.updated_at)],
      ["GPS", location.gps_stale ? "Stale / offline" : "Current"],
      ["Active emergency", activeBooking ? activeBooking.id : "None"],
      ["Journey status", location.booking_status || "No active booking"],
    ]));
  };

  const updatePatientMarker = (booking) => {
    let marker = patientMarkers.get(booking.id);
    if (!booking.location_confirmed || !hasCoordinates(booking.latitude, booking.longitude)) {
      if (marker) {
        map.removeLayer(marker);
        patientMarkers.delete(booking.id);
      }
      return;
    }
    const coordinates = [Number(booking.latitude), Number(booking.longitude)];
    if (!marker) {
      marker = L.marker(coordinates).addTo(map);
      patientMarkers.set(booking.id, marker);
    } else {
      marker.setLatLng(coordinates);
    }
    marker.setIcon(patientIcon(booking.id === selectedBookingId));
    marker.bindPopup(popupDetails(booking.patient, [
      ["Case ID", booking.id],
      ["Emergency Type", booking.emergency_type],
      ["Address", booking.address],
      ["Contact Number", booking.patient_phone],
    ]));
    marker.off("click");
    marker.on("click", () => selectEmergency(booking.id, true));
  };

  const renderEmergencyList = () => {
    emergencyList.replaceChildren();
    document.getElementById("case-count").textContent = String(emergencies.length);
    if (!emergencies.length) {
      const empty = document.createElement("p");
      empty.className = "operations-empty";
      empty.textContent = "No active emergencies.";
      emergencyList.append(empty);
      return;
    }

    emergencies.forEach((booking) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `emergency-card${booking.id === selectedBookingId ? " is-selected" : ""}`;
      button.setAttribute("aria-pressed", String(booking.id === selectedBookingId));
      button.addEventListener("click", () => selectEmergency(booking.id, true));

      const top = document.createElement("div");
      top.className = "emergency-card-top";
      const id = document.createElement("span");
      id.className = "case-id";
      id.textContent = `CASE ${booking.id.slice(0, 8).toUpperCase()}`;
      const badge = document.createElement("span");
      const statusClass = booking.status.toLowerCase().replace(/[^a-z0-9]+/g, "-");
      badge.className = `case-status status-${statusClass}`;
      badge.textContent = booking.status;
      top.append(id, badge);

      const patient = document.createElement("p");
      patient.className = "emergency-patient";
      patient.textContent = booking.patient;
      const address = document.createElement("div");
      address.className = "emergency-address";
      address.textContent = booking.address;
      const meta = document.createElement("div");
      meta.className = "emergency-card-meta";
      const assigned = document.createElement("span");
      assigned.textContent = booking.ambulance
        ? `${booking.ambulance} · ${booking.driver || "Driver pending"}`
        : "Unassigned";
      const count = document.createElement("span");
      count.textContent = `${booking.number_of_patients} patient${booking.number_of_patients === 1 ? "" : "s"}`;
      meta.append(assigned, count);
      const gps = document.createElement("div");
      gps.className = "emergency-card-meta emergency-gps-meta";
      gps.textContent = booking.last_location_update
        ? `${booking.gps_stale ? "GPS stale" : "GPS updated"} · ${formatDate(booking.last_location_update)}`
        : "No assigned ambulance GPS";
      button.append(top, patient, address, meta, gps);
      emergencyList.append(button);
    });
  };

  const renderSelection = () => {
    const booking = emergencies.find((item) => item.id === selectedBookingId);
    detailsElement.replaceChildren();
    const heading = document.createElement("h3");
    heading.textContent = booking ? "Selected emergency" : "Case details";
    detailsElement.append(heading);
    if (!booking) {
      const placeholder = document.createElement("p");
      placeholder.className = "selection-placeholder";
      placeholder.textContent = "Select an emergency to review its patient, ambulance, driver, and route.";
      detailsElement.append(placeholder);
      return;
    }

    const detailList = document.createElement("dl");
    detailList.className = "detail-grid";
    appendDetail(detailList, "Case ID", booking.id);
    appendDetail(detailList, "Patient", booking.patient);
    appendDetail(detailList, "Emergency Type", booking.emergency_type);
    appendDetail(detailList, "Contact", booking.patient_phone);
    appendDetail(detailList, "Address", booking.address);
    appendDetail(
      detailList,
      "Patient location",
      booking.location_confirmed ? "Confirmed" : "Unconfirmed; dispatch is blocked",
    );
    appendDetail(detailList, "Patients", String(booking.number_of_patients));
    appendDetail(detailList, "Requested", formatDate(booking.requested_at));
    appendDetail(detailList, "Status", booking.status);
    appendDetail(detailList, "Driver status", booking.booking_status || booking.status);
    appendDetail(detailList, "Ambulance", booking.ambulance || "Unassigned");
    appendDetail(detailList, "Driver", booking.driver || "Not assigned");
    appendDetail(detailList, "Driver contact", booking.driver_phone || "Not available");
    appendDetail(
      detailList,
      "Ambulance GPS",
      hasCoordinates(booking.ambulance_latitude, booking.ambulance_longitude)
        ? `${Number(booking.ambulance_latitude).toFixed(5)}, ${Number(booking.ambulance_longitude).toFixed(5)}`
        : "Not available",
    );
    appendDetail(
      detailList,
      "Last GPS update",
      booking.last_location_update ? formatDate(booking.last_location_update) : "No assigned ambulance",
      `gps-state${booking.gps_stale ? " is-stale" : " is-fresh"}`,
    );
    appendDetail(
      detailList,
      "GPS accuracy",
      booking.gps_accuracy_meters == null
        ? "Not available"
        : `±${Number(booking.gps_accuracy_meters).toFixed(0)} m`,
    );
    if (booking.suggested_ambulance) {
      appendDetail(
        detailList,
        "Nearest eligible",
        `${booking.suggested_ambulance.vehicle_number} (suggestion only)`,
      );
    }
    detailsElement.append(detailList);
  };

  const removeRoute = () => {
    routeRequestId += 1;
    if (routeLayer) {
      map.removeLayer(routeLayer);
      routeLayer = null;
    }
    routeKey = "";
    routeOrigin = null;
    routeGeometry = null;
  };

  const remainingRouteDistance = (coordinates, point) => {
    if (!Array.isArray(coordinates) || coordinates.length < 2) return null;
    const points = coordinates.map(([longitude, latitude]) => ({ latitude, longitude }));
    let nearestSegment = 0;
    let nearestFraction = 0;
    let nearestDistanceSquared = Infinity;
    for (let index = 0; index < points.length - 1; index += 1) {
      const first = points[index];
      const second = points[index + 1];
      const scale = Math.cos((point.latitude + first.latitude + second.latitude) / 3 * Math.PI / 180);
      const firstX = first.longitude * scale;
      const deltaX = (second.longitude - first.longitude) * scale;
      const deltaY = second.latitude - first.latitude;
      const lengthSquared = deltaX * deltaX + deltaY * deltaY;
      const fraction = lengthSquared === 0
        ? 0
        : Math.max(0, Math.min(1, (
          (point.longitude * scale - firstX) * deltaX
          + (point.latitude - first.latitude) * deltaY
        ) / lengthSquared));
      const offsetX = point.longitude * scale - (firstX + fraction * deltaX);
      const offsetY = point.latitude - (first.latitude + fraction * deltaY);
      const distanceSquared = offsetX * offsetX + offsetY * offsetY;
      if (distanceSquared < nearestDistanceSquared) {
        nearestDistanceSquared = distanceSquared;
        nearestSegment = index;
        nearestFraction = fraction;
      }
    }

    const interpolate = (first, second, fraction) => ({
      latitude: first.latitude + (second.latitude - first.latitude) * fraction,
      longitude: first.longitude + (second.longitude - first.longitude) * fraction,
    });
    const distance = (first, second) => {
      const radians = (degrees) => degrees * Math.PI / 180;
      const latitudeDelta = radians(second.latitude - first.latitude);
      const longitudeDelta = radians(second.longitude - first.longitude);
      const firstLatitude = radians(first.latitude);
      const secondLatitude = radians(second.latitude);
      const value = Math.sin(latitudeDelta / 2) ** 2
        + Math.cos(firstLatitude) * Math.cos(secondLatitude)
        * Math.sin(longitudeDelta / 2) ** 2;
      return 6371000 * 2 * Math.atan2(Math.sqrt(value), Math.sqrt(1 - value));
    };
    let remaining = distance(
      interpolate(points[nearestSegment], points[nearestSegment + 1], nearestFraction),
      points[nearestSegment + 1],
    );
    for (let index = nearestSegment + 1; index < points.length - 1; index += 1) {
      remaining += distance(points[index], points[index + 1]);
    }
    return remaining;
  };

  const routeForSelection = async (force = false) => {
    const booking = emergencies.find((item) => item.id === selectedBookingId);
    if (!booking) {
      removeRoute();
      routeStatusElement.textContent = "Select an active case to view its route.";
      return;
    }
    if (booking.status === "Patient Picked Up") {
      removeRoute();
      routeStatusElement.textContent =
        "Hospital route unavailable: no validated hospital location is configured.";
      return;
    }
    if (!booking.ambulance_id) {
      removeRoute();
      routeStatusElement.textContent =
        booking.suggested_ambulance
          ? `Unassigned. Nearest eligible suggestion: ${booking.suggested_ambulance.vehicle_number}.`
          : "Unassigned: no eligible ambulance with a recent GPS location.";
      return;
    }
    if (
      !hasCoordinates(booking.latitude, booking.longitude)
      || !hasCoordinates(booking.ambulance_latitude, booking.ambulance_longitude)
    ) {
      removeRoute();
      routeStatusElement.textContent = "Route unavailable: patient or ambulance GPS coordinates are missing.";
      return;
    }

    const from = [Number(booking.ambulance_latitude), Number(booking.ambulance_longitude)];
    const to = [Number(booking.latitude), Number(booking.longitude)];
    const key = `${booking.id}:${to.join(",")}`;
    const currentOrigin = { latitude: from[0], longitude: from[1] };
    if (
      !force
      && key === routeKey
      && routeOrigin
      && distanceMeters(routeOrigin, currentOrigin) < 250
      && Date.now() - lastRouteRequestAt < 90000
    ) {
      updateRouteProgress(booking);
      return;
    }
    if (key !== routeKey) {
      if (routeLayer) {
        map.removeLayer(routeLayer);
        routeLayer = null;
      }
      routeGeometry = null;
    }
    const requestId = ++routeRequestId;
    routeKey = key;
    routeOrigin = currentOrigin;
    lastRouteRequestAt = Date.now();
    routeStatusElement.textContent = booking.gps_stale
      ? "Driver GPS is stale. Showing route from the last recorded location…"
      : "Loading road route…";
    const controller = typeof AbortController === "undefined" ? null : new AbortController();
    const timeoutId = window.setTimeout(() => {
      if (controller) controller.abort();
    }, 10000);

    try {
      const url = `${routeUrl}${from[1]},${from[0]};${to[1]},${to[0]}?overview=full&geometries=geojson&steps=false`;
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
        throw new Error("The routing service returned invalid route data.");
      }
      if (routeLayer) map.removeLayer(routeLayer);
      routeLayer = L.geoJSON(route.geometry, {
        style: { color: "#1769aa", weight: 5, opacity: .82 },
      }).addTo(map);
      routeGeometry = route.geometry.coordinates;
      routeDistanceMeters = Number(route.distance);
      routeDurationSeconds = Number(route.duration);
      updateRouteProgress(booking);
    } catch (error) {
      if (requestId !== routeRequestId) return;
      if (routeLayer) {
        map.removeLayer(routeLayer);
        routeLayer = null;
      }
      routeGeometry = null;
      routeOrigin = currentOrigin;
      lastRouteRequestAt = Date.now();
      routeStatusElement.textContent = `Route unavailable: ${error.message}`;
    } finally {
      window.clearTimeout(timeoutId);
    }
  };

  const updateRouteProgress = (booking) => {
    if (!routeGeometry || !hasCoordinates(booking.ambulance_latitude, booking.ambulance_longitude)) {
      return;
    }
    const remainingMeters = remainingRouteDistance(
      routeGeometry,
      {
        latitude: Number(booking.ambulance_latitude),
        longitude: Number(booking.ambulance_longitude),
      },
    );
    if (remainingMeters === null) return;
    const distanceKm = (remainingMeters / 1000).toFixed(1);
    const remainingMinutes = routeDistanceMeters > 0
      ? Math.round(routeDurationSeconds * remainingMeters / routeDistanceMeters / 60)
      : 0;
    routeStatusElement.textContent =
      `Remaining road route: ${distanceKm} km · about ${remainingMinutes} min by OSRM estimate${booking.gps_stale ? " (last known GPS)" : ""}. Not traffic-aware.`;
  };

  function selectEmergency(bookingId, focusMap) {
    selectedBookingId = bookingId;
    renderEmergencyList();
    renderSelection();
    locations.forEach(updateAmbulanceMarker);
    emergencies.forEach(updatePatientMarker);
    const booking = emergencies.find((item) => item.id === bookingId);
    if (focusMap && booking) {
      if (booking.location_confirmed && hasCoordinates(booking.latitude, booking.longitude)) {
        map.setView([Number(booking.latitude), Number(booking.longitude)], 15);
      } else if (hasCoordinates(booking.ambulance_latitude, booking.ambulance_longitude)) {
        map.setView(
          [Number(booking.ambulance_latitude), Number(booking.ambulance_longitude)],
          14,
        );
      }
    }
    routeForSelection(true);
  }

  const updateStats = (stats) => {
    const values = {
      "stat-total": stats.total_ambulances,
      "stat-available": stats.available_ambulances,
      "stat-busy": stats.busy_ambulances,
      "stat-active": stats.active_emergencies,
      "stat-completed": stats.completed_today,
    };
    Object.entries(values).forEach(([id, value]) => {
      const element = document.getElementById(id);
      if (element && Number.isFinite(Number(value))) element.textContent = String(value);
    });
  };

  const mergeLocationUpdate = (location) => {
    const index = locations.findIndex((item) => item.id === location.id);
    if (index >= 0) locations[index] = { ...locations[index], ...location };
    else locations.push(location);
    updateAmbulanceMarker(locations.find((item) => item.id === location.id));
    const booking = emergencies.find(
      (item) => item.id === selectedBookingId && item.ambulance_id === location.id,
    );
    if (booking) {
      booking.ambulance_latitude = location.latitude;
      booking.ambulance_longitude = location.longitude;
      booking.last_location_update = location.updated_at;
      booking.gps_accuracy_meters = location.accuracy_meters;
      booking.booking_status = location.booking_status;
      booking.status = location.booking_status || booking.status;
      booking.gps_stale = Boolean(location.gps_stale);
      renderSelection();
      routeForSelection();
    }
  };

  const refresh = async () => {
    try {
      const response = await fetch(mapElement.dataset.locationsUrl, {
        headers: { Accept: "application/json" },
        cache: "no-store",
      });
      if (!response.ok) throw new Error(`Live dispatch data request failed (${response.status}).`);
      const data = await response.json();
      locations = Array.isArray(data.locations) ? data.locations : [];
      emergencies = Array.isArray(data.emergencies) ? data.emergencies : [];
      updateStats(data.stats || {});

      const ambulanceIds = new Set(locations.map((location) => location.id));
      ambulanceMarkers.forEach((marker, id) => {
        if (!ambulanceIds.has(id)) {
          map.removeLayer(marker);
          ambulanceMarkers.delete(id);
        }
      });
      const emergencyIds = new Set(emergencies.map((booking) => booking.id));
      patientMarkers.forEach((marker, id) => {
        if (!emergencyIds.has(id)) {
          map.removeLayer(marker);
          patientMarkers.delete(id);
        }
      });
      locations.forEach(updateAmbulanceMarker);
      emergencies.forEach(updatePatientMarker);
      if (selectedBookingId && !emergencyIds.has(selectedBookingId)) {
        selectedBookingId = null;
        removeRoute();
      }
      renderEmergencyList();
      renderSelection();
      if (!selectedBookingId && emergencies.length) {
        selectEmergency(emergencies[0].id, false);
      } else {
        routeForSelection();
      }
      const freshCount = locations.filter((location) => !location.gps_stale).length;
      statusElement.textContent =
        `${locations.length} ambulance(s) · ${freshCount} with recent GPS · updated ${new Date().toLocaleTimeString()}.`;
    } catch (error) {
      statusElement.textContent = `Unable to refresh live dispatch data: ${error.message}`;
    }
  };

  const connect = () => {
    const scheme = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${scheme}//${window.location.host}/ws/locations/`);
    socket.onopen = () => {
      statusElement.textContent = "Live GPS connection connected; refreshing case data every 5 seconds.";
    };
    socket.onmessage = (event) => {
      try {
        mergeLocationUpdate(JSON.parse(event.data));
      } catch (error) {
        statusElement.textContent = `Unable to read a live GPS update: ${error.message}`;
      }
    };
    socket.onclose = (event) => {
      if (event.code === 4403) {
        statusElement.textContent = "Live location access ended. Sign in again.";
        return;
      }
      statusElement.textContent = "Live GPS connection lost; polling continues while reconnecting…";
      window.setTimeout(connect, 5000);
    };
    socket.onerror = () => socket.close();
  };

  refresh();
  connect();
  window.setInterval(refresh, refreshInterval);
});
