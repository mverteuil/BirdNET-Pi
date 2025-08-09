# BirdNET-Pi Internationalization (i18n) Locales

This directory contains translation files for the BirdNET-Pi web interface using the gettext/Babel translation system.

## Directory Structure

```
locales/
├── babel.cfg          # Babel extraction configuration (in project root)
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

## Supported Languages

- **en**: English (base language)
- **es**: Spanish (Español)
- **fr**: French (Français)
- **de**: German (Deutsch)

## Translation Workflow

### 1. Extract Translatable Strings

Extract all translatable strings from Python source files and Jinja2 templates:

```bash
# From project root
pybabel extract -F babel.cfg -k lazy_gettext -o locales/messages.pot src/
```

### 2. Initialize New Language

To add support for a new language (e.g., Italian 'it'):

```bash
pybabel init -i locales/messages.pot -d locales -l it
```

### 3. Update Existing Translations

When new translatable strings are added to the code:

```bash
# Update .pot template
pybabel extract -F babel.cfg -k lazy_gettext -o locales/messages.pot src/

# Update all existing .po files
pybabel update -i locales/messages.pot -d locales
```

### 4. Translate Strings

Edit the `.po` files in each language directory to provide translations:

```po
# Example entry in messages.po
msgid "Hello World"
msgstr "Hola Mundo"  # Spanish translation
```

### 5. Compile Translations

Compile `.po` files to binary `.mo` files for use by the application:

```bash
pybabel compile -d locales
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

## Dependencies

- **Babel**: Python internationalization library for extraction and compilation
- **gettext**: Standard GNU translation system used by Python

## Notes

- English is the base language and does not require translation
- The translation system is integrated with FastAPI middleware for automatic language detection
- Languages are detected from the browser's `Accept-Language` header
- Fallback to English occurs when requested language is not available