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
let currentSpeciesList = new Set();

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
  data.forEach((species) => {
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
}

/**
 * Set hourly distribution data
 */
function setHourlyDistribution(data) {
  hourlyDistribution = data;
}

/**
 * Set visualization data
 */
function setVisualizationData(data) {
  visualizationData = data;
}

/**
 * Generate detection points for visualization
 */
function generateDetections() {
  const detections = [];

  // If we have real visualization data, use it
  if (visualizationData && visualizationData.length > 0) {
    visualizationData.forEach((d) => {
      detections.push({
        time: d.x, // Already in hours (0-24)
        confidence: d.y * 100, // Convert from fraction to percentage
        species: d.species,
        color: d.color,
        count: 1,
      });
    });
  } else if (hourlyDistribution && hourlyDistribution.length > 0) {
    // Generate based on hourly distribution
    const species = Object.keys(speciesData);

    hourlyDistribution.forEach((count, hour) => {
      for (let i = 0; i < count; i++) {
        detections.push({
          time: hour + Math.random(),
          confidence: 70 + Math.random() * 30,
          species:
            species.length > 0
              ? species[Math.floor(Math.random() * species.length)]
              : "Unknown",
          count: 1,
        });
      }
    });
  } else {
    // Fallback to minimal mock data
    for (let i = 0; i < 50; i++) {
      detections.push({
        time: Math.random() * 24,
        confidence: 70 + Math.random() * 30,
        species: "Unknown",
        count: 1,
      });
    }
  }

  return detections;
}

/**
 * Draw the abstract visualization
 */
function drawVisualization() {
  const container = document.getElementById("visualization");
  const detections = generateDetections();

  detections.forEach((d, index) => {
    // Create main dot
    const dot = document.createElement("div");
    dot.className = "dot";

    // Position based on time (x) and pseudo-random vertical spread
    const x = (d.time / 24) * 100;

    // Create vertical bands with organic clustering
    const verticalSpread = Math.sin(d.time * 0.5) * 30 + 50;
    const y =
      verticalSpread + (Math.random() - 0.5) * 40 + Math.sin(index * 0.1) * 10;

    // Size based on count and confidence
    const baseSize = 8 + d.count * 4 + (d.confidence - 70) * 0.5;
    const size = baseSize + Math.random() * 20;

    // Color based on species frequency with more variation
    const baseColor =
      d.color ||
      (speciesData[d.species]
        ? speciesData[d.species].color
        : getCSSVariable("--color-text-secondary"));
    const opacity = 0.12 + Math.random() * 0.08;

    // Apply styles
    dot.style.left = `${x}%`;
    dot.style.top = `${y}%`;
    dot.style.width = `${size}px`;
    dot.style.height = `${size}px`;
    dot.style.background = baseColor;

    // Staggered animation
    setTimeout(() => {
      dot.classList.add("visible");
    }, index * 3);

    // Random animation delay for organic movement
    dot.style.animationDelay = `${Math.random() * 4}s`;

    container.appendChild(dot);

    // Add expanding rings for high-confidence detections
    if (d.confidence > 90 && Math.random() > 0.7) {
      const ring = document.createElement("div");
      ring.className = "dot-ring";
      ring.style.left = `${x}%`;
      ring.style.top = `${y}%`;
      ring.style.width = `${size}px`;
      ring.style.height = `${size}px`;
      ring.style.borderColor = baseColor;
      ring.style.animationDelay = `${Math.random() * 8}s`;
      container.appendChild(ring);
    }
  });

  // Add floating particle effect for ambient movement
  for (let i = 0; i < 20; i++) {
    const particle = document.createElement("div");
    particle.className = "dot";
    particle.style.width = "2px";
    particle.style.height = "2px";
    particle.style.background = getCSSVariable("--color-viz-particle");
    particle.style.left = `${Math.random() * 100}%`;
    particle.style.top = `${Math.random() * 100}%`;
    particle.style.animation = `float ${20 + Math.random() * 10}s infinite ease-in-out`;
    particle.style.animationDelay = `${Math.random() * 5}s`;
    particle.classList.add("visible");
    container.appendChild(particle);
  }
}

/**
 * Update times in detection log
 */
function updateTimes() {
  const now = new Date();
  const timeElements = document.querySelectorAll(".log-entry .time");

  timeElements.forEach((el, index) => {
    const minutesAgo = index * 5 + Math.floor(Math.random() * 5);
    const time = new Date(now - minutesAgo * 60000);
    el.textContent = time.toTimeString().slice(0, 5);
  });
}

/**
 * Load system status via API
 */
async function loadSystemStatus() {
  try {
    const response = await fetch("/api/system/hardware/status");
    if (!response.ok) throw new Error("Failed to fetch system status");

    const data = await response.json();

    // Update device name
    const deviceName = document.getElementById("device-name");
    if (deviceName && data.system_info?.device_name) {
      deviceName.textContent = data.system_info.device_name;
    }

    // Update CPU status
    const cpuPercent = data.resources?.cpu?.percent || 0;
    const cpuTemp = data.resources?.cpu?.temperature;
    document.getElementById("cpu-value").textContent =
      `${Math.round(cpuPercent)}%`;
    document.getElementById("cpu-indicator").style.width = `${cpuPercent}%`;
    document.getElementById("cpu-tooltip").textContent =
      cpuTemp !== null
        ? `CPU Temperature: ${cpuTemp}°C`
        : "CPU Temperature: N/A";

    // Update Memory status
    const memory = data.resources?.memory || {};
    const memPercent = memory.percent || 0;
    const memUsedGB = (memory.used / 1024 ** 3).toFixed(1);
    const memTotalGB = (memory.total / 1024 ** 3).toFixed(1);
    document.getElementById("memory-value").textContent =
      `${Math.round(memPercent)}%`;
    document.getElementById("memory-indicator").style.width = `${memPercent}%`;
    document.getElementById("memory-tooltip").textContent =
      `${memUsedGB} GB / ${memTotalGB} GB used`;

    // Update Disk status
    const disk = data.resources?.disk || {};
    const diskPercent = disk.percent || 0;
    const diskUsedGB = (disk.used / 1024 ** 3).toFixed(1);
    const diskTotalGB = (disk.total / 1024 ** 3).toFixed(1);
    document.getElementById("disk-value").textContent =
      `${Math.round(diskPercent)}%`;
    const diskIndicator = document.getElementById("disk-indicator");
    diskIndicator.style.width = `${diskPercent}%`;
    // Add warning/critical classes based on disk usage
    diskIndicator.classList.remove("warning", "critical");
    if (diskPercent > 90) {
      diskIndicator.classList.add("critical");
    } else if (diskPercent > 80) {
      diskIndicator.classList.add("warning");
    }
    document.getElementById("disk-tooltip").textContent =
      `${diskUsedGB} GB / ${diskTotalGB} GB used`;

    // Update Audio status (placeholder for now)
    document.getElementById("audio-value").innerHTML =
      '-60<span class="status-detail">dB</span>';
    document.getElementById("audio-indicator").style.width = "0%";
    document.getElementById("audio-tooltip").textContent =
      "Audio monitoring not available";

    // Update Uptime
    const uptimeDays = data.system_info?.uptime_days || 0;
    document.getElementById("uptime-value").textContent = `${uptimeDays}d`;
    document.getElementById("uptime-tooltip").textContent =
      `System uptime: ${uptimeDays} days`;
  } catch (error) {
    console.error("Failed to load system status:", error);
    // Set error state for all indicators
    document.getElementById("device-name").textContent = "Unknown Device";
    document.querySelectorAll(".status-value").forEach((el) => {
      if (!el.textContent.includes("d")) el.textContent = "ERR";
    });
  }
}

// Real-time detection updates via SSE

/**
 * Initialize the species list from the current frequency table
 */
function initializeSpeciesList() {
  // Build set of current species from the frequency table
  const speciesElements = document.querySelectorAll(
    ".frequency-item .species-name",
  );
  speciesElements.forEach((el) => {
    const name = el.textContent.trim();
    if (name && name !== "No species detected today") {
      currentSpeciesList.add(name);
    }
  });
}

/**
 * Show detection banner notification
 */
function showDetectionBanner(detection) {
  const banner = document.getElementById("detection-banner");
  const content = banner.querySelector(".banner-content");

  // Format the notification message
  const time = new Date(detection.timestamp).toTimeString().slice(0, 5);
  const confidence = (detection.confidence * 100).toFixed(1);
  content.textContent = `New detection: ${detection.common_name} at ${time} (${confidence}% confidence)`;

  // Show banner
  banner.classList.remove("hiding");
  banner.style.display = "block";

  // Hide after 5 seconds
  setTimeout(() => {
    banner.classList.add("hiding");
    setTimeout(() => {
      banner.style.display = "none";
      banner.classList.remove("hiding");
    }, 300);
  }, 5000);
}

/**
 * Update detection log with new detection
 */
function updateDetectionLog(detection) {
  const logContainer = document.querySelector(".detection-log");
  const logHeader = logContainer.querySelector(".log-header");
  const entries = logContainer.querySelectorAll(".log-entry");

  // Create new entry
  const newEntry = document.createElement("div");
  newEntry.className = "log-entry";
  newEntry.style.animation = "fadeIn 0.5s ease-out";

  const time = new Date(detection.timestamp).toTimeString().slice(0, 5);
  const confidence = (detection.confidence * 100).toFixed(1);

  newEntry.innerHTML = `
    <span class="time">${time}</span>
    <span>${detection.common_name}</span>
    <span class="confidence">${confidence}%</span>
  `;

  // Insert after header
  logHeader.after(newEntry);

  // Remove last entry if we have more than 10
  if (entries.length >= 10) {
    entries[entries.length - 1].remove();
  }

  // Remove "No recent detections" message if present
  const noDetections = Array.from(entries).find((e) =>
    e.textContent.includes("No recent detections"),
  );
  if (noDetections) {
    noDetections.remove();
  }
}

/**
 * Update species frequency display
 */
async function updateSpeciesFrequency(detection) {
  // Check if this species is already in our list
  if (currentSpeciesList.has(detection.common_name)) {
    // Species exists - just increment the count locally
    const frequencyItems = document.querySelectorAll(".frequency-item");
    for (const item of frequencyItems) {
      const nameEl = item.querySelector(".species-name");
      if (nameEl && nameEl.textContent === detection.common_name) {
        const countEl = item.querySelector(".freq-count");
        const currentCount = parseInt(countEl.textContent) || 0;
        countEl.textContent = currentCount + 1;
        break;
      }
    }
  } else {
    // New species - need to fetch updated frequency list
    try {
      const response = await fetch(
        "/api/detections/species/frequency?hours=24",
      );
      if (response.ok) {
        const data = await response.json();
        updateSpeciesFrequencyTable(data.species);
        // Add to our tracking set
        currentSpeciesList.add(detection.common_name);
      }
    } catch (error) {
      console.error("Failed to fetch updated species frequency:", error);
    }
  }
}

/**
 * Update species frequency table
 */
function updateSpeciesFrequencyTable(species) {
  const container = document.querySelector(".frequency-list");
  const header = container.querySelector(".list-header");

  // Clear existing entries (except header)
  const existingEntries = container.querySelectorAll(".frequency-item");
  existingEntries.forEach((e) => e.remove());

  // Add new entries
  species.slice(0, 10).forEach((s) => {
    const item = document.createElement("div");
    item.className = "frequency-item";

    const maxCount = species[0]?.count || 1;
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

  // If no species, show empty message
  if (species.length === 0) {
    const item = document.createElement("div");
    item.className = "frequency-item";
    item.innerHTML = `
      <span class="species-name">No species detected today</span>
      <span class="freq-count">0</span>
      <span class="freq-bar">
        <span class="bar" style="width: 0%"></span>
      </span>
    `;
    container.appendChild(item);
  }
}

/**
 * Connect to detection stream via Server-Sent Events
 */
function connectDetectionStream() {
  if (detectionEventSource) {
    detectionEventSource.close();
  }

  detectionEventSource = new EventSource("/api/detections/stream");

  detectionEventSource.addEventListener("connected", (event) => {
    console.log("Connected to detection stream");
  });

  detectionEventSource.addEventListener("detection", (event) => {
    try {
      const detection = JSON.parse(event.data);
      console.log("New detection:", detection);

      // Show banner notification
      showDetectionBanner(detection);

      // Update detection log
      updateDetectionLog(detection);

      // Update species frequency
      updateSpeciesFrequency(detection);

      // Pulse the live indicator
      const pulse = document.querySelector(".live");
      if (pulse) {
        pulse.style.background = getCSSVariable("--color-status-success");
        setTimeout(() => {
          pulse.style.background = getCSSVariable("--color-status-live");
        }, 1000);
      }
    } catch (error) {
      console.error("Failed to process detection event:", error);
    }
  });

  detectionEventSource.addEventListener("heartbeat", (event) => {
    // Heartbeat received - connection is alive
  });

  detectionEventSource.addEventListener("error", (event) => {
    console.error("Detection stream error:", event);
    if (detectionEventSource.readyState === EventSource.CLOSED) {
      // Reconnect after 5 seconds
      setTimeout(connectDetectionStream, 5000);
    }
  });

  detectionEventSource.onerror = (error) => {
    console.error("EventSource error:", error);
    if (detectionEventSource.readyState === EventSource.CLOSED) {
      setTimeout(connectDetectionStream, 5000);
    }
  };
}

/**
 * Initialize dashboard on page load
 */
function initializeDashboard() {
  // Add fadeIn animation style
  const style = document.createElement("style");
  style.textContent = `
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(-10px); }
      to { opacity: 1; transform: translateY(0); }
    }
  `;
  document.head.appendChild(style);

  // Initialize components
  drawVisualization();
  updateTimes();
  loadSystemStatus(); // Load system status on page load
  initializeSpeciesList(); // Build initial species list
  connectDetectionStream(); // Connect to SSE stream

  // Update times every minute
  setInterval(updateTimes, 60000);

  // Refresh system status every 5 seconds
  setInterval(loadSystemStatus, 5000);

  // Simulate live updates
  setInterval(() => {
    const pulse = document.querySelector(".live");
    if (pulse) {
      pulse.style.background = getCSSVariable("--color-status-success");
      setTimeout(() => {
        pulse.style.background = getCSSVariable("--color-status-live");
      }, 1000);
    }
  }, 10000);
}

// Initialize when DOM is ready
document.addEventListener("DOMContentLoaded", initializeDashboard);
