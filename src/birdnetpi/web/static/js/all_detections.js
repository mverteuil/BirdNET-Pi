/**
 * All Detections JavaScript - Detection filtering and period management
 */

// Global state for period bounds
let currentPeriodBounds = null;

// Callback for period selector changes
function onDetectionsPeriodChange(bounds) {
  currentPeriodBounds = bounds;

  // Reset to first page when period changes
  currentPage = 1;

  // Reload data
  loadDetections(1);
  loadSpeciesList();
}

// Helper function to clone and populate a template
function cloneTemplate(templateId) {
  const template = document.getElementById(templateId);
  if (!template) return null;
  return template.content
    ? template.content.cloneNode(true)
    : template.cloneNode(true);
}

// Migration: Now using global _() function from i18n.js
// The getI18nMessage function is provided by i18n-compat.js for backward compatibility

// Handler called when filters change - reload data
function onFiltersChanged() {
  // Reload detections and species list with new filters
  // (updateURL() is called by loadDetections())
  loadDetections(1);
  loadSpeciesList();
}

// Family filter change handler
function onFamilyChange() {
  const familySelect = document.getElementById("family-filter");
  taxonomicFilters.family = familySelect.value || null;
  taxonomicFilters.genus = null;
  taxonomicFilters.species = null;

  loadGenera();
  updateActiveFilters();
  onFiltersChanged();
}

// Genus filter change handler
function onGenusChange() {
  const genusSelect = document.getElementById("genus-filter");
  taxonomicFilters.genus = genusSelect.value || null;
  taxonomicFilters.species = null;

  loadSpecies();
  updateActiveFilters();
  onFiltersChanged();
}

// Species filter change handler
function onSpeciesChange() {
  const speciesSelect = document.getElementById("species-filter");
  taxonomicFilters.species = speciesSelect.value || null;

  updateActiveFilters();
  onFiltersChanged();
}

// Confidence filter change handler
function onConfidenceChange() {
  const confidenceSelect = document.getElementById("confidence-filter");
  taxonomicFilters.minConfidence = parseFloat(confidenceSelect.value) || 0.7;

  updateActiveFilters();
  onFiltersChanged();
}

function updateSpeciesCount() {
  const visibleRows = document.querySelectorAll(".detection-row");
  const uniqueSpecies = new Set();
  let totalDetections = 0;

  visibleRows.forEach((row) => {
    // Only count visible rows
    if (row.style.display !== "none") {
      if (row.dataset.species) {
        uniqueSpecies.add(row.dataset.species);
      }
      totalDetections++;
    }
  });

  document.getElementById("species-count").textContent = uniqueSpecies.size;
  document.getElementById("total-detection-count").textContent =
    totalDetections;
}

// Period selection
function setPeriod(period) {
  // Update URL with new period
  const url = new URL(window.location);
  url.searchParams.set("period", period);

  // If there's a date parameter and we're switching to relative period, remove it
  if (period !== "date") {
    url.searchParams.delete("date");
  }

  window.location.href = url.toString();
}

// Audio playback
let currentAudio = null;
let currentButton = null;

function playAudio(detectionId, audioFileId, button) {
  // Stop current audio if playing
  if (currentAudio && currentButton) {
    currentAudio.pause();
    currentButton.classList.remove("playing");
  }

  // If clicking the same button, just stop
  if (currentButton === button) {
    currentAudio = null;
    currentButton = null;
    return;
  }

  // Start loading
  button.classList.add("loading");
  button.disabled = true;

  // Use the audio file ID directly for the endpoint
  const audio = new Audio(`/api/audio/${audioFileId}`);

  audio.addEventListener("canplay", () => {
    button.classList.remove("loading");
    button.classList.add("playing");
    button.disabled = false;
    audio.play();
  });

  audio.addEventListener("ended", () => {
    button.classList.remove("playing");
    currentAudio = null;
    currentButton = null;
  });

  audio.addEventListener("error", () => {
    button.classList.remove("loading");
    button.disabled = false;
    const statusDiv = document.getElementById(`audio-status-${detectionId}`);
    if (statusDiv) {
      statusDiv.textContent = _("audio-not-available");
      statusDiv.classList.add("audio-missing");
    }
    console.error("Failed to load audio");
  });

  currentAudio = audio;
  currentButton = button;
}

// Period navigation
function goToPreviousPeriod() {
  const url = new URL(window.location);
  const currentPeriod = url.searchParams.get("period") || "today";
  const currentDate = url.searchParams.get("date");

  if (currentPeriod === "date" && currentDate) {
    // Navigate to previous date
    const date = new Date(currentDate);
    date.setDate(date.getDate() - 1);
    url.searchParams.set("date", date.toISOString().split("T")[0]);
  } else if (currentPeriod === "today") {
    // Go to yesterday
    const yesterday = new Date();
    yesterday.setDate(yesterday.getDate() - 1);
    url.searchParams.set("period", "date");
    url.searchParams.set("date", yesterday.toISOString().split("T")[0]);
  } else if (currentPeriod === "week") {
    // Go to previous week
    const weekAgo = new Date();
    weekAgo.setDate(weekAgo.getDate() - 7);
    url.searchParams.set("period", "date");
    url.searchParams.set("date", weekAgo.toISOString().split("T")[0]);
  }

  window.location.href = url.toString();
}

function goToNextPeriod() {
  const url = new URL(window.location);
  const currentPeriod = url.searchParams.get("period") || "today";
  const currentDate = url.searchParams.get("date");

  if (currentPeriod === "date" && currentDate) {
    // Navigate to next date
    const date = new Date(currentDate);
    const tomorrow = new Date(date);
    tomorrow.setDate(date.getDate() + 1);
    const today = new Date();

    if (tomorrow <= today) {
      url.searchParams.set("date", tomorrow.toISOString().split("T")[0]);
    } else {
      // Can't go to future
      return;
    }
  }

  window.location.href = url.toString();
}

// Date picker
function openDatePicker() {
  const datePicker = document.getElementById("date-picker-modal");
  const dateInput = document.getElementById("date-input");

  // Set current date or today
  const url = new URL(window.location);
  const currentDate =
    url.searchParams.get("date") || new Date().toISOString().split("T")[0];
  dateInput.value = currentDate;

  // Set max date to today
  dateInput.max = new Date().toISOString().split("T")[0];

  datePicker.style.display = "block";
}

function closeDatePicker() {
  document.getElementById("date-picker-modal").style.display = "none";
}

function goToSelectedDate() {
  const dateInput = document.getElementById("date-input");
  if (dateInput.value) {
    const url = new URL(window.location);
    url.searchParams.set("period", "date");
    url.searchParams.set("date", dateInput.value);
    window.location.href = url.toString();
  }
}

// Global variables for state management
let currentPage = 1;
let currentPeriod = "today";
let selectedDate = null; // For date picker mode
let detectionsSortColumn = "timestamp";
let detectionsSortDirection = "desc";
let speciesSortColumn = "count";
let speciesSortDirection = "desc";
let searchTerm = "";

// Species pagination
let allSpeciesData = [];
let speciesCurrentPage = 1;
const speciesPageSize = 10; // Determined by trial and error for best fit

// Main data loading function
async function loadDetections(page = 1) {
  currentPage = page;

  // Build query parameters
  const searchParams = new URLSearchParams({
    page: page,
    per_page: 20,
    sort_by: detectionsSortColumn,
    sort_order: detectionsSortDirection,
  });

  // Add period bounds if available (from new period selector)
  if (currentPeriodBounds) {
    searchParams.append("start_date", currentPeriodBounds.start_date);
    searchParams.append("end_date", currentPeriodBounds.end_date);
  } else {
    // Fallback to old period parameter for initial load
    searchParams.append("period", currentPeriod || "day");
  }

  // Add taxonomic filters
  if (taxonomicFilters.family) {
    searchParams.append("family", taxonomicFilters.family);
  }
  if (taxonomicFilters.genus) {
    searchParams.append("genus", taxonomicFilters.genus);
  }
  if (taxonomicFilters.species) {
    searchParams.append("species", taxonomicFilters.species);
  }
  if (taxonomicFilters.minConfidence && taxonomicFilters.minConfidence > 0.7) {
    searchParams.append("min_confidence", taxonomicFilters.minConfidence);
  }

  // Show inline loading indicator
  const detectionsList = document.getElementById("detections-list");
  detectionsList.innerHTML =
    '<tr><td colspan="5" class="loading-indicator">' +
    _("loading-detections") +
    "</td></tr>";

  try {
    const response = await fetch(`/api/detections/?${searchParams}`);
    const data = await response.json();

    // Render detections table
    if (!data.detections || data.detections.length === 0) {
      detectionsList.innerHTML =
        '<tr><td colspan="5" class="no-data">' +
        _("no-detections-found") +
        "</td></tr>";
    } else {
      detectionsList.innerHTML = data.detections
        .map((d) => {
          let firstIndicator = "";
          if (d.is_first_ever) {
            firstIndicator = "★";
          } else if (d.is_first_in_period) {
            firstIndicator = "●";
          }

          return `
                    <tr class="detection-row" data-species="${d.scientific_name || ""}">
                        <td class="detection-time">${d.time || ""}</td>
                        <td class="species-name">${d.common_name || d.scientific_name || ""}</td>
                        <td class="detection-time">${d.date || ""}</td>
                        <td class="text-right">${d.confidence ? (d.confidence < 1 ? (d.confidence * 100).toFixed(0) : d.confidence.toFixed(0)) + "%" : ""}</td>
                        <td class="text-center">${firstIndicator}</td>
                    </tr>
                `;
        })
        .join("");
    }

    // Update sort indicators
    document.querySelectorAll("#detections-table th.sortable").forEach((th) => {
      th.classList.remove("sort-asc", "sort-desc");
      if (th.dataset.sort === detectionsSortColumn) {
        th.classList.add(
          detectionsSortDirection === "asc" ? "sort-asc" : "sort-desc",
        );
      }
    });

    // Update pagination
    updatePagination(data.pagination);

    // Update counts
    document.getElementById("total-detection-count").textContent =
      data.pagination ? data.pagination.total : 0;

    // Update URL with current state
    updateURL();

    // Load species list
    await loadSpeciesList();
  } catch (error) {
    console.error("Failed to load detections:", error);
    detectionsList.innerHTML =
      '<tr><td colspan="5" class="no-data">Error loading detections</td></tr>';
  }
}

// Load species frequency list
async function loadSpeciesList() {
  const searchParams = new URLSearchParams();

  // Add period bounds if available (from new period selector)
  if (currentPeriodBounds) {
    searchParams.append("start_date", currentPeriodBounds.start_date);
    searchParams.append("end_date", currentPeriodBounds.end_date);
  } else {
    // Fallback to old period parameter
    searchParams.append("period", currentPeriod || "day");
  }

  try {
    const response = await fetch(
      `/api/detections/species/summary?${searchParams}`,
    );
    const data = await response.json();

    // Store all species data for client-side pagination
    allSpeciesData = data.species || [];

    // Update total species count
    document.getElementById("species-count").textContent =
      allSpeciesData.length;

    // Reset to first page when data changes
    speciesCurrentPage = 1;

    // Render the species table with pagination
    renderSpeciesTable();
  } catch (error) {
    console.error("Failed to load species list:", error);
  }
}

// Render species table with current page of data
function renderSpeciesTable() {
  // Sort the data
  const sortedData = [...allSpeciesData].sort((a, b) => {
    let aVal, bVal;

    if (speciesSortColumn === "name") {
      aVal = a.name || a.scientific_name;
      bVal = b.name || b.scientific_name;
      return speciesSortDirection === "asc"
        ? aVal.localeCompare(bVal)
        : bVal.localeCompare(aVal);
    } else if (speciesSortColumn === "count") {
      aVal = a.detection_count || 0;
      bVal = b.detection_count || 0;
      return speciesSortDirection === "asc" ? aVal - bVal : bVal - aVal;
    } else if (speciesSortColumn === "first_detection") {
      aVal = a.is_first_ever ? 1 : 0;
      bVal = b.is_first_ever ? 1 : 0;
      return speciesSortDirection === "asc" ? aVal - bVal : bVal - aVal;
    }
    return 0;
  });

  // Calculate pagination
  const startIndex = (speciesCurrentPage - 1) * speciesPageSize;
  const endIndex = startIndex + speciesPageSize;
  const pageData = sortedData.slice(startIndex, endIndex);

  // Render the table
  const speciesList = document.getElementById("species-frequency-tbody");
  if (pageData.length === 0) {
    speciesList.innerHTML =
      '<tr><td colspan="3" class="no-data">' +
      _("no-species-found") +
      "</td></tr>";
  } else {
    speciesList.innerHTML = pageData
      .map((s) => {
        const star = s.is_first_ever ? "★" : "";

        // Use the createCompactTaxonomyDisplay function if available
        let taxonomyHtml;
        if (typeof createCompactTaxonomyDisplay === "function") {
          // Extract genus from scientific name if not provided
          const genusName =
            s.genus ||
            (s.scientific_name ? s.scientific_name.split(" ")[0] : "");

          taxonomyHtml = createCompactTaxonomyDisplay(
            {
              common_name: s.name || s.common_name,
              scientific_name: s.scientific_name,
              order: s.order,
              family: s.family,
              genus: genusName,
              species: s.scientific_name,
            },
            {
              showLinks: true,
              linkFunction: "setFilterFromLabel",
            },
          );
        } else {
          // Fallback to basic display
          taxonomyHtml = `
            <div class="taxonomy-compact">
              <div class="common-name">${s.name || s.scientific_name}</div>
              <div class="scientific-name"><em>${s.scientific_name}</em></div>
              ${s.family ? `<div class="taxonomy-meta">${s.order || ""} ${s.order && s.family ? "·" : ""} ${s.family || ""}</div>` : ""}
            </div>
          `;
        }

        return `
                <tr class="species-row">
                    <td class="species-name-cell">
                        ${taxonomyHtml}
                    </td>
                    <td class="text-center">${star}</td>
                    <td class="text-right">${s.detection_count || 0}</td>
                </tr>
            `;
      })
      .join("");
  }

  // Render pagination controls
  const totalPages = Math.ceil(allSpeciesData.length / speciesPageSize);
  const paginationData = {
    page: speciesCurrentPage,
    total_pages: totalPages,
    total: allSpeciesData.length,
    has_prev: speciesCurrentPage > 1,
    has_next: speciesCurrentPage < totalPages,
  };

  // Use BirdNETPagination if available, otherwise use local function
  if (typeof BirdNETPagination !== "undefined" && BirdNETPagination.render) {
    BirdNETPagination.render(
      "species-pagination",
      paginationData,
      "loadSpeciesPage",
      "species",
    );
  } else if (typeof renderPagination === "function") {
    renderPagination(
      "species-pagination",
      paginationData,
      "loadSpeciesPage",
      "species",
    );
  }

  // Update sort indicators
  document
    .querySelectorAll("#species-frequency-table th.sortable")
    .forEach((th) => {
      th.classList.remove("sort-asc", "sort-desc");
      if (th.dataset.sort === speciesSortColumn) {
        th.classList.add(
          speciesSortDirection === "asc" ? "sort-asc" : "sort-desc",
        );
      }
    });
}

// Load a specific page of species
function loadSpeciesPage(page) {
  speciesCurrentPage = page;
  renderSpeciesTable();
}

// Pagination update using shared component
function updatePagination(pagination) {
  if (!pagination) return;

  // Use the shared BirdNETPagination component
  if (typeof BirdNETPagination !== "undefined" && BirdNETPagination.render) {
    BirdNETPagination.render(
      "pagination",
      pagination,
      "loadDetections",
      "detections",
    );
  } else {
    // Fallback for backwards compatibility
    console.warn("BirdNETPagination not available, using fallback");
    const container = document.getElementById("pagination");
    if (container) {
      container.innerHTML = `Page ${pagination.page} of ${pagination.total_pages}`;
    }
  }
}

// Sorting functions
function sortDetections(column) {
  if (detectionsSortColumn === column) {
    detectionsSortDirection =
      detectionsSortDirection === "asc" ? "desc" : "asc";
  } else {
    detectionsSortColumn = column;
    detectionsSortDirection = column === "species" ? "asc" : "desc";
  }
  loadDetections(1);
}

function sortSpeciesTable(column) {
  if (speciesSortColumn === column) {
    speciesSortDirection = speciesSortDirection === "asc" ? "desc" : "asc";
  } else {
    speciesSortColumn = column;
    speciesSortDirection = column === "name" ? "asc" : "desc";
  }
  // Reset to first page when sorting changes
  speciesCurrentPage = 1;
  renderSpeciesTable();
}

// Update URL with current state (page, period, filters)
function updateURL() {
  const params = new URLSearchParams();

  // Add period/date parameters from period selector if available
  if (currentPeriodBounds) {
    params.set("period", currentPeriodBounds.period_type);
    // Extract date from start_date (YYYY-MM-DD format)
    if (currentPeriodBounds.start_date) {
      params.set("date", currentPeriodBounds.start_date);
    }
  } else {
    // Fallback to old period parameter
    if (currentPeriod && currentPeriod !== "today") {
      params.set("period", currentPeriod);
    }
    if (currentPeriod === "date" && selectedDate) {
      params.set("date", selectedDate);
    }
  }

  // Add page parameter if not on first page
  if (currentPage > 1) {
    params.set("page", currentPage);
  }

  // Add taxonomic filter parameters
  if (taxonomicFilters.family) {
    params.set("family", taxonomicFilters.family);
  }
  if (taxonomicFilters.genus) {
    params.set("genus", taxonomicFilters.genus);
  }
  if (taxonomicFilters.species) {
    params.set("species", taxonomicFilters.species);
  }

  // Update URL without reloading the page
  const newUrl = params.toString()
    ? `${window.location.pathname}?${params.toString()}`
    : window.location.pathname;

  // Build state object for browser history
  const state = {};
  if (currentPeriodBounds) {
    state.period = currentPeriodBounds.period_type;
    state.date = currentPeriodBounds.start_date;
  } else if (currentPeriod) {
    state.period = currentPeriod;
    // Always include a date - default to today if not set
    state.date = selectedDate || new Date().toISOString().split("T")[0];
  }

  window.history.pushState(state, "", newUrl);
}

// Initialize function
function initializePage() {
  // Get initial period from URL
  const url = new URL(window.location);
  currentPeriod = url.searchParams.get("period") || "today";
  const dateParam = url.searchParams.get("date");

  // Get page number from URL
  const urlPage = url.searchParams.get("page");
  if (urlPage) {
    currentPage = parseInt(urlPage, 10);
  }

  // Initialize taxonomic filters from URL parameters using shared function
  initializeFiltersFromURL();

  // Load initial data with page from URL
  loadDetections(currentPage);
  loadSpeciesList();

  // Set initial counts
  updateSpeciesCount();

  // Display current period date
  let displayDate = "";
  if (currentPeriod === "today") {
    displayDate = _("today");
  } else if (currentPeriod === "week") {
    displayDate = _("last-7-days");
  } else if (currentPeriod === "month") {
    displayDate = _("last-30-days");
  } else if (currentPeriod === "all") {
    displayDate = _("all-time");
  } else if (currentPeriod === "date" && dateParam) {
    // Format the date nicely
    const date = new Date(dateParam + "T00:00:00");
    const options = {
      weekday: "long",
      year: "numeric",
      month: "long",
      day: "numeric",
    };
    displayDate = date.toLocaleDateString(undefined, options);
  }

  const periodDateElement = document.getElementById("period-date");
  if (periodDateElement) {
    periodDateElement.textContent = displayDate;
  }

  // Add keyboard shortcuts
  document.addEventListener("keydown", function (e) {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;

    if (e.key === "Escape") {
      clearSpeciesFilter();
    } else if (e.key === "ArrowLeft") {
      goToPreviousPeriod();
    } else if (e.key === "ArrowRight") {
      goToNextPeriod();
    }
  });

  // Close date picker when clicking outside
  window.addEventListener("click", function (e) {
    const modal = document.getElementById("date-picker-modal");
    if (e.target === modal) {
      closeDatePicker();
    }
  });
}

// Initialize on page load - handle both cases
if (document.readyState === "loading") {
  // DOM is still loading, wait for DOMContentLoaded
  document.addEventListener("DOMContentLoaded", initializePage);
} else {
  // DOM is already loaded (script loaded after DOM or with defer)
  initializePage();
}

// Export functions for global access
window.setPeriod = setPeriod;
window.playAudio = playAudio;
window.goToPreviousPeriod = goToPreviousPeriod;
window.goToNextPeriod = goToNextPeriod;
window.openDatePicker = openDatePicker;
window.closeDatePicker = closeDatePicker;
window.loadDetections = loadDetections;
window.loadSpeciesList = loadSpeciesList;
window.sortDetections = sortDetections;
window.sortSpeciesTable = sortSpeciesTable;
window.goToSelectedDate = goToSelectedDate;
window.updatePagination = updatePagination;
window.loadSpeciesPage = loadSpeciesPage;
window.renderSpeciesTable = renderSpeciesTable;
window.updateURL = updateURL;

// Export filter change handlers
window.onFamilyChange = onFamilyChange;
window.onGenusChange = onGenusChange;
window.onSpeciesChange = onSpeciesChange;
window.onConfidenceChange = onConfidenceChange;
window.onFiltersChanged = onFiltersChanged;
