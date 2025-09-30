/**
 * Update System JavaScript
 * Handles update checking, application, and git configuration
 */

// Migration: Now using global _() function from i18n.js

// Update status and progress handling
const updateManager = {
  checkButton: null,
  applyButton: null,
  testButton: null,
  cancelButton: null,
  statusPanel: null,
  progressPanel: null,
  progressFill: null,
  progressText: null,
  progressLog: null,
  updateActions: null,

  init() {
    // Get DOM elements
    this.checkButton = document.getElementById("check-updates-btn");
    this.applyButton = document.getElementById("apply-update-btn");
    this.testButton = document.getElementById("test-update-btn");
    this.cancelButton = document.getElementById("cancel-update-btn");
    this.statusPanel = document.getElementById("update-status-panel");
    this.progressPanel = document.getElementById("update-progress-panel");
    this.progressFill = document.getElementById("progress-fill");
    this.progressText = document.getElementById("progress-text");
    this.progressLog = document.getElementById("progress-log");
    this.updateActions = document.getElementById("update-actions");

    // Set up event listeners
    if (this.checkButton) {
      this.checkButton.addEventListener("click", () => this.checkForUpdates());
    }
    if (this.applyButton) {
      this.applyButton.addEventListener("click", () => this.applyUpdate(false));
    }
    if (this.testButton) {
      this.testButton.addEventListener("click", () => this.applyUpdate(true));
    }
    if (this.cancelButton) {
      this.cancelButton.addEventListener("click", () => this.cancelUpdate());
    }
  },

  async checkForUpdates() {
    try {
      this.checkButton.disabled = true;
      this.checkButton.textContent = _("checking");

      const response = await fetch("/api/update/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ force: true }),
      });

      const data = await response.json();

      if (data.available) {
        // Update UI with available update info
        document.getElementById("latest-version").textContent =
          data.latest_version;
        document.getElementById("update-status").innerHTML =
          `<span class="badge badge-warning">${_("update-available")}</span>`;

        if (data.release_notes) {
          document.getElementById("release-notes").innerHTML =
            data.release_notes;
        }

        // Show update actions
        if (this.updateActions) {
          this.updateActions.style.display = "block";
        }
      } else {
        document.getElementById("update-status").innerHTML =
          `<span class="badge badge-success">${_("up-to-date")}</span>`;

        // Hide update actions
        if (this.updateActions) {
          this.updateActions.style.display = "none";
        }
      }
    } catch (error) {
      console.error(_("failed-to-check-updates"), error);
      document.getElementById("update-status").innerHTML =
        `<span class="badge badge-error">${_("error")}: ${error.message}</span>`;
    } finally {
      this.checkButton.disabled = false;
      this.checkButton.textContent = _("check-for-updates");
    }
  },

  async applyUpdate(dryRun) {
    try {
      const version = document.getElementById("latest-version").textContent;

      // Show progress panel
      this.progressPanel.style.display = "block";
      this.progressText.textContent = dryRun
        ? _("starting-test-update")
        : _("starting-update");

      // Disable buttons
      this.applyButton.disabled = true;
      this.testButton.disabled = true;

      const response = await fetch("/api/update/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          version: version,
          dry_run: dryRun,
        }),
      });

      const data = await response.json();

      if (data.success) {
        this.progressText.textContent = data.message;
        // TODO: Connect to SSE for real-time progress
      } else {
        this.progressText.textContent = `Error: ${data.error}`;
      }
    } catch (error) {
      console.error(_("failed-to-apply-update"), error);
      this.progressText.textContent = `Error: ${error.message}`;
    }
  },

  async cancelUpdate() {
    try {
      const response = await fetch("/api/update/cancel", {
        method: "DELETE",
      });

      const data = await response.json();

      if (data.success) {
        this.progressText.textContent = _("update-cancelled");
        setTimeout(() => {
          this.progressPanel.style.display = "none";
        }, 2000);
      }
    } catch (error) {
      console.error(_("failed-to-cancel-update"), error);
    }
  },
};

// Git configuration handling
const gitConfig = {
  form: null,
  remoteInput: null,
  branchInput: null,
  messageDiv: null,

  init() {
    this.form = document.getElementById("git-config-form");
    this.remoteInput = document.getElementById("git-remote");
    this.branchInput = document.getElementById("git-branch");
    this.messageDiv = document.getElementById("git-config-message");

    if (this.form) {
      this.form.addEventListener("submit", (e) => this.handleSubmit(e));
    }
  },

  async handleSubmit(event) {
    event.preventDefault();

    try {
      // Get form values
      const gitRemote = this.remoteInput.value.trim();
      const gitBranch = this.branchInput.value.trim();

      // Validate inputs
      if (!gitRemote.match(/^[a-zA-Z0-9_-]+$/)) {
        this.showMessage(_("invalid-remote-format"), "error");
        return;
      }

      if (!gitBranch.match(/^[a-zA-Z0-9/_-]+$/)) {
        this.showMessage(_("invalid-branch-format"), "error");
        return;
      }

      // Submit to API
      const response = await fetch("/api/update/config/git", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          git_remote: gitRemote,
          git_branch: gitBranch,
        }),
      });

      const data = await response.json();

      if (data.success) {
        this.showMessage(data.message, "success");
      } else {
        this.showMessage(data.error || _("failed-to-save-config"), "error");
      }
    } catch (error) {
      console.error(_("failed-to-save-git-config"), error);
      this.showMessage(`Error: ${error.message}`, "error");
    }
  },

  showMessage(message, type) {
    if (this.messageDiv) {
      this.messageDiv.textContent = message;
      this.messageDiv.className = `config-message ${type}`;
      this.messageDiv.style.display = "block";

      // Hide message after 5 seconds
      setTimeout(() => {
        this.messageDiv.style.display = "none";
      }, 5000);
    }
  },
};

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  updateManager.init();
  gitConfig.init();
});
