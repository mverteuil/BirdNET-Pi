/**
 * Navigation JavaScript - Admin dropdown accessibility
 */

// Initialize navigation on DOM content loaded
document.addEventListener("DOMContentLoaded", function () {
  const dropdown = document.querySelector(".admin-dropdown");
  if (!dropdown) return; // Exit if no dropdown present

  const button = dropdown.querySelector("button");
  const menu = dropdown.querySelector(".admin-menu");

  if (!button || !menu) return; // Exit if elements not found

  let isMenuOpen = false;
  let hoverTimeout = null;

  // Function to show menu
  function showMenu() {
    clearTimeout(hoverTimeout);
    isMenuOpen = true;
    menu.style.display = "block";
    button.setAttribute("aria-expanded", "true");
  }

  // Function to hide menu
  function hideMenu() {
    clearTimeout(hoverTimeout);
    isMenuOpen = false;
    menu.style.display = "none";
    button.setAttribute("aria-expanded", "false");
  }

  // Handle hover on the entire dropdown container
  dropdown.addEventListener("mouseenter", function () {
    clearTimeout(hoverTimeout);
    showMenu();
  });

  dropdown.addEventListener("mouseleave", function () {
    // Small delay to prevent flickering when moving between button and menu
    hoverTimeout = setTimeout(() => {
      if (!dropdown.matches(":hover")) {
        hideMenu();
      }
    }, 100);
  });

  // Handle click on button to toggle menu
  button.addEventListener("click", function (e) {
    e.preventDefault();
    e.stopPropagation();
    if (isMenuOpen) {
      hideMenu();
    } else {
      showMenu();
    }
  });

  // Close menu when clicking outside
  document.addEventListener("click", function (e) {
    if (!dropdown.contains(e.target)) {
      hideMenu();
    }
  });

  // Handle focus for keyboard navigation
  button.addEventListener("focus", function () {
    showMenu();
  });

  button.addEventListener("blur", function (e) {
    // Check if focus moved to a child element
    setTimeout(() => {
      if (!dropdown.contains(document.activeElement)) {
        hideMenu();
      }
    }, 0);
  });

  // Handle Enter/Space key on button
  button.addEventListener("keydown", function (e) {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      showMenu();
      const firstLink = menu.querySelector("a");
      if (firstLink) firstLink.focus();
    }
  });

  // Keep menu visible when focusing within it
  menu.addEventListener("focusin", function () {
    showMenu();
  });

  // Handle arrow keys in menu
  menu.addEventListener("keydown", function (e) {
    const items = Array.from(menu.querySelectorAll("a"));
    const currentIndex = items.indexOf(document.activeElement);

    if (e.key === "ArrowDown" && currentIndex < items.length - 1) {
      e.preventDefault();
      items[currentIndex + 1].focus();
    } else if (e.key === "ArrowUp" && currentIndex > 0) {
      e.preventDefault();
      items[currentIndex - 1].focus();
    } else if (e.key === "Escape") {
      button.focus();
      hideMenu();
    }
  });
});
