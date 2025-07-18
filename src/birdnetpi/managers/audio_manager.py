import os
import subprocess

from birdnetpi.models.livestream_config import LivestreamConfig
from birdnetpi.services.file_manager import FileManager


class AudioManager:
    """Manages audio recording and livestreaming functionalities."""

    def __init__(self, file_manager: FileManager) -> None:
        self.file_manager = file_manager

    def custom_record(self, duration: int, output_path: str) -> None:
        """Record audio for a specified duration and save it to the output path."""
        print(f"Recording audio for {duration} seconds to {output_path}")

        # Ensure the output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        try:
            # Using arecord for simplicity, common on Raspberry Pi
            # -d duration: recording duration in seconds
            # -f S16_LE: signed 16-bit little-endian format
            # -r 44100: sample rate of 44100 Hz
            # -c 1: mono channel
            subprocess.run(
                [
                    "arecord",
                    "-d",
                    str(duration),
                    "-f",
                    "S16_LE",
                    "-r",
                    "44100",
                    "-c",
                    "1",
                    output_path,
                ],
                check=True,  # Raise CalledProcessError if the command returns a non-zero exit code
                capture_output=True,  # Capture stdout and stderr
            )
            print(f"Successfully recorded audio to {output_path}")
        except FileNotFoundError:
            print(
                "Error: arecord command not found. Please ensure ALSA utilities are installed."
            )
            raise
        except subprocess.CalledProcessError as e:
            print(f"Error recording audio: {e.stderr.decode()}")
            raise

    def livestream(self, config: LivestreamConfig) -> None:
        """Start an audio livestream from the input device to the output URL."""
        print(f"Starting livestream from {config.input_device} to {config.output_url}")
        # This will involve using a library or subprocess to stream audio
        # For now, it's a placeholder.
        pass
