/**
 * Log Viewer JavaScript with SSE Streaming
 */

// Global state
let eventSource = null;
let logs = [];
let filteredLogs = []; // Logs after client-side filtering
let isStreaming = false;
let logLevels = {};

// Log level configuration with colorblind-safe colors
const LOG_LEVEL_CONFIG = {
  DEBUG: { value: 10, color: "#6c757d", symbol: "○" },
  INFO: { value: 20, color: "#0066cc", symbol: "●" },
  WARNING: { value: 30, color: "#ff9900", symbol: "●" },
  ERROR: { value: 40, color: "#9933ff", symbol: "●" },
  CRITICAL: { value: 50, color: "#330066", symbol: "●" },
};

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  initializeEventListeners();
  loadLogLevels();
  setDefaultTimeRange();
  updateEmptyState();
});

/**
 * Initialize all event listeners
 */
function initializeEventListeners() {
  // Prevent form submission on Enter key
  document.getElementById("log-filters").addEventListener("submit", (e) => {
    e.preventDefault();
    return false;
  });

  // Fetch logs button
  document.getElementById("fetch-logs").addEventListener("click", fetchLogs);

  // Stream toggle button
  document
    .getElementById("stream-toggle")
    .addEventListener("click", toggleStreaming);

  // View mode toggle
  document.querySelectorAll('input[name="view-mode"]').forEach((radio) => {
    radio.addEventListener("change", toggleViewMode);
  });

  // Download logs button
  document
    .getElementById("download-logs")
    .addEventListener("click", downloadLogs);

  // Clear display button
  document
    .getElementById("clear-display")
    .addEventListener("click", clearDisplay);

  // Keyboard shortcuts
  document.addEventListener("keydown", handleKeyboardShortcuts);

  // Client-side search filtering (with debounce)
  let searchTimeout;
  document.getElementById("keyword").addEventListener("input", (e) => {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
      applyClientSideFilter();
    }, 300); // 300ms debounce
  });

  // Apply filter immediately on Enter key in search box
  document.getElementById("keyword").addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault(); // Prevent form submission
      clearTimeout(searchTimeout);
      applyClientSideFilter();
    }
  });

  // Service checkbox filtering
  document.querySelectorAll(".service-checkbox").forEach((checkbox) => {
    checkbox.addEventListener("change", () => {
      applyClientSideFilter();
    });
  });

  // Log level filtering
  document.getElementById("log-level").addEventListener("change", () => {
    applyClientSideFilter();
  });
}

/**
 * Load log levels from API
 */
async function loadLogLevels() {
  try {
    const response = await fetch("/api/logs/levels");
    const levels = await response.json();
    levels.forEach((level) => {
      logLevels[level.name] = level;
    });
  } catch (error) {
    console.error("Failed to load log levels:", error);
    // Use defaults
    logLevels = LOG_LEVEL_CONFIG;
  }
}

/**
 * Set default time range (last 24 hours)
 */
function setDefaultTimeRange() {
  const startTime = document.getElementById("start-time");
  const endTime = document.getElementById("end-time");

  // Only set defaults if fields are empty
  if (!startTime.value && !endTime.value) {
    const now = new Date();
    const yesterday = new Date(now.getTime() - 24 * 60 * 60 * 1000);

    // Format for datetime-local input (YYYY-MM-DDTHH:mm)
    const formatDateTime = (date) => {
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, "0");
      const day = String(date.getDate()).padStart(2, "0");
      const hours = String(date.getHours()).padStart(2, "0");
      const minutes = String(date.getMinutes()).padStart(2, "0");
      return `${year}-${month}-${day}T${hours}:${minutes}`;
    };

    startTime.value = formatDateTime(yesterday);
    endTime.value = formatDateTime(now);
  }
}

/**
 * Fetch historical logs
 */
async function fetchLogs() {
  const params = buildQueryParams();

  try {
    console.log("Fetching logs with params:", params.toString());
    const response = await fetch(`/api/logs?${params.toString()}`);

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();
    console.log("Received data:", data);

    if (data.error) {
      showError(data.error);
      return;
    }

    // Replace current logs
    logs = data.logs || [];
    console.log("Loaded", logs.length, "logs");

    // Apply any existing client-side filter
    applyClientSideFilter();

    updateConnectionStatus("Historical", "");

    // If no logs returned, ensure empty state is visible
    if (logs.length === 0) {
      updateEmptyState();
    }
  } catch (error) {
    console.error("Failed to fetch logs:", error);
    showError("Failed to fetch logs: " + error.message);
  }
}

/**
 * Toggle streaming on/off
 */
function toggleStreaming() {
  if (isStreaming) {
    stopStreaming();
  } else {
    startStreaming();
  }
}

/**
 * Start SSE streaming
 */
function startStreaming() {
  if (eventSource) {
    eventSource.close();
  }

  const params = buildQueryParams();
  eventSource = new EventSource(`/api/logs/stream?${params.toString()}`);

  eventSource.addEventListener("open", () => {
    isStreaming = true;
    updateStreamingUI(true);
    updateConnectionStatus("Connected", "text-success");
    console.log("SSE connection opened");
  });

  eventSource.addEventListener("message", (event) => {
    try {
      const logEntry = JSON.parse(event.data);
      addLogEntry(logEntry);
    } catch (error) {
      console.error("Failed to parse log entry:", error);
    }
  });

  eventSource.addEventListener("error", (error) => {
    console.error("SSE error:", error);
    updateConnectionStatus("Error", "text-danger");

    // Reconnect will happen automatically for SSE
    if (eventSource.readyState === EventSource.CONNECTING) {
      updateConnectionStatus("Reconnecting...", "text-warning");
    }
  });

  eventSource.addEventListener("connected", (event) => {
    console.log("Connected:", event.data);
  });

  eventSource.addEventListener("disconnected", (event) => {
    console.log("Disconnected:", event.data);
    stopStreaming();
  });
}

/**
 * Stop SSE streaming
 */
function stopStreaming() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
  isStreaming = false;
  updateStreamingUI(false);
  updateConnectionStatus("Disconnected", "text-secondary");
}

/**
 * Add a new log entry
 */
function addLogEntry(logEntry) {
  // Add to beginning for newest first
  logs.unshift(logEntry);

  // Limit to 1000 entries in memory
  if (logs.length > 1000) {
    logs.pop();
  }

  // Check if this log passes current filters
  const passesFilter = checkLogPassesFilters(logEntry);

  if (passesFilter) {
    // Add to filtered logs at the beginning
    filteredLogs.unshift(logEntry);

    // Limit filtered logs too
    if (filteredLogs.length > 1000) {
      filteredLogs.pop();
    }

    // Hide empty state when we get the first filtered log
    if (filteredLogs.length === 1) {
      document.getElementById("empty-state").style.display = "none";

      // Show the appropriate view
      if (document.getElementById("view-table").checked) {
        document.getElementById("table-view").style.display = "block";
        document.getElementById("json-view").style.display = "none";
      } else {
        document.getElementById("table-view").style.display = "none";
        document.getElementById("json-view").style.display = "block";
      }
    }

    // Update display only if log passes filters
    if (document.getElementById("view-table").checked) {
      addLogToTable(logEntry);
    } else {
      renderJsonView();
    }

    // Announce to screen readers
    announceNewLog(logEntry);
  }

  updateLogCount();
}

/**
 * Check if a log entry passes current filters
 */
function checkLogPassesFilters(log) {
  // Get filter values
  const keyword = document.getElementById("keyword").value.toLowerCase().trim();
  const selectedServices = Array.from(
    document.querySelectorAll(".service-checkbox:checked"),
  ).map((cb) => cb.value.toLowerCase());
  const minLevel = document.getElementById("log-level").value;
  const minLevelValue = LOG_LEVEL_CONFIG[minLevel]?.value || 0;

  // Service filter
  if (selectedServices.length > 0) {
    const logService = (log.service || "unknown").toLowerCase();
    if (!selectedServices.includes(logService)) {
      return false;
    }
  }

  // Level filter
  const logLevelValue = LOG_LEVEL_CONFIG[log.level?.toUpperCase()]?.value || 0;
  if (logLevelValue < minLevelValue) {
    return false;
  }

  // Keyword filter
  if (keyword) {
    const message = (log.message || "").toLowerCase();
    const service = (log.service || "").toLowerCase();
    const level = (log.level || "").toLowerCase();

    if (
      !message.includes(keyword) &&
      !service.includes(keyword) &&
      !level.includes(keyword)
    ) {
      return false;
    }
  }

  return true;
}

/**
 * Build query parameters from form
 */
function buildQueryParams() {
  const params = new URLSearchParams();

  // Only send time range to server - all other filtering is client-side
  const startTime = document.getElementById("start-time").value;
  const endTime = document.getElementById("end-time").value;

  // If no time range specified at all, use last 24 hours
  if (!startTime && !endTime) {
    setDefaultTimeRange();
    params.append("start_time", document.getElementById("start-time").value);
    params.append("end_time", document.getElementById("end-time").value);
  } else {
    if (startTime) params.append("start_time", startTime);
    if (endTime) params.append("end_time", endTime);
  }

  // Note: All filtering (services, level, keyword) is now done client-side

  return params;
}

/**
 * Apply client-side filtering
 */
function applyClientSideFilter() {
  // Get all filter values
  const keyword = document.getElementById("keyword").value.toLowerCase().trim();

  // Get selected services
  const selectedServices = Array.from(
    document.querySelectorAll(".service-checkbox:checked"),
  ).map((cb) => cb.value.toLowerCase());

  // Get minimum log level
  const minLevel = document.getElementById("log-level").value;
  const minLevelValue = LOG_LEVEL_CONFIG[minLevel]?.value || 0;

  // Apply all filters
  filteredLogs = logs.filter((log) => {
    // Service filter (if services are selected)
    if (selectedServices.length > 0) {
      const logService = (log.service || "unknown").toLowerCase();
      if (!selectedServices.includes(logService)) {
        return false;
      }
    }

    // Level filter
    const logLevelValue =
      LOG_LEVEL_CONFIG[log.level?.toUpperCase()]?.value || 0;
    if (logLevelValue < minLevelValue) {
      return false;
    }

    // Keyword filter
    if (keyword) {
      const message = (log.message || "").toLowerCase();
      const service = (log.service || "").toLowerCase();
      const level = (log.level || "").toLowerCase();

      if (
        !message.includes(keyword) &&
        !service.includes(keyword) &&
        !level.includes(keyword)
      ) {
        return false;
      }
    }

    return true;
  });

  renderLogs();
  updateLogCount();
}

/**
 * Render all logs
 */
function renderLogs() {
  // Use filtered logs if available, otherwise use all logs
  const logsToRender =
    filteredLogs.length > 0 || document.getElementById("keyword").value
      ? filteredLogs
      : logs;

  updateEmptyState();

  if (logsToRender.length > 0) {
    const viewMode = document.querySelector(
      'input[name="view-mode"]:checked',
    ).value;

    if (viewMode === "table") {
      renderTableView();
    } else {
      renderJsonView();
    }
  }
}

/**
 * Render table view
 */
function renderTableView() {
  const tbody = document.getElementById("log-tbody");
  tbody.innerHTML = "";

  // Use filtered logs if available, otherwise use all logs
  const logsToRender =
    filteredLogs.length > 0 || document.getElementById("keyword").value
      ? filteredLogs
      : logs;

  logsToRender.forEach((log) => {
    tbody.appendChild(createLogRow(log));
  });
}

/**
 * Create a log table row
 */
function createLogRow(log) {
  const tr = document.createElement("tr");
  tr.className = "log-row";
  tr.setAttribute("role", "row");

  // Level indicator cell
  const levelCell = document.createElement("td");
  levelCell.className = "log-level-cell text-center";
  levelCell.innerHTML = createLevelIndicator(log.level);
  tr.appendChild(levelCell);

  // Timestamp cell
  const timestampCell = document.createElement("td");
  timestampCell.className = "timestamp-cell text-nowrap";
  timestampCell.textContent = formatTimestamp(log.timestamp);
  tr.appendChild(timestampCell);

  // Service cell
  const serviceCell = document.createElement("td");
  serviceCell.className = "service-cell";
  serviceCell.textContent = log.service || "-";
  tr.appendChild(serviceCell);

  // Message cell
  const messageCell = document.createElement("td");
  messageCell.className = "message-cell";
  messageCell.textContent = log.message || "";
  if (log.extra && Object.keys(log.extra).length > 0) {
    messageCell.title = JSON.stringify(log.extra, null, 2);
  }
  tr.appendChild(messageCell);

  return tr;
}

/**
 * Create level indicator HTML
 */
function createLevelIndicator(level) {
  // Ensure level is uppercase for config lookup
  const upperLevel = level ? level.toUpperCase() : "INFO";
  const config = LOG_LEVEL_CONFIG[upperLevel] || LOG_LEVEL_CONFIG.INFO;
  return `<span
        class="log-level-indicator log-level-${upperLevel.toLowerCase()}"
        aria-label="${upperLevel} level"
        title="${upperLevel}"
    ></span>`;
}

/**
 * Add a single log to the table
 */
function addLogToTable(log) {
  const tbody = document.getElementById("log-tbody");
  const row = createLogRow(log);

  // Add to top for newest first
  tbody.insertBefore(row, tbody.firstChild);

  // Remove oldest if over limit
  while (tbody.children.length > 1000) {
    tbody.removeChild(tbody.lastChild);
  }

  // Briefly highlight new row
  row.classList.add("new-log");
  setTimeout(() => row.classList.remove("new-log"), 1000);
}

/**
 * Render JSON view
 */
function renderJsonView() {
  const jsonContent = document.getElementById("json-content");
  // Use filtered logs if available, otherwise use all logs
  const logsToRender =
    filteredLogs.length > 0 || document.getElementById("keyword").value
      ? filteredLogs
      : logs;
  jsonContent.textContent = JSON.stringify(logsToRender, null, 2);
}

/**
 * Toggle between table and JSON view
 */
function toggleViewMode() {
  const viewMode = document.querySelector(
    'input[name="view-mode"]:checked',
  ).value;
  const tableView = document.getElementById("table-view");
  const jsonView = document.getElementById("json-view");
  const emptyState = document.getElementById("empty-state");

  // Hide empty state when we have logs
  if (logs.length > 0) {
    emptyState.style.display = "none";

    if (viewMode === "table") {
      tableView.style.display = "block";
      jsonView.style.display = "none";
      renderTableView();
    } else {
      tableView.style.display = "none";
      jsonView.style.display = "block";
      renderJsonView();
    }
  } else {
    // No logs - hide both views, show empty state
    tableView.style.display = "none";
    jsonView.style.display = "none";
    emptyState.style.display = "block";
  }
}

/**
 * Format timestamp for display
 */
function formatTimestamp(timestamp) {
  if (!timestamp) return "-";

  try {
    const date = new Date(timestamp);
    return date.toLocaleString();
  } catch {
    return timestamp;
  }
}

/**
 * Download logs as JSON file
 */
function downloadLogs() {
  // Downloads currently displayed logs (from memory)
  const blob = new Blob([JSON.stringify(logs, null, 2)], {
    type: "application/json",
  });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `logs-displayed-${new Date().toISOString()}.json`;
  a.click();
  URL.revokeObjectURL(url);

  // Update button text temporarily to show what happened
  const btn = document.getElementById("download-logs");
  const originalText = btn.innerHTML;
  btn.innerHTML = `✓ Downloaded ${logs.length} logs`;
  setTimeout(() => {
    btn.innerHTML = originalText;
  }, 2000);
}

/**
 * Clear displayed logs
 */
function clearDisplay() {
  logs = [];
  filteredLogs = [];
  document.getElementById("keyword").value = ""; // Clear search filter too
  renderLogs();
  updateLogCount();
  updateEmptyState();
}

/**
 * Update streaming UI state
 */
function updateStreamingUI(streaming) {
  const button = document.getElementById("stream-toggle");
  const indicator = document.getElementById("streaming-indicator");
  const fetchArea = document.getElementById("fetch-area");

  if (streaming) {
    button.innerHTML = "■ Stop";
    button.classList.remove("btn-secondary");
    button.classList.add("btn-danger");
    button.setAttribute("aria-pressed", "true");
    indicator.classList.remove("d-none");
    // Hide fetch button when streaming
    if (fetchArea) {
      fetchArea.classList.add("hidden");
    }
  } else {
    button.innerHTML = "▶ Stream";
    button.classList.remove("btn-danger");
    button.classList.add("btn-secondary");
    button.setAttribute("aria-pressed", "false");
    indicator.classList.add("d-none");
    // Show fetch button when not streaming
    if (fetchArea) {
      fetchArea.classList.remove("hidden");
    }
  }
}

/**
 * Update connection status display
 */
function updateConnectionStatus(status, className) {
  const statusElement = document.getElementById("connection-status");
  if (statusElement) {
    statusElement.textContent = status;
    if (className) {
      statusElement.className = className;
    }
  }
}

/**
 * Update log count display
 */
function updateLogCount() {
  const keyword = document.getElementById("keyword").value.trim();
  const displayedCount =
    filteredLogs.length > 0 || keyword ? filteredLogs.length : logs.length;
  const totalCount = logs.length;

  // Show filtered count if filtering is active
  if (keyword) {
    document.getElementById("log-count").textContent =
      `${displayedCount} / ${totalCount}`;
  } else {
    document.getElementById("log-count").textContent = totalCount;
  }
}

/**
 * Update empty state visibility
 */
function updateEmptyState() {
  const emptyState = document.getElementById("empty-state");
  const tableView = document.getElementById("table-view");
  const jsonView = document.getElementById("json-view");

  if (logs.length === 0) {
    emptyState.style.display = "block";
    tableView.style.display = "none";
    jsonView.style.display = "none";
  } else {
    emptyState.style.display = "none";
    // Show the currently selected view
    toggleViewMode();
  }
}

/**
 * Show error message
 */
function showError(message) {
  // Could show in a toast or alert div
  console.error("Error:", message);
  updateConnectionStatus("Error: " + message, "text-danger");
}

/**
 * Announce new log to screen readers
 */
function announceNewLog(log) {
  // Create announcement for screen readers
  const announcement = `New ${log.level} log from ${log.service}: ${log.message}`;

  // Use aria-live region (the tbody has aria-live="polite")
  // The new row addition will be announced automatically
}

/**
 * Handle keyboard shortcuts
 */
function handleKeyboardShortcuts(event) {
  // Space to toggle streaming (when not in input)
  if (event.code === "Space" && event.target.tagName !== "INPUT") {
    event.preventDefault();
    toggleStreaming();
  }

  // Escape to stop streaming
  if (event.code === "Escape" && isStreaming) {
    stopStreaming();
  }

  // Ctrl+D to download
  if (event.ctrlKey && event.code === "KeyD") {
    event.preventDefault();
    downloadLogs();
  }
}
