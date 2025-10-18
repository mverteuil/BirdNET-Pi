"""Installation progress UI using Rich for beautiful terminal output."""

import subprocess
from enum import Enum

from rich.console import Console  # type: ignore[import-untyped]
from rich.panel import Panel  # type: ignore[import-untyped]
from rich.progress import (  # type: ignore[import-untyped]
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table  # type: ignore[import-untyped]


class InstallStep(str, Enum):
    """Installation steps."""

    SYSTEM_DEPS = "Installing system dependencies"
    USER_SETUP = "Creating user and directories"
    VENV_SETUP = "Setting up Python environment"
    SOURCE_CODE = "Copying source code"
    PYTHON_DEPS = "Installing Python dependencies"
    CONFIG_TEMPLATES = "Installing configuration templates"
    ASSETS = "Downloading BirdNET assets"
    SYSTEMD = "Configuring systemd services"
    HEALTH_CHECK = "Verifying installation"


class ProgressUI:
    """Rich-based UI for installation progress tracking."""

    def __init__(self):
        """Initialize progress UI."""
        self.console = Console()
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            console=self.console,
        )
        self.tasks: dict[InstallStep, TaskID] = {}
        self.service_status: dict[str, str] = {}

    def show_header(self, site_name: str) -> None:
        """Show installation header.

        Args:
            site_name: Name of the installation site
        """
        self.console.clear()
        self.console.print(
            Panel.fit(
                f"[bold cyan]BirdNET-Pi Installation[/bold cyan]\n"
                f"Site: [yellow]{site_name}[/yellow]",
                border_style="cyan",
            )
        )
        self.console.print()

    def create_tasks(self) -> None:
        """Create all installation task progress bars."""
        for step in InstallStep:
            self.tasks[step] = self.progress.add_task(step.value, total=100)

    def update_task(self, step: InstallStep, advance: int = 0, total: int | None = None) -> None:
        """Update task progress.

        Args:
            step: Installation step to update
            advance: Amount to advance progress
            total: New total value (optional)
        """
        if total is not None:
            self.progress.update(self.tasks[step], total=total)
        if advance > 0:
            self.progress.update(self.tasks[step], advance=advance)

    def complete_task(self, step: InstallStep) -> None:
        """Mark a task as completed.

        Args:
            step: Installation step to complete
        """
        self.progress.update(self.tasks[step], completed=100)

    def check_service_status(self, service_name: str) -> str:
        """Check systemd service status.

        Args:
            service_name: Name of the systemd service

        Returns:
            str: Status emoji (✓, ✗, or ○)
        """
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.stdout.strip() == "active":
            return "✓"
        elif result.returncode == 3:  # Service not loaded
            return "○"
        else:
            return "✗"

    def show_service_status(self) -> None:
        """Display status of all BirdNET-Pi services."""
        services = [
            "birdnet_redis.service",
            "birdnet_caddy.service",
            "birdnet_fastapi.service",
            "birdnet_pulseaudio.service",
            "birdnet_audio_capture.service",
            "birdnet_audio_analysis.service",
            "birdnet_audio_websocket.service",
            "birdnet_update.service",
        ]

        table = Table(title="Service Status", show_header=True, header_style="bold cyan")
        table.add_column("Service", style="dim")
        table.add_column("Status", justify="center")

        for service in services:
            status = self.check_service_status(service)
            status_style = "green" if status == "✓" else "red" if status == "✗" else "yellow"
            table.add_row(service, f"[{status_style}]{status}[/{status_style}]")

        self.console.print()
        self.console.print(table)

    def show_final_summary(self, ip_address: str, site_name: str) -> None:
        """Show installation completion summary.

        Args:
            ip_address: IP address of the installed system
            site_name: Name of the installation site
        """
        self.console.print()
        self.console.print(
            Panel.fit(
                f"[bold green]✓ Installation Complete![/bold green]\n\n"
                f"Site Name: [yellow]{site_name}[/yellow]\n"
                f"Web Interface: [cyan]http://{ip_address}:8888[/cyan]\n"
                f"SSH Access: [cyan]ssh birdnet@{ip_address}[/cyan]\n\n"
                f"[dim]The system is now capturing and analyzing bird calls.\n"
                f"Visit the web interface to view detections and configure settings.[/dim]",
                border_style="green",
            )
        )

    def show_error(self, message: str, details: str | None = None) -> None:
        """Show error message.

        Args:
            message: Error message
            details: Additional error details (optional)
        """
        error_text = f"[bold red]Error:[/bold red] {message}"
        if details:
            error_text += f"\n\n[dim]{details}[/dim]"

        self.console.print()
        self.console.print(Panel(error_text, border_style="red", title="Installation Failed"))

    def show_info(self, message: str) -> None:
        """Show informational message.

        Args:
            message: Information to display
        """
        self.console.print(f"[cyan]i[/cyan] {message}")
