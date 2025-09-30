/**
 * Best Recordings JavaScript - Filter management and audio playback
 */

// Migration: Now using global _() function from i18n.js

// Helper function to clone and populate a template
function cloneTemplate(templateId) {
  const template = document.getElementById(templateId);
  if (!template) return null;
  return template.content
    ? template.content.cloneNode(true)
    : template.cloneNode(true);
}

// State management - using shared taxonomicFilters from taxonomic_filters.js
let currentRecordings = [];
let currentPage = 1;

// Initialize on page load
document.addEventListener("DOMContentLoaded", async function () {
  // Read URL parameters and set initial filters
  const urlParams = new URLSearchParams(window.location.search);

  // Set page number from URL
  const urlPage = urlParams.get("page");
  if (urlPage) {
    currentPage = parseInt(urlPage, 10);
  }

  // Initialize taxonomic filters from URL parameters using shared function
  await initializeFiltersFromURL();

  // Load recordings with initial filters
  loadRecordings(currentPage);

  // Listen for browser navigation
  window.addEventListener("popstate", async function (event) {
    const state = event.state || {};

    // Update filters from state
    taxonomicFilters.family = state.family || null;
    taxonomicFilters.genus = state.genus || null;
    taxonomicFilters.species = state.species || null;
    taxonomicFilters.minConfidence = state.confidence || 0.7;
    currentPage = state.page || 1;

    // Update UI controls
    document.getElementById("family-filter").value =
      taxonomicFilters.family || "";
    document.getElementById("confidence-filter").value =
      taxonomicFilters.minConfidence;

    // Update dependent selectors
    if (taxonomicFilters.family) {
      await loadGenera();
      if (taxonomicFilters.genus) {
        document.getElementById("genus-filter").value = taxonomicFilters.genus;
        await loadSpecies();
        if (taxonomicFilters.species) {
          document.getElementById("species-filter").value =
            taxonomicFilters.species;
        }
      }
    } else {
      // Reset dependent selectors
      document.getElementById("genus-filter").disabled = true;
      document.getElementById("genus-filter").innerHTML =
        `<option value="">${_("select-family")}</option>`;
      document.getElementById("species-filter").disabled = true;
      document.getElementById("species-filter").innerHTML =
        `<option value="">${_("select-genus")}</option>`;
    }

    // Update active filters display
    updateActiveFilters();

    // Reload recordings
    loadRecordings(currentPage);
  });
});

// Handler called when filters change - reload recordings
function onFiltersChanged() {
  // Reset to first page when filters change
  currentPage = 1;

  // Update URL and reload recordings
  updateURL();
  loadRecordings();
}

// Update URL with current filters
function updateURL() {
  const params = new URLSearchParams();

  if (currentPage > 1) {
    params.set("page", currentPage);
  }

  if (taxonomicFilters.family) {
    params.set("family", taxonomicFilters.family);
  }

  if (taxonomicFilters.genus) {
    params.set("genus", taxonomicFilters.genus);
  }

  if (taxonomicFilters.species) {
    params.set("species", taxonomicFilters.species);
  }

  if (taxonomicFilters.minConfidence !== 0.7) {
    params.set("confidence", taxonomicFilters.minConfidence);
  }

  const newUrl = params.toString()
    ? `${window.location.pathname}?${params.toString()}`
    : window.location.pathname;

  const state = {
    family: taxonomicFilters.family,
    genus: taxonomicFilters.genus,
    species: taxonomicFilters.species,
    confidence: taxonomicFilters.minConfidence,
    page: currentPage,
  };

  window.history.pushState(state, "", newUrl);
}

// Filter change handlers using shared code
function onFamilyChange() {
  const familySelect = document.getElementById("family-filter");
  taxonomicFilters.family = familySelect.value || null;
  taxonomicFilters.genus = null;
  taxonomicFilters.species = null;

  loadGenera();
  updateActiveFilters();
  onFiltersChanged();
}

function onGenusChange() {
  const genusSelect = document.getElementById("genus-filter");
  taxonomicFilters.genus = genusSelect.value || null;
  taxonomicFilters.species = null;

  loadSpecies();
  updateActiveFilters();
  onFiltersChanged();
}

function onSpeciesChange() {
  const speciesSelect = document.getElementById("species-filter");
  taxonomicFilters.species = speciesSelect.value || null;

  updateActiveFilters();
  onFiltersChanged();
}

function onConfidenceChange() {
  const confidenceSelect = document.getElementById("confidence-filter");
  taxonomicFilters.minConfidence = parseFloat(confidenceSelect.value) || 0.7;

  updateActiveFilters();
  onFiltersChanged();
}

// Helper function to format order names (PASSERIFORMES -> Passeriformes)
function formatOrderName(orderName) {
  if (!orderName) return "";
  return orderName.charAt(0).toUpperCase() + orderName.slice(1).toLowerCase();
}

// Load recordings with current filters
async function loadRecordings(page = 1) {
  currentPage = page;
  const container = document.getElementById("detections-container");
  // Use template for loading indicator
  const loadingTemplate = document.getElementById("loading-indicator-template");
  container.innerHTML = loadingTemplate
    ? loadingTemplate.innerHTML
    : '<div class="loading-indicator">' + _("loading") + "</div>";

  // Build query parameters
  const params = new URLSearchParams({
    page: page,
    per_page: 50,
    min_confidence: taxonomicFilters.minConfidence,
  });

  if (taxonomicFilters.species) {
    params.append("species", taxonomicFilters.species);
  } else if (taxonomicFilters.genus) {
    params.append("genus", taxonomicFilters.genus);
  } else if (taxonomicFilters.family) {
    params.append("family", taxonomicFilters.family);
  }

  try {
    const response = await fetch(`/api/detections/best-recordings?${params}`);
    const data = await response.json();

    currentRecordings = data.recordings;

    // Update statistics
    updateStatistics(data);

    // Update active filters display
    updateActiveFilters();

    // Display recordings
    if (currentRecordings.length > 0) {
      displayRecordings(currentRecordings);
    } else {
      const noResultsTemplate = document.getElementById("no-results-template");
      container.innerHTML = noResultsTemplate
        ? noResultsTemplate.innerHTML
        : "";
    }

    // Render pagination
    if (data.pagination) {
      BirdNETPagination.render(
        "pagination",
        data.pagination,
        "loadRecordings",
        "recordings",
      );
    }

    // Update URL to reflect current state
    updateURL();
  } catch (error) {
    console.error("Error loading recordings:", error);
    const errorTemplate = document.getElementById("error-template");
    container.innerHTML = errorTemplate ? errorTemplate.innerHTML : "";
  }
}

// Update statistics display
function updateStatistics(data) {
  const statsDiv = document.getElementById("stats");
  const template = cloneTemplate("stats-template");
  if (template) {
    // Use the template structure
    const container = document.createElement("div");
    container.appendChild(template);
    container.querySelector('[data-field="count"]').textContent = data.count;
    container.querySelector('[data-field="species"]').textContent =
      data.unique_species;
    container.querySelector('[data-field="avg-confidence"]').textContent =
      data.avg_confidence + "%";
    container.querySelector('[data-field="date-range"]').textContent =
      data.date_range;
    statsDiv.innerHTML = container.innerHTML;
  } else {
    // Fallback if template not found
    statsDiv.innerHTML = `
            <span><span class="stat-value">${data.count}</span> ${_("recordings")}</span> ·
            <span><span class="stat-value">${data.unique_species}</span> ${_("species-count")}</span> ·
            <span>${_("average-confidence")}: <span class="stat-value">${data.avg_confidence}%</span></span> ·
            <span>${_("date-range")}: <span class="stat-value">${data.date_range}</span></span>
        `;
  }
}

// Display recordings
function displayRecordings(recordings) {
  const container = document.getElementById("detections-container");

  const html = recordings
    .map(
      (recording) => `
        <div class="detection-entry">
            <button class="play-button" onclick="playAudio('${recording.id}', '${
              recording.audio_file_id
            }', this)" title="${_("Play recording")}"></button>
            <div>
                <div style="font-weight: 500;">${recording.common_name || recording.scientific_name}</div>
                <div style="font-size: 0.8rem; color: var(--color-text-tertiary);">
                    <em>
                        <span class="taxonomy-link"
                              onclick="setFilterFromLabel('genus', '${recording.scientific_name.split(" ")[0]}', '${JSON.stringify(
                                {
                                  family: recording.family || "",
                                  genus:
                                    recording.scientific_name.split(" ")[0],
                                },
                              )
                                .replace(/"/g, "&quot;")
                                .replace(/'/g, "&#39;")}')"
                              title="${_("filter-by-genus")} ${recording.scientific_name.split(" ")[0]}">
                            ${recording.scientific_name.split(" ")[0]}
                        </span>
                        <span class="taxonomy-link"
                              onclick="setFilterFromLabel('species', '${recording.scientific_name}', '${JSON.stringify(
                                {
                                  family: recording.family || "",
                                  genus:
                                    recording.scientific_name.split(" ")[0],
                                  species: recording.scientific_name,
                                },
                              )
                                .replace(/"/g, "&quot;")
                                .replace(/'/g, "&#39;")}')"
                              title="${_("filter-by-species")} ${recording.scientific_name}">
                            ${recording.scientific_name.split(" ").slice(1).join(" ")}
                        </span>
                    </em>
                </div>
                <div style="font-size: 0.7rem; color: var(--color-text-tertiary);">
                    ${formatOrderName(recording.order_name)} ·
                    <span class="taxonomy-link"
                          onclick="setFilterFromLabel('family', '${recording.family}')"
                          title="${_("filter-by-family")} ${recording.family}">
                        ${recording.family}
                    </span>
                </div>
            </div>
            <div>${recording.date}</div>
            <div>${recording.time}</div>
            <div style="text-align: right;">${recording.confidence}%</div>
            <div class="audio-status" id="audio-status-${recording.id}"></div>
        </div>
    `,
    )
    .join("");

  container.innerHTML = html;
}

// Audio playback functionality
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

  // Create audio element using direct audio file endpoint
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
      statusDiv.classList.add("audio-missing");
      statusDiv.textContent = "N/A";
    }
    alert(_("audio-not-available"));
  });

  currentAudio = audio;
  currentButton = button;
}

// Export functions for global access (needed for onclick handlers)
window.setFilterFromLabel = setFilterFromLabel;
window.onFamilyChange = onFamilyChange;
window.onGenusChange = onGenusChange;
window.onSpeciesChange = onSpeciesChange;
window.onConfidenceChange = onConfidenceChange;
window.loadRecordings = loadRecordings;
window.removeFilter = removeFilter;
window.clearAllFilters = clearAllFilters;
window.playAudio = playAudio;
window.formatOrderName = formatOrderName;
window.updateURL = updateURL;
