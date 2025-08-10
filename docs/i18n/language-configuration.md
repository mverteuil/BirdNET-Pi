# Language Configuration Guide

## Overview

BirdNET-Pi provides multilingual support for bird species names through an intelligent translation system. This guide explains how to configure languages, understand coverage by different databases, and troubleshoot common issues.

## Quick Start

### Setting Your Language

1. **Web Interface**: Navigate to Settings → Localization and enter your preferred language code in the "Language" field
2. **Default Language**: English (`en`) is used by default if no language is configured
3. **Language Codes**: Use standard ISO language codes (e.g., `es`, `fr`, `de`, `zh`)

### Example Configuration

In the web interface settings form:
```
Language: es
Timezone: Europe/Madrid
```

This configures Spanish (`es`) as the display language for bird species names.

## Supported Language Codes

The translation system supports a wide variety of languages, with coverage varying by database source:

### Common Language Codes

| Code | Language | IOC Coverage | PatLevin Coverage | Avibase Coverage |
|------|----------|--------------|-------------------|------------------|
| `en` | English | ✓ Full | ✓ Full | ✓ Full |
| `es` | Spanish | ✓ Full | ✓ Partial | ✓ Full |
| `fr` | French | ✓ Full | ✓ Partial | ✓ Full |
| `de` | German | ✓ Full | ✓ Partial | ✓ Full |
| `it` | Italian | ✓ Full | ✓ Limited | ✓ Full |
| `pt` | Portuguese | ✓ Full | ✓ Limited | ✓ Full |
| `nl` | Dutch | ✓ Full | ✓ Limited | ✓ Full |
| `sv` | Swedish | ✓ Full | ✓ Limited | ✓ Full |
| `da` | Danish | ✓ Full | ✓ Limited | ✓ Full |
| `no` | Norwegian | ✓ Full | ✓ Limited | ✓ Full |
| `fi` | Finnish | ✓ Full | ✓ Limited | ✓ Full |
| `ru` | Russian | ✓ Partial | ✗ None | ✓ Full |
| `ja` | Japanese | ✓ Partial | ✗ None | ✓ Full |
| `zh` | Chinese | ✓ Partial | ✗ None | ✓ Full |

### Regional Variants

The system accepts regional language codes but treats them as their base language:
- `en-US`, `en-GB`, `en-AU` → `en`
- `es-ES`, `es-MX`, `es-AR` → `es`
- `fr-FR`, `fr-CA`, `fr-CH` → `fr`
- `pt-BR`, `pt-PT` → `pt`

## Database Coverage Details

### IOC World Bird List
- **Strengths**: Authoritative taxonomic standard, complete English coverage, extensive European language support
- **Coverage**: All species have English names, most species have translations for major European languages
- **Best For**: Scientific accuracy, European languages

### PatLevin BirdNET Labels
- **Strengths**: Optimized for BirdNET detection labels, community-contributed translations
- **Coverage**: Primary support for English, German, Spanish, French; limited coverage for other languages
- **Best For**: BirdNET-specific terminology, common detection species

### Avibase (Lepage 2018)
- **Strengths**: Comprehensive multilingual coverage, global language support
- **Coverage**: Extensive coverage across 100+ languages including Asian, African, and indigenous languages
- **Best For**: Rare languages, global coverage, comprehensive translation fallbacks

## How Translation Precedence Works

When you request a bird name in your configured language, the system checks databases in this order:

1. **IOC World Bird List** (highest priority)
   - Most authoritative and scientifically accurate
   - Used when available for your language

2. **PatLevin BirdNET Labels** (medium priority)
   - BirdNET-specific translations
   - Used when IOC doesn't have your language

3. **Avibase** (fallback)
   - Comprehensive multilingual coverage
   - Used when neither IOC nor PatLevin have your language

### Example Translation Flow

For `Turdus migratorius` in Spanish (`es`):
1. Check IOC → Found: "Petirrojo Americano" ✓ (Return this)
2. ~~Check PatLevin~~ (skipped because IOC found)
3. ~~Check Avibase~~ (skipped because IOC found)

For `Turdus migratorius` in Hindi (`hi`):
1. Check IOC → Not found
2. Check PatLevin → Not found
3. Check Avibase → Found: "अमेरिकी रॉबिन" ✓ (Return this)

## UI Translation vs Species Translation

BirdNET-Pi separates two types of translation:

### UI Translation
- **What**: Interface elements, buttons, menus, messages
- **Configuration**: Set via the "Language" field in Settings
- **Scope**: Web interface, admin panels, system messages

### Species Name Translation
- **What**: Bird species names (common names)
- **Configuration**: Uses the same language code but applies to species names
- **Scope**: Detection results, species lists, reports

Both systems use the same language code, providing a consistent multilingual experience.

## Configuration Examples

### European Languages

```
# German Setup
Language: de
Expected Results:
- UI in German
- Species names like "Amsel" instead of "Blackbird"
- Sources: Primarily IOC, PatLevin fallback

# French Setup
Language: fr
Expected Results:
- UI in French
- Species names like "Merle noir" instead of "Blackbird"
- Sources: Primarily IOC, PatLevin fallback
```

### Asian Languages

```
# Japanese Setup
Language: ja
Expected Results:
- UI in Japanese (if UI translations available)
- Species names like "クロウタドリ" instead of "Blackbird"
- Sources: Primarily Avibase (IOC limited for Japanese)

# Chinese Setup
Language: zh
Expected Results:
- UI in Chinese (if UI translations available)
- Species names like "黑鸫" instead of "Blackbird"
- Sources: Primarily Avibase (IOC limited for Chinese)
```

## Advanced Configuration

### Custom Language Priorities

While the database precedence is fixed (IOC → PatLevin → Avibase), you can influence results by:

1. **Regional Codes**: Use specific regional codes that might have different coverage
2. **Language Fallbacks**: The system gracefully falls back to English if no translation exists

### Multiple Language Support

For environments serving multiple languages:
- Configure the primary language in settings
- Use the web API to request specific languages per request
- Species data includes source attribution for transparency

## Troubleshooting

### Common Issues

#### Species Names Still in English
**Problem**: Configured non-English language but seeing English names
**Solutions**:
1. Verify language code is correct (use `es` not `spanish`)
2. Check if your language has coverage for the detected species
3. Some rare species may only have English names available
4. Restart the service after changing language settings

#### Mixed Language Results
**Problem**: Some species in target language, others in English
**Expected Behavior**: This is normal - coverage varies by species and database
**Information**: Check attribution to see which database provided each name

#### Language Code Not Working
**Problem**: Invalid or unsupported language code
**Solutions**:
1. Use standard ISO language codes (`fr`, not `french`)
2. Check the supported languages table above
3. Try the base language code instead of regional variants (`es` instead of `es-MX`)

#### Database Attribution Missing
**Problem**: Need to know which database provided a translation
**Solution**: Use the "get all translations" feature to see all sources and attributions

### Diagnostic Steps

1. **Verify Configuration**:
   ```
   Check Settings → Localization → Language field
   Expected: Valid ISO language code (e.g., 'es', 'fr', 'de')
   ```

2. **Test with Common Species**:
   - Try well-known species like "Turdus migratorius" (American Robin)
   - These should have translations in most databases

3. **Check Database Availability**:
   - Ensure all translation databases are properly installed
   - Look for database files in the system data directory
   - Check system logs for database connection errors

4. **Language Coverage Verification**:
   - Refer to the coverage table above
   - Try a language with known full coverage (like `es` or `fr`)
   - Compare results across different species

### Getting Help

When reporting translation issues, include:
- Configured language code
- Specific species scientific name
- Expected vs actual common name
- System language configuration
- Which databases are available in your installation

### Database Maintenance

Translation databases are updated periodically:
- **IOC**: Updated with each official IOC World Bird List release
- **PatLevin**: Community contributions, updated as available
- **Avibase**: Based on 2018 snapshot, static content

Check for system updates to get the latest translation database versions.

## Best Practices

### For Administrators
1. **Standard Codes**: Always use standard ISO language codes
2. **Documentation**: Document your language choice for other users
3. **Testing**: Test with multiple species to verify translation coverage
4. **Updates**: Keep translation databases updated for best coverage

### For Users
1. **Fallback Awareness**: Understand that not all species have translations
2. **Source Checking**: Pay attention to attribution information
3. **Regional Adaptation**: Choose the most appropriate regional variant for your use case
4. **Feedback**: Report missing or incorrect translations to help improve coverage

### For Developers
1. **API Usage**: Use the translation API to support multiple languages programmatically
2. **Caching**: Consider caching translation results for performance
3. **Error Handling**: Handle missing translations gracefully
4. **Attribution**: Always display database attribution when required
