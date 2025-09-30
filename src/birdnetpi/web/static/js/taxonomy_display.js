/**
 * Taxonomy Display Component
 * Provides functions for creating consistent taxonomy displays across the application
 */

/**
 * Create a taxonomy display HTML element
 * @param {Object} data - Species data
 * @param {string} data.common_name - Common name
 * @param {string} data.scientific_name - Scientific name
 * @param {string} data.genus - Genus name
 * @param {string} data.species - Species epithet
 * @param {string} data.order - Order name
 * @param {string} data.family - Family name
 * @param {Object} options - Display options
 * @param {boolean} options.showLinks - Whether to show clickable links (default: true)
 * @param {string} options.linkFunction - Function to call on link click (default: 'setFilterFromLabel')
 * @returns {string} HTML string for taxonomy display
 */
function createTaxonomyDisplay(data, options = {}) {
  const showLinks = options.showLinks !== false;
  const linkFunction = options.linkFunction || "setFilterFromLabel";

  // Extract species epithet from scientific name if not provided
  const speciesPart =
    data.species ||
    (data.scientific_name
      ? data.scientific_name.split(" ").slice(1).join(" ")
      : "");

  let html = '<div class="taxonomy-display">';

  // Primary name (common or scientific)
  html += '<div class="taxonomy-primary">';
  html += `<span class="common-name">${data.common_name || data.scientific_name || ""}</span>`;
  html += "</div>";

  // Scientific name with optional links
  if (data.scientific_name) {
    html += '<div class="taxonomy-scientific"><em>';
    if (showLinks && data.genus) {
      // Genus link with family data for hierarchical filtering
      const genusData = JSON.stringify({
        family: data.family || "",
        genus: data.genus,
      })
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
      html += `<span class="taxonomy-link" onclick="${linkFunction}('genus', '${data.genus}', '${genusData}')">${data.genus}</span> `;

      // Species epithet link with full taxonomy data for hierarchical filtering
      const taxonomyData = JSON.stringify({
        family: data.family || "",
        genus: data.genus,
        species: data.scientific_name,
      })
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
      html += `<span class="taxonomy-link" onclick="${linkFunction}('species', '${data.scientific_name}', '${taxonomyData}')">${speciesPart}</span>`;
    } else {
      html += data.scientific_name;
    }
    html += "</em></div>";
  }

  // Order and family classification
  if (data.order || data.family) {
    html += '<div class="taxonomy-classification">';
    if (data.order) {
      html += `<span class="order-name">${data.order}</span>`;
      if (data.family) html += " · ";
    }
    if (data.family) {
      if (showLinks) {
        html += `<span class="taxonomy-link" onclick="${linkFunction}('family', '${data.family}')">${data.family}</span>`;
      } else {
        html += `<span class="family-name">${data.family}</span>`;
      }
    }
    html += "</div>";
  }

  html += "</div>";
  return html;
}

/**
 * Create a compact taxonomy display for table cells
 * @param {Object} data - Species data (same as createTaxonomyDisplay)
 * @param {Object} options - Display options (same as createTaxonomyDisplay)
 * @returns {string} HTML string for compact taxonomy display
 */
function createCompactTaxonomyDisplay(data, options = {}) {
  const showLinks = options.showLinks !== false;
  const linkFunction = options.linkFunction || "setFilterFromLabel";

  let html = '<div class="taxonomy-compact">';

  // Common name
  html += `<div class="common-name">${data.common_name || data.scientific_name || ""}</div>`;

  // Scientific name
  if (data.scientific_name) {
    html += '<div class="scientific-name"><em>';
    if (showLinks) {
      // Extract genus and species epithet from the scientific name
      const parts = data.scientific_name.split(" ");
      const genusName = parts[0] || "";
      const speciesPart = parts.slice(1).join(" ") || "";

      // Genus link with family data for hierarchical filtering
      const genusData = JSON.stringify({
        family: data.family || "",
        genus: genusName,
      })
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
      html += `<span class="taxonomy-link" onclick="${linkFunction}('genus', '${genusName}', '${genusData}')">${genusName}</span> `;

      // Species epithet link with full taxonomy data for hierarchical filtering
      const taxonomyData = JSON.stringify({
        family: data.family || "",
        genus: genusName,
        species: data.scientific_name,
      })
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
      html += `<span class="taxonomy-link" onclick="${linkFunction}('species', '${data.scientific_name}', '${taxonomyData}')">${speciesPart}</span>`;
    } else {
      html += data.scientific_name;
    }
    html += "</em></div>";
  }

  // Order and family on one line
  if (data.order || data.family) {
    html += '<div class="taxonomy-meta">';
    if (data.order) {
      // Format order name to title case (PASSERIFORMES -> Passeriformes)
      const formattedOrder =
        data.order.charAt(0).toUpperCase() + data.order.slice(1).toLowerCase();
      html += `${formattedOrder}`;
      if (data.family) html += " · ";
    }
    if (data.family) {
      if (showLinks) {
        html += `<span class="taxonomy-link" onclick="${linkFunction}('family', '${data.family}')">${data.family}</span>`;
      } else {
        html += data.family;
      }
    }
    html += "</div>";
  }

  html += "</div>";
  return html;
}

// Export functions globally
window.createTaxonomyDisplay = createTaxonomyDisplay;
window.createCompactTaxonomyDisplay = createCompactTaxonomyDisplay;
