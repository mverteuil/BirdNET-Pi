import os
import subprocess

from birdnetpi.models.birdnet_config import BirdNETConfig
from birdnetpi.models.livestream_config import LivestreamConfig
from birdnetpi.services.file_manager import FileManager


class AudioManager:
    """Manages audio recording and livestreaming functionalities."""

    def __init__(self, file_manager: FileManager, config: BirdNETConfig) -> None:
        self.file_manager = file_manager
        self.config = config

    def record(self) -> None:
        """Record audio using default settings from configuration."""
        output_path = self.file_manager.get_full_path(self.config.audio.recordings_dir)
        duration = self.config.audio.default_recording_duration
        self.custom_record(duration, os.path.join(output_path, "default_recording.wav"))

    def custom_record(self, duration: int, output_path: str) -> None:
        """Record audio for a specified duration and save it to the output path."""
        print(f"Recording audio for {duration} seconds to {output_path}")

        # Ensure the output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

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
            print("Error: arecord command not found. Please ensure ALSA utilities are installed.")
            raise
        except subprocess.CalledProcessError as e:
            print(f"Error recording audio: {e.stderr.decode()}")
            raise

    def livestream(self, config: LivestreamConfig) -> None:
        """Start an audio livestream from the input device to the output URL."""
        print(f"Starting livestream from {config.input_device} to {config.output_url}")
        output_format = "rtsp" if config.output_url.startswith("rtsp://") else "mp3"
        try:
            command = [
                "ffmpeg",
                "-f",
                "alsa",  # Input format for ALSA devices
                "-i",
                config.input_device,  # Input device
                "-f",
                output_format,  # Output format
            ]
            if output_format == "mp3":
                command.extend(
                    [
                        "-acodec",
                        "libmp3lame",  # MP3 audio codec
                        "-ab",
                        "128k",  # Audio bitrate
                    ]
                )
            command.append(config.output_url)

            subprocess.run(
                command,
                check=True,  # Raise CalledProcessError if the command returns a non-zero exit code
                capture_output=True,  # Capture stdout and stderr
                text=True,  # Add this to ensure stderr is decoded as text
            )
            print(f"Successfully started livestream to {config.output_url}")
        except FileNotFoundError:
            print("Error: ffmpeg command not found. Please ensure ffmpeg is installed.")
            raise
        except subprocess.CalledProcessError as e:
            print(f"Error livestreaming audio: {e.stderr.decode()}")
            raise
