r"""IOC data processor wrapper script.

This script processes IOC World Bird Names XML and multilingual XLSX files
to create cached JSON data for use by the BirdNET-Pi application.

Usage:
    ioc-data-processor process \
        --xml-file ioc_names_v15.1.xml \
        --xlsx-file ioc_multilingual_v15.1.xlsx \
        --output ioc_data_v15.1.json
    ioc-data-processor info --json-file ioc_data_v15.1.json
"""

import sys
from pathlib import Path

import click

from birdnetpi.utils.ioc_database_builder import IOCDatabaseBuilder


@click.group()
@click.pass_context
def cli(ctx: click.Context) -> None:
    """IOC World Bird Names data processor.

    Process IOC taxonomy and multilingual data for BirdNET-Pi.

    Examples:
      # Process IOC files into JSON format
      ioc-data-processor process \
          --xml-file ioc_names_v15.1.xml \
          --xlsx-file ioc_multilingual_v15.1.xlsx \
          --output data/ioc_data_v15.1.json

      # Show information about processed JSON file
      ioc-data-processor info --json-file data/ioc_data_v15.1.json

      # Test species lookup
      ioc-data-processor lookup \
          --json-file data/ioc_data_v15.1.json \
          --species "Turdus migratorius" \
          --language es
    """
    ctx.ensure_object(dict)


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
    required=True,
    help="Path to IOC multilingual XLSX file",
)
@click.option(
    "--output", type=click.Path(path_type=Path), required=True, help="Path to output JSON file"
)
@click.option("--compress", is_flag=True, help="Compress JSON output with gzip")
@click.option(
    "--db-file",
    type=click.Path(path_type=Path),
    help="Path to output SQLite database file (optional)",
)
def process(
    xml_file: Path, xlsx_file: Path, output: Path, compress: bool, db_file: Path | None
) -> None:
    """Process IOC XML and XLSX files into JSON format."""
    click.echo("Processing IOC data files...")
    click.echo(f"XML file: {xml_file}")
    click.echo(f"XLSX file: {xlsx_file}")
    click.echo(f"Output: {output}")
    click.echo()

    try:
        # Process using IOC reference service
        service = IOCDatabaseBuilder()
        service.load_ioc_data(xml_file, xlsx_file)
        service.export_json(output, compress=compress)

        click.echo(click.style("✓ JSON data saved successfully", fg="green"))
        click.echo(f"  Species count: {service.get_species_count()}")
        click.echo(f"  Languages: {len(service.get_available_languages())}")

        # Optionally create SQLite database
        if db_file:
            click.echo()
            click.echo(f"Creating SQLite database: {db_file}")
            db_service = IOCDatabaseBuilder(db_path=db_file)
            db_service._species_data = service._species_data
            db_service._translations = service._translations
            db_service._ioc_version = service._ioc_version
            db_service._loaded = True
            db_service.populate_database()
            click.echo(click.style("✓ SQLite database created successfully", fg="green"))

    except Exception as e:
        click.echo(click.style(f"✗ Error processing IOC files: {e}", fg="red"), err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--json-file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to IOC JSON file",
)
def info(json_file: Path) -> None:
    """Show information about processed IOC JSON file."""
    try:
        service = IOCDatabaseBuilder()
        service.load_from_json(json_file)

        click.echo("IOC Data Information:")
        click.echo(f"File: {json_file}")
        click.echo(f"Size: {json_file.stat().st_size:,} bytes")
        click.echo(f"IOC Version: {service.get_ioc_version()}")
        click.echo(f"Species count: {service.get_species_count()}")
        click.echo(f"Available languages: {len(service.get_available_languages())}")
        click.echo()

        # Show available languages
        languages = sorted(service.get_available_languages())
        click.echo("Available language codes:")
        for i, lang in enumerate(languages):
            click.echo(f"  {lang}", nl=False)
            if (i + 1) % 8 == 0:  # New line every 8 languages
                click.echo()
        if len(languages) % 8 != 0:
            click.echo()

        click.echo()

        # Show sample species
        click.echo("Sample species (first 5):")
        species_list = list(service._species_data.values())[:5]
        for species in species_list:
            click.echo(f"  {species.scientific_name} - {species.english_name}")
            click.echo(f"    Order: {species.order}, Family: {species.family}")

            # Show sample translations
            translations = service._translations.get(species.scientific_name, {})
            if translations:
                sample_langs = list(translations.keys())[:3]  # Show first 3 translations
                for lang in sample_langs:
                    click.echo(f"    {lang}: {translations[lang]}")
            click.echo()

    except Exception as e:
        click.echo(click.style(f"✗ Error reading IOC JSON file: {e}", fg="red"), err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--json-file",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to IOC JSON file",
)
@click.option("--species", required=True, help="Scientific name to lookup")
@click.option("--language", default="en", help="Language code for translation (default: en)")
def lookup(json_file: Path, species: str, language: str) -> None:
    """Test species lookup functionality."""
    try:
        service = IOCDatabaseBuilder()
        service.load_from_json(json_file)

        click.echo(f"Testing lookup for: {species}")
        click.echo(f"Language: {language}")
        click.echo()

        # Get species info
        species_info = service.get_species_info(species)
        if species_info:
            click.echo(click.style("Species found:", fg="green"))
            click.echo(f"  Scientific name: {species_info.scientific_name}")
            click.echo(f"  English name: {species_info.english_name}")
            click.echo(f"  Order: {species_info.order}")
            click.echo(f"  Family: {species_info.family}")
            click.echo(f"  Authority: {species_info.authority}")

            # Get translation
            if language != "en":
                translation = service.get_translated_common_name(species, language)
                if translation:
                    click.echo(f"  {language.upper()} name: {translation}")
                else:
                    click.echo(f"  No {language.upper()} translation available")
        else:
            click.echo(click.style(f"Species not found: {species}", fg="red"))

            # Suggest similar names
            click.echo("\nSearching for similar names...")
            genus = species.split()[0] if " " in species else species
            similar = [s for s in service._species_data.keys() if s.startswith(genus)][:5]
            if similar:
                click.echo("Similar species found:")
                for name in similar:
                    info = service._species_data[name]
                    click.echo(f"  {name} - {info.english_name}")
            else:
                click.echo("No similar species found")

    except Exception as e:
        click.echo(click.style(f"✗ Error testing lookup: {e}", fg="red"), err=True)
        sys.exit(1)


def main() -> None:
    """Entry point for the IOC data processor CLI."""
    cli(obj={})


if __name__ == "__main__":
    main()
