document.addEventListener("DOMContentLoaded", () => {
  const successCard = document.querySelector("[data-registration-success]");
  if (!successCard) return;

  const redirectUrl = successCard.dataset.redirectUrl;
  if (redirectUrl) {
    window.setTimeout(() => window.location.assign(redirectUrl), 2000);
  }
});
