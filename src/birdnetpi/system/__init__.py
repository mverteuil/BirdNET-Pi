"""System domain package.

This package contains system-level management components:
- FileManager: File system operations and management
- PathResolver: Path resolution and management
- PulseAudioSetup: PulseAudio configuration utilities
- ServiceStrategies: Service management strategies
- SystemControlService: System service control (start/stop/restart)
- SystemInspector: System status inspection utilities
  (replaces HardwareMonitorManager and SystemMonitorService)
- SystemUtils: System utility functions
- LogReaderService: Logging service
- StructlogConfigurator: Structured logging configuration
"""

from birdnetpi.system import structlog_configurator
from birdnetpi.system.log_reader import LogReaderService
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.system.pulseaudio_setup import PulseAudioSetup
from birdnetpi.system.service_strategies import ServiceManagementStrategy
from birdnetpi.system.status import HealthStatus, SystemInspector
from birdnetpi.system.system_control import SystemControlService
from birdnetpi.system.system_utils import SystemUtils

__all__ = [
    "HealthStatus",
    "LogReaderService",
    "PathResolver",
    "PulseAudioSetup",
    "ServiceManagementStrategy",
    "SystemControlService",
    "SystemInspector",
    "SystemUtils",
    "structlog_configurator",
]
