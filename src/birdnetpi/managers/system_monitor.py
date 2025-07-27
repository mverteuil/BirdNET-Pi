import os
import shutil
import subprocess


class SystemMonitor:
    """Monitors system resources like disk usage, logs, and hardware information."""

    def get_disk_usage(self, path: str = ".") -> dict[str, int]:
        """Return disk usage statistics for a given path."""
        total, used, free = shutil.disk_usage(path)
        return {"total": total, "used": used, "free": free}

    def check_disk_space(self, path: str = ".", threshold_percent: int = 10) -> tuple[bool, str]:
        """Check if free disk space is below a specified threshold."""
        total, used, free = shutil.disk_usage(path)
        free_percent = (free / total) * 100
        if free_percent < threshold_percent:
            return (
                False,
                f"Low disk space: {free_percent:.2f}% free, below {threshold_percent}% threshold.",
            )
        return True, f"Disk space is sufficient: {free_percent:.2f}% free."

    def dump_logs(self, log_file_path: str = "/var/log/syslog") -> str:
        """Dump the content of a specified log file."""
        if not os.path.exists(log_file_path):
            return f"Error: Log file not found at {log_file_path}"
        try:
            with open(log_file_path) as f:
                return "\n".join([line.strip() for line in f])
        except Exception as e:
            return f"Error reading log file: {e}"

    def get_extra_info(self) -> dict[str, str]:
        """Retrieve extra system information like CPU temperature and memory usage."""
        info = {}
        try:
            # Get CPU temperature (Raspberry Pi specific)
            temp_output = (
                subprocess.check_output(["vcgencmd", "measure_temp"]).decode("utf-8").strip()
            )
            info["cpu_temperature"] = temp_output.split("=")[1]
        except FileNotFoundError:
            info["cpu_temperature"] = "N/A (vcgencmd not found)"
        except Exception as e:
            info["cpu_temperature"] = f"Error: {e}"

        try:
            # Get memory usage
            mem_output = subprocess.check_output(["free", "-h"]).decode("utf-8").splitlines()
            info["memory_usage"] = mem_output[1]  # Second line contains total, used, free memory
        except FileNotFoundError:
            info["memory_usage"] = "N/A (free command not found)"
        except Exception as e:
            info["memory_usage"] = f"Error: {e}"

        return info
