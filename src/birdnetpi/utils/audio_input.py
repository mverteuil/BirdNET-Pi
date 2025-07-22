from types import TracebackType

import numpy as np
import sounddevice as sd


class AudioInput:
    """A wrapper class to abstract audio capture functions using sounddevice."""

    def __init__(self, samplerate: int, channels: int, blocksize: int):
        self.samplerate = samplerate
        self.channels = channels
        self.blocksize = blocksize
        self.stream = None

    def start_stream(self) -> None:
        """Start the audio input stream."""
        if self.stream is None:
            self.stream = sd.InputStream(
                samplerate=self.samplerate,
                channels=self.channels,
                blocksize=self.blocksize,
            )
            self.stream.start()
            print("Audio input stream started.")

    def read_block(self) -> np.ndarray:
        """Read a block of audio data from the stream."""
        if self.stream is None:
            raise RuntimeError("Audio stream not started. Call start_stream() first.")
        data, overflowed = self.stream.read(self.blocksize)
        if overflowed:
            print("AudioInput: Audio buffer overflowed!")
        return data

    def stop_stream(self) -> None:
        """Stop the audio input stream."""
        if self.stream is not None:
            self.stream.stop()
            self.stream.close()
            self.stream = None
            print("Audio input stream stopped.")

    def __enter__(self):
        self.start_stream()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ):
        self.stop_stream()
