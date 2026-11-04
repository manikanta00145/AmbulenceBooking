document.addEventListener("DOMContentLoaded", () => {
  const card = document.querySelector(".location-card");
  const status = document.getElementById("gps-status");
  const csrfToken = document.querySelector("#gps-csrf [name=csrfmiddlewaretoken]")?.value;
  if (!card || !status) return;
  if (!navigator.geolocation) {
    status.textContent = "This browser does not support GPS location sharing.";
    return;
  }

  let sending = false;
  const sendPosition = async (position) => {
    if (sending) return;
    sending = true;
    const payload = new URLSearchParams({
      latitude: position.coords.latitude.toString(),
      longitude: position.coords.longitude.toString(),
    });
    try {
      const response = await fetch(card.dataset.locationUrl, {
        method: "POST",
        headers: { "X-CSRFToken": csrfToken },
        body: payload,
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || `Location update failed (${response.status}).`);
      status.textContent = `Location shared at ${new Date(result.updated_at).toLocaleTimeString()}.`;
    } catch (error) {
      status.textContent = `GPS update failed: ${error.message}`;
    } finally {
      sending = false;
    }
  };

  navigator.geolocation.watchPosition(
    sendPosition,
    (error) => {
      status.textContent = `GPS unavailable: ${error.message}`;
    },
    { enableHighAccuracy: true, maximumAge: 10000, timeout: 15000 },
  );
  status.textContent = "Waiting for GPS permission and a location fix…";
});
