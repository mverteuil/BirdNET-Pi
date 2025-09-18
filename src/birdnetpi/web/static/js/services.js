/**
 * Service status management with accessibility support
 */

(function () {
  "use strict";

  // State management
  let refreshInterval = null;
  let pendingAction = null;

  // Configuration
  const REFRESH_INTERVAL = 10000; // 10 seconds
  const CRITICAL_SERVICES = {
    fastapi:
      "The web interface will be temporarily unavailable. If settings are misconfigured, you may lose the ability to access the interface.",
    "birdnetpi-fastapi":
      "The web interface will be temporarily unavailable. If settings are misconfigured, you may lose the ability to access the interface.",
    caddy:
      "The web server will restart. All HTTP/HTTPS traffic will be briefly interrupted.",
  };

  /**
   * Initialize the services page
   */
  function init() {
    setupEventListeners();
    setupKeyboardShortcuts();
    startAutoRefresh();

    // Announce page load to screen readers
    announceStatus("Services page loaded");
  }

  /**
   * Setup event listeners for all interactive elements
   */
  function setupEventListeners() {
    // Service action buttons
    document.querySelectorAll(".service-action-btn").forEach((button) => {
      button.addEventListener("click", handleServiceAction);
    });

    // System buttons
    const refreshBtn = document.getElementById("refresh-status-btn");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", refreshAllStatuses);
    }

    const reloadConfigBtn = document.getElementById("reload-config-btn");
    if (reloadConfigBtn) {
      reloadConfigBtn.addEventListener("click", reloadConfiguration);
    }

    const rebootBtn = document.getElementById("reboot-system-btn");
    if (rebootBtn) {
      rebootBtn.addEventListener("click", showRebootModal);
    }

    // Modal confirm buttons
    const confirmActionBtn = document.getElementById("confirmActionBtn");
    if (confirmActionBtn) {
      confirmActionBtn.addEventListener("click", executePendingAction);
    }

    const confirmRebootBtn = document.getElementById("confirmRebootBtn");
    if (confirmRebootBtn) {
      confirmRebootBtn.addEventListener("click", executeReboot);
    }

    // Modal close buttons
    document
      .querySelectorAll(
        '.modal .close, .modal .btn-secondary[data-dismiss="modal"]',
      )
      .forEach((button) => {
        button.addEventListener("click", closeAllModals);
      });

    // Close modal when clicking outside
    document.querySelectorAll(".modal").forEach((modal) => {
      modal.addEventListener("click", (e) => {
        if (e.target === modal) {
          closeAllModals();
        }
      });
    });
  }

  /**
   * Setup keyboard shortcuts for accessibility
   */
  function setupKeyboardShortcuts() {
    document.addEventListener("keydown", (e) => {
      // Alt+R for refresh
      if (e.altKey && e.key === "r") {
        e.preventDefault();
        refreshAllStatuses();
      }
      // Alt+C for config reload
      if (e.altKey && e.key === "c") {
        e.preventDefault();
        reloadConfiguration();
      }
      // Escape to close modals
      if (e.key === "Escape") {
        closeAllModals();
      }
    });
  }

  /**
   * Start automatic status refresh
   */
  function startAutoRefresh() {
    refreshInterval = setInterval(refreshAllStatuses, REFRESH_INTERVAL);
  }

  /**
   * Stop automatic status refresh
   */
  function stopAutoRefresh() {
    if (refreshInterval) {
      clearInterval(refreshInterval);
      refreshInterval = null;
    }
  }

  /**
   * Handle service action button clicks
   */
  function handleServiceAction(event) {
    const button = event.currentTarget;
    const action = button.dataset.action;
    const serviceName = button.dataset.service;
    const serviceCard = button.closest(".service-card");
    const isCritical = serviceCard.dataset.serviceCritical === "true";

    // Store pending action
    pendingAction = { action, serviceName, button };

    // Show confirmation for critical services
    if (isCritical && (action === "restart" || action === "stop")) {
      showCriticalServiceModal(serviceName, action);
    } else {
      executePendingAction();
    }
  }

  /**
   * Show confirmation modal for critical service actions
   */
  function showCriticalServiceModal(serviceName, action) {
    const modal = document.getElementById("confirmModal");
    const modalBody = document.getElementById("confirmModalBody");

    if (!modal) return;

    // Build warning message
    let warningHtml = `
            <p>You are about to <strong>${action}</strong> the critical service: <strong>${serviceName}</strong></p>
        `;

    if (CRITICAL_SERVICES[serviceName]) {
      warningHtml += `
                <div class="alert alert-warning" role="alert">
                    <h6><i class="fas fa-exclamation-triangle"></i> Warning:</h6>
                    <p>${CRITICAL_SERVICES[serviceName]}</p>
                </div>
            `;
    }

    warningHtml += `<p>Are you sure you want to proceed?</p>`;
    modalBody.innerHTML = warningHtml;

    // Show modal using our custom CSS
    modal.classList.add("show");
    modal.style.display = "flex";

    // Focus on cancel button for safety
    setTimeout(() => {
      const cancelBtn = modal.querySelector(".btn-secondary");
      if (cancelBtn) cancelBtn.focus();
    }, 100);
  }

  /**
   * Execute the pending service action
   */
  async function executePendingAction() {
    if (!pendingAction) return;

    const { action, serviceName, button } = pendingAction;

    // Close modal if open
    closeAllModals();

    // Disable button and show loading state
    button.disabled = true;
    const originalHtml = button.innerHTML;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Processing...';

    try {
      const response = await fetch(
        `/api/system/services/${serviceName}/${action}`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ confirm: true }),
        },
      );

      const data = await response.json();

      if (data.success) {
        announceStatus(`Service ${serviceName} ${action}ed successfully`);
        showToast("success", data.message);

        // Refresh status after a short delay
        setTimeout(() => refreshServiceStatus(serviceName), 1000);
      } else {
        throw new Error(data.error || data.message);
      }
    } catch (error) {
      console.error("Service action failed:", error);
      showToast(
        "error",
        `Failed to ${action} ${serviceName}: ${error.message}`,
      );
      announceStatus(`Failed to ${action} service ${serviceName}`);
    } finally {
      // Restore button state
      button.disabled = false;
      button.innerHTML = originalHtml;
      pendingAction = null;
    }
  }

  /**
   * Reload service configuration
   */
  async function reloadConfiguration() {
    const button = document.getElementById("reload-config-btn");
    button.disabled = true;
    const originalHtml = button.innerHTML;
    button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Reloading...';

    try {
      const response = await fetch("/api/system/services/reload-config", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
      });

      const data = await response.json();

      if (data.success) {
        announceStatus("Configuration reloaded successfully");
        showToast("success", data.message);

        if (data.services_affected && data.services_affected.length > 0) {
          showToast(
            "info",
            `Services affected: ${data.services_affected.join(", ")}`,
          );
        }

        // Refresh all statuses
        setTimeout(refreshAllStatuses, 500);
      } else {
        throw new Error(data.error || data.message);
      }
    } catch (error) {
      console.error("Config reload failed:", error);
      showToast("error", `Failed to reload configuration: ${error.message}`);
      announceStatus("Failed to reload configuration");
    } finally {
      button.disabled = false;
      button.innerHTML = originalHtml;
    }
  }

  /**
   * Show reboot confirmation modal
   */
  function showRebootModal() {
    const modal = document.getElementById("rebootModal");
    if (!modal) return;

    // Show modal using our custom CSS
    modal.classList.add("show");
    modal.style.display = "flex";

    // Focus on cancel button for safety
    setTimeout(() => {
      const cancelBtn = modal.querySelector(".btn-secondary");
      if (cancelBtn) cancelBtn.focus();
    }, 100);
  }

  /**
   * Execute system reboot
   */
  async function executeReboot() {
    const button = document.getElementById("confirmRebootBtn");
    button.disabled = true;
    button.innerHTML =
      '<i class="fas fa-spinner fa-spin"></i> Initiating reboot...';

    try {
      const response = await fetch("/api/system/services/reboot", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ confirm: true }),
      });

      const data = await response.json();

      if (data.success && data.reboot_initiated) {
        $("#rebootModal").modal("hide");
        showToast("warning", data.message);
        announceStatus("System reboot initiated");

        // Stop auto-refresh during reboot
        stopAutoRefresh();

        // Show countdown overlay
        showRebootCountdown();
      } else {
        throw new Error(data.error || data.message || "Reboot not available");
      }
    } catch (error) {
      console.error("Reboot failed:", error);
      showToast("error", `Failed to reboot: ${error.message}`);
      button.disabled = false;
      button.innerHTML = '<i class="fas fa-power-off"></i> Reboot System';
    }
  }

  /**
   * Show reboot countdown overlay
   */
  function showRebootCountdown() {
    const overlay = document.createElement("div");
    overlay.className = "reboot-overlay";
    overlay.setAttribute("role", "alert");
    overlay.setAttribute("aria-live", "assertive");
    overlay.innerHTML = `
            <div class="reboot-message">
                <i class="fas fa-power-off fa-3x mb-3"></i>
                <h2>System is rebooting...</h2>
                <p>The page will automatically reload when the system is back online.</p>
                <div class="spinner-border text-light mt-3" role="status">
                    <span class="sr-only">Waiting for system...</span>
                </div>
            </div>
        `;
    document.body.appendChild(overlay);

    // Start checking for system availability
    setTimeout(() => checkSystemAvailability(), 10000);
  }

  /**
   * Check if system is back online after reboot
   */
  async function checkSystemAvailability() {
    try {
      const response = await fetch("/api/system/services/info", {
        method: "GET",
        signal: AbortSignal.timeout(5000),
      });

      if (response.ok) {
        // System is back, reload page
        window.location.reload();
      } else {
        // Not ready yet, check again
        setTimeout(() => checkSystemAvailability(), 5000);
      }
    } catch {
      // Network error, system not ready
      setTimeout(() => checkSystemAvailability(), 5000);
    }
  }

  /**
   * Refresh all service statuses
   */
  async function refreshAllStatuses() {
    const refreshBtn = document.getElementById("refresh-status-btn");
    const originalHtml = refreshBtn ? refreshBtn.innerHTML : "";

    try {
      // Show loading state
      if (refreshBtn) {
        refreshBtn.disabled = true;
        refreshBtn.innerHTML =
          '<i class="fas fa-spinner fa-spin"></i> Refreshing...';
      }

      const response = await fetch("/api/system/services/status");
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const data = await response.json();
      console.log("Refresh data received:", data);

      // Update service cards
      if (data.services && Array.isArray(data.services)) {
        data.services.forEach((service) => {
          updateServiceCard(service);
        });
      }

      // Update system info
      if (data.system) {
        updateSystemInfo(data.system);
      }

      announceStatus("Service statuses refreshed");
      showToast("success", "Status refreshed successfully");
    } catch (error) {
      console.error("Failed to refresh statuses:", error);
      showToast("error", "Failed to refresh service statuses");
    } finally {
      // Restore button state
      if (refreshBtn) {
        refreshBtn.disabled = false;
        refreshBtn.innerHTML = originalHtml;
      }
    }
  }

  /**
   * Refresh a single service status
   */
  async function refreshServiceStatus(serviceName) {
    try {
      const response = await fetch("/api/system/services/status");
      const data = await response.json();

      const service = data.services.find((s) => s.name === serviceName);
      if (service) {
        updateServiceCard(service);
      }
    } catch (error) {
      console.error(`Failed to refresh status for ${serviceName}:`, error);
    }
  }

  /**
   * Update a service card with new status
   */
  function updateServiceCard(service) {
    const card = document.querySelector(
      `[data-service-name="${service.name}"]`,
    );
    if (!card) return;

    // Update status indicator
    const statusDiv = card.querySelector(".service-status");
    if (statusDiv) {
      statusDiv.className = `service-status status-${service.status}`;
      statusDiv.setAttribute("aria-label", `Service status: ${service.status}`);

      let statusHtml = "";
      switch (service.status) {
        case "active":
          statusHtml =
            '<i class="fas fa-circle text-success"></i> <span>Running</span>';
          break;
        case "inactive":
          statusHtml =
            '<i class="fas fa-circle text-secondary"></i> <span>Stopped</span>';
          break;
        case "starting":
          statusHtml =
            '<i class="fas fa-spinner fa-spin text-info"></i> <span>Starting</span>';
          break;
        case "failed":
          statusHtml =
            '<i class="fas fa-times-circle text-danger"></i> <span>Failed</span>';
          break;
        default:
          statusHtml =
            '<i class="fas fa-question-circle text-muted"></i> <span>Unknown</span>';
      }
      statusDiv.innerHTML = statusHtml;
    }

    // Update PID
    let pidRow = null;
    const detailRows = card.querySelectorAll(".detail-row");
    detailRows.forEach((row) => {
      const label = row.querySelector(".detail-label");
      if (label && label.textContent.includes("PID")) {
        pidRow = row;
      }
    });

    if (service.pid) {
      if (pidRow) {
        pidRow.querySelector(".detail-value").textContent = service.pid;
      } else {
        // Create PID row if it doesn't exist
        const detailsDiv = card.querySelector(".service-details");
        if (detailsDiv) {
          const newPidRow = document.createElement("div");
          newPidRow.className = "detail-row";
          newPidRow.innerHTML = `
                        <span class="detail-label">PID:</span>
                        <span class="detail-value">${service.pid}</span>
                    `;
          detailsDiv.appendChild(newPidRow);
        }
      }
    } else if (pidRow) {
      pidRow.remove();
    }

    // Update uptime
    let uptimeRow = null;
    detailRows.forEach((row) => {
      const value = row.querySelector(".service-uptime");
      if (value) {
        uptimeRow = value;
      }
    });

    if (uptimeRow && service.uptime_formatted) {
      uptimeRow.textContent = service.uptime_formatted;
    } else if (service.uptime_formatted && service.status === "active") {
      // Create uptime row if service is active and has uptime
      const detailsDiv = card.querySelector(".service-details");
      if (detailsDiv && !uptimeRow) {
        const newUptimeRow = document.createElement("div");
        newUptimeRow.className = "detail-row";
        newUptimeRow.innerHTML = `
                    <span class="detail-label">Uptime:</span>
                    <span class="detail-value service-uptime">${service.uptime_formatted}</span>
                `;
        detailsDiv.appendChild(newUptimeRow);
      }
    }

    // Update action buttons
    updateServiceActions(card, service);
  }

  /**
   * Update service action buttons based on status
   */
  function updateServiceActions(card, service) {
    const actionsDiv = card.querySelector(".service-actions");
    if (!actionsDiv) return;

    // Skip if service is unavailable
    if (service.optional && service.status === "error") {
      actionsDiv.innerHTML =
        '<span class="text-muted">Service not available</span>';
      return;
    }

    let actionsHtml = "";
    if (service.status === "active") {
      actionsHtml = `
                <button type="button" class="btn btn-sm btn-warning service-action-btn"
                    data-action="restart" data-service="${service.name}"
                    aria-label="Restart ${service.name}">
                    <i class="fas fa-redo"></i> Restart
                </button>
                <button type="button" class="btn btn-sm btn-danger service-action-btn"
                    data-action="stop" data-service="${service.name}"
                    aria-label="Stop ${service.name}">
                    <i class="fas fa-stop"></i> Stop
                </button>
            `;
    } else {
      actionsHtml = `
                <button type="button" class="btn btn-sm btn-success service-action-btn"
                    data-action="start" data-service="${service.name}"
                    aria-label="Start ${service.name}">
                    <i class="fas fa-play"></i> Start
                </button>
            `;
    }

    actionsDiv.innerHTML = actionsHtml;

    // Re-attach event listeners
    actionsDiv.querySelectorAll(".service-action-btn").forEach((button) => {
      button.addEventListener("click", handleServiceAction);
    });
  }

  /**
   * Update system information display
   */
  function updateSystemInfo(systemInfo) {
    console.log("Updating system info:", systemInfo);

    // Update uptime
    const uptimeElement = document.getElementById("system-uptime");
    if (uptimeElement && systemInfo.uptime_formatted) {
      uptimeElement.textContent = systemInfo.uptime_formatted;
    }

    // Update deployment type if element exists
    const deploymentElement = document.querySelector(".info-value");
    if (deploymentElement && systemInfo.deployment_type) {
      // Update the deployment type icon and text if needed
      const deploymentType = systemInfo.deployment_type;
      let iconClass = "fas fa-question";
      let displayText = "Unknown";

      if (deploymentType === "docker") {
        iconClass = "fab fa-docker";
        displayText = "Docker Container";
      } else if (deploymentType === "sbc") {
        iconClass = "fas fa-microchip";
        displayText = "Single Board Computer";
      }

      // Only update if changed
      const currentIcon = deploymentElement.querySelector("i");
      if (
        currentIcon &&
        !currentIcon.classList.contains(iconClass.split(" ")[1])
      ) {
        deploymentElement.innerHTML = `<i class="${iconClass}" aria-hidden="true"></i> ${displayText}`;
      }
    }
  }

  /**
   * Close all modals
   */
  function closeAllModals() {
    document.querySelectorAll(".modal").forEach((modal) => {
      modal.classList.remove("show");
      modal.style.display = "none";
    });
    pendingAction = null;
  }

  /**
   * Show toast notification
   */
  function showToast(type, message) {
    // You can implement a toast library here or use a simple alert
    console.log(`[${type.toUpperCase()}] ${message}`);

    // For now, using console and updating status message
    const statusDiv = document.getElementById("status-message");
    if (statusDiv) {
      statusDiv.textContent = message;
    }
  }

  /**
   * Announce status to screen readers
   */
  function announceStatus(message) {
    const statusDiv = document.getElementById("status-message");
    if (statusDiv) {
      statusDiv.textContent = message;
    }
  }

  // Initialize when DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
