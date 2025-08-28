/**
 * AudioWorklet Processor for BirdNET-Pi Live Audio Stream
 * Handles PCM audio buffering and conversion from WebSocket stream
 * Runs on dedicated audio thread for low-latency processing
 */

class PCMAudioProcessor extends AudioWorkletProcessor {
  constructor() {
    super();

    // Audio buffer for incoming PCM data
    this.audioBuffer = [];
    this.bufferThreshold = 512; // Balance between latency and smooth playback

    // Port for receiving data from main thread
    this.port.onmessage = this.handleMessage.bind(this);

    // Track processing state
    this.isProcessing = false;
    this.sampleRate = 48000; // Expected sample rate from stream
  }

  handleMessage(event) {
    if (event.data instanceof ArrayBuffer) {
      // Convert ArrayBuffer to Float32 samples
      const pcmData = new Int16Array(event.data);
      const floatData = new Float32Array(pcmData.length);

      // Convert 16-bit PCM to float32 (-1 to 1 range)
      for (let i = 0; i < pcmData.length; i++) {
        floatData[i] = pcmData[i] / 32768.0;
      }

      // Add to buffer
      this.audioBuffer.push(...floatData);

      // Notify main thread of buffer status
      if (
        !this.isProcessing &&
        this.audioBuffer.length > this.bufferThreshold
      ) {
        this.isProcessing = true;
        this.port.postMessage({
          type: "bufferReady",
          bufferSize: this.audioBuffer.length,
        });
      }
    } else if (event.data.type === "config") {
      // Handle configuration updates
      if (event.data.sampleRate) {
        this.sampleRate = event.data.sampleRate;
      }
      if (event.data.bufferThreshold) {
        this.bufferThreshold = event.data.bufferThreshold;
      }
    } else if (event.data.type === "clear") {
      // Clear buffer on demand
      this.audioBuffer = [];
      this.isProcessing = false;
    }
  }

  process(inputs, outputs, parameters) {
    const output = outputs[0];

    // Only process if we have output channels
    if (!output || output.length === 0) {
      return true;
    }

    const channelLength = output[0].length;

    // Fill output buffer from our audio buffer
    if (this.audioBuffer.length >= channelLength) {
      // Extract samples for this frame
      const frameSamples = this.audioBuffer.splice(0, channelLength);

      // Copy to all output channels (mono to stereo/multichannel)
      for (let channelIndex = 0; channelIndex < output.length; channelIndex++) {
        const channel = output[channelIndex];
        for (let i = 0; i < channelLength; i++) {
          channel[i] = frameSamples[i] || 0;
        }
      }

      // Update processing state
      if (this.audioBuffer.length < this.bufferThreshold / 4) {
        this.isProcessing = false;
      }

      // Report metrics periodically (using a simple counter)
      // Note: We could use currentFrame from parameters if needed
      // For now, we'll report based on buffer state changes
    } else {
      // Not enough data, output silence to all channels
      for (let channelIndex = 0; channelIndex < output.length; channelIndex++) {
        const channel = output[channelIndex];
        for (let i = 0; i < channelLength; i++) {
          channel[i] = 0;
        }
      }

      // Report underrun if we were processing
      if (this.isProcessing) {
        this.isProcessing = false;

        // Adaptive buffering: increase threshold on underrun
        if (this.bufferThreshold < 2048) {
          this.bufferThreshold = Math.min(this.bufferThreshold * 1.5, 2048);
          console.log(
            "Buffer underrun - increasing threshold to:",
            this.bufferThreshold,
          );
        }

        this.port.postMessage({
          type: "underrun",
          bufferSize: this.audioBuffer.length,
          newThreshold: this.bufferThreshold,
        });
      }
    }

    // Keep processor alive
    return true;
  }
}

// Register the processor
registerProcessor("pcm-audio-processor", PCMAudioProcessor);
