#!/usr/bin/env python3
"""Translation management script for BirdNET-Pi i18n workflow.

This script provides convenient commands for managing translations:
- extract: Extract translatable strings from source code
- update: Update existing translation files with new strings
- compile: Compile .po files to .mo files for production use
- init: Initialize a new language
"""

import argparse
import subprocess
import sys
from pathlib import Path


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


def extract_strings() -> bool:
    """Extract translatable strings from source code."""
    cmd = [
        "pybabel",
        "extract",
        "-F",
        "babel.cfg",
        "-k",
        "lazy_gettext",
        "-o",
        "locales/messages.pot",
        "src/",
    ]
    return run_command(cmd, "Extracting translatable strings")


def update_translations() -> bool:
    """Update existing translation files with new strings."""
    cmd = ["pybabel", "update", "-i", "locales/messages.pot", "-d", "locales"]
    return run_command(cmd, "Updating translation files")


def compile_translations() -> bool:
    """Compile .po files to .mo files."""
    cmd = ["pybabel", "compile", "-d", "locales"]
    return run_command(cmd, "Compiling translation files")


def init_language(language: str) -> bool:
    """Initialize a new language."""
    cmd = ["pybabel", "init", "-i", "locales/messages.pot", "-d", "locales", "-l", language]
    return run_command(cmd, f"Initializing language: {language}")


def main() -> None:
    """Main script entry point."""
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

    # Change to project root directory
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    print(f"Working directory: {project_root}")
    import os

    os.chdir(project_root)

    success = True

    if args.command == "extract":
        success = extract_strings()
    elif args.command == "update":
        success = update_translations()
    elif args.command == "compile":
        success = compile_translations()
    elif args.command == "init":
        if not args.language:
            print("Error: --language is required for 'init' command")
            sys.exit(1)
        success = init_language(args.language)
    elif args.command == "all":
        success = extract_strings() and update_translations() and compile_translations()

    if success:
        print("✓ Translation operation completed successfully")
    else:
        print("✗ Translation operation failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
