r"""IOC database builder CLI.

This script builds IOC World Bird Names SQLite database from XML and XLSX files.

Usage:
    ioc-database-builder build \
        --xml-file ioc_names_v15.1.xml \
        --xlsx-file ioc_multilingual_v15.1.xlsx \
        --db-file ioc_database.db
"""

import sys
from pathlib import Path

import click

from birdnetpi.utils.ioc_database_builder import IOCDatabaseBuilder


@click.group()
def cli() -> None:
    """IOC World Bird Names database builder."""
    pass


@cli.command()
@click.option(
    "--xml-file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to IOC XML file",
)
@click.option(
    "--xlsx-file",
    type=click.Path(exists=True, path_type=Path),
    help="Path to IOC multilingual XLSX file (optional)",
)
@click.option(
    "--db-file",
    type=click.Path(path_type=Path),
    required=True,
    help="Path to output SQLite database file",
)
def build(xml_file: Path, xlsx_file: Path | None, db_file: Path) -> None:
    """Build IOC database from XML and optionally XLSX files."""
    click.echo("Building IOC database...")
    click.echo(f"XML file: {xml_file}")
    if xlsx_file:
        click.echo(f"XLSX file: {xlsx_file}")
    click.echo(f"Database: {db_file}")
    click.echo()

    try:
        # Create database builder
        builder = IOCDatabaseBuilder(db_path=db_file)

        # Populate from files
        builder.populate_from_files(xml_file, xlsx_file)

        click.echo(click.style("✓ Database built successfully", fg="green"))

    except FileNotFoundError as e:
        click.echo(click.style(f"✗ File not found: {e}", fg="red"), err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(click.style(f"✗ Error building database: {e}", fg="red"), err=True)
        sys.exit(1)


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
