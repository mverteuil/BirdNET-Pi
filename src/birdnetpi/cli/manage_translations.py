#!/usr/bin/env python3
"""Translation management CLI for BirdNET-Pi i18n workflow."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import click

from birdnetpi.utils.path_resolver import PathResolver


def run_command(cmd: list[str], description: str) -> bool:
    """Run a command and handle errors."""
    click.echo(f"Running: {description}")
    click.echo(f"Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        if result.stdout:
            click.echo(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        if e.stderr:
            click.echo(f"stderr: {e.stderr}", err=True)
        return False


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Manage BirdNET-Pi translations.

    Tools for extracting, updating, and compiling translation files.
    """
    # Set BIRDNETPI_APP to the current working directory
    os.environ["BIRDNETPI_APP"] = str(Path.cwd())

    # Initialize the file path resolver
    ctx.ensure_object(dict)
    ctx.obj["resolver"] = PathResolver()


@cli.command()
@click.pass_obj
def extract(obj: dict[str, Any]) -> None:
    """Extract translatable strings from source code."""
    resolver = obj["resolver"]

    # Get paths relative to src directory
    src_dir = Path(resolver.get_src_dir())
    babel_cfg = Path(resolver.get_babel_config_path()).relative_to(src_dir.parent)
    messages_pot = Path(resolver.get_messages_pot_path()).relative_to(src_dir.parent)
    # Get the source directory relative to its parent (should be "src" in production)
    src_dir_relative = src_dir.relative_to(src_dir.parent)

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
        str(src_dir_relative),
    ]

    success = run_command(cmd, "Extracting translatable strings")
    if success:
        click.echo(click.style("✓ String extraction completed successfully", fg="green"))
    else:
        click.echo(click.style("✗ String extraction failed", fg="red"), err=True)
        sys.exit(1)


@cli.command()
@click.pass_obj
def update(obj: dict[str, Any]) -> None:
    """Update existing translation files with new strings."""
    resolver = obj["resolver"]

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

    success = run_command(cmd, "Updating translation files")
    if success:
        click.echo(click.style("✓ Translation update completed successfully", fg="green"))
    else:
        click.echo(click.style("✗ Translation update failed", fg="red"), err=True)
        sys.exit(1)


@cli.command("compile")
@click.pass_obj
def compile_translations(obj: dict[str, Any]) -> None:
    """Compile .po files to .mo files."""
    resolver = obj["resolver"]

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

    success = run_command(cmd, "Compiling translation files")
    if success:
        click.echo(click.style("✓ Translation compilation completed successfully", fg="green"))
    else:
        click.echo(click.style("✗ Translation compilation failed", fg="red"), err=True)
        sys.exit(1)


@cli.command()
@click.argument("language")
@click.pass_obj
def init(obj: dict[str, Any], language: str) -> None:
    """Initialize a new language.

    LANGUAGE: Language code (e.g., 'it', 'pt', 'zh')
    """
    resolver = obj["resolver"]

    # Get paths relative to src directory parent (repo root)
    src_dir = resolver.get_src_dir()
    messages_pot = resolver.get_messages_pot_path().relative_to(src_dir.parent)
    locales_dir = resolver.get_locales_dir().relative_to(src_dir.parent)

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

    success = run_command(cmd, f"Initializing language: {language}")
    if success:
        click.echo(click.style(f"✓ Language '{language}' initialized successfully", fg="green"))
    else:
        click.echo(click.style("✗ Language initialization failed", fg="red"), err=True)
        sys.exit(1)


@cli.command("all")
@click.pass_context
def run_all(ctx: click.Context) -> None:
    """Run extract, update, and compile in sequence."""
    click.echo(click.style("Running complete translation workflow...", bold=True))
    click.echo()

    # Run extract
    click.echo(click.style("Step 1/3: Extracting strings", bold=True))
    ctx.invoke(extract)
    click.echo()

    # Run update
    click.echo(click.style("Step 2/3: Updating translations", bold=True))
    ctx.invoke(update)
    click.echo()

    # Run compile
    click.echo(click.style("Step 3/3: Compiling translations", bold=True))
    ctx.invoke(compile_translations)
    click.echo()

    click.echo(
        click.style("✓ Complete translation workflow finished successfully", fg="green", bold=True)
    )


def main() -> None:
    """Entry point for the translation management CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()
