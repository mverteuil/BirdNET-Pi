/**
 * Analysis JavaScript - Data visualization using Plotly.js
 */

// Global state for period bounds
let primaryPeriodBounds = null;
let comparisonEnabled = false;

// Callback for primary period selector changes
function onPrimaryPeriodChange(bounds) {
  console.log("[Analysis] Primary period changed:", bounds);
  primaryPeriodBounds = bounds;
  updateURL();
  loadAnalysisData();
}

// Update URL with current state
function updateURL() {
  const params = new URLSearchParams();
  if (primaryPeriodBounds) {
    params.set("period", primaryPeriodBounds.period_type);
    if (primaryPeriodBounds.start_date) {
      params.set("date", primaryPeriodBounds.start_date);
    }
  }
  if (comparisonEnabled) {
    params.set("comparison", "previous");
  }
  const newUrl = params.toString()
    ? `${window.location.pathname}?${params.toString()}`
    : window.location.pathname;
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
  updateURL();
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
    window.analysisData = data.analyses || {};
    if (data.dates) {
      window.analysisData.dates = data.dates;
    }

    console.log(
      "[Analysis] Data loaded, keys:",
      Object.keys(window.analysisData),
    );

    analysisLoading.style.display = "none";
    analysisContent.style.display = "block";

    initializeAnalysis();
  } catch (error) {
    console.error("[Analysis] Error fetching data:", error);
    analysisLoading.style.display = "none";
    analysisContent.style.display = "block";
    showErrorState(error.message);
  }
}

// Initialize analysis page
async function initAnalysisPage() {
  console.log("[Analysis] Initializing analysis page...");
  if (!window.analysisConfig) {
    console.log("[Analysis] Not on analysis page");
    return;
  }
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
    initAnalysisPage();
  }
});

// Initialize on DOM ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", initAnalysisPage);
} else {
  initAnalysisPage();
}

// Initialize all analysis visualizations
function initializeAnalysis() {
  console.log("[Analysis] Starting chart initialization...");
  let chartsDrawn = 0;

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
  if (document.getElementById("similarity-matrix-container")) {
    console.log("[Analysis] Populating similarity matrix...");
    populateSimilarityMatrix();
    chartsDrawn++;
  }

  updateWeatherCorrelationValues();
  updateMetricsSummary();

  console.log(
    `[Analysis] Initialization complete. ${chartsDrawn} charts drawn.`,
  );
}

// Plotly configuration for consistent styling
const plotlyConfig = {
  displayModeBar: false,
  responsive: true,
};

const plotlyLayout = {
  paper_bgcolor: "#fdfcfa",
  plot_bgcolor: "#fdfcfa",
  font: {
    family: "system-ui, -apple-system, sans-serif",
    size: 11,
    color: "#555",
  },
  margin: { l: 50, r: 30, t: 20, b: 40 },
  hovermode: "closest",
  showlegend: true,
  legend: {
    orientation: "h",
    y: 1.1,
    x: 0,
  },
};

// Draw diversity timeline using Plotly
function drawDiversityTimeline() {
  const element = document.getElementById("diversity-timeline");
  if (!element || !window.analysisData.diversity) return;

  const data = window.analysisData.diversity;

  // Sample data for cleaner rendering if too many points
  let displayData = data;
  if (data.periods.length > 100) {
    const sampleRate = Math.ceil(data.periods.length / 100);
    displayData = {
      periods: [],
      shannon: [],
      simpson: [],
      richness: [],
    };
    for (let i = 0; i < data.periods.length; i += sampleRate) {
      displayData.periods.push(data.periods[i]);
      displayData.shannon.push(data.shannon[i]);
      displayData.simpson.push(data.simpson[i]);
      displayData.richness.push(data.richness[i]);
    }
  }

  // Calculate marker sizes based on richness (proportional sizing)
  const maxRichness = Math.max(...displayData.richness);
  const markerSizes = displayData.richness.map(
    (r) => (r / maxRichness) * 12 + 3,
  );

  const traces = [
    {
      x: displayData.periods,
      y: displayData.shannon,
      name: "Shannon H'",
      type: "scatter",
      mode: "lines",
      line: { color: "#111", width: 1.5 },
      hovertemplate: "Shannon H': %{y:.3f}<extra></extra>",
    },
    {
      x: displayData.periods,
      y: displayData.simpson,
      name: "Simpson D",
      type: "scatter",
      mode: "lines",
      line: { color: "#666", width: 1 },
      hovertemplate: "Simpson D: %{y:.3f}<extra></extra>",
    },
    {
      x: displayData.periods,
      y: displayData.shannon,
      name: "Richness S",
      type: "scatter",
      mode: "markers",
      marker: {
        color: "#111",
        size: markerSizes,
      },
      hovertemplate: "Richness: %{text}<extra></extra>",
      text: displayData.richness,
      showlegend: true,
    },
  ];

  const layout = {
    ...plotlyLayout,
    xaxis: {
      title: "",
      showgrid: false,
      showline: true,
      linecolor: "#111",
      linewidth: 1,
    },
    yaxis: {
      title: "",
      showgrid: false,
      showline: true,
      linecolor: "#111",
      linewidth: 1,
      zeroline: false,
    },
    margin: { l: 40, r: 40, t: 10, b: 30 },
  };

  Plotly.newPlot(element, traces, layout, plotlyConfig);
}

// Draw species accumulation curve
function drawAccumulationCurve() {
  const element = document.getElementById("accumulation-curve");
  if (!element || !window.analysisData.accumulation) return;

  const data = window.analysisData.accumulation;

  const trace = {
    x: data.samples,
    y: data.species_counts,
    type: "scatter",
    mode: "lines+markers",
    line: { color: "#111", width: 1.5 },
    marker: { color: "#111", size: 3 },
    hovertemplate: "Detections: %{x}<br>Species: %{y}<extra></extra>",
  };

  // Add annotations at regular intervals
  const annotations = [];
  const numLabels = 5;
  const labelInterval = Math.max(
    1,
    Math.floor(data.samples.length / numLabels),
  );

  for (let i = 0; i < data.samples.length; i += labelInterval) {
    annotations.push({
      x: data.samples[i],
      y: data.species_counts[i],
      text: `${data.species_counts[i]} sp.<br>(${data.samples[i]} det.)`,
      showarrow: true,
      arrowhead: 0,
      arrowsize: 0.5,
      arrowwidth: 1,
      arrowcolor: "#666",
      ax: 0,
      ay: -30,
      font: { size: 9, color: "#666" },
      bgcolor: "rgba(255,255,255,0.8)",
      borderpad: 2,
    });
  }

  // Add final point if not already labeled
  const lastIdx = data.samples.length - 1;
  if (lastIdx % labelInterval !== 0) {
    annotations.push({
      x: data.samples[lastIdx],
      y: data.species_counts[lastIdx],
      text: `${data.species_counts[lastIdx]} sp.<br>(${data.samples[lastIdx]} det.)`,
      showarrow: true,
      arrowhead: 0,
      arrowsize: 0.5,
      arrowwidth: 1,
      arrowcolor: "#666",
      ax: -20,
      ay: -30,
      font: { size: 9, color: "#666" },
      bgcolor: "rgba(255,255,255,0.8)",
      borderpad: 2,
    });
  }

  const layout = {
    ...plotlyLayout,
    xaxis: {
      title: "Number of Detections",
      showgrid: false,
      showline: true,
      linecolor: "#111",
      linewidth: 1,
    },
    yaxis: {
      title: "Number of Species",
      showgrid: false,
      showline: true,
      linecolor: "#111",
      linewidth: 1,
    },
    showlegend: false,
    annotations: annotations,
    margin: { l: 40, r: 30, t: 30, b: 40 },
  };

  Plotly.newPlot(element, [trace], layout, plotlyConfig);
}

// Draw beta diversity chart
function drawBetaDiversity() {
  const element = document.getElementById("beta-diversity");
  if (!element || !window.analysisData.beta_diversity) return;

  const data = window.analysisData.beta_diversity;

  // Color bars based on turnover intensity
  const colors = data.turnover_rates.map((rate) => {
    if (rate > 0.6) return "rgba(200, 0, 0, 0.6)";
    if (rate > 0.3) return "rgba(180, 180, 0, 0.6)";
    return "rgba(0, 100, 0, 0.6)";
  });

  const trace = {
    x: data.periods,
    y: data.turnover_rates,
    type: "bar",
    marker: { color: colors },
    hovertemplate: "β-diversity: %{y:.2f}<extra></extra>",
  };

  const layout = {
    ...plotlyLayout,
    xaxis: { title: "Time Windows", showgrid: false },
    yaxis: {
      title: "Whittaker β-diversity",
      showgrid: true,
      gridcolor: "#eee",
      range: [0, 1],
    },
    showlegend: false,
  };

  Plotly.newPlot(element, [trace], layout, plotlyConfig);
}

// Draw weather correlation scatter plots
function drawWeatherCorrelations() {
  const correlations = [
    {
      id: "temp-correlation",
      data: "temperature",
      color: "#d2691e",
      name: "Temperature",
    },
    {
      id: "humidity-correlation",
      data: "humidity",
      color: "#4682b4",
      name: "Humidity",
    },
    {
      id: "wind-correlation",
      data: "wind_speed",
      color: "#2e8b57",
      name: "Wind Speed",
    },
  ];

  correlations.forEach((corr) => {
    const element = document.getElementById(corr.id);
    if (!element || !window.analysisData.weather) return;

    const weatherData = window.analysisData.weather;
    const weatherVar = weatherData.weather_variables[corr.data];
    if (!weatherVar) return;

    // Filter out null values
    const validIndices = [];
    const xValues = [];
    const yValues = [];

    weatherData.detection_counts.forEach((count, i) => {
      if (weatherVar[i] != null) {
        validIndices.push(i);
        xValues.push(count);
        yValues.push(weatherVar[i]);
      }
    });

    if (validIndices.length === 0) return;

    const trace = {
      x: xValues,
      y: yValues,
      type: "scatter",
      mode: "markers",
      marker: {
        color: corr.color,
        size: 5,
        opacity: 0.6,
      },
      hovertemplate:
        "Detections: %{x}<br>" + corr.name + ": %{y:.1f}<extra></extra>",
    };

    const layout = {
      paper_bgcolor: "#fdfcfa",
      plot_bgcolor: "#fdfcfa",
      font: {
        family: "system-ui, -apple-system, sans-serif",
        size: 9,
        color: "#555",
      },
      margin: { l: 40, r: 20, t: 10, b: 35 },
      xaxis: {
        title: "Detections",
        showgrid: true,
        gridcolor: "#eee",
      },
      yaxis: {
        title: corr.name,
        showgrid: true,
        gridcolor: "#eee",
      },
      showlegend: false,
      hovermode: "closest",
    };

    Plotly.newPlot(element, [trace], layout, plotlyConfig);
  });
}

// Draw activity heatmap
function drawActivityHeatmap() {
  const element = document.getElementById("activity-heatmap");
  if (!element || !window.analysisData.temporal_patterns) return;

  const data = window.analysisData.temporal_patterns.heatmap;
  const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  const trace = {
    z: data,
    x: Array.from({ length: 24 }, (_, i) => i),
    y: days,
    type: "heatmap",
    colorscale: [
      [0, "#ffffff"],
      [0.2, "#e8e8e8"],
      [0.4, "#d0d0d0"],
      [0.6, "#a0a0a0"],
      [0.8, "#707070"],
      [1, "#404040"],
    ],
    hovertemplate: "Day: %{y}<br>Hour: %{x}<br>Detections: %{z}<extra></extra>",
    showscale: false,
  };

  const layout = {
    ...plotlyLayout,
    xaxis: {
      title: "Hour of Day",
      showgrid: false,
      tickmode: "linear",
      tick0: 0,
      dtick: 3,
    },
    yaxis: {
      title: "",
      showgrid: false,
    },
    margin: { l: 50, r: 20, t: 20, b: 40 },
  };

  Plotly.newPlot(element, [trace], layout, plotlyConfig);
}

// Update weather correlation values in DOM
function updateWeatherCorrelationValues() {
  if (
    !window.analysisData ||
    !window.analysisData.weather ||
    !window.analysisData.weather.correlations
  ) {
    return;
  }

  const correlations = window.analysisData.weather.correlations;
  const tempElements = document.querySelectorAll(
    "#weather-section .correlation-value",
  );

  const updateCorrelation = (element, value) => {
    element.textContent = `r = ${value.toFixed(3)}`;
    element.className = "correlation-value correlation-weak";
    if (Math.abs(value) > 0.5) {
      element.className = "correlation-value correlation-strong";
    } else if (Math.abs(value) > 0.3) {
      element.className = "correlation-value correlation-moderate";
    }
  };

  if (tempElements.length >= 1 && correlations.temperature !== undefined) {
    updateCorrelation(tempElements[0], correlations.temperature);
  }
  if (tempElements.length >= 2 && correlations.humidity !== undefined) {
    updateCorrelation(tempElements[1], correlations.humidity);
  }
  if (tempElements.length >= 3 && correlations.wind_speed !== undefined) {
    updateCorrelation(tempElements[2], correlations.wind_speed);
  }
}

// Populate similarity matrix
function populateSimilarityMatrix() {
  const container = document.getElementById("similarity-matrix-container");
  if (!container || !window.analysisData || !window.analysisData.similarity) {
    return;
  }

  const data = window.analysisData.similarity;
  container.innerHTML = "";

  const numCols = data.labels.length + 1;
  container.style.gridTemplateColumns = `100px repeat(${data.labels.length}, 1fr)`;

  const emptyCell = document.createElement("div");
  emptyCell.className = "matrix-cell";
  container.appendChild(emptyCell);

  data.labels.forEach((label) => {
    const cell = document.createElement("div");
    cell.className = "matrix-cell font-normal";
    if (label.startsWith("Period ")) {
      const num = label.substring(7);
      cell.textContent = `Period ${num}`;
    } else {
      cell.textContent = label;
    }
    container.appendChild(cell);
  });

  data.matrix.forEach((row, rowIndex) => {
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

    row.forEach((cellData) => {
      const cell = document.createElement("div");
      cell.className = `matrix-cell intensity-${cellData.intensity}`;
      cell.textContent = cellData.display;
      container.appendChild(cell);
    });
  });

  if (data.period_info) {
    const subtitle = document.getElementById("similarity-subtitle");
    if (subtitle) {
      subtitle.innerHTML = `Jaccard similarity coefficients between time periods · Values shown as percentages for similarity >50%<br>
        <span class="text-xs">Comparing ${data.period_info.count} periods of ${data.period_info.size_days} days each · Total period: ${data.period_info.total_days} days</span>`;
    }
  }
}

// Update metrics summary
function updateMetricsSummary() {
  let summaryElement = document.querySelector(".metrics-summary");
  if (!summaryElement) {
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

  let html = `Shannon H': <span class="metric-value">${Math.abs(diversity.shannon[lastIndex] || 0).toFixed(4)}</span>`;

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

// Export functions
window.drawDiversityTimeline = drawDiversityTimeline;
window.drawActivityHeatmap = drawActivityHeatmap;
window.drawAccumulationCurve = drawAccumulationCurve;
window.drawBetaDiversity = drawBetaDiversity;
window.drawWeatherCorrelations = drawWeatherCorrelations;
window.populateSimilarityMatrix = populateSimilarityMatrix;
window.updateWeatherCorrelationValues = updateWeatherCorrelationValues;
window.updateMetricsSummary = updateMetricsSummary;
