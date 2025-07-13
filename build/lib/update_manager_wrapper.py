import sys

from .managers.update_manager import UpdateManager


def main():
    update_manager = UpdateManager()

    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "update_birdnet":
            remote = "origin"
            branch = "main"
            # Parse arguments for remote and branch if provided
            i = 2
            while i < len(sys.argv):
                if sys.argv[i] == "-r" and i + 1 < len(sys.argv):
                    remote = sys.argv[i + 1]
                    i += 2
                elif sys.argv[i] == "-b" and i + 1 < len(sys.argv):
                    branch = sys.argv[i + 1]
                    i += 2
                else:
                    print(f"Unknown argument: {sys.argv[i]}")
                    sys.exit(1)
            update_manager.update_birdnet(remote=remote, branch=branch)
        elif command == "update_birdnet_snippets":
            # This would call a method in UpdateManager for snippets
            # For now, it just prints a message
            print(
                "update_birdnet_snippets called. (Implementation pending in UpdateManager)"
            )
        elif command == "update_caddyfile":
            birdnetpi_url = os.environ.get("BIRDNETPI_URL")
            extracted_path = os.environ.get("EXTRACTED")
            caddy_pwd = os.environ.get("CADDY_PWD")
            if not birdnetpi_url or not extracted_path:
                print(
                    "Error: BIRDNETPI_URL and EXTRACTED environment variables must be set."
                )
                sys.exit(1)
            update_manager.update_caddyfile(
                birdnetpi_url=birdnetpi_url,
                extracted_path=extracted_path,
                caddy_pwd=caddy_pwd,
            )
        else:
            print(f"Unknown command: {command}")
            sys.exit(1)
    else:
        print("No command provided.")
        sys.exit(1)


if __name__ == "__main__":
    main()
