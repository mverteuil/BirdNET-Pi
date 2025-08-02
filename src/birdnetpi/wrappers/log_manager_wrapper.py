import argparse

from birdnetpi.services.log_service import LogService


def main_cli() -> None:
    """Provide the main entry point for the Log Manager Wrapper CLI."""
    parser = argparse.ArgumentParser(description="Log Manager Wrapper")
    parser.add_argument(
        "action",
        type=str,
        help="Action to perform (e.g., get_logs)",
    )

    args = parser.parse_args()

    log_service = LogService()

    if args.action == "get_logs":
        logs = log_service.get_logs()
        print(logs)
    else:
        parser.error(f"Unknown action: {args.action}")


if __name__ == "__main__":
    main_cli()
