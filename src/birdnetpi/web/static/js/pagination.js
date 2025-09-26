/**
 * Common pagination functionality for BirdNET-Pi
 *
 * This module provides reusable pagination rendering for all paginated views.
 */

/**
 * Render pagination controls
 *
 * @param {string} elementId - ID of the element to render pagination into
 * @param {Object} data - Pagination data from API response
 * @param {number} data.page - Current page number
 * @param {number} data.total_pages - Total number of pages
 * @param {number} data.total - Total number of items
 * @param {boolean} data.has_prev - Whether there's a previous page
 * @param {boolean} data.has_next - Whether there's a next page
 * @param {Function} loadFunction - Function to call to load a specific page
 * @param {string} itemName - Name of items being paginated (default: 'items')
 */
function renderPagination(elementId, data, loadFunction, itemName = "items") {
  const pagination = document.getElementById(elementId);
  if (!pagination) {
    console.error(`Pagination element ${elementId} not found`);
    return;
  }

  let paginationHTML = "";

  if (data.total_pages > 1) {
    // Show page info
    paginationHTML = `
            <span class="text-secondary">
                Page ${data.page} of ${data.total_pages}
                (${data.total} total ${itemName})
            </span><br>
        `;

    // Previous page links
    if (data.has_prev) {
      paginationHTML += `<a href="#" onclick="${loadFunction}(1); return false;">« First</a> `;
      paginationHTML += `<a href="#" onclick="${loadFunction}(${data.page - 1}); return false;">‹ Prev</a> `;
    }

    // Page numbers
    const startPage = Math.max(1, data.page - 2);
    const endPage = Math.min(data.total_pages, data.page + 2);

    for (let i = startPage; i <= endPage; i++) {
      if (i === data.page) {
        paginationHTML += `<span class="current-page">${i}</span> `;
      } else {
        paginationHTML += `<a href="#" onclick="${loadFunction}(${i}); return false;">${i}</a> `;
      }
    }

    // Next page links
    if (data.has_next) {
      paginationHTML += `<a href="#" onclick="${loadFunction}(${data.page + 1}); return false;">Next ›</a> `;
      paginationHTML += `<a href="#" onclick="${loadFunction}(${data.total_pages}); return false;">Last »</a>`;
    }
  } else if (data.total > 0) {
    // Single page with items
    paginationHTML = `<span class="text-secondary">${data.total} ${itemName}</span>`;
  } else {
    // No items
    paginationHTML = `<span class="text-secondary">No ${itemName} found</span>`;
  }

  pagination.innerHTML = paginationHTML;
}

/**
 * Create a pagination handler for a specific view
 *
 * @param {string} elementId - ID of pagination container
 * @param {Function} loadFunction - Function to load page data
 * @param {string} itemName - Name of items for display
 * @returns {Function} Function to render pagination for this view
 */
function createPaginationHandler(elementId, loadFunction, itemName = "items") {
  return function (data) {
    renderPagination(elementId, data, loadFunction, itemName);
  };
}

// Export for use in other scripts
window.BirdNETPagination = {
  render: renderPagination,
  createHandler: createPaginationHandler,
};
