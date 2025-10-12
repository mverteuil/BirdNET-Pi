/**
 * Analysis JavaScript - Data visualization and chart rendering
 */

// Global state for period bounds
let primaryPeriodBounds = null;
let comparisonEnabled = false;

// Callback for primary period selector changes
function onPrimaryPeriodChange(bounds) {
  console.log("[Analysis] Primary period changed:", bounds);
  primaryPeriodBounds = bounds;

  // Update URL with current state
  updateURL();

  // Reload analysis with new period
  loadAnalysisData();
}

// Update URL with current state (period, date, comparison)
function updateURL() {
  const params = new URLSearchParams();

  // Add period/date parameters from period selector if available
  if (primaryPeriodBounds) {
    params.set("period", primaryPeriodBounds.period_type);
    if (primaryPeriodBounds.start_date) {
      params.set("date", primaryPeriodBounds.start_date);
    }
  }

  // Add comparison parameter if enabled
  if (comparisonEnabled) {
    params.set("comparison", "previous");
  }

  const newUrl = params.toString()
    ? `${window.location.pathname}?${params.toString()}`
    : window.location.pathname;

  // Build state object for browser history
  const state = {};
  if (primaryPeriodBounds) {
    state.period = primaryPeriodBounds.period_type;
    state.date = primaryPeriodBounds.start_date;
  }
  if (comparisonEnabled) {
    state.comparison = "previous";
  }

  window.history.pushState(state, "", newUrl);
}

// Toggle comparison mode
function toggleComparison() {
  const checkbox = document.getElementById("enable-comparison");
  comparisonEnabled = checkbox ? checkbox.checked : false;

  console.log("[Analysis] Comparison toggled:", comparisonEnabled);

  // Update URL with current state
  updateURL();

  // Reload analysis with comparison
  loadAnalysisData();
}

// Load analysis data from API
async function loadAnalysisData() {
  if (!primaryPeriodBounds) {
    console.log("[Analysis] No period bounds yet");
    return;
  }

  const analysisLoading = document.getElementById("analysis-loading");
  const analysisContent = document.getElementById("analysis-content");

  // Show inline loading indicator, hide content
  analysisLoading.style.display = "block";
  analysisContent.style.display = "none";

  try {
    const params = new URLSearchParams({
      start_date: primaryPeriodBounds.start_date,
      end_date: primaryPeriodBounds.end_date,
      comparison: comparisonEnabled ? "previous" : "none",
    });

    console.log("[Analysis] Fetching data from API...");
    const response = await fetch(`/api/analysis?${params}`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();

    // Store the analyses data globally
    window.analysisData = data.analyses || {};
    if (data.dates) {
      window.analysisData.dates = data.dates;
    }

    console.log(
      "[Analysis] Data loaded, keys:",
      Object.keys(window.analysisData),
    );

    // Hide loading, show content
    analysisLoading.style.display = "none";
    analysisContent.style.display = "block";

    // Re-initialize all visualizations
    initializeAnalysis();
  } catch (error) {
    console.error("[Analysis] Error fetching data:", error);

    // Hide loading, show content with error
    analysisLoading.style.display = "none";
    analysisContent.style.display = "block";

    showErrorState(error.message);
  }
}

// Initialize analysis data via AJAX
async function initAnalysisPage() {
  console.log("[Analysis] Initializing analysis page...");

  // Check if we're on the analysis page
  if (!window.analysisConfig) {
    console.log("[Analysis] Not on analysis page");
    return;
  }

  // Note: We don't load data here. The period selector will trigger the initial
  // data load via onPrimaryPeriodChange() callback once it's initialized.
  // This prevents duplicate API calls on page load.
  console.log(
    "[Analysis] Waiting for period selector to trigger initial load...",
  );
}

function showErrorState(message) {
  const sections = document.querySelectorAll(".analysis-section");
  sections.forEach((section) => {
    const error = document.createElement("div");
    error.className = "error-message";
    error.style.color = "red";
    error.textContent = `Error loading data: ${message}`;
    section.appendChild(error);
  });
}

// Handle browser back/forward navigation
window.addEventListener("popstate", function (event) {
  if (window.analysisConfig) {
    // Reload the page with the URL parameters
    initAnalysisPage();
  }
});

// Handle both DOMContentLoaded and immediate execution
if (document.readyState === "loading") {
  // DOM is still loading, wait for it
  document.addEventListener("DOMContentLoaded", initAnalysisPage);
} else {
  // DOM is already ready (script loaded after DOMContentLoaded fired)
  initAnalysisPage();
}

// Function to update analysis when period changes
function updateAnalysis() {
  const primaryPeriod = document.getElementById("primary-period").value;
  const comparisonPeriod = document.getElementById("comparison-period").value;

  // Update the config
  window.analysisConfig = {
    period: primaryPeriod,
    comparisonPeriod: comparisonPeriod,
  };

  // Update the URL with the new parameters
  const params = new URLSearchParams();
  params.set("period", primaryPeriod);
  params.set("comparison", comparisonPeriod);

  // Push the new state to browser history
  const newUrl = `${window.location.pathname}?${params.toString()}`;
  window.history.pushState(
    { period: primaryPeriod, comparison: comparisonPeriod },
    "",
    newUrl,
  );

  // Reload the analysis data
  initAnalysisPage();
}

// Initialize all analysis visualizations
function initializeAnalysis() {
  console.log("[Analysis] Starting chart initialization...");
  let chartsDrawn = 0;

  // Draw only charts that have canvas elements in the DOM
  if (document.getElementById("diversity-timeline")) {
    console.log("[Analysis] Drawing diversity timeline...");
    drawDiversityTimeline();
    chartsDrawn++;
  }
  if (document.getElementById("activity-heatmap")) {
    console.log("[Analysis] Drawing activity heatmap...");
    drawActivityHeatmap();
    chartsDrawn++;
  }
  if (document.getElementById("accumulation-curve")) {
    console.log("[Analysis] Drawing accumulation curve...");
    drawAccumulationCurve();
    chartsDrawn++;
  }
  if (document.getElementById("beta-diversity")) {
    console.log("[Analysis] Drawing beta diversity...");
    drawBetaDiversity();
    chartsDrawn++;
  }
  if (
    document.getElementById("temp-correlation") ||
    document.getElementById("humidity-correlation") ||
    document.getElementById("wind-correlation")
  ) {
    console.log("[Analysis] Drawing weather correlations...");
    drawWeatherCorrelations();
    chartsDrawn++;
  }

  // Populate similarity matrix if we have the data
  if (document.getElementById("similarity-matrix-container")) {
    console.log("[Analysis] Populating similarity matrix...");
    populateSimilarityMatrix();
    chartsDrawn++;
  }

  // Update weather correlation values in the UI
  updateWeatherCorrelationValues();

  // Update metrics summary line
  updateMetricsSummary();

  console.log(
    `[Analysis] Initialization complete. ${chartsDrawn} charts drawn.`,
  );
}

// Draw diversity timeline using canvas
function drawDiversityTimeline() {
  const canvas = document.getElementById("diversity-timeline");
  if (!canvas || !window.analysisData.diversity) return;

  const ctx = canvas.getContext("2d");
  const data = window.analysisData.diversity;

  // Canvas dimensions
  const padding = { left: 50, right: 30, top: 20, bottom: 40 };
  const width = canvas.width - padding.left - padding.right;
  const height = canvas.height - padding.top - padding.bottom;

  // Clear canvas
  ctx.fillStyle = "#fdfcfa";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Draw axes
  ctx.strokeStyle = "#111";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(padding.left, padding.top);
  ctx.lineTo(padding.left, padding.top + height);
  ctx.lineTo(padding.left + width, padding.top + height);
  ctx.stroke();

  // Scale data
  const maxShannon = Math.max(...data.shannon);
  const maxRichness = Math.max(...data.richness);

  // Determine if we need to sample the data for cleaner lines
  const maxLinePoints = 100; // Maximum points for smooth line drawing
  let lineData = data;

  if (data.periods.length > maxLinePoints) {
    // Sample the data to reduce points
    const sampleRate = Math.ceil(data.periods.length / maxLinePoints);
    lineData = {
      periods: [],
      shannon: [],
      simpson: [],
      richness: [],
      evenness: [],
    };

    for (let i = 0; i < data.periods.length; i += sampleRate) {
      lineData.periods.push(data.periods[i]);
      lineData.shannon.push(data.shannon[i]);
      lineData.simpson.push(data.simpson[i]);
      lineData.richness.push(data.richness[i]);
      lineData.evenness.push(data.evenness[i]);
    }

    // Always include the last point
    if ((data.periods.length - 1) % sampleRate !== 0) {
      lineData.periods.push(data.periods[data.periods.length - 1]);
      lineData.shannon.push(data.shannon[data.shannon.length - 1]);
      lineData.simpson.push(data.simpson[data.simpson.length - 1]);
      lineData.richness.push(data.richness[data.richness.length - 1]);
      lineData.evenness.push(data.evenness[data.evenness.length - 1]);
    }
  }

  // Draw Shannon line with sampled data
  ctx.strokeStyle = "#111";
  ctx.lineWidth = 1.5;
  ctx.beginPath();

  lineData.periods.forEach((period, i) => {
    const x = padding.left + (i / (lineData.periods.length - 1)) * width;
    const y =
      padding.top + height - (lineData.shannon[i] / maxShannon) * height * 0.8;

    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Draw Simpson line with sampled data (thinner, gray)
  ctx.strokeStyle = "#666";
  ctx.lineWidth = 1;
  ctx.beginPath();

  lineData.periods.forEach((period, i) => {
    const x = padding.left + (i / (lineData.periods.length - 1)) * width;
    const y = padding.top + height - lineData.simpson[i] * height * 0.8;

    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Draw Richness circles at sampled points (show every 10th point for clarity)
  const circleInterval = Math.max(1, Math.floor(lineData.periods.length / 20));

  for (let i = 0; i < lineData.periods.length; i += circleInterval) {
    const x = padding.left + (i / (lineData.periods.length - 1)) * width;
    const shannonY =
      padding.top + height - (lineData.shannon[i] / maxShannon) * height * 0.8;

    // Circle size based on richness
    const radius = (lineData.richness[i] / maxRichness) * 12 + 3;

    ctx.beginPath();
    ctx.arc(x, shannonY, radius * 0.6, 0, 2 * Math.PI); // Smaller dots (60% of calculated radius)
    ctx.fillStyle = "#111"; // Solid black fill
    ctx.fill();
  }

  // Y-axis labels
  ctx.fillStyle = "#555";
  ctx.font = "9px system-ui, -apple-system, sans-serif";
  ctx.textAlign = "right";

  // Shannon scale
  for (let i = 0; i <= 4; i++) {
    const value = (maxShannon * i) / 4;
    const y = padding.top + height - (i / 4) * height * 0.8;
    ctx.fillText(value.toFixed(1), padding.left - 5, y + 3);
  }

  // X-axis labels (dates) - show 4 labels
  ctx.textAlign = "center";
  const dateInterval = Math.max(1, Math.floor(lineData.periods.length / 3));

  for (let i = 0; i < lineData.periods.length; i += dateInterval) {
    const x = padding.left + (i / (lineData.periods.length - 1)) * width;
    const date = new Date(lineData.periods[i]);
    const label = `${date.getMonth() + 1}/${date.getDate()}`;
    ctx.fillText(label, x, padding.top + height + 15);
  }

  // Legend
  ctx.font = "10px system-ui, -apple-system, sans-serif";
  const legendY = 15;

  ctx.fillStyle = "#111";
  ctx.fillText("Shannon H'", padding.left + 60, legendY);

  ctx.fillStyle = "#666";
  ctx.fillText("Simpson D", padding.left + 140, legendY);

  ctx.fillStyle = "#111";
  ctx.fillText("○ Richness S", padding.left + 220, legendY);
}

// Draw species accumulation curve
function drawAccumulationCurve() {
  const canvas = document.getElementById("accumulation-curve");
  if (!canvas || !window.analysisData.accumulation) return;

  const ctx = canvas.getContext("2d");
  const data = window.analysisData.accumulation;

  // Canvas dimensions
  const padding = { left: 60, right: 30, top: 30, bottom: 45 };
  const width = canvas.width - padding.left - padding.right;
  const height = canvas.height - padding.top - padding.bottom;

  // Clear canvas
  ctx.fillStyle = "#fdfcfa";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Draw Y-axis
  ctx.strokeStyle = "#111";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(padding.left, padding.top);
  ctx.lineTo(padding.left, padding.top + height);
  ctx.stroke();

  // Draw X-axis
  ctx.beginPath();
  ctx.moveTo(padding.left, padding.top + height);
  ctx.lineTo(padding.left + width, padding.top + height);
  ctx.stroke();

  // Y-axis label
  ctx.save();
  ctx.translate(15, padding.top + height / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillStyle = "#555";
  ctx.font = "10px system-ui, -apple-system, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("Number of Species", 0, 0);
  ctx.restore();

  // X-axis label
  ctx.fillStyle = "#555";
  ctx.font = "10px system-ui, -apple-system, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText(
    "Number of Detections",
    padding.left + width / 2,
    canvas.height - 10,
  );

  // Draw accumulation curve
  ctx.strokeStyle = "#111";
  ctx.lineWidth = 1.5;
  ctx.beginPath();

  const maxSpecies = Math.max(...data.species_counts);
  const maxSamples = data.samples.length;

  // Store points for labeling
  const curvePoints = [];

  data.samples.forEach((sample, i) => {
    const x = padding.left + (i / (maxSamples - 1)) * width;
    const y =
      padding.top +
      height -
      (data.species_counts[i] / maxSpecies) * height * 0.9;

    curvePoints.push({ x, y, species: data.species_counts[i], samples: i });

    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.stroke();

  // Add point labels at regular intervals (5-6 points)
  const labelInterval = Math.max(1, Math.floor(maxSamples / 5));
  ctx.fillStyle = "#111";
  ctx.font = "10px system-ui, -apple-system, sans-serif";

  // Track last labeled point to avoid overlap
  let lastLabeledIndex = -1;

  for (let i = 0; i < maxSamples; i += labelInterval) {
    const point = curvePoints[i];
    if (point) {
      // Draw small circle at point
      ctx.beginPath();
      ctx.arc(point.x, point.y, 3, 0, 2 * Math.PI);
      ctx.fillStyle = "#111";
      ctx.fill();

      // Add label above point
      ctx.fillStyle = "#666";
      ctx.textAlign = "center";
      ctx.fillText(`${point.species} sp.`, point.x, point.y - 8);
      ctx.font = "9px system-ui, -apple-system, sans-serif";
      ctx.fillText(`(${point.samples} det.)`, point.x, point.y - 20);
      ctx.font = "10px system-ui, -apple-system, sans-serif";

      lastLabeledIndex = i;
    }
  }

  // Label the final point only if it's not too close to the last labeled point
  if (maxSamples > 0) {
    const lastPoint = curvePoints[curvePoints.length - 1];

    // Check if final point is at least 10% of the width away from last labeled point
    const minDistance = width * 0.1;
    const shouldLabelFinal =
      lastLabeledIndex < 0 ||
      lastPoint.x - curvePoints[lastLabeledIndex].x > minDistance;

    if (shouldLabelFinal) {
      ctx.beginPath();
      ctx.arc(lastPoint.x, lastPoint.y, 3, 0, 2 * Math.PI);
      ctx.fillStyle = "#111";
      ctx.fill();

      ctx.fillStyle = "#666";
      ctx.textAlign = "right";
      ctx.fillText(
        `${lastPoint.species} sp.`,
        lastPoint.x - 5,
        lastPoint.y - 8,
      );
      ctx.font = "9px system-ui, -apple-system, sans-serif";
      ctx.fillText(
        `(${lastPoint.samples} det.)`,
        lastPoint.x - 5,
        lastPoint.y - 20,
      );
    }
  }
}

// Draw beta diversity horizon chart
function drawBetaDiversity() {
  const canvas = document.getElementById("beta-diversity");
  if (!canvas || !window.analysisData.beta_diversity) return;

  const ctx = canvas.getContext("2d");
  const data = window.analysisData.beta_diversity;

  // Canvas dimensions - increased padding to accommodate all labels
  const padding = { left: 60, right: 30, top: 45, bottom: 70 };
  const width = canvas.width - padding.left - padding.right;
  const height = canvas.height - padding.top - padding.bottom;

  // Clear canvas
  ctx.fillStyle = "#fdfcfa";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Draw Y-axis
  ctx.strokeStyle = "#111";
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(padding.left, padding.top);
  ctx.lineTo(padding.left, padding.top + height);
  ctx.stroke();

  // Draw X-axis
  ctx.beginPath();
  ctx.moveTo(padding.left, padding.top + height);
  ctx.lineTo(padding.left + width, padding.top + height);
  ctx.stroke();

  // Y-axis labels
  ctx.fillStyle = "#555";
  ctx.font = "9px system-ui, -apple-system, sans-serif";
  ctx.textAlign = "right";

  for (let i = 0; i <= 4; i++) {
    const value = i * 0.25;
    const y = padding.top + height - (i / 4) * height;
    ctx.fillText(value.toFixed(2), padding.left - 5, y + 3);
  }

  // Y-axis title
  ctx.save();
  ctx.translate(20, padding.top + height / 2);
  ctx.rotate(-Math.PI / 2);
  ctx.fillStyle = "#555";
  ctx.font = "10px system-ui, -apple-system, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("Whittaker β-diversity", 0, 0);
  ctx.restore();

  // Draw turnover rate bars with labels
  const maxTurnover = Math.max(...data.turnover_rates, 0.1); // Ensure minimum scale
  const barWidth = width / data.periods.length;

  data.periods.forEach((period, i) => {
    const x = padding.left + i * barWidth;
    const barHeight = (data.turnover_rates[i] / maxTurnover) * height * 0.8;
    const y = padding.top + height - barHeight;
    const barActualWidth = barWidth * 0.7;
    const barX = x + (barWidth - barActualWidth) / 2;

    // Bar color based on turnover rate
    const intensity = data.turnover_rates[i];
    if (intensity > 0.6) ctx.fillStyle = "rgba(200, 0, 0, 0.4)";
    else if (intensity > 0.3) ctx.fillStyle = "rgba(180, 180, 0, 0.4)";
    else ctx.fillStyle = "rgba(0, 100, 0, 0.4)";

    ctx.fillRect(barX, y, barActualWidth, barHeight);

    // Value label on top of bar
    ctx.fillStyle = "#111";
    ctx.font = "11px system-ui, -apple-system, sans-serif";
    ctx.textAlign = "center";
    const value = data.turnover_rates[i].toFixed(2);
    ctx.fillText(value, barX + barActualWidth / 2, y - 5);

    // Period label below - no rotation
    const date = new Date(period);
    const label = `${date.getMonth() + 1}/${date.getDate()}`;
    ctx.fillStyle = "#555";
    ctx.font = "9px system-ui, -apple-system, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(label, barX + barActualWidth / 2, padding.top + height + 15);

    // Species change indicators
    if (data.species_gained && data.species_lost) {
      ctx.font = "9px system-ui, -apple-system, sans-serif";
      ctx.textAlign = "center";
      const changeY = padding.top + height + 35;

      ctx.fillStyle = "green";
      ctx.fillText(
        `+${data.species_gained[i]}`,
        barX + barActualWidth / 2 - 15,
        changeY,
      );

      ctx.fillStyle = "red";
      ctx.fillText(
        `-${data.species_lost[i]}`,
        barX + barActualWidth / 2 + 15,
        changeY,
      );
    }
  });

  // X-axis label
  ctx.fillStyle = "#555";
  ctx.font = "10px system-ui, -apple-system, sans-serif";
  ctx.textAlign = "center";
  ctx.fillText("Time Windows", padding.left + width / 2, canvas.height - 20);
}

// Draw weather correlation scatter plots
function drawWeatherCorrelations() {
  const correlations = [
    {
      id: "temp-correlation",
      label: "Temperature (°C)",
      data: "temperature",
      color: "#d2691e",
    },
    {
      id: "humidity-correlation",
      label: "Humidity (%)",
      data: "humidity",
      color: "#4682b4",
    },
    {
      id: "wind-correlation",
      label: "Wind Speed (m/s)",
      data: "wind_speed",
      color: "#2e8b57",
    },
  ];

  correlations.forEach((corr) => {
    const canvas = document.getElementById(corr.id);
    if (!canvas || !window.analysisData.weather) return;

    const ctx = canvas.getContext("2d");
    const weatherData = window.analysisData.weather;

    // Canvas dimensions
    const padding = { left: 40, right: 20, top: 30, bottom: 40 };
    const width = canvas.width - padding.left - padding.right;
    const height = canvas.height - padding.top - padding.bottom;

    // Clear canvas
    ctx.fillStyle = "#fdfcfa";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    // Draw axes
    ctx.strokeStyle = "#ccc";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padding.left, padding.top);
    ctx.lineTo(padding.left, padding.top + height);
    ctx.lineTo(padding.left + width, padding.top + height);
    ctx.stroke();

    // Title
    ctx.fillStyle = "#555";
    ctx.font = "11px system-ui, -apple-system, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(corr.label, canvas.width / 2, 15);

    // Axis labels
    ctx.font = "9px system-ui, -apple-system, sans-serif";
    ctx.fillText("Detections", canvas.width / 2, canvas.height - 5);

    ctx.save();
    ctx.translate(10, padding.top + height / 2);
    ctx.rotate(-Math.PI / 2);
    ctx.textAlign = "center";
    ctx.fillText(corr.label.split(" ")[0], 0, 0);
    ctx.restore();

    // If we have detailed weather data, plot it
    if (
      weatherData.hours &&
      weatherData.detection_counts &&
      weatherData.weather_variables
    ) {
      const weatherVar = weatherData.weather_variables[corr.data];
      if (weatherVar) {
        const maxDetections = Math.max(...weatherData.detection_counts);
        // Filter out null values for min/max calculations
        const validWeatherValues = weatherVar.filter((v) => v != null);
        if (validWeatherValues.length === 0) return; // Skip if no valid data

        const maxWeather = Math.max(...validWeatherValues);
        const minWeather = Math.min(...validWeatherValues);

        // Plot points (skip null values)
        ctx.fillStyle = corr.color + "66"; // Add transparency
        weatherData.hours.forEach((hour, i) => {
          // Skip null or undefined weather values
          if (weatherVar[i] == null) return;

          const x =
            padding.left +
            (weatherData.detection_counts[i] / maxDetections) * width;
          const y =
            padding.top +
            height -
            ((weatherVar[i] - minWeather) / (maxWeather - minWeather)) * height;
          ctx.beginPath();
          ctx.arc(x, y, 2, 0, 2 * Math.PI);
          ctx.fill();
        });

        // Add trend line if correlation is significant
        const correlation = weatherData.correlations[corr.data];
        if (Math.abs(correlation) > 0.1) {
          // Simple linear regression visualization
          ctx.save();
          // Clip to chart area to prevent drawing outside bounds
          ctx.beginPath();
          ctx.rect(padding.left, padding.top, width, height);
          ctx.clip();

          ctx.strokeStyle = corr.color;
          ctx.lineWidth = 1.5;
          ctx.setLineDash([5, 5]);
          ctx.beginPath();

          // Calculate simple trend line endpoints
          const avgDetections =
            weatherData.detection_counts.reduce((a, b) => a + b, 0) /
            weatherData.detection_counts.length;
          const avgWeather =
            weatherVar.reduce((a, b) => a + b, 0) / weatherVar.length;

          // Draw a line through the average point with slope based on correlation
          const slope =
            (correlation * (maxWeather - minWeather)) / maxDetections;
          const intercept = avgWeather - slope * avgDetections;

          // Calculate y values at x boundaries
          const y1 =
            padding.top +
            height -
            ((intercept - minWeather) / (maxWeather - minWeather)) * height;
          const y2 =
            padding.top +
            height -
            ((intercept + slope * maxDetections - minWeather) /
              (maxWeather - minWeather)) *
              height;

          ctx.moveTo(padding.left, y1);
          ctx.lineTo(padding.left + width, y2);
          ctx.stroke();
          ctx.setLineDash([]);
          ctx.restore();
        }
      }
    }
  });
}

// Draw activity heatmap
function drawActivityHeatmap() {
  const canvas = document.getElementById("activity-heatmap");
  if (!canvas || !window.analysisData.temporal_patterns) return;

  const ctx = canvas.getContext("2d");
  const data = window.analysisData.temporal_patterns.heatmap;

  // Canvas dimensions
  const padding = { left: 50, right: 20, top: 20, bottom: 30 };
  const cellWidth = (canvas.width - padding.left - padding.right) / 24;
  const cellHeight = (canvas.height - padding.top - padding.bottom) / 7;

  // Clear canvas
  ctx.fillStyle = "#fdfcfa";
  ctx.fillRect(0, 0, canvas.width, canvas.height);

  // Days of week
  const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  // Find max value for normalization
  const maxValue = Math.max(...data.flat());

  // Draw cells
  data.forEach((dayData, dayIndex) => {
    dayData.forEach((value, hourIndex) => {
      const x = padding.left + hourIndex * cellWidth;
      const y = padding.top + dayIndex * cellHeight;

      // Cell color based on intensity
      const intensity = maxValue > 0 ? value / maxValue : 0;
      const grayValue = Math.floor(255 - intensity * 100);
      ctx.fillStyle = `rgb(${grayValue}, ${grayValue}, ${grayValue})`;
      ctx.fillRect(x, y, cellWidth - 1, cellHeight - 1);
    });
  });

  // Draw day labels
  ctx.fillStyle = "#555";
  ctx.font = "10px system-ui, -apple-system, sans-serif";
  ctx.textAlign = "right";
  days.forEach((day, i) => {
    const y = padding.top + i * cellHeight + cellHeight / 2 + 3;
    ctx.fillText(day, padding.left - 5, y);
  });

  // Draw hour labels (every 3 hours)
  ctx.textAlign = "center";
  for (let hour = 0; hour < 24; hour += 3) {
    const x = padding.left + hour * cellWidth + cellWidth / 2;
    ctx.fillText(hour.toString(), x, padding.top + 7 * cellHeight + 15);
  }

  // Title
  ctx.fillStyle = "#222";
  ctx.font = "9px system-ui, -apple-system, sans-serif";
  ctx.textAlign = "left";
  ctx.fillText(
    "Hour of Day",
    padding.left + 12 * cellWidth - 30,
    canvas.height - 5,
  );
}

// Update weather correlation values in the DOM
function updateWeatherCorrelationValues() {
  if (
    !window.analysisData ||
    !window.analysisData.weather ||
    !window.analysisData.weather.correlations
  ) {
    return;
  }

  const correlations = window.analysisData.weather.correlations;

  // Update temperature correlation
  const tempElements = document.querySelectorAll(
    "#weather-section .correlation-value",
  );
  if (tempElements.length >= 1 && correlations.temperature !== undefined) {
    tempElements[0].textContent = `r = ${correlations.temperature.toFixed(3)}`;
    // Update class based on strength
    tempElements[0].className = "correlation-value correlation-weak";
    if (Math.abs(correlations.temperature) > 0.5) {
      tempElements[0].className = "correlation-value correlation-strong";
    } else if (Math.abs(correlations.temperature) > 0.3) {
      tempElements[0].className = "correlation-value correlation-moderate";
    }
  }

  // Update humidity correlation
  if (tempElements.length >= 2 && correlations.humidity !== undefined) {
    tempElements[1].textContent = `r = ${correlations.humidity.toFixed(3)}`;
    tempElements[1].className = "correlation-value correlation-weak";
    if (Math.abs(correlations.humidity) > 0.5) {
      tempElements[1].className = "correlation-value correlation-strong";
    } else if (Math.abs(correlations.humidity) > 0.3) {
      tempElements[1].className = "correlation-value correlation-moderate";
    }
  }

  // Update wind speed correlation
  if (tempElements.length >= 3 && correlations.wind_speed !== undefined) {
    tempElements[2].textContent = `r = ${correlations.wind_speed.toFixed(3)}`;
    tempElements[2].className = "correlation-value correlation-weak";
    if (Math.abs(correlations.wind_speed) > 0.5) {
      tempElements[2].className = "correlation-value correlation-strong";
    } else if (Math.abs(correlations.wind_speed) > 0.3) {
      tempElements[2].className = "correlation-value correlation-moderate";
    }
  }
}

// Populate similarity matrix from data
function populateSimilarityMatrix() {
  const container = document.getElementById("similarity-matrix-container");
  if (!container || !window.analysisData || !window.analysisData.similarity) {
    return;
  }

  const data = window.analysisData.similarity;

  // Clear existing content
  container.innerHTML = "";

  // Set up grid columns
  const numCols = data.labels.length + 1; // +1 for header column
  container.style.gridTemplateColumns = `100px repeat(${data.labels.length}, 1fr)`;

  // Add empty top-left cell
  const emptyCell = document.createElement("div");
  emptyCell.className = "matrix-cell";
  container.appendChild(emptyCell);

  // Add header row
  data.labels.forEach((label) => {
    const cell = document.createElement("div");
    cell.className = "matrix-cell font-normal";
    // Handle i18n for "Period X" labels
    if (label.startsWith("Period ")) {
      const num = label.substring(7);
      cell.textContent = `Period ${num}`;
    } else {
      cell.textContent = label;
    }
    container.appendChild(cell);
  });

  // Add data rows
  data.matrix.forEach((row, rowIndex) => {
    // Add row header
    const rowHeader = document.createElement("div");
    rowHeader.className = "matrix-cell text-right font-normal";
    const label = data.labels[rowIndex];
    if (label.startsWith("Period ")) {
      const num = label.substring(7);
      rowHeader.textContent = `Period ${num}`;
    } else {
      rowHeader.textContent = label;
    }
    container.appendChild(rowHeader);

    // Add data cells
    row.forEach((cellData) => {
      const cell = document.createElement("div");
      cell.className = `matrix-cell intensity-${cellData.intensity}`;
      cell.textContent = cellData.display;
      container.appendChild(cell);
    });
  });

  // Update subtitle with period info if available
  if (data.period_info) {
    const subtitle = document.getElementById("similarity-subtitle");
    if (subtitle) {
      subtitle.innerHTML = `Jaccard similarity coefficients between time periods · Values shown as percentages for similarity >50%<br>
        <span class="text-xs">Comparing ${data.period_info.count} periods of ${data.period_info.size_days} days each · Total period: ${data.period_info.total_days} days</span>`;
    }
  }
}

// Export functions for global access if needed
window.drawDiversityTimeline = drawDiversityTimeline;
window.drawActivityHeatmap = drawActivityHeatmap;
window.drawAccumulationCurve = drawAccumulationCurve;
window.drawBetaDiversity = drawBetaDiversity;
window.drawWeatherCorrelations = drawWeatherCorrelations;
window.populateSimilarityMatrix = populateSimilarityMatrix;
window.updateAnalysis = updateAnalysis;
// Update metrics summary line with actual data
function updateMetricsSummary() {
  let summaryElement = document.querySelector(".metrics-summary");
  if (!summaryElement) {
    // Create the metrics summary if it doesn't exist
    const controlsDiv = document.querySelector(".analysis-controls");
    if (controlsDiv && window.analysisData && window.analysisData.diversity) {
      const metricsDiv = document.createElement("div");
      metricsDiv.className = "metrics-summary";
      controlsDiv.insertAdjacentElement("afterend", metricsDiv);
      summaryElement = metricsDiv;
    } else {
      return;
    }
  }

  if (!window.analysisData || !window.analysisData.diversity) {
    summaryElement.style.display = "none";
    return;
  }

  const diversity = window.analysisData.diversity;
  const lastIndex = diversity.shannon.length - 1;

  let html = `
    Shannon H': <span class="metric-value">${Math.abs(diversity.shannon[lastIndex] || 0).toFixed(4)}</span>`;

  if (
    window.analysisData.diversity_comparison &&
    window.analysisData.diversity_comparison.changes
  ) {
    const changes = window.analysisData.diversity_comparison.changes;
    if (changes.shannon_change) {
      html += ` <span class="metric-change change-${changes.shannon_change.trend}">(${changes.shannon_change.value.toFixed(2)})</span>`;
    }
  }

  html += ` · Simpson D: <span class="metric-value">${Math.abs(diversity.simpson[lastIndex] || 0).toFixed(4)}</span>`;

  if (
    window.analysisData.diversity_comparison &&
    window.analysisData.diversity_comparison.changes
  ) {
    const changes = window.analysisData.diversity_comparison.changes;
    if (changes.simpson_change) {
      html += ` <span class="metric-change change-${changes.simpson_change.trend}">(${changes.simpson_change.value.toFixed(2)})</span>`;
    }
  }

  html += ` · Richness S: <span class="metric-value">${Math.round(diversity.richness[lastIndex] || 0)}</span>`;

  if (
    window.analysisData.diversity_comparison &&
    window.analysisData.diversity_comparison.changes
  ) {
    const changes = window.analysisData.diversity_comparison.changes;
    if (changes.richness_change) {
      html += ` <span class="metric-change change-${changes.richness_change.trend}">(${Math.round(changes.richness_change.value)})</span>`;
    }
  }

  html += ` · Evenness J': <span class="metric-value">${(diversity.evenness[lastIndex] || 0).toFixed(4)}</span>`;

  if (
    window.analysisData.diversity_comparison &&
    window.analysisData.diversity_comparison.changes
  ) {
    const changes = window.analysisData.diversity_comparison.changes;
    if (changes.evenness_change) {
      html += ` <span class="metric-change change-${changes.evenness_change.trend}">(${changes.evenness_change.value.toFixed(2)})</span>`;
    }
  }

  summaryElement.innerHTML = html;
  summaryElement.style.display = "block";
}

window.updateWeatherCorrelationValues = updateWeatherCorrelationValues;
window.updateMetricsSummary = updateMetricsSummary;
