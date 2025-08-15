"""CLI wrapper for PulseAudio setup utility.

This script provides command-line access to configure PulseAudio
for streaming from macOS host to container services.
"""

import argparse
import json
import sys

from birdnetpi.utils.pulseaudio_setup import PulseAudioSetup


def setup_command(args: argparse.Namespace) -> None:
    """Set up PulseAudio for container streaming."""
    print("Setting up PulseAudio for container streaming...")
    if args.container_ip:
        print(f"Container IP: {args.container_ip}")
    else:
        detected_ip = PulseAudioSetup.get_container_ip(args.container_name)
        print(f"Auto-detected container IP: {detected_ip}")
    print(f"Port: {args.port}")
    print()

    success, message = PulseAudioSetup.setup_streaming(
        container_ip=args.container_ip,
        port=args.port,
        backup_existing=not args.no_backup,
        container_name=args.container_name,
    )

    if success:
        print("✓ " + message)
        print()
        print("Next steps:")
        print("1. Start your BirdNET-Pi container with PulseAudio enabled")
        print("2. Run 'pulseaudio-setup test' to verify connection")
        print("3. Use 'pulseaudio-setup devices' to see available audio sources")
    else:
        print("✗ Setup failed: " + message)
        sys.exit(1)


def command_test(args: argparse.Namespace) -> None:
    """Test connection to container PulseAudio service."""
    if args.container_ip:
        print(f"Testing connection to {args.container_ip}:{args.port}...")
    else:
        detected_ip = PulseAudioSetup.get_container_ip(args.container_name)
        print(f"Testing connection to auto-detected IP {detected_ip}:{args.port}...")

    success, message = PulseAudioSetup.test_connection(
        container_ip=args.container_ip,
        port=args.port,
        container_name=args.container_name,
    )

    if success:
        print("✓ " + message)
    else:
        print("✗ " + message)
        print()
        print("Troubleshooting:")
        print("- Ensure your container is running and PulseAudio is enabled")
        print("- Check that the container IP and port are correct")
        print("- Verify network connectivity between host and container")
        sys.exit(1)


def status_command(args: argparse.Namespace) -> None:
    """Show current PulseAudio setup status."""
    status = PulseAudioSetup.get_status()

    print("PulseAudio Setup Status:")
    print("=" * 50)
    print(f"Platform: {'macOS' if status['macos'] else 'Other'}")
    print(f"PulseAudio installed: {'✓' if status['pulseaudio_installed'] else '✗'}")
    print(f"Configuration exists: {'✓' if status['config_exists'] else '✗'}")
    print(f"Authentication cookie: {'✓' if status['cookie_exists'] else '✗'}")
    print(f"Server running: {'✓' if status['server_running'] else '✗'}")
    print(f"Config directory: {status['config_dir']}")
    print()

    if status["audio_devices"]:
        print("Available Audio Devices:")
        print("-" * 30)
        for device in status["audio_devices"]:
            print(f"  [{device['id']}] {device['description']}")
    else:
        print("No audio devices detected")

    if args.json:
        print()
        print("Raw Status (JSON):")
        print(json.dumps(status, indent=2))


def devices_command(args: argparse.Namespace) -> None:
    """List available audio input devices."""
    devices = PulseAudioSetup.get_audio_devices()

    if not devices:
        print("No audio devices found")
        print("Make sure PulseAudio is running and devices are connected")
        sys.exit(1)

    print("Available Audio Input Devices:")
    print("=" * 40)

    for device in devices:
        print(f"ID: {device['id']}")
        print(f"Name: {device['name']}")
        print(f"Description: {device['description']}")
        print("-" * 40)

    if args.json:
        print()
        print("Devices (JSON):")
        print(json.dumps(devices, indent=2))


def cleanup_command(args: argparse.Namespace) -> None:
    """Clean up PulseAudio configuration."""
    if not args.force:
        response = input(
            "This will remove PulseAudio configuration and stop the server. Continue? [y/N]: "
        )
        if response.lower() not in ["y", "yes"]:
            print("Cleanup cancelled")
            return

    print("Cleaning up PulseAudio configuration...")

    success, message = PulseAudioSetup.cleanup_config()

    if success:
        print("✓ " + message)
    else:
        print("✗ Cleanup failed: " + message)
        sys.exit(1)


def detect_ip_command(args: argparse.Namespace) -> None:
    """Detect and display container IP address."""
    print(f"Detecting IP for container '{args.container_name}'...")
    container_ip = PulseAudioSetup.get_container_ip(args.container_name)
    print(f"Detected IP: {container_ip}")

    if container_ip == "127.0.0.1":
        print("\nNote: Fallback IP used. This may indicate:")
        print("- Container is not running")
        print("- Docker is not available")
        print("- Container name is incorrect")
        print("- Container is using host networking")


def install_command(args: argparse.Namespace) -> None:
    """Install PulseAudio via Homebrew."""
    if not PulseAudioSetup.is_macos():
        print("✗ PulseAudio installation only supported on macOS")
        sys.exit(1)

    if PulseAudioSetup.is_pulseaudio_installed():
        print("✓ PulseAudio is already installed")
        return

    print("Installing PulseAudio via Homebrew...")
    print("This may take a few minutes...")

    success = PulseAudioSetup.install_pulseaudio()

    if success:
        print("✓ PulseAudio installed successfully")
        print("You can now run 'pulseaudio-setup setup' to configure streaming")
    else:
        print("✗ Failed to install PulseAudio")
        print("Please install manually: brew install pulseaudio")
        sys.exit(1)


def main() -> None:
    """Run the PulseAudio setup CLI."""
    parser = argparse.ArgumentParser(
        description="PulseAudio Setup for Container Streaming",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Install PulseAudio (macOS only)
  pulseaudio-setup install

  # Setup streaming to container (auto-detects IP)
  pulseaudio-setup setup

  # Setup streaming to specific container IP
  pulseaudio-setup setup --container-ip 192.168.1.100

  # Setup streaming to different container
  pulseaudio-setup setup --container-name my-container

  # Auto-detect container IP
  pulseaudio-setup detect-ip

  # Test connection to container
  pulseaudio-setup test

  # Check current status
  pulseaudio-setup status

  # List available audio devices
  pulseaudio-setup devices

  # Clean up configuration
  pulseaudio-setup cleanup --force
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Install command
    subparsers.add_parser("install", help="Install PulseAudio via Homebrew (macOS only)")

    # Setup command
    setup_parser = subparsers.add_parser("setup", help="Configure PulseAudio streaming")
    setup_parser.add_argument(
        "--container-ip",
        help="IP address of the container (auto-detected if not specified)",
    )
    setup_parser.add_argument(
        "--container-name",
        default="birdnet-pi",
        help="Docker container name for auto-detection (default: birdnet-pi)",
    )
    setup_parser.add_argument(
        "--port",
        type=int,
        default=4713,
        help="PulseAudio port in container (default: 4713)",
    )
    setup_parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Don't backup existing configuration",
    )

    # Test command
    test_parser = subparsers.add_parser("test", help="Test connection to container PulseAudio")
    test_parser.add_argument(
        "--container-ip",
        help="IP address of the container (auto-detected if not specified)",
    )
    test_parser.add_argument(
        "--container-name",
        default="birdnet-pi",
        help="Docker container name for auto-detection (default: birdnet-pi)",
    )
    test_parser.add_argument(
        "--port",
        type=int,
        default=4713,
        help="PulseAudio port in container (default: 4713)",
    )

    # Status command
    status_parser = subparsers.add_parser("status", help="Show current setup status")
    status_parser.add_argument(
        "--json",
        action="store_true",
        help="Output status in JSON format",
    )

    # Devices command
    devices_parser = subparsers.add_parser("devices", help="List available audio input devices")
    devices_parser.add_argument(
        "--json",
        action="store_true",
        help="Output devices in JSON format",
    )

    # Cleanup command
    cleanup_parser = subparsers.add_parser("cleanup", help="Remove PulseAudio configuration")
    cleanup_parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt",
    )

    # Detect IP command
    detect_parser = subparsers.add_parser("detect-ip", help="Show auto-detected container IP")
    detect_parser.add_argument(
        "--container-name",
        default="birdnet-pi",
        help="Docker container name to detect IP for (default: birdnet-pi)",
    )

    args = parser.parse_args()

    if args.command == "install":
        install_command(args)
    elif args.command == "setup":
        setup_command(args)
    elif args.command == "test":
        command_test(args)
    elif args.command == "status":
        status_command(args)
    elif args.command == "devices":
        devices_command(args)
    elif args.command == "cleanup":
        cleanup_command(args)
    elif args.command == "detect-ip":
        detect_ip_command(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
