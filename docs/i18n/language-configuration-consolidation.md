# Language Configuration

## Overview

BirdNET-Pi uses a single unified `language` field in the `birdnetpi.yaml` configuration file. This provides a consistent interface for both UI translations and species name translations.

## Configuration

The language is controlled by a single field:
- `language`: Language code for both UI and species translations (default: "en")

## Usage

Edit your `birdnetpi.yaml` file:
```yaml
# Set language for UI and species names
language: en  # or es, fr, de, etc.
```

## Supported Languages

The `language` field accepts standard ISO 639-1 language codes:
- `en` - English (default)
- `es` - Spanish
- `fr` - French
- `de` - German
- `pt` - Portuguese
- `nl` - Dutch
- `it` - Italian
- `pl` - Polish
- `ru` - Russian
- `ja` - Japanese
- `zh` - Chinese

Note: Not all languages have complete translations. English fallback is used for missing translations.

## How It Works

### UI Translations
The `language` field controls:
- Web interface text (buttons, labels, messages)
- System notifications
- Report generation

UI translations use the gettext/Babel system with `.po` and `.mo` files in the `locales/` directory.

### Species Name Translations
The `language` field also controls:
- Common bird names in the specified language
- Database lookups across IOC, Avibase, and PatLevin databases
- API responses and detection displays

Species translations use the MultilingualDatabaseService with the precedence order:
1. IOC World Bird List
2. PatLevin BirdNET labels
3. Avibase

## Configuration Examples

### Basic Configuration
```yaml
# Localization
language: en  # English interface and species names
timezone: UTC
```

### Spanish Configuration
```yaml
# Localización
language: es  # Interfaz y nombres de especies en español
timezone: Europe/Madrid
```

### French Configuration
```yaml
# Localisation
language: fr  # Interface et noms d'espèces en français
timezone: Europe/Paris
```

## API Usage

When using the API, the language configuration is automatically applied:

```python
# The configured language is used automatically
config = BirdNETConfig(language="es")

# Services use the configured language
species_database.get_best_common_name(
    session,
    "Turdus merula",
    config.language  # Uses "es" from config
)
```

## Troubleshooting

### Configuration Not Taking Effect
1. Restart the web server after changing configuration
2. Clear browser cache if UI translations don't appear
3. Verify the language code is valid (ISO 639-1)

### Missing Translations
- UI translations: Check if `.mo` files exist in `locales/<language>/LC_MESSAGES/`
- Species names: Verify database files are present and accessible
- Fall back to English occurs automatically for missing translations

### Migration Issues
If the migration script fails:
1. Check the backup file (`.yaml.bak`) was created
2. Manually edit the configuration as shown above
3. Validate YAML syntax using an online validator

## Development

### Adding New Language Support
1. Create locale directory: `locales/<language_code>/LC_MESSAGES/`
2. Extract translatable strings: `pybabel extract -F babel.cfg -o locales/messages.pot .`
3. Create language catalog: `pybabel init -i locales/messages.pot -d locales -l <language_code>`
4. Translate strings in the `.po` file
5. Compile translations: `pybabel compile -d locales`

### Testing Language Configuration
```python
# Test configuration loading
parser = ConfigFileParser()
config = parser.load_config()
assert config.language == "expected_language"

# Test backward compatibility
old_config = {"database_lang": "fr"}
# Should load as language="fr"
```

## Related Documentation
- [Internationalization Overview](./README.md)
- [Species Translation System](./species-translation.md)
- [UI Translation Guide](./ui-translations.md)
