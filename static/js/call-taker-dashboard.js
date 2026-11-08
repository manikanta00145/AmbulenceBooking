document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("emergencyForm");
  const submitButton = document.getElementById("submitRequest");
  const toast = document.getElementById("toast");
  const sidebar = document.getElementById("workspaceSidebar");
  const menuToggle = document.querySelector(".menu-toggle");
  let toastTimer;

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

  if (form && submitButton) {
    form.addEventListener("submit", (event) => {
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
