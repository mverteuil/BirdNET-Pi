import argparse

from birdnetpi.services.system_control_service import SystemControlService


def main_cli() -> None:
    """Provide the main entry point for the Service Manager Wrapper CLI."""
    parser = argparse.ArgumentParser(description="Service Manager Wrapper")
    parser.add_argument("action", type=str, help="Action to perform (e.g., restart_services)")
    parser.add_argument("services", nargs="*", help="List of services to restart")

    args = parser.parse_args()

    service_manager = SystemControlService()

    if args.action == "restart_services":
        if not args.services:
            parser.error("At least one service name is required for restart_services action.")
        service_manager.restart_services(args.services)
    else:
        parser.error(f"Unknown action: {args.action}")


if __name__ == "__main__":
    main_cli()
