import argparse
import sys

from birdnetpi.managers.system_monitor import SystemMonitor


def main_cli() -> None:
    """Provide the main entry point for the System Monitor Wrapper CLI."""
    parser = argparse.ArgumentParser(description="System Monitor Wrapper")
    parser.add_argument("action", type=str, help="Action to perform (e.g., disk_check, dump_logs)")
    parser.add_argument("--path", type=str, default=".", help="Path to check disk usage for")
    parser.add_argument("--threshold", type=int, default=10, help="Disk space threshold in percent")
    parser.add_argument(
        "--log_file",
        type=str,
        default="/var/log/syslog",
        help="Path to the log file to dump",
    )

    args = parser.parse_args()

    system_monitor = SystemMonitor()

    if args.action == "disk_check":
        is_sufficient, message = system_monitor.check_disk_space(args.path, args.threshold)
        print(message)
        if not is_sufficient:
            sys.exit(1)
    elif args.action == "dump_logs":
        system_monitor.dump_logs(args.log_file)
    elif args.action == "extra_info":
        info = system_monitor.get_extra_info()
        for key, value in info.items():
            print(f"{key}: {value}")
    else:
        parser.error(f"Unknown action: {args.action}")


if __name__ == "__main__":
    main_cli()
