/**
 * Livestream JavaScript - Real-time audio streaming and detection monitoring
 */

// Helper function to get CSS variables
function getCSSVariable(varName) {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(varName)
    .trim();
}

// WebSocket connection (ONLY ONE!)
let audioWs = null;
let audioContext = null;
let analyser = null;
let gainNode = null;
let oscillator = null;
let audioWorkletNode = null;
let useAudioWorklet = false; // Flag for AudioWorklet support
window.audioWorkletNode = null; // Expose globally for debugging
window.useAudioWorklet = false; // Expose globally for debugging

// Canvas contexts
const spectrogramCanvas = document.getElementById("spectrogramCanvas");
const spectrogramCtx = spectrogramCanvas.getContext("2d", { alpha: false });
const waveformCanvas = document.getElementById("waveformCanvas");
const waveformCtx = waveformCanvas.getContext("2d", { alpha: false });

// Create offscreen canvas for double buffering
let offscreenCanvas = null;
let offscreenCtx = null;

// Data storage
let spectrogramHistory = [];
let detections = [];
let lastFrameTime = Date.now();
let frameCount = 0;
let performanceStart = 0;
let animationFrameId = null;
let pendingFFTData = null;
let lastFFTTime = 0;
const MIN_FFT_INTERVAL = 20; // 50 Hz update rate for smooth visualization

// Settings
let maxFrequency = 12000; // Extended range for bird vocalizations
let timeWindow = 10; // 10 seconds visible
let gain = 25; // Lower gain reduces visual noise
let volume = 60;
let fftSize = 2048; // Higher resolution for smoother gradients

// Audio buffer for continuous playback
let audioQueue = [];
let isPlaying = false;
let nextStartTime = 0;

// Debug counters
let totalBytesReceived = 0;
let framesProcessed = 0;
let audioBuffersPlayed = 0;

// Real-time detection updates via SSE
let detectionEventSource = null;
const MAX_DETECTIONS = 50; // Keep last 50 detections in the list

// Resize canvases
function resizeCanvases() {
  spectrogramCanvas.width = spectrogramCanvas.offsetWidth;
  spectrogramCanvas.height = 300;
  waveformCanvas.width = waveformCanvas.offsetWidth;
  waveformCanvas.height = 60;
}

// Toggle audio connection
function toggleAudio() {
  const button = document.getElementById("audioToggle");
  if (audioWs && audioWs.readyState === WebSocket.OPEN) {
    audioWs.close();
    button.textContent = "Connect Audio";
    button.classList.remove("active");

    // Clean up AudioWorklet if used
    if (useAudioWorklet && audioWorkletNode) {
      audioWorkletNode.port.postMessage({ type: "clear" });
      audioWorkletNode.disconnect();
      audioWorkletNode = null;
    }

    // Reset audio context to allow reconnection
    if (audioContext) {
      audioContext.close();
      audioContext = null;
      analyser = null;
      gainNode = null;
      useAudioWorklet = false;
      window.useAudioWorklet = false;
      window.audioWorkletNode = null;
    }

    // Reset timing
    nextStartTime = 0;

    if (animationFrameId) {
      cancelAnimationFrame(animationFrameId);
      animationFrameId = null;
    }
  } else {
    connectAudio();
    button.textContent = "Disconnect Audio";
    button.classList.add("active");
  }
}

// Connect audio WebSocket
function connectAudio() {
  const wsProtocol = location.protocol === "https:" ? "wss:" : "ws:";
  audioWs = new WebSocket(`${wsProtocol}//${location.host}/ws/audio`);
  audioWs.binaryType = "arraybuffer"; // Ensure binary data is received as ArrayBuffer

  audioWs.onopen = () => {
    updateStatus("audioStatus", "Connected", true);
    addMessage("✅ Audio connected");
    window.audioWs = audioWs; // Make available for debugging
    initAudioContext();
  };

  audioWs.onmessage = (event) => {
    if (event.data instanceof ArrayBuffer) {
      handleAudioData(event.data);
    }
  };

  audioWs.onclose = () => {
    updateStatus("audioStatus", "Disconnected", false);
    addMessage("Audio disconnected");

    // Clean up oscillator (for fallback mode)
    if (oscillator) {
      oscillator.stop();
      oscillator.disconnect();
      oscillator = null;
    }

    // Clean up AudioWorklet
    if (audioWorkletNode) {
      audioWorkletNode.disconnect();
      audioWorkletNode = null;
    }

    // Close audio context to free resources
    if (audioContext && audioContext.state !== "closed") {
      audioContext.close();
      audioContext = null;
      analyser = null;
      gainNode = null;
    }

    // Reset state
    useAudioWorklet = false;
    window.useAudioWorklet = false;
    window.audioWorkletNode = null;
    nextStartTime = 0;

    if (animationFrameId) {
      cancelAnimationFrame(animationFrameId);
      animationFrameId = null;
    }
  };

  audioWs.onerror = (error) => {
    addMessage("WebSocket error: " + error);
  };
}

// Initialize audio context with Web Audio API FFT
async function initAudioContext() {
  if (!audioContext) {
    audioContext = new (window.AudioContext || window.webkitAudioContext)({
      sampleRate: 48000,
    });

    // Create analyser node for FFT
    analyser = audioContext.createAnalyser();
    analyser.fftSize = fftSize;
    analyser.smoothingTimeConstant = 0;

    // Create gain node for volume control
    gainNode = audioContext.createGain();
    gainNode.gain.value = volume / 100;

    // Try to use AudioWorklet if available
    if (typeof AudioWorkletNode !== "undefined" && audioContext.audioWorklet) {
      try {
        // Note: The URL will be provided by the template
        const moduleUrl =
          window.audioProcessorUrl || "/static/js/audio-processor.js";

        // Load the AudioWorklet processor directly
        await audioContext.audioWorklet.addModule(moduleUrl);

        // Create AudioWorklet node with explicit output configuration
        audioWorkletNode = new AudioWorkletNode(
          audioContext,
          "pcm-audio-processor",
          {
            numberOfInputs: 0, // We're not using inputs
            numberOfOutputs: 1, // We need one output
            outputChannelCount: [2], // Stereo output
          },
        );

        // Connect audio graph: worklet -> analyser -> gain -> destination
        // This matches the BufferSource path that was working
        audioWorkletNode.connect(analyser);
        analyser.connect(gainNode);
        gainNode.connect(audioContext.destination);

        // Set up message handling
        audioWorkletNode.port.onmessage = (event) => {
          if (event.data.type === "underrun") {
            console.warn("Audio buffer underrun");
          } else if (event.data.type === "metrics") {
            console.log("AudioWorklet metrics:", event.data);
          }
          // Removed bufferReady logging - too noisy
        };

        // Configure the worklet with balanced threshold
        audioWorkletNode.port.postMessage({
          type: "config",
          sampleRate: 48000,
          bufferThreshold: 512, // Balance between latency and smooth playback
        });

        useAudioWorklet = true;
        window.useAudioWorklet = true; // Expose globally
        window.audioWorkletNode = audioWorkletNode; // Expose globally
        addMessage("✅ AudioWorklet initialized - low-latency mode active");
      } catch (error) {
        console.error("❌ AudioWorklet initialization failed:", error);
        console.error("Error details:", {
          name: error.name,
          message: error.message,
          stack: error.stack,
        });
        useAudioWorklet = false;
        addMessage(`⚠️ AudioWorklet failed: ${error.message} - using fallback`);
      }
    }

    // Fallback: Create a silent oscillator for the analyser if not using AudioWorklet
    if (!useAudioWorklet) {
      gainNode.connect(audioContext.destination);

      // Create a constant tone source for the analyser (silent)
      oscillator = audioContext.createOscillator();
      oscillator.frequency.value = 0; // Silent
      oscillator.connect(analyser);
      oscillator.start();

      console.log("Using BufferSource fallback for audio processing");
    }

    // Use requestAnimationFrame for smoother rendering
    startVisualization();
  }

  if (audioContext.state === "suspended") {
    await audioContext.resume();
  }
}

// Handle audio data from WebSocket
function handleAudioData(arrayBuffer) {
  totalBytesReceived += arrayBuffer.byteLength;
  window.totalBytesReceived = totalBytesReceived; // For debugging

  if (!audioContext || !analyser) return;

  try {
    const dataView = new DataView(arrayBuffer);
    const dataLength = dataView.getUint32(0, true);
    const pcmData = new Int16Array(arrayBuffer, 4, dataLength / 2);

    framesProcessed++;
    window.framesProcessed = framesProcessed; // For debugging

    if (useAudioWorklet && audioWorkletNode) {
      // Send PCM data directly to AudioWorklet as ArrayBuffer
      // The worklet will handle conversion and buffering
      const audioData = arrayBuffer.slice(4);
      audioWorkletNode.port.postMessage(audioData);
    } else {
      // Fallback: Use BufferSource approach
      // Convert to float32 for Web Audio API
      const audioBuffer = audioContext.createBuffer(1, pcmData.length, 48000);
      const channelData = audioBuffer.getChannelData(0);
      for (let i = 0; i < pcmData.length; i++) {
        channelData[i] = pcmData[i] / 32768.0;
      }

      // Schedule audio playback with proper timing
      scheduleAudioBuffer(audioBuffer);
    }

    // Update buffer size
    document.getElementById("bufferSize").textContent =
      (arrayBuffer.byteLength / 1024).toFixed(1) + " KB";
  } catch (e) {
    console.error("Audio processing error:", e);
    addMessage("Audio processing error: " + e.message);
  }
}

// Schedule audio buffer for continuous playback
function scheduleAudioBuffer(audioBuffer) {
  const source = audioContext.createBufferSource();
  source.buffer = audioBuffer;

  // Connect through analyser for FFT, then to gain for output
  source.connect(analyser);
  analyser.connect(gainNode);

  // Calculate when to start this buffer
  const now = audioContext.currentTime;
  const bufferDuration = audioBuffer.duration;

  if (nextStartTime < now) {
    // If we're behind, start immediately
    nextStartTime = now;
  }

  // Schedule this buffer
  source.start(nextStartTime);

  // Update next start time for seamless playback
  nextStartTime += bufferDuration;

  audioBuffersPlayed++;

  // Clean up old start times to prevent drift
  if (nextStartTime < now - 5) {
    nextStartTime = now;
  }
}

// Start visualization loop using requestAnimationFrame
function startVisualization() {
  function visualize() {
    animationFrameId = requestAnimationFrame(visualize);

    const now = performance.now();

    // Update FFT more frequently - every animation frame
    if (analyser) {
      performanceStart = now;

      // Get frequency data from analyser
      const freqData = new Uint8Array(analyser.frequencyBinCount);
      analyser.getByteFrequencyData(freqData);

      // Check if we have actual data (not silence)
      const hasData = freqData.some((val) => val > 0);

      if (hasData) {
        // Get time domain data for waveform
        const timeData = new Uint8Array(analyser.frequencyBinCount * 2);
        analyser.getByteTimeDomainData(timeData);

        // Store FFT data for processing
        pendingFFTData = {
          freqData: freqData,
          timeData: timeData,
          timestamp: Date.now(),
        };

        // Process immediately
        processFFTData();
      }

      // Track performance
      const elapsed = now - performanceStart;
      document.getElementById("performanceStatus").textContent =
        elapsed.toFixed(1) + " ms/frame";
      const frameRate = 1000 / Math.max(1, now - lastFFTTime);
      document.getElementById("frameRate").textContent =
        frameRate.toFixed(1) + " fps";
      lastFFTTime = now;
    }
  }
  visualize();
}

// Process FFT data without blocking
function processFFTData() {
  if (!pendingFFTData) return;

  const { freqData, timeData, timestamp } = pendingFFTData;
  pendingFFTData = null;

  // Interpolate to fill gaps if needed
  if (spectrogramHistory.length > 0) {
    const lastFrame = spectrogramHistory[spectrogramHistory.length - 1];
    const timeDiff = timestamp - lastFrame.timestamp;

    // If there's a gap, interpolate frames
    if (timeDiff > 100) {
      // More than 100ms gap
      const interpolatedFrames = Math.min(3, Math.floor(timeDiff / 50));
      for (let i = 1; i <= interpolatedFrames; i++) {
        const alpha = i / (interpolatedFrames + 1);
        const interpolatedData = lastFrame.data.map((val, idx) =>
          Math.round(val * (1 - alpha) + freqData[idx] * alpha),
        );
        spectrogramHistory.push({
          data: interpolatedData,
          timestamp: lastFrame.timestamp + timeDiff * alpha,
          interpolated: true,
        });
      }
    }
  }

  // Store actual FFT frame
  spectrogramHistory.push({
    data: Array.from(freqData),
    timestamp: timestamp,
    interpolated: false,
  });

  // Limit history based on time window for high resolution
  const maxSlices = Math.ceil(timeWindow * 50); // 50 Hz for smooth continuous display
  if (spectrogramHistory.length > maxSlices) {
    spectrogramHistory = spectrogramHistory.slice(-maxSlices);
  }

  // Update waveform
  updateWaveformFromTimeData(timeData);

  // Draw updates
  drawSpectrogram();
  updateMetrics();
}

// Draw spectrogram from client-side FFT data with rolling buffer
function drawSpectrogram() {
  const width = spectrogramCanvas.width;
  const height = spectrogramCanvas.height;

  // Initialize offscreen canvas if needed
  if (
    !offscreenCanvas ||
    offscreenCanvas.width !== width ||
    offscreenCanvas.height !== height
  ) {
    offscreenCanvas = document.createElement("canvas");
    offscreenCanvas.width = width;
    offscreenCanvas.height = height;
    offscreenCtx = offscreenCanvas.getContext("2d", { alpha: false });
    // Initial clear with background
    offscreenCtx.fillStyle = "#fffef0"; // Light warm yellow
    offscreenCtx.fillRect(0, 0, width, height);
  }

  if (spectrogramHistory.length === 0) {
    return;
  }

  // Rolling buffer approach - shift existing content left and draw only new data
  const pixelsPerFrame = 2; // How many pixels to shift per update

  // Get the last (newest) FFT frame
  const lastItem = spectrogramHistory[spectrogramHistory.length - 1];
  if (!lastItem || !lastItem.data) return;

  // Shift existing content to the left
  offscreenCtx.drawImage(
    offscreenCanvas,
    pixelsPerFrame,
    0,
    width - pixelsPerFrame,
    height,
    0,
    0,
    width - pixelsPerFrame,
    height,
  );

  // Clear the rightmost strip
  offscreenCtx.fillStyle = "#fffef0";
  offscreenCtx.fillRect(width - pixelsPerFrame, 0, pixelsPerFrame, height);

  // Draw new FFT data in the rightmost strip
  const nyquist = audioContext.sampleRate / 2;
  const maxFreqBin = Math.floor(
    (maxFrequency / nyquist) * analyser.frequencyBinCount,
  );
  const freqData = lastItem.data;

  for (let freqIndex = 0; freqIndex < maxFreqBin; freqIndex++) {
    const magnitude = freqData[freqIndex];
    const normalized = (magnitude / 255) * (gain / 50);
    const intensity = Math.max(0, Math.min(1, normalized));

    if (intensity > 0.001) {
      // Lower threshold for more detail
      // Create vibrant gradient from yellow to orange to red to dark red
      let r, g, b;
      if (intensity < 0.33) {
        // Yellow to orange (low intensity)
        const t = intensity * 3;
        r = 255;
        g = 255 - 100 * t; // 255 -> 155
        b = 100 * (1 - t); // 100 -> 0
      } else if (intensity < 0.66) {
        // Orange to red (medium intensity)
        const t = (intensity - 0.33) * 3;
        r = 255;
        g = 155 - 155 * t; // 155 -> 0
        b = 0;
      } else {
        // Red to dark red (high intensity)
        const t = (intensity - 0.66) * 3;
        r = 255 - 100 * t; // 255 -> 155
        g = 0;
        b = 0;
      }

      // Use full opacity for vibrant colors
      const alpha = lastItem.interpolated ? 0.95 : 1.0;
      offscreenCtx.fillStyle = `rgba(${Math.floor(r)},${Math.floor(g)},${Math.floor(b)},${alpha})`;

      const y = height - (freqIndex / maxFreqBin) * height;
      const h = Math.ceil(height / maxFreqBin) + 1;

      offscreenCtx.fillRect(
        width - pixelsPerFrame,
        y - h,
        pixelsPerFrame + 1,
        h,
      );
    }
  }

  // Copy offscreen buffer to main canvas
  spectrogramCtx.drawImage(offscreenCanvas, 0, 0);

  frameCount++;
}

// Update waveform from time domain data
function updateWaveformFromTimeData(timeData) {
  const width = waveformCanvas.width;
  const height = waveformCanvas.height;

  // Clear
  waveformCtx.fillStyle = getCSSVariable("--color-bg-hover") || "#ffffff";
  waveformCtx.fillRect(0, 0, width, height);

  // Draw zero line
  waveformCtx.strokeStyle = getCSSVariable("--color-input-border") || "#ccc";
  waveformCtx.lineWidth = 1;
  waveformCtx.beginPath();
  waveformCtx.moveTo(0, height / 2);
  waveformCtx.lineTo(width, height / 2);
  waveformCtx.stroke();

  // Draw waveform
  waveformCtx.strokeStyle = getCSSVariable("--color-text-emphasis") || "#111";
  waveformCtx.lineWidth = 1;
  waveformCtx.beginPath();

  const step = Math.ceil(timeData.length / width);
  let peak = 0;
  let rms = 0;

  for (let i = 0; i < width; i++) {
    const index = Math.floor((i * timeData.length) / width);
    const value = (timeData[index] - 128) / 128; // Convert from 0-255 to -1 to 1
    const y = ((1 - value) * height) / 2;

    if (i === 0) {
      waveformCtx.moveTo(i, y);
    } else {
      waveformCtx.lineTo(i, y);
    }

    peak = Math.max(peak, Math.abs(value));
    rms += value * value;
  }

  waveformCtx.stroke();

  // Update levels
  rms = Math.sqrt(rms / width);
  document.getElementById("peakLevel").textContent =
    peak > 0 ? (20 * Math.log10(peak)).toFixed(1) + " dB" : "-∞ dB";
  document.getElementById("rmsLevel").textContent =
    rms > 0 ? (20 * Math.log10(rms)).toFixed(1) + " dB" : "-∞ dB";
  document.getElementById("sampleCount").textContent =
    timeData.length.toLocaleString();
}

// Update metrics
function updateMetrics() {
  const now = Date.now();
  const elapsed = (now - lastFrameTime) / 1000;

  if (elapsed > 1) {
    const fps = frameCount / elapsed;
    document.getElementById("frameRate").textContent = fps.toFixed(1) + " fps";
    document.getElementById("updateRate").textContent = fps.toFixed(1) + " Hz";

    frameCount = 0;
    lastFrameTime = now;
  }
}

// Update status
function updateStatus(elementId, text, active) {
  const element = document.getElementById(elementId);
  element.textContent = text;
  element.className = active
    ? "status-value status-active"
    : "status-value status-inactive";
}

// Add message to log
function addMessage(text) {
  const log = document.getElementById("messageLog");
  const message = document.createElement("div");
  message.className = "message";
  message.textContent = new Date().toTimeString().slice(0, 8) + " " + text;
  log.appendChild(message);

  // Limit to 20 messages
  while (log.children.length > 20) {
    log.removeChild(log.firstChild);
  }

  log.scrollTop = log.scrollHeight;
}

// Settings functions
function setVolume(value) {
  volume = value;
  document.getElementById("volumeValue").textContent = value + "%";
  if (gainNode) {
    gainNode.gain.value = value / 100;
  }
}

function updateFFTSize(value) {
  fftSize = parseInt(value);
  document.getElementById("fftSizeDisplay").textContent = value;

  if (analyser) {
    analyser.fftSize = fftSize;
    const resolution = audioContext.sampleRate / fftSize;
    document.getElementById("freqResolution").textContent =
      resolution.toFixed(1) + " Hz";
  }

  // Clear history for clean redraw
  spectrogramHistory = [];
}

function updateFrequencyRange() {
  maxFrequency = parseInt(document.getElementById("maxFreq").value);
  // Update frequency labels dynamically (reversed order: high to low)
  const labels = document.querySelectorAll(".freq-axis-container span");
  const step = maxFrequency / (labels.length - 1);
  labels.forEach((label, i) => {
    if (label.id !== "maxFreqLabel") {
      // Reverse the frequency calculation since labels go from top to bottom
      const freq = maxFrequency - i * step;
      label.textContent =
        freq >= 1000 ? (freq / 1000).toFixed(1) + "k" : freq.toFixed(0);
    }
  });
  document.getElementById("maxFreqLabel").textContent =
    maxFrequency >= 1000
      ? (maxFrequency / 1000).toFixed(1) + "k"
      : maxFrequency;
}

function updateTimeWindow() {
  timeWindow = parseInt(document.getElementById("timeWindow").value);
  document.getElementById("timeStart").textContent = "-" + timeWindow + "s";
}

function updateGain(value) {
  gain = value;
}

// Real-time detection updates functions

function addDetection(detection) {
  const detectionList = document.getElementById("detectionList");

  // Remove "No detections yet" message if present
  const noDataMsg = detectionList.querySelector(".no-data");
  if (noDataMsg) {
    noDataMsg.remove();
  }

  // Create detection entry
  const entry = document.createElement("div");
  entry.className = "log-entry";
  entry.style.animation = "fadeIn 0.5s ease-out";

  const time = new Date(detection.timestamp).toTimeString().slice(0, 5);
  const confidence = (detection.confidence * 100).toFixed(1);

  entry.innerHTML = `
        <span class="time">${time}</span>
        <span>${detection.common_name}</span>
        <span class="confidence">${confidence}%</span>
    `;

  // Insert at the beginning (most recent first)
  detectionList.insertBefore(entry, detectionList.firstChild);

  // Keep only the last MAX_DETECTIONS entries
  while (detectionList.children.length > MAX_DETECTIONS) {
    detectionList.removeChild(detectionList.lastChild);
  }

  // Add to detections array for reference
  detections.unshift({
    time: time,
    species: detection.common_name,
    confidence: confidence,
    timestamp: detection.timestamp,
  });

  // Log the detection
  addMessage(`Detection: ${detection.common_name} (${confidence}%)`);

  // Flash the detection indicator
  const liveIndicator = document.querySelector(".live");
  if (liveIndicator) {
    liveIndicator.style.background = getCSSVariable("--color-status-success");
    setTimeout(() => {
      liveIndicator.style.background = getCSSVariable("--color-status-live");
    }, 1000);
  }
}

function connectDetectionStream() {
  if (detectionEventSource) {
    detectionEventSource.close();
  }

  detectionEventSource = new EventSource("/api/detections/stream");

  detectionEventSource.addEventListener("connected", (event) => {
    console.log("Connected to detection stream");
    addMessage("Detection stream connected");
  });

  detectionEventSource.addEventListener("detection", (event) => {
    try {
      const detection = JSON.parse(event.data);
      console.log("New detection:", detection);
      addDetection(detection);
    } catch (error) {
      console.error("Failed to process detection event:", error);
    }
  });

  detectionEventSource.addEventListener("heartbeat", (event) => {
    // Heartbeat received - connection is alive
  });

  detectionEventSource.addEventListener("error", (event) => {
    console.error("Detection stream error:", event);
    addMessage("Detection stream error - reconnecting...");
    if (detectionEventSource.readyState === EventSource.CLOSED) {
      // Reconnect after 5 seconds
      setTimeout(connectDetectionStream, 5000);
    }
  });

  detectionEventSource.onerror = (error) => {
    console.error("EventSource error:", error);
    if (detectionEventSource.readyState === EventSource.CLOSED) {
      setTimeout(connectDetectionStream, 5000);
    }
  };
}

// Initialize livestream page
function initializeLivestream() {
  // Add fadeIn animation style
  const style = document.createElement("style");
  style.textContent = `
        @keyframes fadeIn {
            from {
                opacity: 0;
                transform: translateY(-10px);
                background-color: rgba(var(--color-accent-rgb), 0.1);
            }
            to {
                opacity: 1;
                transform: translateY(0);
                background-color: transparent;
            }
        }
        .log-entry {
            transition: background-color 0.5s ease;
        }
    `;
  document.head.appendChild(style);

  // Initialize components
  resizeCanvases();
  addMessage("System ready - Client-side FFT mode");

  // Update initial FFT resolution display
  const resolution = 48000 / fftSize;
  document.getElementById("freqResolution").textContent =
    resolution.toFixed(1) + " Hz";

  // Connect to detection stream
  connectDetectionStream();
}

// Initialize
window.addEventListener("load", initializeLivestream);

window.addEventListener("resize", resizeCanvases);

// Keep connection alive
setInterval(() => {
  if (audioWs && audioWs.readyState === WebSocket.OPEN) {
    audioWs.send("ping");
  }
}, 30000);
