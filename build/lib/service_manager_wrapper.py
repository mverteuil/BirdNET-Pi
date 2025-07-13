import argparse

from .managers.service_manager import ServiceManager

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Service Manager Wrapper")
    parser.add_argument(
        "action", type=str, help="Action to perform (e.g., restart_services)"
    )
    parser.add_argument("services", nargs="*", help="List of services to restart")

    args = parser.parse_args()

    service_manager = ServiceManager()

    if args.action == "restart_services":
        if not args.services:
            parser.error(
                "At least one service name is required for restart_services action."
            )
        service_manager.restart_services(args.services)
    else:
        parser.error(f"Unknown action: {args.action}")
