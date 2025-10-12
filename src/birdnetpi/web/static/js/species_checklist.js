/**
 * Species Checklist - Progressive Loading and Filtering
 *
 * This module handles the species checklist page, which shows all bird species
 * from the IOC reference database along with their detection status.
 */

// State management
const state = {
  currentPage: 1,
  perPage: 50,
  detectionFilter: "all", // 'all', 'detected', 'undetected'
  family: null,
  genus: null,
  order: null,
  totalSpecies: 0,
  detectedCount: 0,
  undetectedCount: 0,
  isLoading: false,
  sortColumn: "name",
  sortDirection: "asc",
};

// API endpoint
const API_BASE = "/api/detections/species/checklist";

/**
 * Initialize the page
 */
document.addEventListener("DOMContentLoaded", () => {
  loadSpeciesData();
  loadFamilies();
});

/**
 * Load species checklist data from API
 */
async function loadSpeciesData() {
  if (state.isLoading) return;

  state.isLoading = true;
  showLoadingState();

  try {
    // Build query parameters
    const params = new URLSearchParams({
      page: state.currentPage,
      per_page: state.perPage,
      detection_filter: state.detectionFilter,
      sort_by: state.sortColumn,
      sort_order: state.sortDirection,
    });

    if (state.family) params.append("family", state.family);
    if (state.genus) params.append("genus", state.genus);
    if (state.order) params.append("order", state.order);

    // Fetch data
    const response = await fetch(`${API_BASE}?${params}`);
    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data = await response.json();

    // Update state with counts
    state.totalSpecies = data.total_species;
    state.detectedCount = data.detected_species;
    state.undetectedCount = data.undetected_species;

    // Update UI
    updateStatistics();
    renderSpeciesTable(data.species);
    updatePagination(data.pagination);

    // Show/hide empty state
    if (data.species.length === 0) {
      showEmptyState();
    } else {
      hideEmptyState();
    }
  } catch (error) {
    console.error("Error loading species data:", error);
    showErrorState(error.message);
  } finally {
    state.isLoading = false;
  }
}

/**
 * Load families for the family filter dropdown
 */
async function loadFamilies() {
  try {
    // Get families from taxonomy endpoint
    const response = await fetch(
      "/api/detections/taxonomy/families?has_detections=false",
    );
    const data = await response.json();

    const familySelect = document.getElementById("family-filter");
    familySelect.innerHTML = '<option value="">All families</option>';

    data.families.forEach((family) => {
      const option = document.createElement("option");
      option.value = family;
      option.textContent = family;
      familySelect.appendChild(option);
    });
  } catch (error) {
    console.error("Error loading families:", error);
  }
}

/**
 * Render the species table
 */
function renderSpeciesTable(species) {
  const tbody = document.getElementById("species-table-body");
  tbody.innerHTML = "";

  species.forEach((s) => {
    const row = createSpeciesRow(s);
    tbody.appendChild(row);
  });
}

/**
 * Create a table row for a species
 */
function createSpeciesRow(species) {
  const row = document.createElement("tr");
  row.className = species.is_detected ? "detected" : "undetected";

  // Thumbnail column
  const thumbnailCell = document.createElement("td");
  thumbnailCell.className = "col-thumbnail";
  if (species.image_url) {
    const img = document.createElement("img");
    img.src = species.image_url;
    img.alt = species.common_name || species.scientific_name;
    img.className = "species-thumbnail";
    img.loading = "lazy";
    thumbnailCell.appendChild(img);
  }
  row.appendChild(thumbnailCell);

  // Status column (checkmark or circle)
  const statusCell = document.createElement("td");
  statusCell.className = "col-status";
  const statusIcon = document.createElement("span");
  statusIcon.className = species.is_detected
    ? "status-icon detected"
    : "status-icon undetected";
  statusIcon.textContent = species.is_detected ? "✓" : "○";
  statusIcon.setAttribute(
    "aria-label",
    species.is_detected ? "Detected" : "Not detected",
  );
  statusCell.appendChild(statusIcon);
  row.appendChild(statusCell);

  // Species name column using taxonomy display component
  const nameCell = document.createElement("td");
  nameCell.className = "col-species";

  // Extract genus from scientific name
  const genusName =
    species.genus ||
    (species.scientific_name ? species.scientific_name.split(" ")[0] : "");

  // Prepare data for taxonomy display
  const taxonomyData = {
    common_name: species.translated_name || species.common_name,
    scientific_name: species.scientific_name,
    genus: genusName,
    family: species.family,
    order: species.order_name,
  };

  // Create taxonomy display with clickable links
  const taxonomyHtml = createCompactTaxonomyDisplay(taxonomyData, {
    showLinks: true,
    linkFunction: "setFilterFromLabel",
  });

  // If there's a BoW URL, wrap the common name in a link
  if (species.bow_url) {
    const tempDiv = document.createElement("div");
    tempDiv.innerHTML = taxonomyHtml;
    const commonNameDiv = tempDiv.querySelector(".common-name");
    if (commonNameDiv) {
      const commonNameText = commonNameDiv.textContent;
      commonNameDiv.innerHTML = `<a href="${species.bow_url}" target="_blank" rel="noopener noreferrer" class="bow-link" aria-label="Birds of the World: ${species.scientific_name}">${commonNameText}</a>`;
    }
    nameCell.innerHTML = tempDiv.innerHTML;
  } else {
    nameCell.innerHTML = taxonomyHtml;
  }

  row.appendChild(nameCell);

  // Detections count column
  const countCell = document.createElement("td");
  countCell.className = "col-detections";
  countCell.textContent = species.detection_count || "-";
  row.appendChild(countCell);

  // Latest detection column
  const latestCell = document.createElement("td");
  latestCell.className = "col-latest";
  if (species.latest_detection) {
    const date = new Date(species.latest_detection);
    latestCell.textContent = date.toLocaleDateString();
  } else {
    latestCell.textContent = "-";
  }
  row.appendChild(latestCell);

  // Conservation status column
  const conservationCell = document.createElement("td");
  conservationCell.className = "col-conservation";
  if (species.conservation_status) {
    const conservationSpan = document.createElement("span");
    conservationSpan.className = "conservation-status";
    conservationSpan.setAttribute("role", "img");
    const statusLabel = window._
      ? window._("Conservation status: %(status)s", {
          status: species.conservation_status,
        })
      : `Conservation status: ${species.conservation_status}`;
    conservationSpan.setAttribute("aria-label", statusLabel);
    conservationSpan.textContent = getConservationIcon(
      species.conservation_status,
    );
    conservationCell.appendChild(conservationSpan);
  } else {
    const unknownLabel = window._
      ? window._("Conservation status unknown")
      : "Conservation status unknown";
    conservationCell.innerHTML = `<span aria-label="${unknownLabel}">-</span>`;
  }
  row.appendChild(conservationCell);

  return row;
}

/**
 * Get icon for conservation status (colorblind-safe symbols)
 */
function getConservationIcon(status) {
  // Normalize status to uppercase for comparison
  const normalizedStatus = status.toUpperCase();

  // Map both short codes and full names to colorblind-safe symbols
  // Using distinct shapes that work without color perception
  const iconMap = {
    // Short codes
    CR: "⬛", // Critically Endangered - filled square
    EN: "◆", // Endangered - diamond
    VU: "▲", // Vulnerable - triangle
    NT: "●", // Near Threatened - filled circle
    LC: "○", // Least Concern - empty circle
    DD: "◯", // Data Deficient - large empty circle
    EX: "✕", // Extinct - X mark
    EW: "✕", // Extinct in the Wild - X mark
    // Full names from Wikidata
    "CRITICALLY ENDANGERED": "⬛",
    ENDANGERED: "◆",
    "ENDANGERED STATUS": "◆", // Alternative Wikidata format
    VULNERABLE: "▲",
    "NEAR THREATENED": "●",
    "LEAST CONCERN": "○",
    "DATA DEFICIENT": "◯",
    EXTINCT: "✕",
    "EXTINCT IN THE WILD": "✕",
  };

  return iconMap[normalizedStatus] || "?";
}

/**
 * Update statistics display
 */
function updateStatistics() {
  document.getElementById("total-species").textContent = state.totalSpecies;
  document.getElementById("detected-count").textContent = state.detectedCount;
  document.getElementById("undetected-count").textContent =
    state.undetectedCount;
}

/**
 * Update pagination controls
 */
function updatePagination(pagination) {
  BirdNETPagination.render(
    "species-pagination",
    pagination,
    "goToPage",
    "species",
  );
}

/**
 * Show loading state
 */
function showLoadingState() {
  const tbody = document.getElementById("species-table-body");
  tbody.innerHTML = `
        <tr id="loading-row">
            <td colspan="6" class="loading-cell">
                <div class="loading-spinner" role="status">
                    <span class="sr-only">Loading species data...</span>
                    <div class="spinner"></div>
                </div>
            </td>
        </tr>
    `;
}

/**
 * Show error state
 */
function showErrorState(message) {
  const tbody = document.getElementById("species-table-body");
  tbody.innerHTML = `
        <tr>
            <td colspan="6" class="error-cell">
                <p>Error loading species data: ${message}</p>
                <button onclick="loadSpeciesData()" class="btn-retry">Retry</button>
            </td>
        </tr>
    `;
}

/**
 * Show empty state
 */
function showEmptyState() {
  document.getElementById("empty-state").style.display = "block";
  document.querySelector(".species-table-container").style.display = "none";
}

/**
 * Hide empty state
 */
function hideEmptyState() {
  document.getElementById("empty-state").style.display = "none";
  document.querySelector(".species-table-container").style.display = "block";
}

/**
 * Detection filter change handler
 */
function onDetectionFilterChange(filter) {
  state.detectionFilter = filter;
  state.currentPage = 1; // Reset to first page

  // Update button states
  document.querySelectorAll(".detection-filter-btn").forEach((btn) => {
    btn.classList.remove("active");
    btn.setAttribute("aria-checked", "false");
  });

  const activeBtn = document.getElementById(`filter-${filter}`);
  activeBtn.classList.add("active");
  activeBtn.setAttribute("aria-checked", "true");

  // Reload data
  loadSpeciesData();
}

/**
 * Family filter change handler (required by taxonomic_filters component)
 */
function onFamilyChange() {
  const familySelect = document.getElementById("family-filter");
  state.family = familySelect.value || null;
  state.genus = null; // Reset dependent filters
  state.currentPage = 1;

  // Enable/disable genus filter
  const genusSelect = document.getElementById("genus-filter");
  if (state.family) {
    genusSelect.disabled = false;
    loadGenera(state.family);
  } else {
    genusSelect.disabled = true;
    genusSelect.innerHTML = '<option value="">Select family first</option>';
  }

  // Reset species filter
  const speciesSelect = document.getElementById("species-filter");
  speciesSelect.disabled = true;
  speciesSelect.innerHTML = '<option value="">Select genus first</option>';

  loadSpeciesData();
}

/**
 * Genus filter change handler (required by taxonomic_filters component)
 */
function onGenusChange() {
  const genusSelect = document.getElementById("genus-filter");
  state.genus = genusSelect.value || null;
  state.currentPage = 1;

  // Enable/disable species filter
  const speciesSelect = document.getElementById("species-filter");
  if (state.genus) {
    speciesSelect.disabled = false;
    loadSpeciesList(state.family, state.genus);
  } else {
    speciesSelect.disabled = true;
    speciesSelect.innerHTML = '<option value="">Select genus first</option>';
  }

  loadSpeciesData();
}

/**
 * Species filter change handler (required by taxonomic_filters component)
 */
function onSpeciesChange() {
  // Not implemented for checklist page - filtering by specific species
  // doesn't make sense when viewing the full checklist
  loadSpeciesData();
}

/**
 * Clear all filters (required by taxonomic_filters component)
 */
function clearAllFilters() {
  state.family = null;
  state.genus = null;
  state.order = null;
  state.detectionFilter = "all";
  state.currentPage = 1;

  // Reset filter UI
  document.getElementById("family-filter").value = "";
  document.getElementById("genus-filter").value = "";
  document.getElementById("genus-filter").disabled = true;
  document.getElementById("species-filter").value = "";
  document.getElementById("species-filter").disabled = true;

  // Reset detection filter
  onDetectionFilterChange("all");
}

/**
 * Load genera for a family
 */
async function loadGenera(family) {
  try {
    const response = await fetch(
      `/api/detections/taxonomy/genera?family=${family}&has_detections=false`,
    );
    const data = await response.json();

    const genusSelect = document.getElementById("genus-filter");
    genusSelect.innerHTML = '<option value="">All genera</option>';

    data.genera.forEach((genus) => {
      const option = document.createElement("option");
      option.value = genus;
      option.textContent = genus;
      genusSelect.appendChild(option);
    });
  } catch (error) {
    console.error("Error loading genera:", error);
  }
}

/**
 * Load species list for a genus
 */
async function loadSpeciesList(family, genus) {
  try {
    const params = new URLSearchParams({ genus, has_detections: "false" });
    if (family) params.append("family", family);

    const response = await fetch(`/api/detections/taxonomy/species?${params}`);
    const data = await response.json();

    const speciesSelect = document.getElementById("species-filter");
    speciesSelect.innerHTML = '<option value="">All species</option>';

    data.species.forEach((species) => {
      const option = document.createElement("option");
      option.value = species.scientific_name;
      option.textContent = `${species.common_name} (${species.scientific_name})`;
      speciesSelect.appendChild(option);
    });
  } catch (error) {
    console.error("Error loading species:", error);
  }
}

/**
 * Page change handler (for pagination component)
 */
function goToPage(page) {
  state.currentPage = page;
  loadSpeciesData();
}

/**
 * Sort table by column
 */
function sortTable(column) {
  if (state.sortColumn === column) {
    // Toggle direction if same column
    state.sortDirection = state.sortDirection === "asc" ? "desc" : "asc";
  } else {
    // New column - set default direction
    state.sortColumn = column;
    state.sortDirection = column === "name" ? "asc" : "desc";
  }

  // Reset to first page when sorting changes
  state.currentPage = 1;

  // Update sort indicators
  document.querySelectorAll(".species-table th.sortable").forEach((th) => {
    th.classList.remove("sort-asc", "sort-desc");
    if (th.dataset.sort === state.sortColumn) {
      th.classList.add(
        state.sortDirection === "asc" ? "sort-asc" : "sort-desc",
      );
    }
  });

  // Reload data with new sort
  loadSpeciesData();
}

/**
 * Filter changed callback for taxonomic filters
 */
function onFiltersChanged() {
  state.currentPage = 1;
  loadSpeciesData();
}
