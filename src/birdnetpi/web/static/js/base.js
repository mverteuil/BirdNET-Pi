/**
 * Base JavaScript - Common functionality for all pages
 */

// Check system health status and update indicator
async function updateSystemHealthIndicator() {
  try {
    const response = await fetch("/api/health/detailed");
    const indicator = document.getElementById("system-health-indicator");

    if (!indicator) return;

    if (response.ok) {
      const data = await response.json();

      // Remove all state classes
      indicator.classList.remove("healthy", "warning", "unhealthy");

      // Apply appropriate class based on status
      if (data.status === "healthy") {
        indicator.classList.add("healthy");
        indicator.title = _("System Healthy");
      } else if (data.status === "degraded") {
        indicator.classList.add("warning");
        indicator.title = _("System Degraded - Some components unavailable");
      } else {
        indicator.classList.add("unhealthy");
        indicator.title = _("System Unhealthy");
      }
    } else {
      // API returned error status (503, etc.)
      indicator.classList.remove("healthy", "warning");
      indicator.classList.add("unhealthy");
      indicator.title = _("Health Check Failed");
    }
  } catch (error) {
    // Network error or API unavailable
    console.error("Failed to check system health:", error);
    const indicator = document.getElementById("system-health-indicator");
    if (indicator) {
      indicator.classList.remove("healthy", "warning");
      indicator.classList.add("unhealthy");
      indicator.title = _("Health Check Unavailable");
    }
  }
}

// Initialize on DOM content loaded
document.addEventListener("DOMContentLoaded", function () {
  // Check on load and every 2.5 minutes (150 seconds)
  updateSystemHealthIndicator();
  setInterval(updateSystemHealthIndicator, 150000);
});
