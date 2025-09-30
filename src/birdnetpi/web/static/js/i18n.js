/**
 * i18n module for BirdNET-Pi JavaScript
 *
 * This module provides internationalization support for JavaScript code,
 * loading translations from the server and providing a simple API for
 * accessing translated strings.
 */

(function (window) {
  "use strict";

  // Cache for translations
  let translations = {};
  let currentLanguage = "en";
  let isLoaded = false;
  let loadPromise = null;

  /**
   * Load translations from the server
   * @param {string} lang - Optional language code to load
   * @returns {Promise} Promise that resolves when translations are loaded
   */
  function loadTranslations(lang) {
    // If already loading, return the existing promise
    if (loadPromise) {
      return loadPromise;
    }

    const url = lang
      ? `/api/i18n/translations?lang=${lang}`
      : "/api/i18n/translations";

    loadPromise = fetch(url)
      .then((response) => response.json())
      .then((data) => {
        translations = data.translations || {};
        currentLanguage = data.language || "en";
        isLoaded = true;
        loadPromise = null;
        return data;
      })
      .catch((error) => {
        console.error("Failed to load translations:", error);
        // Fallback to empty translations
        translations = {};
        isLoaded = true;
        loadPromise = null;
        throw error;
      });

    return loadPromise;
  }

  /**
   * Get a translated string
   * @param {string} key - Translation key
   * @param {Object} params - Optional parameters for string interpolation
   * @returns {string} Translated string or key if not found
   */
  function gettext(key, params) {
    // Fallback to key if translation not found
    let text = translations[key] || key;

    // Handle parameter interpolation (Python-style %(name)s format)
    if (params) {
      for (const [name, value] of Object.entries(params)) {
        const pattern = new RegExp(`%\\(${name}\\)s`, "g");
        text = text.replace(pattern, value);
      }
    }

    return text;
  }

  /**
   * Shorthand alias for gettext
   */
  function _(key, params) {
    return gettext(key, params);
  }

  /**
   * Get plural form of a translated string
   * @param {string} singular - Singular form key
   * @param {string} plural - Plural form key
   * @param {number} count - Count for determining plural form
   * @param {Object} params - Optional parameters for string interpolation
   * @returns {string} Translated string
   */
  function ngettext(singular, plural, count, params) {
    // Simple English pluralization for now
    // TODO: Support language-specific plural rules
    const key = count === 1 ? singular : plural;
    const text = gettext(key, params);

    // Replace %(count)s with the actual count
    return text.replace(/%(count)s/g, count);
  }

  /**
   * Initialize i18n with auto-loading based on page language
   * @returns {Promise} Promise that resolves when initialization is complete
   */
  function init() {
    // Check query parameter first (for testing)
    const urlParams = new URLSearchParams(window.location.search);
    const queryLang = urlParams.get("lang");

    // Get language from query param, HTML lang attribute, or browser
    const htmlLang = document.documentElement.lang;
    const lang =
      queryLang || htmlLang || navigator.language.split("-")[0] || "en";

    return loadTranslations(lang);
  }

  /**
   * Get current language
   * @returns {string} Current language code
   */
  function getLanguage() {
    return currentLanguage;
  }

  /**
   * Check if translations are loaded
   * @returns {boolean} True if translations are loaded
   */
  function ready() {
    return isLoaded;
  }

  /**
   * Ensure translations are loaded before executing callback
   * @param {Function} callback - Function to execute after translations are loaded
   */
  function ensureLoaded(callback) {
    if (isLoaded) {
      callback();
    } else {
      init()
        .then(callback)
        .catch((error) => {
          console.error("Failed to initialize i18n:", error);
          callback(); // Continue anyway with fallback to keys
        });
    }
  }

  // Export the i18n module
  window.i18n = {
    init: init,
    load: loadTranslations,
    gettext: gettext,
    _: _,
    ngettext: ngettext,
    getLanguage: getLanguage,
    ready: ready,
    ensureLoaded: ensureLoaded,
  };

  // Also export as globals for compatibility with existing code
  window.gettext = gettext;
  window._ = _;
  window.ngettext = ngettext;

  // Auto-initialize when DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    // DOM is already loaded
    init();
  }
})(window);
