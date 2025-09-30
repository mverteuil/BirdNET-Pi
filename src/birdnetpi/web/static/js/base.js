/**
 * Base JavaScript - Common functionality for all pages
 */

// Check audio capture service status and update indicator
async function updateAudioCaptureIndicator() {
  try {
    const response = await fetch("/api/system/services/status");
    if (response.ok) {
      const data = await response.json();
      const audioService = data.services.find(
        (s) =>
          s.name === "audio_capture" || s.name === "birdnetpi-audio-capture",
      );
      const indicator = document.getElementById("audio-capture-indicator");
      if (indicator && audioService) {
        if (audioService.status === "running") {
          indicator.classList.add("pulse");
          indicator.title = "Audio Capture Active";
        } else {
          indicator.classList.remove("pulse");
          indicator.title = "Audio Capture Stopped";
        }
      }
    }
  } catch (error) {
    console.error("Failed to check audio capture status:", error);
  }
}

// Initialize on DOM content loaded
document.addEventListener("DOMContentLoaded", function () {
  // Check on load and every 10 seconds
  updateAudioCaptureIndicator();
  setInterval(updateAudioCaptureIndicator, 10000);
});
