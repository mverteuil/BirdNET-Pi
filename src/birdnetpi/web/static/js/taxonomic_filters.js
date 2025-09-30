/**
 * Shared Taxonomic Filter Functionality
 * Provides common filtering functionality for pages with taxonomic filters
 */

// Filter state management
const taxonomicFilters = {
  family: null,
  genus: null,
  species: null,
  minConfidence: 0.7,
};

/**
 * Load all families into the family filter dropdown
 */
async function loadFamilies() {
  try {
    const response = await fetch(
      "/api/detections/taxonomy/families?has_detections=true",
    );
    const data = await response.json();

    const familySelect = document.getElementById("family-filter");
    if (familySelect) {
      // Clear existing options except the first one
      familySelect.innerHTML =
        '<option value="">' +
        (window._ ? _("All families") : "All families") +
        "</option>";

      // Add family options - API returns { families: [...] }
      const families = data.families || [];
      families.forEach((family) => {
        const option = document.createElement("option");
        // Handle both string and object formats
        const familyName = typeof family === "string" ? family : family.name;
        option.value = familyName;
        option.textContent = familyName;
        if (typeof family === "object" && family.detection_count) {
          option.textContent += ` (${family.detection_count})`;
        }
        familySelect.appendChild(option);
      });
    }
  } catch (error) {
    console.error("Failed to load families:", error);
  }
}

/**
 * Load genera for selected family
 */
async function loadGenera() {
  const family = taxonomicFilters.family;
  const genusSelect = document.getElementById("genus-filter");
  const speciesSelect = document.getElementById("species-filter");

  if (!genusSelect) return;

  if (!family) {
    genusSelect.innerHTML =
      '<option value="">' +
      (window._ ? _("Select family first") : "Select family first") +
      "</option>";
    genusSelect.disabled = true;
    if (speciesSelect) {
      speciesSelect.innerHTML =
        '<option value="">' +
        (window._ ? _("Select genus first") : "Select genus first") +
        "</option>";
      speciesSelect.disabled = true;
    }
    return;
  }

  genusSelect.innerHTML =
    '<option value="">' +
    (window._ ? _("Loading...") : "Loading...") +
    "</option>";

  try {
    const response = await fetch(
      `/api/detections/taxonomy/genera?family=${encodeURIComponent(family)}&has_detections=true`,
    );
    const data = await response.json();

    genusSelect.innerHTML =
      '<option value="">' +
      (window._ ? _("All genera") : "All genera") +
      "</option>";
    genusSelect.disabled = false;

    // Handle both array and object response formats
    const genera = data.genera || [];
    genera.forEach((genus) => {
      const option = document.createElement("option");
      // Handle both string and object formats
      const genusName = typeof genus === "string" ? genus : genus.name;
      option.value = genusName;
      option.textContent = genusName;
      if (typeof genus === "object" && genus.detection_count) {
        option.textContent += ` (${genus.detection_count})`;
      }
      genusSelect.appendChild(option);
    });

    // Reset species select
    if (speciesSelect) {
      speciesSelect.innerHTML =
        '<option value="">' +
        (window._ ? _("Select genus first") : "Select genus first") +
        "</option>";
      speciesSelect.disabled = true;
    }
  } catch (error) {
    console.error("Failed to load genera:", error);
    genusSelect.innerHTML =
      '<option value="">' +
      (window._ ? _("Error loading genera") : "Error loading genera") +
      "</option>";
  }
}

/**
 * Load species for selected genus
 */
async function loadSpecies() {
  const genus = taxonomicFilters.genus;
  const speciesSelect = document.getElementById("species-filter");

  if (!speciesSelect) return;

  if (!genus) {
    speciesSelect.innerHTML =
      '<option value="">' +
      (window._ ? _("Select genus first") : "Select genus first") +
      "</option>";
    speciesSelect.disabled = true;
    return;
  }

  speciesSelect.innerHTML =
    '<option value="">' +
    (window._ ? _("Loading...") : "Loading...") +
    "</option>";

  try {
    const params = new URLSearchParams({
      genus: genus,
      has_detections: true,
    });
    if (taxonomicFilters.family) {
      params.append("family", taxonomicFilters.family);
    }

    const response = await fetch(`/api/detections/taxonomy/species?${params}`);
    const data = await response.json();

    speciesSelect.innerHTML =
      '<option value="">' +
      (window._ ? _("All species") : "All species") +
      "</option>";
    speciesSelect.disabled = false;

    data.species.forEach((sp) => {
      const option = document.createElement("option");
      option.value = sp.scientific_name;
      option.textContent = `${sp.common_name || sp.scientific_name} (${sp.scientific_name})`;
      if (sp.detection_count) {
        option.textContent += ` - ${sp.detection_count} detections`;
      }
      speciesSelect.appendChild(option);
    });
  } catch (error) {
    console.error("Failed to load species:", error);
    speciesSelect.innerHTML =
      '<option value="">' +
      (window._ ? _("Error loading species") : "Error loading species") +
      "</option>";
  }
}

/**
 * Update active filter display
 */
function updateActiveFilters() {
  const container = document.getElementById("active-filters");
  if (!container) return;

  const filters = [];

  if (taxonomicFilters.family) {
    filters.push({
      type: "family",
      label: window._ ? _("Family") : "Family",
      value: taxonomicFilters.family,
    });
  }

  if (taxonomicFilters.genus) {
    filters.push({
      type: "genus",
      label: window._ ? _("Genus") : "Genus",
      value: taxonomicFilters.genus,
    });
  }

  if (taxonomicFilters.species) {
    const speciesDisplay =
      taxonomicFilters.species.split(" ").slice(1).join(" ") ||
      taxonomicFilters.species;
    filters.push({
      type: "species",
      label: window._ ? _("Species") : "Species",
      value: speciesDisplay,
    });
  }

  if (taxonomicFilters.minConfidence && taxonomicFilters.minConfidence > 0.7) {
    filters.push({
      type: "confidence",
      label: window._ ? _("Min Confidence") : "Min Confidence",
      value: `${(taxonomicFilters.minConfidence * 100).toFixed(0)}%`,
    });
  }

  if (filters.length > 0) {
    container.style.display = "flex";

    // Build filter tags HTML
    const filterTagsHTML = filters
      .map(
        (f) => `
            <div class="filter-tag">
                <span>${f.label}: ${f.value}</span>
                <span class="filter-tag-remove" onclick="removeFilter('${f.type}')">×</span>
            </div>
        `,
      )
      .join("");

    // Add clear all button at the end
    const clearButtonHTML = `
            <button class="filter-clear-all" onclick="clearAllFilters()" aria-label="${window._ ? _("Clear all applied filters") : "Clear all filters"}">
                ${window._ ? _("Clear all") : "Clear all"}
            </button>
        `;

    container.innerHTML = filterTagsHTML + clearButtonHTML;
  } else {
    container.style.display = "none";
    container.innerHTML = "";
  }
}

/**
 * Remove a specific filter
 */
function removeFilter(filterType) {
  if (filterType === "family") {
    taxonomicFilters.family = null;
    taxonomicFilters.genus = null;
    taxonomicFilters.species = null;
    document.getElementById("family-filter").value = "";
    loadGenera();
  } else if (filterType === "genus") {
    taxonomicFilters.genus = null;
    taxonomicFilters.species = null;
    document.getElementById("genus-filter").value = "";
    loadSpecies();
  } else if (filterType === "species") {
    taxonomicFilters.species = null;
    document.getElementById("species-filter").value = "";
  } else if (filterType === "confidence") {
    taxonomicFilters.minConfidence = 0.7;
    document.getElementById("confidence-filter").value = "0.7";
  }

  updateActiveFilters();

  // Call page-specific reload function
  if (typeof onFiltersChanged === "function") {
    onFiltersChanged();
  }
}

/**
 * Clear all filters
 */
function clearAllFilters() {
  taxonomicFilters.family = null;
  taxonomicFilters.genus = null;
  taxonomicFilters.species = null;
  taxonomicFilters.minConfidence = 0.7;

  const familyFilter = document.getElementById("family-filter");
  if (familyFilter) {
    familyFilter.value = "";
  }

  const confidenceFilter = document.getElementById("confidence-filter");
  if (confidenceFilter) {
    confidenceFilter.value = "0.7";
  }

  loadGenera();
  updateActiveFilters();

  // Call page-specific reload function
  if (typeof onFiltersChanged === "function") {
    onFiltersChanged();
  }
}

/**
 * Set a filter from a taxonomy link
 * @param {string} type - The type of filter (family, genus, or species)
 * @param {string} value - The value to set
 * @param {string} taxonomyData - Optional JSON string with full taxonomy hierarchy (for species)
 */
function setFilterFromLabel(type, value, taxonomyData) {
  if (type === "family") {
    taxonomicFilters.family = value;
    taxonomicFilters.genus = null;
    taxonomicFilters.species = null;

    const familySelect = document.getElementById("family-filter");
    if (familySelect) {
      familySelect.value = value;
      loadGenera();
    }
  } else if (type === "genus") {
    // Handle hierarchical filtering for genus
    if (taxonomyData) {
      try {
        // Parse the taxonomy data
        const taxonomy = JSON.parse(taxonomyData);

        // Set family and genus hierarchically
        taxonomicFilters.family = taxonomy.family || null;
        taxonomicFilters.genus = taxonomy.genus || value;
        taxonomicFilters.species = null;

        // Update family dropdown if we have a family
        if (taxonomy.family) {
          const familySelect = document.getElementById("family-filter");
          if (familySelect) {
            familySelect.value = taxonomy.family;
            // Load genera for this family
            loadGenera().then(() => {
              // After genera are loaded, set the genus
              const genusSelect = document.getElementById("genus-filter");
              if (genusSelect) {
                genusSelect.value = taxonomy.genus || value;
                // Load species for this genus
                loadSpecies();
              }
            });
          }
        }
      } catch (e) {
        console.error("Error parsing genus taxonomy data:", e);
        // Fallback to just setting genus
        taxonomicFilters.genus = value;
        taxonomicFilters.species = null;
        const genusSelect = document.getElementById("genus-filter");
        if (genusSelect && !genusSelect.disabled) {
          genusSelect.value = value;
          loadSpecies();
        }
      }
    } else {
      // Fallback for backward compatibility
      taxonomicFilters.genus = value;
      taxonomicFilters.species = null;
      const genusSelect = document.getElementById("genus-filter");
      if (genusSelect && !genusSelect.disabled) {
        genusSelect.value = value;
        loadSpecies();
      }
    }
  } else if (type === "species") {
    // Handle hierarchical filtering for species
    if (taxonomyData) {
      try {
        // Parse the taxonomy data
        const taxonomy = JSON.parse(taxonomyData);

        // Set all three levels hierarchically
        taxonomicFilters.family = taxonomy.family || null;
        taxonomicFilters.genus = taxonomy.genus || null;
        taxonomicFilters.species = taxonomy.species || value;

        // Update family dropdown if we have a family
        if (taxonomy.family) {
          const familySelect = document.getElementById("family-filter");
          if (familySelect) {
            familySelect.value = taxonomy.family;
            // Load genera for this family
            loadGenera().then(() => {
              // After genera are loaded, set the genus
              if (taxonomy.genus) {
                const genusSelect = document.getElementById("genus-filter");
                if (genusSelect) {
                  genusSelect.value = taxonomy.genus;
                  // Load species for this genus
                  loadSpecies().then(() => {
                    // After species are loaded, set the species
                    const speciesSelect =
                      document.getElementById("species-filter");
                    if (speciesSelect) {
                      speciesSelect.value = taxonomy.species;
                    }
                  });
                }
              }
            });
          }
        }
      } catch (e) {
        console.error("Error parsing taxonomy data:", e);
        // Fallback to just setting species
        taxonomicFilters.species = value;
        const speciesSelect = document.getElementById("species-filter");
        if (speciesSelect && !speciesSelect.disabled) {
          speciesSelect.value = value;
        }
      }
    } else {
      // Fallback for backward compatibility
      taxonomicFilters.species = value;
      const speciesSelect = document.getElementById("species-filter");
      if (speciesSelect && !speciesSelect.disabled) {
        speciesSelect.value = value;
      }
    }
  }

  updateActiveFilters();

  // Call page-specific reload function
  if (typeof onFiltersChanged === "function") {
    onFiltersChanged();
  }
}

/**
 * Initialize taxonomic filters from URL parameters
 * This should be called on page load to restore filter state from URL
 */
async function initializeFiltersFromURL() {
  const url = new URL(window.location.href);

  // Read URL parameters into filter state
  if (url.searchParams.has("family")) {
    taxonomicFilters.family = url.searchParams.get("family");
  }
  if (url.searchParams.has("genus")) {
    taxonomicFilters.genus = url.searchParams.get("genus");
  }
  if (url.searchParams.has("species")) {
    taxonomicFilters.species = url.searchParams.get("species");
  }
  if (url.searchParams.has("confidence")) {
    taxonomicFilters.minConfidence = parseFloat(
      url.searchParams.get("confidence"),
    );
  }

  // Load families and set filter values hierarchically
  await loadFamilies();

  // Set family filter if present
  if (taxonomicFilters.family) {
    const familySelect = document.getElementById("family-filter");
    if (familySelect) {
      familySelect.value = taxonomicFilters.family;
      await loadGenera();
    }
  }

  // Set genus filter if present
  if (taxonomicFilters.genus) {
    const genusSelect = document.getElementById("genus-filter");
    if (genusSelect) {
      genusSelect.value = taxonomicFilters.genus;
      await loadSpecies();
    }
  }

  // Set species filter if present
  if (taxonomicFilters.species) {
    const speciesSelect = document.getElementById("species-filter");
    if (speciesSelect) {
      speciesSelect.value = taxonomicFilters.species;
    }
  }

  // Set confidence filter if present and element exists
  if (taxonomicFilters.minConfidence) {
    const confidenceFilter = document.getElementById("confidence-filter");
    if (confidenceFilter) {
      confidenceFilter.value = taxonomicFilters.minConfidence;
    }
  }

  // Update active filter display
  updateActiveFilters();
}

// Export functions globally
window.loadFamilies = loadFamilies;
window.loadGenera = loadGenera;
window.loadSpecies = loadSpecies;
window.updateActiveFilters = updateActiveFilters;
window.removeFilter = removeFilter;
window.clearAllFilters = clearAllFilters;
window.setFilterFromLabel = setFilterFromLabel;
window.initializeFiltersFromURL = initializeFiltersFromURL;
window.taxonomicFilters = taxonomicFilters;
