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
    // Show page info with i18n support
    const pageInfo = window._
      ? window._("Page %(page)s of %(total_pages)s", {
          page: data.page,
          total_pages: data.total_pages,
        })
      : `Page ${data.page} of ${data.total_pages}`;

    const totalItems = window._
      ? window._("%(count)s total %(items)s", {
          count: data.total,
          items: itemName,
        })
      : `${data.total} total ${itemName}`;

    paginationHTML = `
            <span class="text-secondary" aria-live="polite">
                ${pageInfo}
                (${totalItems})
            </span><br>
        `;

    // Previous page links
    if (data.has_prev) {
      const firstLabel = window._
        ? window._("Go to first page")
        : "Go to first page";
      const prevLabel = window._
        ? window._("Go to previous page")
        : "Go to previous page";
      const firstText = window._ ? window._("First") : "First";
      const prevText = window._ ? window._("Prev") : "Prev";

      paginationHTML += `<a href="#" onclick="${loadFunction}(1); return false;" aria-label="${firstLabel}">« ${firstText}</a> `;
      paginationHTML += `<a href="#" onclick="${loadFunction}(${data.page - 1}); return false;" aria-label="${prevLabel}">‹ ${prevText}</a> `;
    }

    // Page numbers
    const startPage = Math.max(1, data.page - 2);
    const endPage = Math.min(data.total_pages, data.page + 2);

    for (let i = startPage; i <= endPage; i++) {
      if (i === data.page) {
        const currentLabel = window._
          ? window._("Current page, page %(page)s", { page: i })
          : `Current page, page ${i}`;
        paginationHTML += `<span class="current-page" aria-current="page" aria-label="${currentLabel}">${i}</span> `;
      } else {
        const pageLabel = window._
          ? window._("Go to page %(page)s", { page: i })
          : `Go to page ${i}`;
        paginationHTML += `<a href="#" onclick="${loadFunction}(${i}); return false;" aria-label="${pageLabel}">${i}</a> `;
      }
    }

    // Next page links
    if (data.has_next) {
      const nextLabel = window._
        ? window._("Go to next page")
        : "Go to next page";
      const lastLabel = window._
        ? window._("Go to last page")
        : "Go to last page";
      const nextText = window._ ? window._("Next") : "Next";
      const lastText = window._ ? window._("Last") : "Last";

      paginationHTML += `<a href="#" onclick="${loadFunction}(${data.page + 1}); return false;" aria-label="${nextLabel}">${nextText} ›</a> `;
      paginationHTML += `<a href="#" onclick="${loadFunction}(${data.total_pages}); return false;" aria-label="${lastLabel}">${lastText} »</a>`;
    }
  } else if (data.total > 0) {
    // Single page with items
    const totalItems = window._
      ? window._("%(count)s %(items)s", { count: data.total, items: itemName })
      : `${data.total} ${itemName}`;
    paginationHTML = `<span class="text-secondary" aria-live="polite">${totalItems}</span>`;
  } else {
    // No items
    const noItems = window._
      ? window._("No %(items)s found", { items: itemName })
      : `No ${itemName} found`;
    paginationHTML = `<span class="text-secondary" aria-live="polite">${noItems}</span>`;
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
