r"""IOC data processor wrapper script.

This script processes IOC World Bird Names XML and multilingual XLSX files
to create cached JSON data for use by the BirdNET-Pi application.

Usage:
    python -m birdnetpi.wrappers.ioc_data_processor process \\
        --xml-file ioc_names_v15.1.xml \\
        --xlsx-file ioc_multilingual_v15.1.xlsx \\
        --output ioc_data_v15.1.json
    python -m birdnetpi.wrappers.ioc_data_processor info --json-file ioc_data_v15.1.json
"""

import argparse
import sys
from pathlib import Path

from birdnetpi.services.ioc_database_service import IOCDatabaseService
from birdnetpi.services.ioc_reference_service import IOCReferenceService


def process_ioc_files(
    xml_file: Path,
    xlsx_file: Path,
    output_file: Path,
    compress: bool = False,
    db_file: Path | None = None,
) -> None:
    """Process IOC XML and XLSX files into JSON and/or SQLite database format.

    Args:
        xml_file: Path to IOC XML file
        xlsx_file: Path to IOC multilingual XLSX file
        output_file: Path to output JSON file
        compress: Whether to compress JSON output with gzip
        db_file: Path to output SQLite database file (optional)
    """
    print("Processing IOC data files...")
    print(f"XML file: {xml_file}")
    print(f"XLSX file: {xlsx_file}")
    print(f"Output: {output_file}")
    print()

    # Validate input files
    if not xml_file.exists():
        print(f"Error: XML file not found: {xml_file}")
        sys.exit(1)

    if not xlsx_file.exists():
        print(f"Error: XLSX file not found: {xlsx_file}")
        sys.exit(1)

    # Create output directory if needed
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Process files
    try:
        service = IOCReferenceService(data_dir=xml_file.parent)
        service.load_ioc_data(xml_file=xml_file, xlsx_file=xlsx_file)

        # Export to JSON
        service.export_json(output_file, include_translations=True, compress=compress)
        json_size = output_file.stat().st_size

        # Export to SQLite database if requested
        db_size = 0
        if db_file:
            print("Creating SQLite database...")
            db_service = IOCDatabaseService(db_file)
            db_service.populate_from_ioc_service(service)
            db_size = db_service.get_database_size()

        # Print summary
        print()
        print("Processing complete!")
        print(f"IOC Version: {service.get_ioc_version()}")
        print(f"Species count: {service.get_species_count()}")
        print(f"Available languages: {len(service.get_available_languages())}")
        compression_note = " (gzipped)" if compress else ""
        print(f"JSON output: {output_file} ({json_size:,} bytes{compression_note})")
        if db_file:
            print(f"SQLite output: {db_file} ({db_size:,} bytes)")
            if compress:
                print(
                    f"SQLite vs compressed JSON: "
                    f"{((db_size - json_size) / json_size * 100):+.1f}% size difference"
                )
            else:
                print(
                    f"SQLite vs JSON: "
                    f"{((db_size - json_size) / json_size * 100):+.1f}% size difference"
                )

    except Exception as e:
        print(f"Error processing IOC files: {e}")
        sys.exit(1)


def show_ioc_info(json_file: Path) -> None:
    """Show information about processed IOC JSON file.

    Args:
        json_file: Path to IOC JSON file
    """
    if not json_file.exists():
        print(f"Error: JSON file not found: {json_file}")
        sys.exit(1)

    try:
        service = IOCReferenceService()
        service.load_from_json(json_file)

        print("IOC Data Information:")
        print(f"File: {json_file}")
        print(f"Size: {json_file.stat().st_size:,} bytes")
        print(f"IOC Version: {service.get_ioc_version()}")
        print(f"Species count: {service.get_species_count()}")
        print(f"Available languages: {len(service.get_available_languages())}")
        print()

        # Show available languages
        languages = sorted(service.get_available_languages())
        print("Available language codes:")
        for i, lang in enumerate(languages):
            print(f"  {lang}", end="")
            if (i + 1) % 8 == 0:  # New line every 8 languages
                print()
        if len(languages) % 8 != 0:
            print()

        print()

        # Show sample species
        print("Sample species (first 5):")
        species_list = list(service._species_data.values())[:5]
        for species in species_list:
            print(f"  {species.scientific_name} - {species.english_name}")
            print(f"    Order: {species.order}, Family: {species.family}")

            # Show sample translations
            translations = service._translations.get(species.scientific_name, {})
            if translations:
                sample_langs = list(translations.keys())[:3]  # Show first 3 translations
                for lang in sample_langs:
                    print(f"    {lang}: {translations[lang]}")
            print()

    except Exception as e:
        print(f"Error reading IOC JSON file: {e}")
        sys.exit(1)


def lookup_species(json_file: Path, scientific_name: str, language_code: str = "en") -> None:
    """Test species lookup functionality.

    Args:
        json_file: Path to IOC JSON file
        scientific_name: Scientific name to lookup
        language_code: Language code for translation
    """
    if not json_file.exists():
        print(f"Error: JSON file not found: {json_file}")
        sys.exit(1)

    try:
        service = IOCReferenceService()
        service.load_from_json(json_file)

        print(f"Testing lookup for: {scientific_name}")
        print(f"Language: {language_code}")
        print()

        # Get species info
        species = service.get_species_info(scientific_name)
        if species:
            print("Species found:")
            print(f"  Scientific name: {species.scientific_name}")
            print(f"  English name: {species.english_name}")
            print(f"  Order: {species.order}")
            print(f"  Family: {species.family}")
            print(f"  Authority: {species.authority}")

            # Get translation
            if language_code != "en":
                translation = service.get_translated_common_name(scientific_name, language_code)
                if translation:
                    print(f"  {language_code.upper()} name: {translation}")
                else:
                    print(f"  No {language_code.upper()} translation available")
        else:
            print(f"Species not found: {scientific_name}")

            # Suggest similar names
            print("\nSearching for similar names...")
            genus = scientific_name.split()[0] if " " in scientific_name else scientific_name
            similar = [s for s in service._species_data.keys() if s.startswith(genus)][:5]
            if similar:
                print("Similar species found:")
                for name in similar:
                    print(f"  {name}")
            else:
                print("No similar species found")

    except Exception as e:
        print(f"Error testing lookup: {e}")
        sys.exit(1)


def main() -> None:
    """Provide main entry point for IOC data processor."""
    parser = argparse.ArgumentParser(
        description="IOC World Bird Names data processor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process IOC files into JSON format
  python -m birdnetpi.wrappers.ioc_data_processor process \\
      --xml-file ioc_names_v15.1.xml \\
      --xlsx-file ioc_multilingual_v15.1.xlsx \\
      --output data/ioc_data_v15.1.json

  # Show information about processed JSON file
  python -m birdnetpi.wrappers.ioc_data_processor info --json-file data/ioc_data_v15.1.json

  # Test species lookup
  python -m birdnetpi.wrappers.ioc_data_processor lookup \\
      --json-file data/ioc_data_v15.1.json \\
      --species "Turdus migratorius" \\
      --language es
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Process command
    process_parser = subparsers.add_parser(
        "process", help="Process IOC XML and XLSX files into JSON"
    )
    process_parser.add_argument("--xml-file", type=Path, required=True, help="Path to IOC XML file")
    process_parser.add_argument(
        "--xlsx-file", type=Path, required=True, help="Path to IOC multilingual XLSX file"
    )
    process_parser.add_argument(
        "--output", type=Path, required=True, help="Path to output JSON file"
    )
    process_parser.add_argument(
        "--compress", action="store_true", help="Compress JSON output with gzip"
    )
    process_parser.add_argument(
        "--db-file", type=Path, help="Path to output SQLite database file (optional)"
    )

    # Info command
    info_parser = subparsers.add_parser("info", help="Show information about IOC JSON file")
    info_parser.add_argument("--json-file", type=Path, required=True, help="Path to IOC JSON file")

    # Lookup command
    lookup_parser = subparsers.add_parser("lookup", help="Test species lookup")
    lookup_parser.add_argument(
        "--json-file", type=Path, required=True, help="Path to IOC JSON file"
    )
    lookup_parser.add_argument(
        "--species", type=str, required=True, help="Scientific name to lookup"
    )
    lookup_parser.add_argument(
        "--language", type=str, default="en", help="Language code for translation (default: en)"
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "process":
        process_ioc_files(args.xml_file, args.xlsx_file, args.output, args.compress, args.db_file)
    elif args.command == "info":
        show_ioc_info(args.json_file)
    elif args.command == "lookup":
        lookup_species(args.json_file, args.species, args.language)


if __name__ == "__main__":
    main()
