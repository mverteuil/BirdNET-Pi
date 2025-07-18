import shutil
import subprocess
from pathlib import Path

# Define paths relative to the BirdNET-Pi directory
BIRDNET_PI_ROOT = Path(__file__).parent.parent
CONFIG_TEMPLATE_PATH = BIRDNET_PI_ROOT / "config_templates" / "birdnet.conf.template"
TEST_AUDIO_DIR = BIRDNET_PI_ROOT / "tests" / "temp_audio_formats_test"
TEST_WAV_INPUT = TEST_AUDIO_DIR / "test_input.wav"


def get_audio_formats_from_template(template_path: Path) -> list[str]:
    """Extract available audio formats from the birdnet.conf.template file."""
    formats = []
    try:
        with open(template_path) as f:
            for line in f:
                if "Available formats are:" in line:
                    # Extract the part after "Available formats are: "
                    parts = line.split("Available formats are:")
                    if len(parts) > 1:
                        formats_str = parts[1].strip()
                        # Split by space and filter out empty strings
                        formats = [f.strip() for f in formats_str.split() if f.strip()]
                        break  # Found the line, no need to continue
    except FileNotFoundError:
        print(f"Error: Template file not found at {template_path}")
    return formats


def create_test_wav_file(output_path: Path):
    """Create a short, silent WAV file for testing conversions."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        # Generate a 0.1 second silent WAV file
        subprocess.run(
            [
                "sox",
                "-n",
                str(output_path),
                "rate",
                "44100",
                "channels",
                "1",
                "trim",
                "0.0",
                "0.1",
            ],
            check=True,
            capture_output=True,
        )
        print(f"Created test WAV file: {output_path}")
    except subprocess.CalledProcessError as e:
        print(f"Error creating test WAV file: {e.stderr.decode()}")
        raise
    except FileNotFoundError:
        print(
            "Error: sox command not found. Please ensure it's installed and in your PATH."
        )
        raise


def test_audio_format_conversion(input_file: Path, output_format: str):
    """Test converting the input WAV file to the specified format."""
    output_file = input_file.with_suffix(f".{output_format}")
    try:
        subprocess.run(
            ["sox", str(input_file), str(output_file)], check=True, capture_output=True
        )
        if output_file.exists() and output_file.stat().st_size > 0:
            print(f"Successfully converted to {output_format}: {output_file}")
            return True
        else:
            print(
                f"Failed to convert to {output_format}: Output file is empty or missing."
            )
            return False
    except subprocess.CalledProcessError as e:
        print(f"Error converting to {output_format}: {e.stderr.decode()}")
        return False
    except FileNotFoundError:
        print(
            "Error: sox command not found. Please ensure it's installed and in your PATH."
        )
        return False
    finally:
        if output_file.exists():
            output_file.unlink()  # Clean up generated file


def run_audio_format_tests():
    """Run all audio format conversion tests."""
    print("Starting audio format conversion tests...")

    # Clean up previous test directory if it exists
    if TEST_AUDIO_DIR.exists():
        shutil.rmtree(TEST_AUDIO_DIR)
    TEST_AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    try:
        create_test_wav_file(TEST_WAV_INPUT)
        formats = get_audio_formats_from_template(CONFIG_TEMPLATE_PATH)

        if not formats:
            print("No audio formats found in the template. Skipping tests.")
            return

        all_passed = True
        for fmt in formats:
            if not test_audio_format_conversion(TEST_WAV_INPUT, fmt):
                all_passed = False

        if all_passed:
            print("All specified audio format conversions passed.")
        else:
            print("Some audio format conversions failed.")

    finally:
        if TEST_AUDIO_DIR.exists():
            shutil.rmtree(TEST_AUDIO_DIR)
        print("Audio format conversion tests finished. Cleaned up temporary files.")


if __name__ == "__main__":
    run_audio_format_tests()
