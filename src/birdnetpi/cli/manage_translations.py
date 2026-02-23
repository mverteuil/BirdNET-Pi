#!/usr/bin/env python3
"""Translation management CLI for BirdNET-Pi i18n workflow."""

import os
import re
import subprocess
import sys
from pathlib import Path
from re import Match
from typing import Any

import click

from birdnetpi.system.path_resolver import PathResolver


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
        "-k",
        "_",
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
    """Compile .po files to .mo files.

    Uses msgfmt instead of pybabel compile to avoid overly strict
    format string checking that incorrectly flags Jinja2 template
    placeholders as Python format specifiers.
    """
    resolver = obj["resolver"]
    locales_dir = Path(resolver.get_locales_dir())

    # Find all locale directories
    compiled = 0
    errors = 0
    skipped = 0

    for locale_dir in sorted(locales_dir.iterdir()):
        if not locale_dir.is_dir():
            continue

        po_file = locale_dir / "LC_MESSAGES" / "messages.po"
        mo_file = locale_dir / "LC_MESSAGES" / "messages.mo"

        if not po_file.exists():
            continue

        locale = locale_dir.name

        # Check if header is marked as fuzzy (skip test locales like xx, yy)
        try:
            with open(po_file, encoding="utf-8") as f:
                # Read until first real msgid (after header)
                header_section = ""
                for line in f:
                    header_section += line
                    # Stop after we've seen the header msgstr block
                    if line.startswith('msgid "') and 'msgid ""' not in header_section[-50:]:
                        break
                if "#, fuzzy" in header_section:
                    click.echo(f"  {locale}: skipped (fuzzy header)")
                    skipped += 1
                    continue
        except OSError:
            pass

        # Use msgfmt for compilation (more lenient than pybabel)
        cmd = ["msgfmt", "--no-hash", "-o", str(mo_file), str(po_file)]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
            click.echo(click.style(f"  ✓ {locale}", fg="green"))
            compiled += 1
        except subprocess.CalledProcessError as e:
            click.echo(click.style(f"  ✗ {locale}: {e.stderr}", fg="red"), err=True)
            errors += 1

    click.echo()
    if errors == 0:
        click.echo(
            click.style(
                f"✓ Compiled {compiled} locales successfully ({skipped} skipped)",
                fg="green",
            )
        )
    else:
        click.echo(
            click.style(
                f"✗ Compiled {compiled} locales, {errors} failed, {skipped} skipped",
                fg="red",
            ),
            err=True,
        )
        sys.exit(1)


def _check_pot_freshness(src_dir: Path, babel_cfg: Path, messages_pot: Path) -> list[str]:
    """Check if POT file is up to date with source code.

    Returns a list of issues found.
    """
    import tempfile

    import polib

    issues: list[str] = []

    click.echo("Checking if POT file is up to date...")
    with tempfile.NamedTemporaryFile(suffix=".pot", delete=False) as tmp:
        tmp_pot = Path(tmp.name)

    try:
        extract_cmd = [
            "pybabel",
            "extract",
            "-F",
            str(babel_cfg),
            "-k",
            "lazy_gettext",
            "-k",
            "_",
            "-o",
            str(tmp_pot),
            str(src_dir),
        ]
        result = subprocess.run(extract_cmd, capture_output=True, text=True)
        if result.returncode != 0:
            click.echo(click.style(f"  ✗ Failed to extract: {result.stderr}", fg="red"))
            issues.append("POT extraction failed")
            return issues

        # Compare msgids
        current_pot = polib.pofile(str(messages_pot))
        new_pot = polib.pofile(str(tmp_pot))

        current_msgids = {e.msgid for e in current_pot if e.msgid}
        new_msgids = {e.msgid for e in new_pot if e.msgid}

        missing_from_pot = new_msgids - current_msgids
        removed_from_source = current_msgids - new_msgids

        if missing_from_pot:
            click.echo(
                click.style(
                    f"  ✗ POT missing {len(missing_from_pot)} strings from source:",
                    fg="red",
                )
            )
            for msgid in sorted(missing_from_pot)[:5]:
                click.echo(f"      - {msgid[:50]!r}...")
            if len(missing_from_pot) > 5:
                click.echo(f"      ... and {len(missing_from_pot) - 5} more")
            issues.append(f"POT missing {len(missing_from_pot)} strings")
        elif removed_from_source:
            click.echo(
                click.style(
                    f"  ⚠ POT has {len(removed_from_source)} obsolete strings",
                    fg="yellow",
                )
            )
        else:
            click.echo(click.style("  ✓ POT is up to date", fg="green"))
    finally:
        tmp_pot.unlink(missing_ok=True)

    return issues


def _check_locale(locale: str, po_file: Path, pot_msgids: set[str]) -> list[str]:
    """Check a single locale for completeness.

    Returns a list of issues found.
    """
    import polib

    issues: list[str] = []
    po = polib.pofile(str(po_file))

    # Check sync with POT
    po_msgids = {e.msgid for e in po if e.msgid and not e.obsolete}
    missing_from_po = pot_msgids - po_msgids

    # Check translations
    untranslated = [e for e in po if e.msgid and not e.obsolete and not e.msgstr]
    fuzzy = [e for e in po if e.msgid and not e.obsolete and "fuzzy" in e.flags]

    locale_issues = []

    if missing_from_po:
        locale_issues.append(f"{len(missing_from_po)} missing from PO")
        issues.append(f"{locale}: {len(missing_from_po)} strings not in PO file")

    if untranslated:
        locale_issues.append(f"{len(untranslated)} untranslated")
        issues.append(f"{locale}: {len(untranslated)} untranslated strings")

    if fuzzy:
        locale_issues.append(f"{len(fuzzy)} fuzzy")
        issues.append(f"{locale}: {len(fuzzy)} fuzzy strings")

    if locale_issues:
        click.echo(click.style(f"  ✗ {locale}: {', '.join(locale_issues)}", fg="red"))
        for entry in (untranslated + fuzzy)[:3]:
            click.echo(f"      - {entry.msgid[:50]!r}...")
    else:
        active = len([e for e in po if e.msgid and not e.obsolete])
        click.echo(click.style(f"  ✓ {locale}: {active} strings, 100% translated", fg="green"))

    return issues


@cli.command()
@click.option(
    "--warn-only",
    is_flag=True,
    help="Exit 0 even if issues found (for non-blocking CI)",
)
@click.option(
    "--skip",
    multiple=True,
    default=["en", "xx", "yy"],
    help="Locales to skip (default: en, xx, yy)",
)
@click.pass_obj
def check(obj: dict[str, Any], warn_only: bool, skip: tuple[str, ...]) -> None:
    """Check translation files for completeness.

    Verifies that:
    - POT file is up to date with source code
    - PO files are in sync with POT template
    - All strings are translated (no untranslated or fuzzy entries)

    Exits with error code 1 if any issues are found (unless --warn-only).
    """
    try:
        import polib
    except ImportError:
        click.echo(
            click.style(
                "✗ polib is required for check. Install with: uv pip install polib",
                fg="red",
            ),
            err=True,
        )
        sys.exit(1)

    resolver = obj["resolver"]
    src_dir = Path(resolver.get_src_dir())
    locales_dir = Path(resolver.get_locales_dir())
    messages_pot = Path(resolver.get_messages_pot_path())
    babel_cfg = Path(resolver.get_babel_config_path())

    issues: list[str] = []

    # Step 1: Check if POT is up to date
    issues.extend(_check_pot_freshness(src_dir, babel_cfg, messages_pot))

    # Step 2: Check each locale
    click.echo("\nChecking locale files...")
    pot = polib.pofile(str(messages_pot))
    pot_msgids = {e.msgid for e in pot if e.msgid}

    skip_locales = set(skip)

    for locale_dir in sorted(locales_dir.iterdir()):
        if not locale_dir.is_dir() or locale_dir.name in skip_locales:
            continue

        po_file = locale_dir / "LC_MESSAGES" / "messages.po"
        if not po_file.exists():
            continue

        issues.extend(_check_locale(locale_dir.name, po_file, pot_msgids))

    # Summary
    click.echo()
    if issues:
        click.echo(click.style(f"Found {len(issues)} issue(s):", fg="red", bold=True))
        for issue in issues:
            click.echo(f"  - {issue}")
        if not warn_only:
            sys.exit(1)
    else:
        click.echo(
            click.style(
                "✓ All translation files are complete and up to date",
                fg="green",
                bold=True,
            )
        )


@cli.command()
@click.argument("language")
@click.pass_obj
def init(obj: dict[str, Any], language: str) -> None:
    """Initialize a new language.

    LANGUAGE: Language code (e.g., 'it', 'pt', 'zh')
    """
    resolver = obj["resolver"]

    # Get paths relative to src directory parent (repo root)
    src_dir_parent = resolver.get_src_dir().parent
    messages_pot = resolver.get_messages_pot_path().relative_to(src_dir_parent)
    locales_dir = resolver.get_locales_dir().relative_to(src_dir_parent)

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


@cli.command()
@click.argument("language")
@click.argument("input_file", type=click.Path(exists=True))
@click.option(
    "--compile/--no-compile",
    "compile_mo",
    default=True,
    help="Compile to .mo after merging (default: True)",
)
@click.pass_obj
def merge(obj: dict[str, Any], language: str, input_file: str, compile_mo: bool) -> None:
    """Merge external translations into existing PO file.

    Integrates translations from an external PO file while preserving
    all source references (comments) from the existing file.

    LANGUAGE: Target language code (e.g., 'es', 'de', 'fr')

    INPUT_FILE: Path to the PO file containing translations to merge
    """
    try:
        import polib
    except ImportError:
        click.echo(
            click.style(
                "✗ polib is required for merge. Install with: uv pip install polib",
                fg="red",
            ),
            err=True,
        )
        sys.exit(1)

    resolver = obj["resolver"]
    locales_dir = Path(resolver.get_locales_dir())
    po_path = locales_dir / language / "LC_MESSAGES" / "messages.po"

    # Check if target PO file exists
    if not po_path.exists():
        click.echo(
            click.style(
                f"✗ Target PO file not found: {po_path}\n"
                f"  Run 'manage-translations init {language}' first.",
                fg="red",
            ),
            err=True,
        )
        sys.exit(1)

    click.echo(f"Merging translations into {language}...")

    # Load files
    target_po = polib.pofile(str(po_path))
    source_po = polib.pofile(input_file)

    # Build lookup of source translations
    source_translations = {entry.msgid: entry.msgstr for entry in source_po if entry.msgstr}

    # Merge translations
    updated = 0
    for entry in target_po:
        if source_translations.get(entry.msgid):
            new_msgstr = source_translations[entry.msgid]
            if entry.msgstr != new_msgstr:
                entry.msgstr = new_msgstr
                # Remove fuzzy flag when translation is updated
                if "fuzzy" in entry.flags:
                    entry.flags.remove("fuzzy")
                updated += 1

    # Save the merged file
    target_po.save()
    click.echo(click.style(f"✓ Updated {updated} translations", fg="green"))

    # Remove duplicates using msguniq
    click.echo("Removing duplicate entries...")
    msguniq_cmd = ["msguniq", str(po_path), "-o", str(po_path)]
    try:
        subprocess.run(msguniq_cmd, check=True, capture_output=True, text=True)
        click.echo(click.style("✓ Duplicates removed", fg="green"))
    except subprocess.CalledProcessError as e:
        click.echo(
            click.style(f"Warning: msguniq failed: {e.stderr}", fg="yellow"),
            err=True,
        )

    # Compile if requested
    if compile_mo:
        mo_path = po_path.with_suffix(".mo")
        click.echo("Compiling to .mo file...")
        msgfmt_cmd = ["msgfmt", "--no-hash", "-o", str(mo_path), str(po_path)]
        try:
            subprocess.run(msgfmt_cmd, check=True, capture_output=True, text=True)
            click.echo(click.style(f"✓ Compiled to {mo_path}", fg="green"))
        except subprocess.CalledProcessError as e:
            click.echo(
                click.style(f"✗ Compilation failed: {e.stderr}", fg="red"),
                err=True,
            )
            sys.exit(1)

    click.echo(
        click.style(
            f"✓ Merge completed successfully for '{language}'",
            fg="green",
            bold=True,
        )
    )


def _transform_string(text: str, reverse: bool, brackets: bool) -> str:
    """Transform a string for the fake locale.

    - Preserves %(name)s style placeholders
    - Preserves HTML entities like &nbsp; &times;
    - Reverses the text (optional)
    - Adds brackets (optional)
    """
    if not text:
        return text

    # Find all placeholders and HTML entities to preserve
    placeholder_pattern = r"%\([^)]+\)s|%\([^)]+\)d|&[a-zA-Z]+;|&#?[0-9a-fA-F]+;"
    placeholders: list[str] = []

    def save_placeholder(match: Match[str]) -> str:
        idx = len(placeholders)
        placeholders.append(match.group(0))
        return f"__PLACEHOLDER_{idx}__"

    # Replace placeholders with markers
    text_with_markers = re.sub(placeholder_pattern, save_placeholder, text)

    # Transform the text
    if reverse:
        text_with_markers = _reverse_text_with_placeholders(text_with_markers)

    # Restore placeholders
    for idx, placeholder in enumerate(placeholders):
        text_with_markers = text_with_markers.replace(f"__PLACEHOLDER_{idx}__", placeholder)

    # Add brackets
    if brackets:
        text_with_markers = f"[[{text_with_markers}]]"

    return text_with_markers


def _reverse_text_with_placeholders(text: str) -> str:
    """Reverse text while preserving placeholder markers."""
    parts = text.split("__PLACEHOLDER_")
    reversed_parts = []

    for i, part in enumerate(parts):
        if i == 0:
            # First part is always text
            reversed_parts.append(part[::-1])
        elif "__" in part:
            # This contains a marker number and possibly text after
            marker_end = part.index("__") + 2
            marker = part[:marker_end]
            remaining = part[marker_end:]
            reversed_parts.append(f"__PLACEHOLDER_{marker}{remaining[::-1]}")
        else:
            reversed_parts.append(part[::-1])

    return "".join(reversed_parts)


def _process_pot_file(pot_content: str, reverse: bool, brackets: bool) -> list[str]:
    """Process POT file content to create PO file lines."""
    po_lines = []
    in_msgid = False
    current_msgid = []

    for line in pot_content.split("\n"):
        if line.startswith('msgid "'):
            in_msgid = True
            current_msgid = [line[7:-1]]  # Remove 'msgid "' and trailing '"'
            po_lines.append(line)
        elif line.startswith('msgstr "'):
            in_msgid = False
            # Get the complete msgid
            msgid_text = "".join(current_msgid)
            # Transform it
            if msgid_text:  # Don't transform empty strings
                transformed = _transform_string(msgid_text, reverse, brackets)
                po_lines.append(f'msgstr "{transformed}"')
            else:
                po_lines.append(line)
            current_msgid = []
        elif line.startswith('"') and in_msgid:
            # Continuation of msgid
            current_msgid.append(line[1:-1])  # Remove quotes
            po_lines.append(line)
        elif line.startswith("#") or line == "" or line.startswith("msgid_plural"):
            # Pass through comments and other metadata
            in_msgid = False
            po_lines.append(line)
        else:
            po_lines.append(line)

    return po_lines


@cli.command("fake-locale")
@click.option(
    "--locale",
    default="xx",
    help="Locale code for the fake language (default: xx)",
)
@click.option(
    "--reverse/--no-reverse",
    default=True,
    help="Reverse the strings (default: True)",
)
@click.option(
    "--brackets/--no-brackets",
    default=True,
    help="Add brackets around strings (default: True)",
)
@click.pass_obj
def fake_locale(obj: dict[str, Any], locale: str, reverse: bool, brackets: bool) -> None:
    """Generate a fake locale for testing untranslated strings.

    This creates a pseudo-locale that transforms all translatable strings
    to make untranslated strings immediately visible in the UI.

    Features:
    - Reverses string characters (keeps placeholders intact)
    - Adds brackets [[ ]] to mark translated strings
    - Preserves %(variable)s placeholders
    - Preserves HTML entities like &nbsp;
    """
    resolver = obj["resolver"]

    # Get paths
    messages_pot = Path(resolver.get_messages_pot_path())
    locales_dir = Path(resolver.get_locales_dir())
    locale_dir = locales_dir / locale / "LC_MESSAGES"
    po_file = locale_dir / "messages.po"

    # Create locale directory if it doesn't exist
    locale_dir.mkdir(parents=True, exist_ok=True)

    # Check if POT file exists
    if not messages_pot.exists():
        click.echo(
            click.style(
                "✗ messages.pot not found. Run 'extract' first.",
                fg="red",
            ),
            err=True,
        )
        sys.exit(1)

    click.echo(f"Creating fake locale '{locale}'...")

    # Read the POT file
    with open(messages_pot, encoding="utf-8") as f:
        pot_content = f.read()

    # Process the POT file using helper functions
    po_lines = _process_pot_file(pot_content, reverse, brackets)

    # Write the PO file
    with open(po_file, "w", encoding="utf-8") as f:
        f.write("\n".join(po_lines))

    click.echo(click.style(f"✓ Created {po_file}", fg="green"))

    # Compile the PO file to MO
    mo_file = locale_dir / "messages.mo"
    cmd = [
        "uv",
        "run",
        "msgfmt",
        "-o",
        str(mo_file),
        str(po_file),
    ]

    success = run_command(cmd, f"Compiling fake locale {locale}")
    if success:
        click.echo(click.style(f"✓ Fake locale '{locale}' created successfully", fg="green"))
        click.echo()
        click.echo("To use this locale:")
        click.echo(f"  1. Set environment variable: export LANGUAGE={locale}")
        click.echo(f"  2. Or add 'Accept-Language: {locale}' header in browser")
        click.echo()
        click.echo("Features:")
        if reverse:
            click.echo("  • Strings are reversed (but placeholders preserved)")
        if brackets:
            click.echo("  • Strings are wrapped in [[ ]]")
        click.echo("  • Untranslated strings will appear normal")
        click.echo("  • Translated strings will be visibly transformed")
    else:
        click.echo(click.style("✗ Failed to compile fake locale", fg="red"), err=True)
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
