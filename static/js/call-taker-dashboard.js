document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("emergencyForm");
  const submitButton = document.getElementById("submitRequest");
  const toast = document.getElementById("toast");
  const sidebar = document.getElementById("workspaceSidebar");
  const menuToggle = document.querySelector(".menu-toggle");
  const addressInput = document.getElementById("id_location_address");
  const geocodeButton = document.getElementById("geocodeAddress");
  const geocodeStatus = document.getElementById("geocodeStatus");
  const locationMapElement = document.getElementById("patient-location-map");
  const latitudeInput = document.getElementById("id_latitude");
  const longitudeInput = document.getElementById("id_longitude");
  const locationConfirmed = document.getElementById("id_location_confirmed");
  let toastTimer;
  let locationMap;
  let patientMarker;

  const showToast = (message, isError = false) => {
    if (!toast || !message) return;
    toast.textContent = message;
    toast.classList.toggle("error", isError);
    toast.classList.add("show");
    window.clearTimeout(toastTimer);
    toastTimer = window.setTimeout(() => toast.classList.remove("show"), 3600);
  };

  document.querySelectorAll(".message").forEach((message) => {
    const dismiss = message.querySelector(".message-dismiss");
    if (dismiss) {
      dismiss.addEventListener("click", () => message.remove());
    }
    showToast(message.querySelector("span:nth-child(2)")?.textContent.trim());
  });

  document.querySelectorAll(".field-error").forEach((error) => {
    showToast(error.textContent.trim(), true);
  });

  document.querySelectorAll('a[href^="#"]').forEach((link) => {
    link.addEventListener("click", (event) => {
      const target = document.querySelector(link.getAttribute("href"));
      if (!target) return;
      event.preventDefault();
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      if (sidebar?.classList.contains("is-open")) {
        sidebar.classList.remove("is-open");
        menuToggle?.setAttribute("aria-expanded", "false");
      }
    });
  });

  menuToggle?.addEventListener("click", () => {
    const isOpen = sidebar.classList.toggle("is-open");
    menuToggle.setAttribute("aria-expanded", String(isOpen));
    menuToggle.setAttribute(
      "aria-label",
      isOpen ? "Close dashboard menu" : "Open dashboard menu",
    );
  });

  const setPatientLocation = (latitude, longitude, message) => {
    const lat = Number(latitude);
    const lon = Number(longitude);
    if (
      !Number.isFinite(lat) || lat < -90 || lat > 90
      || !Number.isFinite(lon) || lon < -180 || lon > 180
    ) {
      geocodeStatus.textContent = "Invalid coordinates. Select the location again.";
      showToast(geocodeStatus.textContent, true);
      return;
    }

    latitudeInput.value = lat.toFixed(7);
    longitudeInput.value = lon.toFixed(7);
    locationConfirmed.checked = false;
    const point = [lat, lon];
    if (!patientMarker) {
      patientMarker = window.L.marker(point, { draggable: true }).addTo(locationMap);
      patientMarker.on("dragend", () => {
        const moved = patientMarker.getLatLng();
        setPatientLocation(moved.lat, moved.lng, "Pin adjusted. Confirm the location before saving.");
      });
    } else {
      patientMarker.setLatLng(point);
    }
    locationMap.setView(point, 16);
    geocodeStatus.textContent = message;
  };

  const initializeLocationMap = () => {
    if (locationMap) return true;
    if (!window.L) {
      geocodeStatus.textContent = "The map library did not load. Reload the page or contact support.";
      return false;
    }
    locationMap = window.L.map(locationMapElement).setView([17.6868, 83.2185], 12);
    window.L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "&copy; OpenStreetMap contributors",
    }).addTo(locationMap);
    locationMap.on("click", (event) => {
      setPatientLocation(
        event.latlng.lat,
        event.latlng.lng,
        "Manual map pin selected. Confirm the location before saving.",
      );
    });
    return true;
  };

  initializeLocationMap();

  addressInput?.addEventListener("input", () => {
    latitudeInput.value = "";
    longitudeInput.value = "";
    locationConfirmed.checked = false;
    if (patientMarker) {
      locationMap.removeLayer(patientMarker);
      patientMarker = null;
    }
    geocodeStatus.textContent = "Address changed. Find it again or select a manual map pin.";
  });

  geocodeButton?.addEventListener("click", async () => {
    const address = addressInput.value.trim();
    if (!address) {
      geocodeStatus.textContent = "Enter a patient address before searching.";
      showToast(geocodeStatus.textContent, true);
      addressInput.focus();
      return;
    }
    if (!initializeLocationMap()) return;

    geocodeButton.disabled = true;
    geocodeStatus.textContent = "Looking up the address…";
    try {
      const csrfToken = form.querySelector('[name="csrfmiddlewaretoken"]').value;
      const body = new URLSearchParams({ address });
      const response = await fetch(form.dataset.geocodeUrl, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
          "X-CSRFToken": csrfToken,
        },
        body,
      });
      const result = await response.json();
      if (!response.ok || !result.ok) {
        throw new Error(result.error || `Address lookup failed (${response.status}).`);
      }
      setPatientLocation(
        result.latitude,
        result.longitude,
        `Address result: ${result.display_name}. Review the pin and confirm or adjust it.`,
      );
    } catch (error) {
      geocodeStatus.textContent = `${error.message} You can still select a pin manually.`;
      showToast(geocodeStatus.textContent, true);
    } finally {
      geocodeButton.disabled = false;
    }
  });

  if (form && submitButton) {
    form.addEventListener("submit", (event) => {
      if (!latitudeInput.value || !longitudeInput.value || !locationConfirmed.checked) {
        event.preventDefault();
        geocodeStatus.textContent =
          "Select a patient location and confirm it before saving the emergency.";
        showToast(geocodeStatus.textContent, true);
        locationConfirmed.focus();
        return;
      }
      if (!form.checkValidity()) {
        event.preventDefault();
        form.reportValidity();
        const firstInvalid = form.querySelector(":invalid");
        firstInvalid?.focus();
        showToast(
          firstInvalid?.validationMessage || "Please complete all required fields.",
          true,
        );
        return;
      }

      submitButton.disabled = true;
      submitButton.querySelector(".submit-label").textContent =
        "Submitting emergency request…";
    });
  }

  const navLinks = [...document.querySelectorAll(".side-nav .nav-link[href^='#']")];
  const observedSections = navLinks
    .map((link) => document.querySelector(link.getAttribute("href")))
    .filter(Boolean);

  if ("IntersectionObserver" in window && observedSections.length) {
    const sectionObserver = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((left, right) => right.intersectionRatio - left.intersectionRatio)[0];
        if (!visible) return;

        navLinks.forEach((link) => {
          const isActive = link.getAttribute("href") === `#${visible.target.id}`;
          link.classList.toggle("active", isActive);
          if (isActive) link.setAttribute("aria-current", "location");
          else link.removeAttribute("aria-current");
        });
      },
      { rootMargin: "-18% 0px -62% 0px", threshold: [0, 0.1, 0.35] },
    );

    observedSections.forEach((section) => sectionObserver.observe(section));
  }
});
