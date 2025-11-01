/**
 * Period Selector - Calendar-based time period selection with hemisphere-aware seasons
 */

class PeriodSelector {
  constructor(containerId, options = {}) {
    this.container = document.getElementById(containerId);
    if (!this.container) {
      throw new Error(`Period selector container not found: ${containerId}`);
    }

    // Configuration
    this.latitude =
      options.latitude !== undefined
        ? options.latitude
        : window.siteConfig?.latitude || 0;
    this.longitude =
      options.longitude !== undefined
        ? options.longitude
        : window.siteConfig?.longitude || 0;
    this.onChangeCallback = options.onChangeCallback || null;
    this.showHistorical = options.showHistorical !== false;
    this.oldestDetectionDate = options.oldestDetectionDate || null;
    this.updateUrl = options.updateUrl !== false; // Enable URL updates by default

    // Initialize state from URL or defaults
    this.initializeFromUrl(options);

    // Initialize
    this.render();
    this.attachEventListeners();
    this.setupPopStateHandler();

    // Push initial state to URL if not already present
    if (!window.location.search.includes("period=")) {
      this.updateUrlState();
    }

    // Notify callback on initialization so parent page has initial bounds
    this.notifyChange();
  }

  /**
   * Initialize period and date from URL query parameters
   */
  initializeFromUrl(options) {
    const params = new URLSearchParams(window.location.search);

    // Get period from URL or use provided default
    this.currentPeriod = params.get("period") || options.initialPeriod || "day";

    // Get date from URL or use provided default
    const dateParam = params.get("date");
    if (dateParam) {
      this.currentDate = new Date(dateParam);
    } else if (options.initialDate) {
      this.currentDate = new Date(options.initialDate);
    } else {
      this.currentDate = new Date();
    }
  }

  /**
   * Setup handler for browser back/forward navigation
   */
  setupPopStateHandler() {
    window.addEventListener("popstate", (event) => {
      if (event.state && event.state.period) {
        this.currentPeriod = event.state.period;
        this.currentDate = new Date(event.state.date);
        this.render();
        this.notifyChange();
      }
    });
  }

  /**
   * Update URL with current period selection
   */
  updateUrlState() {
    if (!this.updateUrl) {
      return;
    }

    const params = new URLSearchParams(window.location.search);
    params.set("period", this.currentPeriod);
    params.set("date", this.currentDate.toISOString().split("T")[0]);

    const newUrl = `${window.location.pathname}?${params.toString()}`;
    const state = {
      period: this.currentPeriod,
      date: this.currentDate.toISOString().split("T")[0],
    };

    // Push to history to enable back/forward navigation
    window.history.pushState(state, "", newUrl);
  }

  /**
   * Get hemisphere from latitude
   */
  getHemisphere() {
    if (Math.abs(this.latitude) < 23.5) {
      return "equatorial";
    }
    return this.latitude > 0 ? "northern" : "southern";
  }

  /**
   * Get season name based on month and hemisphere
   */
  getSeasonName(month, year) {
    const hemisphere = this.getHemisphere();

    if (hemisphere === "equatorial") {
      // Simple dry/wet season or quarters
      return month >= 5 && month <= 10
        ? _("Wet Season %(year)s", { year })
        : _("Dry Season %(year)s", { year });
    }

    const isNorthern = hemisphere === "northern";

    // Month is 0-indexed (0=Jan, 11=Dec)
    if (month === 11 || month === 0 || month === 1) {
      // Dec, Jan, Feb
      return isNorthern
        ? _("Winter %(year)s", { year })
        : _("Summer %(year)s", { year });
    } else if (month >= 2 && month <= 4) {
      // Mar, Apr, May
      return isNorthern
        ? _("Spring %(year)s", { year })
        : _("Fall %(year)s", { year });
    } else if (month >= 5 && month <= 7) {
      // Jun, Jul, Aug
      return isNorthern
        ? _("Summer %(year)s", { year })
        : _("Winter %(year)s", { year });
    } else {
      // Sep, Oct, Nov
      return isNorthern
        ? _("Fall %(year)s", { year })
        : _("Spring %(year)s", { year });
    }
  }

  /**
   * Get bounds for the current period
   */
  getPeriodBounds() {
    const date = new Date(this.currentDate);
    let startDate, endDate, displayLabel;

    switch (this.currentPeriod) {
      case "day":
        startDate = new Date(date);
        startDate.setHours(0, 0, 0, 0);
        endDate = new Date(date);
        endDate.setHours(23, 59, 59, 999);
        displayLabel = date.toLocaleDateString(undefined, {
          weekday: "long",
          year: "numeric",
          month: "long",
          day: "numeric",
        });
        break;

      case "week":
        // Get Monday of the week
        const dayOfWeek = date.getDay();
        const diff = dayOfWeek === 0 ? -6 : 1 - dayOfWeek; // Sunday = 0, Monday = 1
        startDate = new Date(date);
        startDate.setDate(date.getDate() + diff);
        startDate.setHours(0, 0, 0, 0);

        endDate = new Date(startDate);
        endDate.setDate(startDate.getDate() + 6);
        endDate.setHours(23, 59, 59, 999);

        displayLabel = _("Week of %(date)s", {
          date: startDate.toLocaleDateString(undefined, {
            month: "short",
            day: "numeric",
            year: "numeric",
          }),
        });
        break;

      case "month":
        startDate = new Date(
          date.getFullYear(),
          date.getMonth(),
          1,
          0,
          0,
          0,
          0,
        );
        endDate = new Date(
          date.getFullYear(),
          date.getMonth() + 1,
          0,
          23,
          59,
          59,
          999,
        );
        displayLabel = date.toLocaleDateString(undefined, {
          month: "long",
          year: "numeric",
        });
        break;

      case "season":
        const seasonBounds = this.getSeasonBounds(date);
        startDate = seasonBounds.start;
        endDate = seasonBounds.end;
        displayLabel = this.getSeasonName(date.getMonth(), date.getFullYear());
        break;

      case "year":
        startDate = new Date(date.getFullYear(), 0, 1, 0, 0, 0, 0);
        endDate = new Date(date.getFullYear(), 11, 31, 23, 59, 59, 999);
        displayLabel = date.getFullYear().toString();
        break;

      case "historical":
        // Use actual oldest detection date, or fall back to 1970-01-01
        if (this.oldestDetectionDate) {
          startDate = new Date(this.oldestDetectionDate);
          startDate.setHours(0, 0, 0, 0);
        } else {
          startDate = new Date(1970, 0, 1, 0, 0, 0, 0);
        }
        endDate = new Date();
        displayLabel = _("All Time");
        break;

      default:
        throw new Error(`Unknown period type: ${this.currentPeriod}`);
    }

    return {
      period_type: this.currentPeriod,
      start_date: this.formatDateISO(startDate),
      end_date: this.formatDateISO(endDate),
      display_label: displayLabel,
      hemisphere: this.getHemisphere(),
    };
  }

  /**
   * Get season bounds based on hemisphere
   */
  getSeasonBounds(date) {
    const hemisphere = this.getHemisphere();
    const year = date.getFullYear();
    const month = date.getMonth(); // 0-indexed

    if (hemisphere === "equatorial") {
      // Wet: May-Oct, Dry: Nov-Apr
      if (month >= 4 && month <= 9) {
        // Wet season
        return {
          start: new Date(year, 4, 1, 0, 0, 0, 0),
          end: new Date(year, 9, 31, 23, 59, 59, 999),
        };
      } else {
        // Dry season spans year boundary
        if (month >= 10) {
          return {
            start: new Date(year, 10, 1, 0, 0, 0, 0),
            end: new Date(year + 1, 3, 30, 23, 59, 59, 999),
          };
        } else {
          return {
            start: new Date(year - 1, 10, 1, 0, 0, 0, 0),
            end: new Date(year, 3, 30, 23, 59, 59, 999),
          };
        }
      }
    }

    const isNorthern = hemisphere === "northern";

    if (month === 11 || month === 0 || month === 1) {
      // Dec, Jan, Feb - Winter (N) / Summer (S)
      if (month === 11) {
        return {
          start: new Date(year, 11, 1, 0, 0, 0, 0),
          end: new Date(year + 1, 1, isNorthern ? 28 : 29, 23, 59, 59, 999),
        };
      } else {
        return {
          start: new Date(year - 1, 11, 1, 0, 0, 0, 0),
          end: new Date(year, 1, isNorthern ? 28 : 29, 23, 59, 59, 999),
        };
      }
    } else if (month >= 2 && month <= 4) {
      // Mar, Apr, May - Spring (N) / Fall (S)
      return {
        start: new Date(year, 2, 1, 0, 0, 0, 0),
        end: new Date(year, 4, 31, 23, 59, 59, 999),
      };
    } else if (month >= 5 && month <= 7) {
      // Jun, Jul, Aug - Summer (N) / Winter (S)
      return {
        start: new Date(year, 5, 1, 0, 0, 0, 0),
        end: new Date(year, 7, 31, 23, 59, 59, 999),
      };
    } else {
      // Sep, Oct, Nov - Fall (N) / Spring (S)
      return {
        start: new Date(year, 8, 1, 0, 0, 0, 0),
        end: new Date(year, 10, 30, 23, 59, 59, 999),
      };
    }
  }

  /**
   * Format date as ISO string (YYYY-MM-DD)
   */
  formatDateISO(date) {
    return date.toISOString().split("T")[0];
  }

  /**
   * Navigate to previous period
   */
  navigatePrevious() {
    const newDate = new Date(this.currentDate);

    switch (this.currentPeriod) {
      case "day":
        newDate.setDate(newDate.getDate() - 1);
        break;

      case "week":
        newDate.setDate(newDate.getDate() - 7);
        break;

      case "month":
        newDate.setMonth(newDate.getMonth() - 1);
        break;

      case "season":
        newDate.setMonth(newDate.getMonth() - 3);
        break;

      case "year":
        newDate.setFullYear(newDate.getFullYear() - 1);
        break;

      case "historical":
        return; // No navigation for historical
    }

    this.currentDate = newDate;
    this.update();
  }

  /**
   * Navigate to next period
   */
  navigateNext() {
    if (this.currentPeriod === "historical") {
      return; // No navigation for historical
    }

    const newDate = new Date(this.currentDate);

    switch (this.currentPeriod) {
      case "day":
        newDate.setDate(newDate.getDate() + 1);
        break;

      case "week":
        newDate.setDate(newDate.getDate() + 7);
        break;

      case "month":
        newDate.setMonth(newDate.getMonth() + 1);
        break;

      case "season":
        newDate.setMonth(newDate.getMonth() + 3);
        break;

      case "year":
        newDate.setFullYear(newDate.getFullYear() + 1);
        break;
    }

    // Don't allow navigation to future
    const today = new Date();
    const bounds = this.getPeriodBoundsForDate(newDate, this.currentPeriod);
    if (bounds.start > today) {
      return; // Future period, don't navigate
    }

    this.currentDate = newDate;
    this.update();
  }

  /**
   * Helper to get period bounds for a specific date
   */
  getPeriodBoundsForDate(date, periodType) {
    const oldPeriod = this.currentPeriod;
    const oldDate = this.currentDate;

    this.currentPeriod = periodType;
    this.currentDate = date;

    const bounds = this.getPeriodBounds();

    this.currentPeriod = oldPeriod;
    this.currentDate = oldDate;

    return {
      start: new Date(bounds.start_date),
      end: new Date(bounds.end_date),
    };
  }

  /**
   * Set period type
   */
  setPeriod(periodType) {
    if (this.currentPeriod === periodType) {
      return;
    }

    this.currentPeriod = periodType;
    this.currentDate = new Date(); // Reset to current date when changing period type
    this.update();
  }

  /**
   * Update display and notify callback
   */
  update() {
    this.render();
    this.attachEventListeners();

    // Don't update URL here - let the page callback handle it
    // to avoid race conditions with page-specific URL params

    // Notify callback (which will trigger page to update URL)
    this.notifyChange();
  }

  /**
   * Notify change listeners without updating URL
   * Used for browser back/forward navigation
   */
  notifyChange() {
    if (this.onChangeCallback) {
      const bounds = this.getPeriodBounds();
      this.onChangeCallback(bounds);
    }

    // Emit custom event
    this.container.dispatchEvent(
      new CustomEvent("periodchange", {
        detail: this.getPeriodBounds(),
        bubbles: true,
      }),
    );
  }

  /**
   * Render the selector
   */
  render() {
    const bounds = this.getPeriodBounds();
    const canGoNext = !this.isFuturePeriod();
    const canGoPrev = this.currentPeriod !== "historical";
    const canNavigate = this.currentPeriod !== "historical";

    const hemisphereLabel = this.getHemisphere();
    const seasonTooltip = `Seasons based on your location (${hemisphereLabel === "northern" ? "Northern" : hemisphereLabel === "southern" ? "Southern" : "Equatorial"} Hemisphere)`;

    this.container.innerHTML = `
      <div class="period-selector-container" role="group" aria-label="${_("Time period selection")}">
        <div class="period-types" role="radiogroup" aria-label="${_("Select period type")}">
          <button type="button"
                  role="radio"
                  aria-checked="${this.currentPeriod === "day"}"
                  class="period-btn ${this.currentPeriod === "day" ? "active" : ""}"
                  data-period="day">
            ${_("Day")}
          </button>
          <button type="button"
                  role="radio"
                  aria-checked="${this.currentPeriod === "week"}"
                  class="period-btn ${this.currentPeriod === "week" ? "active" : ""}"
                  data-period="week">
            ${_("Week")}
          </button>
          <button type="button"
                  role="radio"
                  aria-checked="${this.currentPeriod === "month"}"
                  class="period-btn ${this.currentPeriod === "month" ? "active" : ""}"
                  data-period="month">
            ${_("Month")}
          </button>
          <button type="button"
                  role="radio"
                  aria-checked="${this.currentPeriod === "season"}"
                  class="period-btn ${this.currentPeriod === "season" ? "active" : ""}"
                  data-period="season"
                  title="${seasonTooltip}">
            ${_("Season")}
          </button>
          <button type="button"
                  role="radio"
                  aria-checked="${this.currentPeriod === "year"}"
                  class="period-btn ${this.currentPeriod === "year" ? "active" : ""}"
                  data-period="year">
            ${_("Year")}
          </button>
          ${
            this.showHistorical
              ? `<button type="button"
                        role="radio"
                        aria-checked="${this.currentPeriod === "historical"}"
                        class="period-btn ${this.currentPeriod === "historical" ? "active" : ""}"
                        data-period="historical">
                  ${_("Historical")}
                </button>`
              : ""
          }
        </div>

        ${
          canNavigate
            ? `
        <div class="period-display">
          <button type="button"
                  class="nav-btn nav-prev ${!canGoPrev ? "disabled" : ""}"
                  aria-label="${_(`Previous ${this.currentPeriod}`)}"
                  ${!canGoPrev ? "disabled" : ""}>
            ←
          </button>
          <span class="period-label" role="status" aria-live="polite">
            ${bounds.display_label}
          </span>
          <button type="button"
                  class="nav-btn nav-next ${!canGoNext ? "disabled" : ""}"
                  aria-label="${_(`Next ${this.currentPeriod}`)}"
                  ${!canGoNext ? "disabled" : ""}>
            →
          </button>
        </div>
        `
            : `
        <div class="period-display">
          <span class="period-label" role="status">
            ${bounds.display_label}
          </span>
        </div>
        `
        }
      </div>
    `;
  }

  /**
   * Check if navigating forward would be in the future
   */
  isFuturePeriod() {
    if (this.currentPeriod === "historical") {
      return true;
    }

    const nextDate = new Date(this.currentDate);
    switch (this.currentPeriod) {
      case "day":
        nextDate.setDate(nextDate.getDate() + 1);
        break;
      case "week":
        nextDate.setDate(nextDate.getDate() + 7);
        break;
      case "month":
        nextDate.setMonth(nextDate.getMonth() + 1);
        break;
      case "season":
        nextDate.setMonth(nextDate.getMonth() + 3);
        break;
      case "year":
        nextDate.setFullYear(nextDate.getFullYear() + 1);
        break;
    }

    const bounds = this.getPeriodBoundsForDate(nextDate, this.currentPeriod);
    return bounds.start > new Date();
  }

  /**
   * Attach event listeners
   */
  attachEventListeners() {
    // Period type buttons
    this.container.querySelectorAll(".period-btn").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        const period = e.target.dataset.period;
        this.setPeriod(period);
      });
    });

    // Navigation buttons
    const prevBtn = this.container.querySelector(".nav-prev");
    const nextBtn = this.container.querySelector(".nav-next");

    if (prevBtn) {
      prevBtn.addEventListener("click", () => this.navigatePrevious());
    }

    if (nextBtn) {
      nextBtn.addEventListener("click", () => this.navigateNext());
    }

    // Keyboard navigation
    this.container.addEventListener("keydown", (e) => {
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        this.navigatePrevious();
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        this.navigateNext();
      }
    });
  }

  /**
   * Get current state
   */
  getState() {
    return this.getPeriodBounds();
  }
}

// Export for use in other scripts
window.PeriodSelector = PeriodSelector;
