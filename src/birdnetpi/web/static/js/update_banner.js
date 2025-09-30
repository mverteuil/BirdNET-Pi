/**
 * Update Banner JavaScript - Development and update banner management
 */

// Apply body class when development banner is present
function initDevelopmentBanner() {
  const devBanner = document.getElementById("development-banner");
  if (devBanner) {
    document.body.classList.add("has-development-banner");
  }
}

// Apply body class when update banner is present
function initUpdateBanner() {
  const updateBanner = document.getElementById("update-banner");
  if (updateBanner && !updateBanner.classList.contains("hidden")) {
    document.body.classList.add("has-update-banner");
  }
}

// Dismiss update banner function (global for onclick handler)
window.dismissUpdateBanner = function () {
  const banner = document.getElementById("update-banner");
  if (banner) {
    // Add animation
    banner.style.animation = "slideUp 0.3s ease-out forwards";

    // Remove after animation
    setTimeout(() => {
      banner.classList.add("hidden");
      document.body.classList.remove("has-update-banner");
    }, 300);

    // Store dismissal in session storage
    // Note: Version will be set from template via data attribute
    const version = banner.dataset.version || "";
    sessionStorage.setItem("update-banner-dismissed", "true");
    sessionStorage.setItem("update-banner-version", version);
  }
};

// Check if banner was previously dismissed for this version
function checkDismissalState() {
  const banner = document.getElementById("update-banner");
  if (!banner) return;

  const dismissed = sessionStorage.getItem("update-banner-dismissed");
  const dismissedVersion = sessionStorage.getItem("update-banner-version");
  const currentVersion = banner.dataset.version || "";

  if (dismissed === "true" && dismissedVersion === currentVersion) {
    banner.classList.add("hidden");
    document.body.classList.remove("has-update-banner");
  }
}

// Initialize on DOM content loaded
document.addEventListener("DOMContentLoaded", function () {
  initDevelopmentBanner();
  initUpdateBanner();
  checkDismissalState();
});
