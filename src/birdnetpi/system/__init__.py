"""System domain package.

This package contains system-level management components:
- FileManager: File system operations and management
- HardwareMonitorManager: Hardware monitoring and status reporting
- PathResolver: Path resolution and management
- PulseAudioSetup: PulseAudio configuration utilities
- ServiceStrategies: Service management strategies
- SystemControlService: System service control (start/stop/restart)
- SystemMonitorService: System monitoring and status reporting
- SystemUtils: System utility functions
- LogService: Logging service
- StructlogConfigurator: Structured logging configuration
"""

from birdnetpi.system import structlog_configurator
from birdnetpi.system.file_manager import FileManager
from birdnetpi.system.hardware_monitor_manager import HardwareMonitorManager
from birdnetpi.system.log_service import LogService
from birdnetpi.system.path_resolver import PathResolver
from birdnetpi.system.pulseaudio_setup import PulseAudioSetup
from birdnetpi.system.service_strategies import ServiceManagementStrategy
from birdnetpi.system.system_control_service import SystemControlService
from birdnetpi.system.system_monitor_service import SystemMonitorService
from birdnetpi.system.system_utils import SystemUtils

__all__ = [
    "FileManager",
    "HardwareMonitorManager",
    "LogService",
    "PathResolver",
    "PulseAudioSetup",
    "ServiceManagementStrategy",
    "SystemControlService",
    "SystemMonitorService",
    "SystemUtils",
    "structlog_configurator",
]
