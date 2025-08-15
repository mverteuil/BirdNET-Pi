"""CLI wrapper for PulseAudio setup utility.

This script provides command-line access to configure PulseAudio
for streaming from macOS host to container services.
"""

import json
import sys

import click

from birdnetpi.utils.pulseaudio_setup import PulseAudioSetup


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """PulseAudio Setup for Container Streaming.

    Configure PulseAudio to stream audio from macOS to Docker containers.

    Examples:
      # Install PulseAudio (macOS only)
      pulseaudio-tool install

      # Setup streaming to container (auto-detects IP)
      pulseaudio-tool setup

      # Setup streaming to specific container IP
      pulseaudio-tool setup --container-ip 192.168.1.100

      # Setup streaming to different container
      pulseaudio-tool setup --container-name my-container

      # Auto-detect container IP
      pulseaudio-tool detect-ip

      # Test connection to container
      pulseaudio-tool test

      # Check current status
      pulseaudio-tool status

      # List available audio devices
      pulseaudio-tool devices

      # Clean up configuration
      pulseaudio-tool cleanup --force
    """
    ctx.ensure_object(dict)


@cli.command()
def install() -> None:
    """Install PulseAudio via Homebrew (macOS only)."""
    if not PulseAudioSetup.is_macos():
        click.echo(click.style("✗ PulseAudio installation only supported on macOS", fg="red"))
        sys.exit(1)

    if PulseAudioSetup.is_pulseaudio_installed():
        click.echo(click.style("✓ PulseAudio is already installed", fg="green"))
        return

    click.echo("Installing PulseAudio via Homebrew...")
    click.echo("This may take a few minutes...")

    success = PulseAudioSetup.install_pulseaudio()

    if success:
        click.echo(click.style("✓ PulseAudio installed successfully", fg="green"))
        click.echo("You can now run 'pulseaudio-tool setup' to configure streaming")
    else:
        click.echo(click.style("✗ Failed to install PulseAudio", fg="red"))
        click.echo("Please install manually: brew install pulseaudio")
        sys.exit(1)


@cli.command()
@click.option("--container-ip", help="IP address of the container (auto-detected if not specified)")
@click.option(
    "--container-name",
    default="birdnet-pi",
    help="Docker container name for auto-detection (default: birdnet-pi)",
)
@click.option("--port", type=int, default=4713, help="PulseAudio port in container (default: 4713)")
@click.option("--no-backup", is_flag=True, help="Don't backup existing configuration")
def setup(container_ip: str | None, container_name: str, port: int, no_backup: bool) -> None:
    """Configure PulseAudio streaming to container."""
    click.echo("Setting up PulseAudio for container streaming...")
    if container_ip:
        click.echo(f"Container IP: {container_ip}")
    else:
        detected_ip = PulseAudioSetup.get_container_ip(container_name)
        click.echo(f"Auto-detected container IP: {detected_ip}")
    click.echo(f"Port: {port}")
    click.echo()

    success, message = PulseAudioSetup.setup_streaming(
        container_ip=container_ip,
        port=port,
        backup_existing=not no_backup,
        container_name=container_name,
    )

    if success:
        click.echo(click.style(f"✓ {message}", fg="green"))
        click.echo()
        click.echo("Next steps:")
        click.echo("1. Start your BirdNET-Pi container with PulseAudio enabled")
        click.echo("2. Run 'pulseaudio-tool test' to verify connection")
        click.echo("3. Use 'pulseaudio-tool devices' to see available audio sources")
    else:
        click.echo(click.style(f"✗ Setup failed: {message}", fg="red"), err=True)
        sys.exit(1)


@cli.command()
@click.option("--container-ip", help="IP address of the container (auto-detected if not specified)")
@click.option(
    "--container-name",
    default="birdnet-pi",
    help="Docker container name for auto-detection (default: birdnet-pi)",
)
@click.option("--port", type=int, default=4713, help="PulseAudio port in container (default: 4713)")
def test(container_ip: str | None, container_name: str, port: int) -> None:
    """Test connection to container PulseAudio service."""
    if container_ip:
        click.echo(f"Testing connection to {container_ip}:{port}...")
    else:
        detected_ip = PulseAudioSetup.get_container_ip(container_name)
        click.echo(f"Testing connection to auto-detected IP {detected_ip}:{port}...")

    success, message = PulseAudioSetup.test_connection(
        container_ip=container_ip,
        port=port,
        container_name=container_name,
    )

    if success:
        click.echo(click.style(f"✓ {message}", fg="green"))
    else:
        click.echo(click.style(f"✗ {message}", fg="red"), err=True)
        click.echo()
        click.echo("Troubleshooting:")
        click.echo("- Ensure your container is running and PulseAudio is enabled")
        click.echo("- Check that the container IP and port are correct")
        click.echo("- Verify network connectivity between host and container")
        sys.exit(1)


@cli.command()
@click.option("--json", "output_json", is_flag=True, help="Output status in JSON format")
def status(output_json: bool) -> None:
    """Show current PulseAudio setup status."""
    status = PulseAudioSetup.get_status()

    click.echo("PulseAudio Setup Status:")
    click.echo("=" * 50)
    click.echo(f"Platform: {'macOS' if status['macos'] else 'Other'}")
    click.echo(f"PulseAudio installed: {'✓' if status['pulseaudio_installed'] else '✗'}")
    click.echo(f"Configuration exists: {'✓' if status['config_exists'] else '✗'}")
    click.echo(f"Authentication cookie: {'✓' if status['cookie_exists'] else '✗'}")
    click.echo(f"Server running: {'✓' if status['server_running'] else '✗'}")
    click.echo(f"Config directory: {status['config_dir']}")
    click.echo()

    if status["audio_devices"]:
        click.echo("Available Audio Devices:")
        click.echo("-" * 30)
        for device in status["audio_devices"]:
            click.echo(f"  [{device['id']}] {device['description']}")
    else:
        click.echo("No audio devices detected")

    if output_json:
        click.echo()
        click.echo("Raw Status (JSON):")
        click.echo(json.dumps(status, indent=2))


@cli.command()
@click.option("--json", "output_json", is_flag=True, help="Output devices in JSON format")
def devices(output_json: bool) -> None:
    """List available audio input devices."""
    devices = PulseAudioSetup.get_audio_devices()

    if not devices:
        click.echo(click.style("No audio devices found", fg="red"))
        click.echo("Make sure PulseAudio is running and devices are connected")
        sys.exit(1)

    click.echo("Available Audio Input Devices:")
    click.echo("=" * 40)

    for device in devices:
        click.echo(f"ID: {device['id']}")
        click.echo(f"Name: {device['name']}")
        click.echo(f"Description: {device['description']}")
        click.echo("-" * 40)

    if output_json:
        click.echo()
        click.echo("Devices (JSON):")
        click.echo(json.dumps(devices, indent=2))


@cli.command()
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def cleanup(force: bool) -> None:
    """Remove PulseAudio configuration."""
    if not force:
        if not click.confirm(
            "This will remove PulseAudio configuration and stop the server. Continue?"
        ):
            click.echo("Cleanup cancelled")
            return

    click.echo("Cleaning up PulseAudio configuration...")

    success, message = PulseAudioSetup.cleanup_config()

    if success:
        click.echo(click.style(f"✓ {message}", fg="green"))
    else:
        click.echo(click.style(f"✗ Cleanup failed: {message}", fg="red"), err=True)
        sys.exit(1)


@cli.command("detect-ip")
@click.option(
    "--container-name",
    default="birdnet-pi",
    help="Docker container name to detect IP for (default: birdnet-pi)",
)
def detect_ip(container_name: str) -> None:
    """Show auto-detected container IP address."""
    click.echo(f"Detecting IP for container '{container_name}'...")
    container_ip = PulseAudioSetup.get_container_ip(container_name)
    click.echo(click.style(f"Detected IP: {container_ip}", bold=True))

    if container_ip == "127.0.0.1":
        click.echo()
        click.echo(click.style("Note: Fallback IP used. This may indicate:", fg="yellow"))
        click.echo("- Container is not running")
        click.echo("- Docker is not available")
        click.echo("- Container name is incorrect")
        click.echo("- Container is using host networking")


def main() -> None:
    """Entry point for the PulseAudio tool CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()
