document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".message").forEach((message) => {
    window.setTimeout(() => message.remove(), 8000);
  });
});
