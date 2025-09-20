/**
 * Dashboard JavaScript - Real-time detection monitoring and system status
 */

// Helper function to get CSS variable values
function getCSSVariable(varName) {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(varName)
    .trim();
}

// Global variables for SSE
let detectionEventSource = null;
// Initialize species tracking Set on window object for global access
if (!window.currentSpeciesList) {
  window.currentSpeciesList = new Set();
}

// Species buffer - Map to track all species counts locally
// This includes top 20 loaded initially plus any new species detected
if (!window.speciesBuffer) {
  window.speciesBuffer = new Map();
}

// Initialize species data from template variables (will be set by template)
let speciesData = {};
let hourlyDistribution = [];
let visualizationData = [];

/**
 * Initialize species data from server-provided frequency data
 * This function should be called from the template with the actual data
 */
function initializeSpeciesData(data) {
  speciesData = {};
  // Clear and populate the species buffer with all 20 species
  window.speciesBuffer.clear();
  window.currentSpeciesList.clear();

  data.forEach((species) => {
    // Add to buffer (all 20 species)
    window.speciesBuffer.set(species.name, species.count);

    // Add to display data (for charts)
    speciesData[species.name] = {
      count: species.count,
      color:
        species.count > 200
          ? getCSSVariable("--color-activity-high")
          : species.count > 50
            ? getCSSVariable("--color-activity-medium")
            : getCSSVariable("--color-activity-low"),
    };
  });

  // Display only top 10 initially
  updateSpeciesFrequencyTableFromBuffer();
}

/**
 * Set hourly distribution data
 */
function setHourlyDistribution(data) {
  hourlyDistribution = data;
}

/**
 * Set visualization data and render artistic representation
 */
function setVisualizationData(data) {
  visualizationData = data;
  renderArtisticVisualization();
}

/**
 * Render artistic visualization with circles spread across full width
 */
function renderArtisticVisualization() {
  const container = document.getElementById("visualization");
  if (!container || !visualizationData || visualizationData.length === 0)
    return;

  // Clear existing dots
  const existingDots = container.querySelectorAll(".dot");
  existingDots.forEach((dot) => dot.remove());

  // Create artistic representation - sample and spread dots across full width
  const maxDots = 50; // Limit for artistic effect
  const step = Math.max(1, Math.floor(visualizationData.length / maxDots));
  const sampledData = [];

  // Sample data evenly
  for (let i = 0; i < visualizationData.length; i += step) {
    sampledData.push(visualizationData[i]);
  }

  // Calculate the actual min and max confidence values for normalization
  const confidenceValues = sampledData.map((d) => d.y);
  const minConfidence = Math.min(...confidenceValues);
  const maxConfidence = Math.max(...confidenceValues);
  const confidenceRange = maxConfidence - minConfidence || 0.1; // Avoid division by zero

  // Distribute dots artistically across the full 24-hour width
  sampledData.forEach((detection, index) => {
    const dot = document.createElement("div");
    dot.className = "dot visible";

    // Spread dots across full width for artistic effect
    const xPosition = (index / sampledData.length) * 100;
    dot.style.left = `${xPosition}%`;

    // Normalize Y position to use full height based on actual confidence range
    // Map minConfidence -> 5%, maxConfidence -> 95% (with padding)
    const normalizedY =
      5 + ((detection.y - minConfidence) / confidenceRange) * 90;
    dot.style.bottom = `${normalizedY}%`;

    // Use normalized confidence for sizing too (20-50px range)
    const normalizedSize = (detection.y - minConfidence) / confidenceRange;
    const size = 20 + normalizedSize * 30;
    dot.style.width = `${size}px`;
    dot.style.height = `${size}px`;

    // Apply colors from the data
    dot.style.backgroundColor =
      detection.color || getCSSVariable("--color-activity-medium");

    container.appendChild(dot);
  });
}

/**
 * Update visualization with new detection (pulse effect on existing dots)
 */
function addDetectionToVisualization(detection) {
  const container = document.getElementById("visualization");
  if (!container) return;

  // Find a random dot to pulse for artistic effect
  const dots = container.querySelectorAll(".dot");
  if (dots.length > 0) {
    // Pick a dot near the current time (if we were doing time-based)
    // For artistic effect, just pick one randomly or in sequence
    const dotIndex = Math.floor(Math.random() * dots.length);
    const dot = dots[dotIndex];

    // Create a pulse effect
    const originalSize = dot.style.width;
    const originalOpacity = dot.style.opacity || "0.12";

    // Apply pulse animation
    dot.style.transition = "all 0.3s ease-out";
    dot.style.transform = "scale(1.5)";
    dot.style.opacity = "0.8";

    // Determine color based on confidence
    const color =
      detection.confidence > 0.9
        ? getCSSVariable("--color-activity-high")
        : detection.confidence > 0.8
          ? getCSSVariable("--color-activity-medium")
          : getCSSVariable("--color-activity-low");

    // Temporarily change color to show activity
    const originalColor = dot.style.backgroundColor;
    dot.style.backgroundColor = color;

    // Reset after animation
    setTimeout(() => {
      dot.style.transform = "scale(1)";
      dot.style.opacity = originalOpacity;
      dot.style.backgroundColor = originalColor;
    }, 2000);
  }

  // Add to our data array for potential re-render
  if (visualizationData) {
    const now = new Date();
    const hour = now.getHours() + now.getMinutes() / 60;

    visualizationData.push({
      x: hour, // Store as hour value (0-24) like server data
      y: detection.confidence,
      color:
        detection.confidence > 0.9
          ? "#2e7d32"
          : detection.confidence > 0.8
            ? "#f57c00"
            : "#c62828",
      species: detection.common_name,
    });

    // Occasionally re-render to incorporate new data
    if (visualizationData.length % 50 === 0) {
      renderArtisticVisualization();
    }
  }
}

/**
 * Add CSS for animations if not already present
 */
function addVisualizationStyles() {
  // No additional styles needed - using CSS from style.css
  // The .dot class already has the necessary animations
}

/**
 * Create placeholder detection log
 */
function createDetectionLog() {
  const container = document.querySelector("#detection-log");
  if (!container) return;

  const table = document.createElement("table");
  table.className = "log-table";

  // Create header
  const thead = document.createElement("thead");
  thead.innerHTML = `
    <tr>
      <th>Time</th>
      <th>Species</th>
      <th>Conf.</th>
    </tr>
  `;
  table.appendChild(thead);

  // Create body - will be populated by SSE events
  const tbody = document.createElement("tbody");
  table.appendChild(tbody);

  container.appendChild(table);
}

/**
 * Update detection log with new detection
 */
function updateDetectionLog(detection) {
  const tbody = document.querySelector("#detection-log tbody");
  if (!tbody) return;

  // Create new row
  const row = document.createElement("tr");
  row.className = "fade-in";

  // Format time
  const time = new Date(detection.timestamp).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });

  // Format confidence as percentage
  const confidence = (detection.confidence * 100).toFixed(1) + "%";

  row.innerHTML = `
    <td>${time}</td>
    <td>${detection.common_name}</td>
    <td>${confidence}</td>
  `;

  // Insert at the beginning
  tbody.insertBefore(row, tbody.firstChild);

  // Remove old entries (keep only 10)
  while (tbody.children.length > 10) {
    tbody.removeChild(tbody.lastChild);
  }
}

/**
 * Initialize visualizations that exist in DOM
 */
function initializeVisualizations() {
  // Add CSS for animations if needed
  addVisualizationStyles();

  // The gradients and waves are already in the HTML
  // Dots will be added when data is set
}

/**
 * Load system hardware status
 */
async function loadSystemStatus() {
  try {
    const response = await fetch("/api/system/hardware/status");
    if (response.ok) {
      const data = await response.json();
      updateSystemStatus(data);
    }
  } catch (error) {
    // Silently fail - hardware endpoint may not be available
  }
}

/**
 * Update system status display
 */
function updateSystemStatus(status) {
  // The API returns data in the 'resources' object
  const resources = status.resources || {};

  // Update CPU
  const cpuEl = document.getElementById("cpu-value");
  const cpuIndicator = document.getElementById("cpu-indicator");
  const cpuTooltip = document.getElementById("cpu-tooltip");
  if (cpuEl && resources.cpu) {
    const usage = resources.cpu.percent || 0;
    cpuEl.textContent = `${usage.toFixed(0)}%`;
    cpuEl.className = usage > 80 ? "status-high" : "";

    if (cpuIndicator) {
      cpuIndicator.style.width = `${usage}%`;
    }

    if (cpuTooltip) {
      if (resources.temperature?.cpu) {
        cpuTooltip.textContent = `Temperature: ${resources.temperature.cpu.toFixed(1)}°C`;
      } else {
        cpuTooltip.textContent = "Temperature: N/A";
      }
    }
  }

  // Update Memory
  const memEl = document.getElementById("memory-value");
  const memIndicator = document.getElementById("memory-indicator");
  const memTooltip = document.getElementById("memory-tooltip");
  if (memEl && resources.memory) {
    const usage = resources.memory.percent || 0;
    memEl.textContent = `${usage.toFixed(0)}%`;
    memEl.className = usage > 80 ? "status-high" : "";

    if (memIndicator) {
      memIndicator.style.width = `${usage}%`;
    }

    if (memTooltip) {
      const used = (resources.memory.used || 0) / 1024 ** 3;
      const total = (resources.memory.total || 0) / 1024 ** 3;
      memTooltip.textContent = `${used.toFixed(1)} GB / ${total.toFixed(1)} GB used`;
    }
  }

  // Update Disk
  const diskEl = document.getElementById("disk-value");
  const diskIndicator = document.getElementById("disk-indicator");
  const diskTooltip = document.getElementById("disk-tooltip");
  if (diskEl && resources.disk) {
    const usage = resources.disk.percent || 0;
    diskEl.textContent = `${usage.toFixed(0)}%`;
    diskEl.className = usage > 80 ? "status-high" : "";

    if (diskIndicator) {
      diskIndicator.style.width = `${usage}%`;
    }

    if (diskTooltip) {
      const used = (resources.disk.used || 0) / 1024 ** 3;
      const total = (resources.disk.total || 0) / 1024 ** 3;
      diskTooltip.textContent = `${used.toFixed(1)} GB / ${total.toFixed(1)} GB used`;
    }
  }

  // Update Audio level (if available)
  const audioEl = document.getElementById("audio-value");
  const audioIndicator = document.getElementById("audio-indicator");
  const audioTooltip = document.getElementById("audio-tooltip");
  if (audioEl) {
    if (resources.audio) {
      const level = resources.audio.level_db || -60;
      audioEl.textContent = `${level.toFixed(0)}dB`;
      audioEl.className = level > -10 ? "status-high" : "";

      if (audioIndicator) {
        // Map dB to percentage (assuming -60dB to 0dB range)
        const percent = Math.max(0, ((60 + level) / 60) * 100);
        audioIndicator.style.width = `${percent}%`;
      }

      if (audioTooltip) {
        audioTooltip.textContent = resources.audio.is_capturing
          ? "Audio monitoring active"
          : "Audio monitoring not available";
      }
    } else {
      audioEl.textContent = "N/A";
      if (audioTooltip) {
        audioTooltip.textContent = "Audio monitoring not available";
      }
    }
  }

  // Update System Uptime
  const uptimeEl = document.getElementById("uptime-value");
  const uptimeTooltip = document.getElementById("uptime-tooltip");
  if (uptimeEl && status.system_info) {
    const days = status.system_info.uptime_days || 0;
    uptimeEl.textContent = `${days}d`;

    if (uptimeTooltip) {
      uptimeTooltip.textContent = `System uptime: ${days} days`;
    }
  }
}

/**
 * Update species frequency based on new detection
 */
async function updateSpeciesFrequency(detection) {
  // Ensure the buffer and Set exist
  if (!window.speciesBuffer) {
    window.speciesBuffer = new Map();
  }
  if (!window.currentSpeciesList) {
    window.currentSpeciesList = new Set();
  }

  // Update the buffer with the new detection
  const currentCount = window.speciesBuffer.get(detection.common_name) || 0;
  window.speciesBuffer.set(detection.common_name, currentCount + 1);

  // Re-render the table from buffer (will automatically show top 10)
  updateSpeciesFrequencyTableFromBuffer();
}

/**
 * Update species frequency table from buffer
 * This sorts the buffer and displays the top 10 species
 */
function updateSpeciesFrequencyTableFromBuffer() {
  // Convert Map to array and sort by count (descending)
  const sortedSpecies = Array.from(window.speciesBuffer.entries())
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count);

  const container = document.querySelector(".frequency-list");
  if (!container) return;

  const header = container.querySelector(".list-header");

  // Clear existing entries (except header)
  const existingEntries = container.querySelectorAll(".frequency-item");
  existingEntries.forEach((e) => e.remove());

  // Add top 10 entries
  const top10 = sortedSpecies.slice(0, 10);
  const maxCount = top10[0]?.count || 1;

  top10.forEach((s) => {
    const item = document.createElement("div");
    item.className = "frequency-item";
    const barWidth = (s.count / maxCount) * 100 + "%";

    item.innerHTML = `
      <span class="species-name">${s.name}</span>
      <span class="freq-count">${s.count}</span>
      <span class="freq-bar">
        <span class="bar" style="width: ${barWidth}"></span>
      </span>
    `;

    container.appendChild(item);
  });

  // Update tracking set with current top 10
  window.currentSpeciesList.clear();
  top10.forEach((s) => window.currentSpeciesList.add(s.name));
}

/**
 * Update species frequency table (legacy - now just calls buffer version)
 */
function updateSpeciesFrequencyTable(species) {
  // Convert API response to buffer format and update
  window.speciesBuffer.clear();
  species.forEach((s) => {
    window.speciesBuffer.set(s.name, s.count);
  });
  updateSpeciesFrequencyTableFromBuffer();
}

/**
 * Start SSE connection for real-time updates
 */
function startSSEConnection() {
  if (detectionEventSource) {
    detectionEventSource.close();
  }

  detectionEventSource = new EventSource("/api/detections/stream");

  detectionEventSource.onopen = () => {
    console.log("Connected to detection stream");
  };

  detectionEventSource.onmessage = (event) => {
    try {
      const detection = JSON.parse(event.data);
      console.log("New detection:", detection);

      // Update detection log
      updateDetectionLog(detection);

      // Update species frequency
      updateSpeciesFrequency(detection);

      // Add to visualization
      addDetectionToVisualization(detection);

      // Show notification banner
      showDetectionBanner(detection);
    } catch (error) {
      console.error("Failed to parse detection event:", error);
    }
  };

  detectionEventSource.onerror = (error) => {
    console.error("Detection stream error:", error);

    if (detectionEventSource.readyState === EventSource.CLOSED) {
      console.log("Detection stream closed, reconnecting in 5 seconds...");
      setTimeout(startSSEConnection, 5000);
    }
  };

  // Additional error handling for connection issues
  detectionEventSource.addEventListener("error", (event) => {
    console.error("EventSource error:", event);
  });
}

/**
 * Show detection notification banner
 */
function showDetectionBanner(detection) {
  const banner = document.getElementById("detection-banner");
  if (!banner) return;

  const content = banner.querySelector(".banner-content");
  if (!content) return;

  // Format the message
  const time = new Date(detection.timestamp).toLocaleTimeString("en-US", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  const confidence = (detection.confidence * 100).toFixed(1);

  content.textContent = `New detection: ${detection.common_name} at ${time} (${confidence}% confidence)`;

  // Show the banner
  banner.classList.remove("d-none");
  banner.classList.remove("hiding");

  // Hide after 5 seconds
  setTimeout(() => {
    banner.classList.add("hiding");
    setTimeout(() => {
      banner.classList.add("d-none");
    }, 300);
  }, 5000);
}

/**
 * Initialize dashboard on page load
 */
document.addEventListener("DOMContentLoaded", () => {
  // Initialize visualizations
  initializeVisualizations();

  // Load initial hardware status
  loadSystemStatus();

  // Update hardware status every 15 seconds (reduced from 5s to avoid overwhelming workers)
  setInterval(loadSystemStatus, 15000);

  // Start SSE connection for real-time detections
  startSSEConnection();

  // Initialize data if provided by template
  // (The template will call these functions directly)
});

// Export functions that need to be called from template
window.initializeSpeciesData = initializeSpeciesData;
window.setHourlyDistribution = setHourlyDistribution;
window.setVisualizationData = setVisualizationData;
