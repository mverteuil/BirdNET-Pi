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

// Git configuration handling (SBC only)
const gitConfig = {
  form: null,
  remoteSelect: null,
  branchSelect: null,
  messageDiv: null,
  manageRemotesBtn: null,
  currentRemotes: [],

  init() {
    // Only init for SBC deployments
    if (typeof deploymentType === "undefined" || deploymentType !== "sbc") {
      return;
    }

    this.form = document.getElementById("git-config-form");
    this.remoteSelect = document.getElementById("git-remote");
    this.branchSelect = document.getElementById("git-branch");
    this.messageDiv = document.getElementById("git-config-message");
    this.manageRemotesBtn = document.getElementById("manage-remotes-btn");

    if (this.form) {
      this.form.addEventListener("submit", (e) => this.handleSubmit(e));
    }

    if (this.remoteSelect) {
      this.remoteSelect.addEventListener("change", () => this.loadBranches());
    }

    if (this.manageRemotesBtn) {
      this.manageRemotesBtn.addEventListener("click", () =>
        gitRemoteManager.openModal(),
      );
    }

    // Load remotes on init
    this.loadRemotes();
  },

  async loadRemotes() {
    try {
      const response = await fetch("/api/update/git/remotes");
      const data = await response.json();

      this.currentRemotes = data.remotes;

      // Populate remote select
      this.remoteSelect.innerHTML = "";

      if (data.remotes.length === 0) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = _("no-remotes-configured");
        this.remoteSelect.appendChild(option);
      } else {
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = _("select-remote");
        this.remoteSelect.appendChild(placeholder);

        data.remotes.forEach((remote) => {
          const option = document.createElement("option");
          option.value = remote.name;
          option.textContent = `${remote.name} (${remote.url})`;
          this.remoteSelect.appendChild(option);
        });

        // Try to select current remote if available
        const currentRemoteValue = this.remoteSelect.dataset.currentValue;
        if (currentRemoteValue) {
          this.remoteSelect.value = currentRemoteValue;
          // Load branches for current remote
          this.loadBranches();
        }
      }
    } catch (error) {
      console.error("Failed to load git remotes:", error);
      this.showMessage(_("failed-to-load-remotes"), "error");
    }
  },

  async loadBranches() {
    const remoteName = this.remoteSelect.value;

    if (!remoteName) {
      this.branchSelect.innerHTML =
        '<option value="">' + _("select-remote-first") + "</option>";
      return;
    }

    try {
      this.branchSelect.innerHTML =
        '<option value="">' + _("loading-branches") + "</option>";
      this.branchSelect.disabled = true;

      const response = await fetch(
        `/api/update/git/branches/${encodeURIComponent(remoteName)}`,
      );
      const data = await response.json();

      this.branchSelect.innerHTML = "";
      this.branchSelect.disabled = false;

      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = _("select-branch-or-tag");
      this.branchSelect.appendChild(placeholder);

      // Add tags group
      if (data.tags && data.tags.length > 0) {
        const tagsGroup = document.createElement("optgroup");
        tagsGroup.label = _("tags");
        data.tags.forEach((tag) => {
          const option = document.createElement("option");
          option.value = tag;
          option.textContent = tag;
          tagsGroup.appendChild(option);
        });
        this.branchSelect.appendChild(tagsGroup);
      }

      // Add branches group
      if (data.branches && data.branches.length > 0) {
        const branchesGroup = document.createElement("optgroup");
        branchesGroup.label = _("branches");
        data.branches.forEach((branch) => {
          const option = document.createElement("option");
          option.value = branch;
          option.textContent = branch;
          branchesGroup.appendChild(option);
        });
        this.branchSelect.appendChild(branchesGroup);
      }

      // Try to select current branch if available
      const currentBranchValue = this.branchSelect.dataset.currentValue;
      if (currentBranchValue) {
        this.branchSelect.value = currentBranchValue;
      }
    } catch (error) {
      console.error("Failed to load branches:", error);
      this.branchSelect.innerHTML =
        '<option value="">' + _("failed-to-load-branches") + "</option>";
      this.branchSelect.disabled = false;
    }
  },

  async handleSubmit(event) {
    event.preventDefault();

    try {
      const gitRemote = this.remoteSelect.value;
      const gitBranch = this.branchSelect.value;

      if (!gitRemote || !gitBranch) {
        this.showMessage(_("select-remote-and-branch"), "error");
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

// Git Remote Management Modal
const gitRemoteManager = {
  modal: null,
  remoteList: null,
  addRemoteForm: null,
  closeBtn: null,

  init() {
    // Only init for SBC deployments
    if (typeof deploymentType === "undefined" || deploymentType !== "sbc") {
      return;
    }

    this.modal = document.getElementById("remote-management-modal");
    this.remoteList = document.getElementById("remote-list");
    this.addRemoteForm = document.getElementById("add-remote-form");
    this.closeBtn = this.modal?.querySelector(".modal-close");

    if (this.closeBtn) {
      this.closeBtn.addEventListener("click", () => this.closeModal());
    }

    if (this.addRemoteForm) {
      this.addRemoteForm.addEventListener("submit", (e) =>
        this.handleAddRemote(e),
      );
    }

    // Close modal on background click
    if (this.modal) {
      this.modal.addEventListener("click", (e) => {
        if (e.target === this.modal) {
          this.closeModal();
        }
      });
    }
  },

  openModal() {
    if (this.modal) {
      this.modal.style.display = "block";
      this.modal.setAttribute("aria-hidden", "false");
      this.loadRemotesList();
    }
  },

  closeModal() {
    if (this.modal) {
      this.modal.style.display = "none";
      this.modal.setAttribute("aria-hidden", "true");
      // Reload main remotes list
      gitConfig.loadRemotes();
    }
  },

  async loadRemotesList() {
    try {
      const response = await fetch("/api/update/git/remotes");
      const data = await response.json();

      this.remoteList.innerHTML = "";

      if (data.remotes.length === 0) {
        this.remoteList.innerHTML = `<p>${_("no-remotes-configured")}</p>`;
        return;
      }

      data.remotes.forEach((remote) => {
        const remoteItem = this.createRemoteItem(remote);
        this.remoteList.appendChild(remoteItem);
      });
    } catch (error) {
      console.error("Failed to load remotes list:", error);
      this.remoteList.innerHTML = `<p class="error">${_("failed-to-load-remotes")}</p>`;
    }
  },

  createRemoteItem(remote) {
    const item = document.createElement("div");
    item.className = "remote-item";
    item.setAttribute("role", "listitem");

    const info = document.createElement("div");
    info.className = "remote-info";

    const name = document.createElement("strong");
    name.textContent = remote.name;
    info.appendChild(name);

    const url = document.createElement("div");
    url.className = "remote-url";
    url.textContent = remote.url;
    info.appendChild(url);

    item.appendChild(info);

    const actions = document.createElement("div");
    actions.className = "remote-actions";

    const editBtn = document.createElement("button");
    editBtn.type = "button";
    editBtn.className = "btn btn-sm btn-secondary";
    editBtn.textContent = _("edit");
    editBtn.setAttribute("aria-label", `${_("edit")} ${remote.name}`);
    editBtn.addEventListener("click", () => this.editRemote(remote));
    actions.appendChild(editBtn);

    // Only allow deletion for non-origin remotes
    if (remote.name !== "origin") {
      const deleteBtn = document.createElement("button");
      deleteBtn.type = "button";
      deleteBtn.className = "btn btn-sm btn-danger";
      deleteBtn.textContent = _("delete");
      deleteBtn.setAttribute("aria-label", `${_("delete")} ${remote.name}`);
      deleteBtn.addEventListener("click", () => this.deleteRemote(remote.name));
      actions.appendChild(deleteBtn);
    }

    item.appendChild(actions);

    return item;
  },

  async handleAddRemote(event) {
    event.preventDefault();

    const formData = new FormData(this.addRemoteForm);
    const name = formData.get("name");
    const url = formData.get("url");

    try {
      const response = await fetch("/api/update/git/remotes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, url }),
      });

      const data = await response.json();

      if (data.success) {
        this.addRemoteForm.reset();
        this.loadRemotesList();
        this.showNotification(data.message, "success");
      } else {
        this.showNotification(data.error, "error");
      }
    } catch (error) {
      console.error("Failed to add remote:", error);
      this.showNotification(_("failed-to-add-remote"), "error");
    }
  },

  editRemote(remote) {
    const newUrl = prompt(
      _("enter-new-url-for-remote") + ` ${remote.name}:`,
      remote.url,
    );

    if (newUrl && newUrl !== remote.url) {
      this.updateRemote(remote.name, remote.name, newUrl);
    }
  },

  async updateRemote(oldName, newName, newUrl) {
    try {
      const response = await fetch(
        `/api/update/git/remotes/${encodeURIComponent(oldName)}`,
        {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: newName, url: newUrl }),
        },
      );

      const data = await response.json();

      if (data.success) {
        this.loadRemotesList();
        this.showNotification(data.message, "success");
      } else {
        this.showNotification(data.error, "error");
      }
    } catch (error) {
      console.error("Failed to update remote:", error);
      this.showNotification(_("failed-to-update-remote"), "error");
    }
  },

  async deleteRemote(name) {
    if (name === "origin") {
      this.showNotification(_("cannot-delete-origin"), "error");
      return;
    }

    if (!confirm(_("confirm-delete-remote") + ` ${name}?`)) {
      return;
    }

    try {
      const response = await fetch(
        `/api/update/git/remotes/${encodeURIComponent(name)}`,
        {
          method: "DELETE",
        },
      );

      const data = await response.json();

      if (data.success) {
        this.loadRemotesList();
        this.showNotification(data.message, "success");
      } else {
        this.showNotification(data.error, "error");
      }
    } catch (error) {
      console.error("Failed to delete remote:", error);
      this.showNotification(_("failed-to-delete-remote"), "error");
    }
  },

  showNotification(message, type) {
    // Create a simple notification (could be enhanced with a toast system)
    alert(message);
  },
};

// Region Pack Management
const regionPackManager = {
  downloadBtn: null,
  pollInterval: null,
  originalBtnText: null,

  init() {
    this.downloadBtn = document.getElementById("download-region-pack-btn");

    if (this.downloadBtn) {
      this.originalBtnText = this.downloadBtn.textContent;
      this.downloadBtn.addEventListener("click", () =>
        this.downloadRegionPack(),
      );
      // Check if there's already a download in progress
      this.checkExistingDownload();
    }
  },

  async checkExistingDownload() {
    try {
      const response = await fetch("/api/update/region-pack/download-status");
      const status = await response.json();
      if (status.status === "downloading") {
        this.downloadBtn.disabled = true;
        this.startPolling();
      }
    } catch {
      // Ignore errors on initial check
    }
  },

  async downloadRegionPack() {
    try {
      this.downloadBtn.disabled = true;
      this.downloadBtn.textContent = _("downloading") + "...";

      const response = await fetch("/api/update/region-pack/download", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
      });

      const data = await response.json();

      if (response.ok && data.success) {
        this.showNotification(data.message, "success");
        // Start polling for progress
        this.startPolling();
      } else {
        this.downloadBtn.textContent = this.originalBtnText;
        this.downloadBtn.disabled = false;
        this.showNotification(
          data.error || _("failed-to-download-region-pack"),
          "error",
        );
      }
    } catch (error) {
      console.error("Failed to download region pack:", error);
      this.downloadBtn.disabled = false;
      this.downloadBtn.textContent = this.originalBtnText;
      this.showNotification(
        _("failed-to-download-region-pack") + ": " + error.message,
        "error",
      );
    }
  },

  startPolling() {
    // Poll every second for progress
    this.pollInterval = setInterval(() => this.pollStatus(), 1000);
  },

  stopPolling() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
  },

  async pollStatus() {
    try {
      const response = await fetch("/api/update/region-pack/download-status");
      const status = await response.json();

      if (status.status === "downloading") {
        // Update button with progress
        const progress = status.progress || 0;
        const downloaded = status.downloaded_mb?.toFixed(1) || "0";
        const total = status.total_mb?.toFixed(1) || "?";
        this.downloadBtn.textContent = `${_("downloading")} ${progress}% (${downloaded}/${total} MB)`;
      } else if (status.status === "complete") {
        this.stopPolling();
        this.downloadBtn.textContent = _("download-complete");
        this.showNotification(_("region-pack-installed"), "success");
        // Reload page after a short delay to show updated status
        setTimeout(() => {
          window.location.reload();
        }, 1500);
      } else if (status.status === "error") {
        this.stopPolling();
        this.downloadBtn.textContent = this.originalBtnText;
        this.downloadBtn.disabled = false;
        this.showNotification(
          status.error || _("failed-to-download-region-pack"),
          "error",
        );
      } else if (status.status === "idle") {
        // Download completed and status cleared, reload
        this.stopPolling();
        window.location.reload();
      }
    } catch (error) {
      console.error("Failed to poll download status:", error);
      // Continue polling on transient errors
    }
  },

  showNotification(message, type) {
    const notification = document.createElement("div");
    notification.className = "notification notification-" + type;
    notification.textContent = message;
    notification.style.cssText =
      "position: fixed; top: 20px; right: 20px; padding: 1rem 1.5rem; " +
      "border-radius: 8px; background: " +
      (type === "success" ? "#10b981" : "#ef4444") +
      "; " +
      "color: white; z-index: 1000; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);";
    document.body.appendChild(notification);

    setTimeout(() => {
      notification.remove();
    }, 5000);
  },
};

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  updateManager.init();
  gitConfig.init();
  gitRemoteManager.init();
  regionPackManager.init();
});
