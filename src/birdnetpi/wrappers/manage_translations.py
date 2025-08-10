#!/usr/bin/env python3
"""Translation management wrapper for BirdNET-Pi i18n workflow."""

import argparse
import subprocess
import sys
from pathlib import Path

from birdnetpi.utils.file_path_resolver import FilePathResolver


def run_command(cmd: list[str], description: str) -> bool:
    """Run a command and handle errors."""
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error: {e}")
        if e.stderr:
            print(f"stderr: {e.stderr}")
        return False


def extract_strings(resolver: FilePathResolver) -> bool:
    """Extract translatable strings from source code."""
    # Get paths relative to src directory
    src_dir = Path(resolver.get_src_dir())
    babel_cfg = Path(resolver.get_babel_config_path()).relative_to(src_dir.parent)
    messages_pot = Path(resolver.get_messages_pot_path()).relative_to(src_dir.parent)

    cmd = [
        "uv",
        "run",
        "pybabel",
        "extract",
        "-F",
        str(babel_cfg),
        "-k",
        "lazy_gettext",
        "--project=BirdNET-Pi",
        "--version=2.0.0",
        "--msgid-bugs-address=https://github.com/mverteuil/BirdNET-Pi/issues",
        "--copyright-holder=BirdNET-Pi Contributors",
        "-o",
        str(messages_pot),
        "src",
    ]
    return run_command(cmd, "Extracting translatable strings")


def update_translations(resolver: FilePathResolver) -> bool:
    """Update existing translation files with new strings."""
    # Get paths relative to src directory parent (repo root)
    src_dir = Path(resolver.get_src_dir())
    messages_pot = Path(resolver.get_messages_pot_path()).relative_to(src_dir.parent)
    locales_dir = Path(resolver.get_locales_dir()).relative_to(src_dir.parent)

    cmd = [
        "uv",
        "run",
        "pybabel",
        "update",
        "-i",
        str(messages_pot),
        "-d",
        str(locales_dir),
    ]
    return run_command(cmd, "Updating translation files")


def compile_translations(resolver: FilePathResolver) -> bool:
    """Compile .po files to .mo files."""
    # Get paths relative to src directory parent (repo root)
    src_dir = Path(resolver.get_src_dir())
    locales_dir = Path(resolver.get_locales_dir()).relative_to(src_dir.parent)

    cmd = [
        "uv",
        "run",
        "pybabel",
        "compile",
        "-d",
        str(locales_dir),
    ]
    return run_command(cmd, "Compiling translation files")


def init_language(resolver: FilePathResolver, language: str) -> bool:
    """Initialize a new language."""
    # Get paths relative to src directory parent (repo root)
    src_dir = Path(resolver.get_src_dir())
    messages_pot = Path(resolver.get_messages_pot_path()).relative_to(src_dir.parent)
    locales_dir = Path(resolver.get_locales_dir()).relative_to(src_dir.parent)

    cmd = [
        "uv",
        "run",
        "pybabel",
        "init",
        "-i",
        str(messages_pot),
        "-d",
        str(locales_dir),
        "-l",
        language,
    ]
    return run_command(cmd, f"Initializing language: {language}")


def main() -> None:
    """Execute the main script entry point."""
    parser = argparse.ArgumentParser(description="Manage BirdNET-Pi translations")
    parser.add_argument(
        "command",
        choices=["extract", "update", "compile", "init", "all"],
        help="Translation command to run",
    )
    parser.add_argument(
        "--language", help="Language code for 'init' command (e.g., 'it', 'pt', 'zh')"
    )

    args = parser.parse_args()

    # Set BIRDNETPI_APP to the current working directory
    import os
    from pathlib import Path

    os.environ["BIRDNETPI_APP"] = str(Path.cwd())

    # Initialize the file path resolver
    resolver = FilePathResolver()

    success = True

    if args.command == "extract":
        success = extract_strings(resolver)
    elif args.command == "update":
        success = update_translations(resolver)
    elif args.command == "compile":
        success = compile_translations(resolver)
    elif args.command == "init":
        if not args.language:
            print("Error: --language is required for 'init' command")
            sys.exit(1)
        success = init_language(resolver, args.language)
    elif args.command == "all":
        success = (
            extract_strings(resolver)
            and update_translations(resolver)
            and compile_translations(resolver)
        )

    if success:
        print("✓ Translation operation completed successfully")
    else:
        print("✗ Translation operation failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
