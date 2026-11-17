document.addEventListener("DOMContentLoaded", () => {
  const tracker = document.querySelector("[data-gps-tracker]");
  if (!tracker) return;

  const startButton = tracker.querySelector("[data-gps-start]");
  const pauseButton = tracker.querySelector("[data-gps-pause]");
  const stopButton = tracker.querySelector("[data-gps-stop]");
  const csrfToken = tracker.querySelector("[data-gps-csrf] [name=csrfmiddlewaretoken]")?.value;
  const staleAfterMs = Number(tracker.dataset.gpsStaleAfterSeconds || 300) * 1000;
  const minIntervalMs = Number(tracker.dataset.gpsMinIntervalMs || 5000);
  const minMovementMeters = Number(tracker.dataset.gpsMinMovementMeters || 15);
  const heartbeatMs = Number(tracker.dataset.gpsHeartbeatMs || 60000);
  const bookingId = tracker.dataset.bookingId || "";
  const values = {};
  tracker.querySelectorAll("[data-gps-value]").forEach((element) => {
    values[element.dataset.gpsValue] = element;
  });

  let watchId = null;
  let retryTimer = null;
  let heartbeatTimer = null;
  let inFlight = false;
  let queuedPosition = null;
  let latestPosition = null;
  let lastServerTimestamp = Date.parse(tracker.dataset.gpsLastUpdated || "") || null;
  let lastServerLatitude = Number(tracker.dataset.gpsLatitude);
  let lastServerLongitude = Number(tracker.dataset.gpsLongitude);
  let deviceFixTimestamp = lastServerTimestamp;
  let trackingState = "Stopped";

  const setValue = (name, value, state) => {
    const element = values[name];
    if (!element) return;
    element.textContent = value;
    if (state) element.dataset.state = state;
    else delete element.dataset.state;
  };
  const setMessage = (message) => {
    const element = tracker.querySelector("[data-gps-message]");
    if (element) element.textContent = message;
  };
  const formatTime = (timestamp) => {
    if (!timestamp) return "No update";
    return new Date(timestamp).toLocaleString();
  };
  const dispatchPosition = (position) => {
    window.dispatchEvent(new CustomEvent("driver:gps-position", {
      detail: {
        latitude: position.coords.latitude,
        longitude: position.coords.longitude,
        accuracy: position.coords.accuracy,
        timestamp: position.timestamp,
      },
    }));
  };
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
  const setTracking = (state) => {
    trackingState = state;
    setValue("tracking", state, state === "Running" ? "good" : "");
    if (startButton) {
      startButton.hidden = state === "Running";
      startButton.textContent = state === "Paused"
        ? "Resume GPS sharing"
        : startButton.dataset.startLabel || "Start GPS sharing";
    }
    if (pauseButton) pauseButton.hidden = state !== "Running";
    if (stopButton) stopButton.hidden = state === "Stopped";
  };
  const updateFreshness = () => {
    const age = deviceFixTimestamp ? Date.now() - deviceFixTimestamp : Infinity;
    const fresh = age <= staleAfterMs;
    setValue(
      "freshness",
      fresh ? "Fresh" : deviceFixTimestamp ? "Stale GPS warning" : "No current fix",
      fresh ? "good" : "warning",
    );
    if (!fresh && deviceFixTimestamp && trackingState === "Running") {
      setValue("device", "Unavailable", "warning");
    }
  };
  const scheduleRetry = (delay) => {
    window.clearTimeout(retryTimer);
    retryTimer = window.setTimeout(attemptSync, Math.max(100, delay));
  };

  const attemptSync = async () => {
    if (!queuedPosition || trackingState !== "Running" || inFlight) return;
    if (Date.now() - queuedPosition.timestamp > staleAfterMs) {
      queuedPosition = null;
      setValue("freshness", "Stale GPS warning", "warning");
      setValue("sync", "Failed (GPS fix is stale)", "warning");
      return;
    }
    if (!navigator.onLine) {
      setValue("network", "Offline", "warning");
      setValue("sync", "Pending", "warning");
      return;
    }

    const now = Date.now();
    const elapsed = lastServerTimestamp ? now - lastServerTimestamp : Infinity;
    const lastServerPosition = Number.isFinite(lastServerLatitude)
      && Number.isFinite(lastServerLongitude)
      ? { latitude: lastServerLatitude, longitude: lastServerLongitude }
      : null;
    const movement = distanceMeters(lastServerPosition, {
      latitude: queuedPosition.coords.latitude,
      longitude: queuedPosition.coords.longitude,
    });

    if (elapsed < minIntervalMs) {
      setValue("sync", "Pending (rate limit)", "warning");
      scheduleRetry(minIntervalMs - elapsed);
      return;
    }
    if (movement < minMovementMeters && elapsed < heartbeatMs) {
      setValue("sync", "Waiting for movement/heartbeat", "warning");
      scheduleRetry(heartbeatMs - elapsed);
      return;
    }

    inFlight = true;
    const sentPosition = queuedPosition;
    setValue("sync", "Pending", "warning");
    const payload = new URLSearchParams({
      latitude: sentPosition.coords.latitude.toString(),
      longitude: sentPosition.coords.longitude.toString(),
      accuracy_meters: sentPosition.coords.accuracy.toString(),
      observed_at: sentPosition.timestamp.toString(),
    });
    if (bookingId) payload.set("booking_id", bookingId);

    try {
      const response = await fetch(tracker.dataset.locationUrl, {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "X-CSRFToken": csrfToken || "",
          "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
        },
        body: payload,
      });
      const contentType = response.headers.get("content-type") || "";
      if (!contentType.includes("application/json")) {
        const error = new Error(`Location endpoint returned a non-JSON response (${response.status}).`);
        error.fatal = true;
        throw error;
      }
      const result = await response.json();
      if (!response.ok) {
        const error = new Error(result.error || `Location update failed (${response.status}).`);
        error.fatal = response.status === 400 || response.status === 403 || response.status === 404;
        throw error;
      }

      lastServerTimestamp = Date.parse(result.updated_at) || Date.now();
      lastServerLatitude = Number(result.latitude);
      lastServerLongitude = Number(result.longitude);
      setValue("last-update", formatTime(lastServerTimestamp));
      setValue(
        "sync",
        result.updated ? "Synced" : "Skipped (server rate limit)",
        result.updated ? "good" : "warning",
      );
      if (queuedPosition === sentPosition) queuedPosition = null;
    } catch (error) {
      setValue("sync", "Failed", "warning");
      setMessage(`GPS update failed: ${error.message}`);
      if (error.fatal) {
        if (watchId !== null && navigator.geolocation) navigator.geolocation.clearWatch(watchId);
        watchId = null;
        queuedPosition = null;
        setTracking("Stopped");
      }
    } finally {
      inFlight = false;
      if (queuedPosition && trackingState === "Running" && navigator.onLine) {
        scheduleRetry(minIntervalMs);
      }
    }
  };

  const onPosition = (position) => {
    deviceFixTimestamp = position.timestamp || Date.now();
    latestPosition = position;
    setValue("device", "Available", "good");
    setValue("accuracy", `${Math.round(position.coords.accuracy)} m`);
    setValue("freshness", "Fresh", "good");
    setValue("permission", "Granted", "good");
    if (bookingId && tracker.dataset.bookingStatus !== "Arrived") {
      setValue("navigation", "Active", "good");
    }
    setValue("network", navigator.onLine ? "Online" : "Offline", navigator.onLine ? "good" : "warning");
    queuedPosition = position;
    dispatchPosition(position);
    setValue("sync", navigator.onLine ? "Pending" : "Pending (offline)", "warning");
    attemptSync();
  };

  const onPositionError = (error) => {
    if (error.code === 1) {
      setValue("permission", "Denied", "warning");
      setValue("device", "Unavailable", "warning");
      latestPosition = null;
      queuedPosition = null;
      window.clearTimeout(retryTimer);
      window.clearInterval(heartbeatTimer);
      setMessage("Location permission was denied. Allow location access in your browser settings, then try again.");
      if (watchId !== null) navigator.geolocation.clearWatch(watchId);
      watchId = null;
      setTracking("Stopped");
      return;
    }
    latestPosition = null;
    queuedPosition = null;
    window.clearTimeout(retryTimer);
    setValue("device", "Unavailable", "warning");
    setValue("freshness", "GPS unavailable", "warning");
    setValue("sync", "Failed (GPS unavailable)", "warning");
    setMessage(error.code === 3
      ? "GPS location timed out. Keep location services enabled while the browser retries."
      : "The device could not determine a GPS location. Check location services and signal.");
  };

  const startTracking = () => {
    if (!navigator.geolocation) {
      setValue("device", "Unsupported", "warning");
      setMessage("This browser does not support GPS location sharing.");
      return;
    }
    latestPosition = null;
    queuedPosition = null;
    setValue("permission", "Requested");
    setMessage("Waiting for location permission and a GPS fix…");
    setTracking("Running");
    try {
      watchId = navigator.geolocation.watchPosition(
        onPosition,
        onPositionError,
        { enableHighAccuracy: true, maximumAge: 0, timeout: 20000 },
      );
      window.clearInterval(heartbeatTimer);
      heartbeatTimer = window.setInterval(() => {
        if (
          latestPosition
          && Date.now() - latestPosition.timestamp <= staleAfterMs
        ) {
          queuedPosition = latestPosition;
          attemptSync();
        }
      }, heartbeatMs);
    } catch (error) {
      setTracking("Stopped");
      setValue("device", "Unavailable", "warning");
      setMessage(`Could not start GPS tracking: ${error.message}`);
    }
  };

  if (startButton) startButton.addEventListener("click", startTracking);
  if (pauseButton) {
    pauseButton.addEventListener("click", () => {
      if (watchId !== null) navigator.geolocation.clearWatch(watchId);
      watchId = null;
      window.clearTimeout(retryTimer);
      window.clearInterval(heartbeatTimer);
      setTracking("Paused");
      setValue("sync", queuedPosition ? "Pending" : "Idle", queuedPosition ? "warning" : "");
      setMessage("GPS sharing is paused. Resume only when you are ready to share your location again.");
    });
  }
  if (stopButton) {
    stopButton.addEventListener("click", () => {
      if (watchId !== null && navigator.geolocation) navigator.geolocation.clearWatch(watchId);
      watchId = null;
      window.clearTimeout(retryTimer);
      window.clearInterval(heartbeatTimer);
      queuedPosition = null;
      latestPosition = null;
      setTracking("Stopped");
      setValue("sync", "Idle");
      setMessage("GPS sharing is stopped. Start it again when you are ready.");
    });
  }
  window.addEventListener("online", () => {
    setValue("network", "Online", "good");
    if (queuedPosition) attemptSync();
  });
  window.addEventListener("offline", () => {
    setValue("network", "Offline", "warning");
    if (trackingState === "Running") setValue("sync", "Pending (offline)", "warning");
  });
  window.addEventListener("pagehide", () => {
    if (watchId !== null && navigator.geolocation) navigator.geolocation.clearWatch(watchId);
    window.clearTimeout(retryTimer);
    window.clearInterval(heartbeatTimer);
  });

  setValue("network", navigator.onLine ? "Online" : "Offline", navigator.onLine ? "good" : "warning");
  if (lastServerTimestamp) {
    setValue("last-update", formatTime(lastServerTimestamp));
    setValue("device", Date.now() - lastServerTimestamp <= staleAfterMs ? "Available" : "Stale", Date.now() - lastServerTimestamp <= staleAfterMs ? "good" : "warning");
  }
  if (navigator.permissions?.query) {
    navigator.permissions.query({ name: "geolocation" }).then((permission) => {
      const state = permission.state;
      setValue("permission", state === "prompt" ? "Not requested" : state === "granted" ? "Granted" : "Denied");
      permission.addEventListener("change", () => {
        setValue("permission", permission.state === "granted" ? "Granted" : permission.state === "denied" ? "Denied" : "Not requested");
      });
    }).catch(() => {
      setValue("permission", "Check browser prompt");
    });
  }
  updateFreshness();
  window.setInterval(updateFreshness, 1000);
});
