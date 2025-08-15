# BirdNET-Pi Internationalization (i18n) Locales

This directory contains translation files for the BirdNET-Pi web interface using the gettext/Babel translation system.

## Directory Structure

```
locales/
├── messages.pot       # Translation template (auto-generated)
├── en/                # English (base language)
│   └── LC_MESSAGES/
│       ├── messages.po    # Translation source file
│       └── messages.mo    # Compiled translation file
├── es/                # Spanish
│   └── LC_MESSAGES/
│       ├── messages.po
│       └── messages.mo
├── fr/                # French
│   └── LC_MESSAGES/
│       ├── messages.po
│       └── messages.mo
└── de/                # German
    └── LC_MESSAGES/
        ├── messages.po
        └── messages.mo
```

Note: The `babel.cfg` configuration file is located in the project root.

## Supported Languages

- **en**: English (base language)
- **es**: Spanish (Español)
- **fr**: French (Français)
- **de**: German (Deutsch)

## Translation Workflow

BirdNET-Pi provides a `manage-translations` command to handle all translation operations.

### Quick Start

```bash
# Extract, update, and compile all translations at once
uv run manage-translations all
```

### Individual Operations

#### 1. Extract Translatable Strings

Extract all translatable strings from Python source files and Jinja2 templates:

```bash
uv run manage-translations extract
```

This creates/updates the `messages.pot` template file with all translatable strings found in the codebase.

#### 2. Initialize New Language

To add support for a new language (e.g., Italian 'it'):

```bash
uv run manage-translations init --language it
```

This creates a new language directory with the appropriate `.po` file.

#### 3. Update Existing Translations

When new translatable strings are added to the code:

```bash
# Update all existing .po files with new strings from the template
uv run manage-translations update
```

This synchronizes all language `.po` files with the latest `messages.pot` template.

#### 4. Translate Strings

Edit the `.po` files in each language directory to provide translations:

```po
# Example entry in locales/es/LC_MESSAGES/messages.po
msgid "Hello World"
msgstr "Hola Mundo"  # Spanish translation
```

#### 5. Compile Translations

Compile `.po` files to binary `.mo` files for use by the application:

```bash
uv run manage-translations compile
```

### Complete Workflow Example

```bash
# 1. Make code changes with new translatable strings
# 2. Extract new strings and update all languages
uv run manage-translations all

# 3. Edit .po files to add translations
# 4. Compile the translations
uv run manage-translations compile
```

## Code Integration

### Python Code

Use gettext functions for translatable strings:

```python
from birdnetpi.managers.translation_manager import _

# Simple translation
message = _("Hello World")

# Pluralization
from birdnetpi.managers.translation_manager import ngettext
message = ngettext("%(count)d bird detected", "%(count)d birds detected", count)
```

### Jinja2 Templates

Use the `_()` function in templates:

```html
<h1>{{ _("Welcome to BirdNET-Pi") }}</h1>
<p>{{ ngettext("%(count)d detection", "%(count)d detections", count) }}</p>
```

## Translation Guidelines

1. **Context**: Provide context for translators when terms might be ambiguous
2. **Pluralization**: Use `ngettext()` for strings that change based on quantity
3. **Formatting**: Use named placeholders for variable substitution: `%(name)s`
4. **Length**: Keep translations concise to fit UI layouts
5. **Consistency**: Use consistent terminology across the application

## File Formats

- **`.pot`**: Template file containing all extractable strings (generated)
- **`.po`**: Translation source files (human-readable, editable)
- **`.mo`**: Compiled binary translation files (generated from `.po` files)

## Project Metadata

Translation files are automatically generated with the following metadata:
- **Project**: BirdNET-Pi 2.0.0
- **Copyright**: BirdNET-Pi Contributors
- **Bug Reports**: https://github.com/mverteuil/BirdNET-Pi/issues

## Dependencies

- **Babel**: Python internationalization library for extraction and compilation (babel>=2.14.0)
- **gettext**: Standard GNU translation system used by Python

## Notes

- English is the base language and does not require translation
- The translation system is integrated with FastAPI middleware for automatic language detection
- Languages are detected from the browser's `Accept-Language` header
- Fallback to English occurs when requested language is not available
- The `manage-translations` command automatically sets the correct paths using PathResolver
