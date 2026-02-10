# Language Configuration Guide

## Overview

BirdNET-Pi provides multilingual support for bird species names through an intelligent translation system. This guide explains how to configure languages, understand coverage by different databases, and troubleshoot common issues.

## Quick Start

### Setting Your Language

**Configuration File** (`birdnetpi.yaml`):
```yaml
# Set language for UI and species names
language: en  # or es, fr, de, etc.
```

**Web Interface**: Navigate to Settings → Localization and enter your preferred language code

### Common Setup Examples

**German Configuration**:
```yaml
language: de
timezone: Europe/Berlin
```

**Spanish Configuration**:
```yaml
language: es
timezone: Europe/Madrid
```

**Default**: English (`en`) is used by default if no language is configured

## Supported Language Codes

The translation system supports 44 languages in IOC and 57 in Wikidata, with coverage varying by source.

### Full Coverage Languages (10,000+ species in IOC)

| Code | Language | IOC | Wikidata |
|------|----------|-----|----------|
| `en` | English | ✓ 10,983 | ✓ 8,138 |
| `zh` | Chinese | ✓ 10,983 | ✓ 4,935 |
| `nl` | Dutch | ✓ 10,983 | ✓ 8,389 |
| `fr` | French | ✓ 10,983 | ✓ 6,893 |
| `sk` | Slovak | ✓ 10,983 | ✓ 8,471 |
| `sv` | Swedish | ✓ 10,983 | ✓ 8,972 |
| `pt` | Portuguese | ✓ 10,981 | ✓ 4,641 |
| `no` | Norwegian | ✓ 10,974 | — |
| `da` | Danish | ✓ 10,937 | ✓ 8,213 |
| `pl` | Polish | ✓ 10,921 | ✓ 8,521 |
| `es` | Spanish | ✓ 10,823 | ✓ 1,871 |
| `de` | German | ✓ 10,785 | ✓ 4,244 |
| `uk` | Ukrainian | ✓ 10,754 | ✓ 1,175 |
| `hr` | Croatian | ✓ 10,605 | ✓ 799 |
| `tr` | Turkish | ✓ 10,570 | ✓ 1,160 |
| `ru` | Russian | ✓ 10,567 | ✓ 3,231 |
| `ja` | Japanese | ✓ 10,537 | ✓ 8,046 |
| `cs` | Czech | ✓ 10,159 | ✓ 8,017 |
| `ca` | Catalan | ✓ 10,065 | ✓ 6,828 |
| `fi` | Finnish | ✓ 10,033 | ✓ 7,990 |
| `it` | Italian | ✓ 10,006 | ✓ 670 |

### Good Coverage Languages (5,000-10,000 species)

| Code | Language | IOC | Wikidata |
|------|----------|-----|----------|
| `lt` | Lithuanian | ✓ 9,846 | ✓ 2,235 |
| `sr` | Serbian | ✓ 8,029 | ✓ 778 |
| `hu` | Hungarian | ✓ 6,488 | ✓ 5,980 |
| `et` | Estonian | ✓ 5,620 | ✓ 4,946 |
| `nb` | Norwegian Bokmål | — | ✓ 8,570 |
| `fa` | Persian | ✓ 548 | ✓ 6,763 |
| `he` | Hebrew | ✓ 1,145 | ✓ 5,475 |

### Partial Coverage Languages (1,000-5,000 species)

| Code | Language | IOC | Wikidata |
|------|----------|-----|----------|
| `lv` | Latvian | ✓ 2,017 | ✓ 1,829 |
| `id` | Indonesian | ✓ 1,560 | ✓ 2,232 |
| `bg` | Bulgarian | ✓ 1,416 | ✓ 2,882 |
| `sl` | Slovenian | ✓ 1,107 | ✓ 526 |
| `ar` | Arabic | ✓ 583 | ✓ 2,853 |
| `eu` | Basque | — | ✓ 2,162 |
| `vi` | Vietnamese | — | ✓ 1,627 |
| `nn` | Norwegian Nynorsk | — | ✓ 1,309 |
| `ta` | Tamil | — | ✓ 1,253 |

### Limited Coverage Languages (<1,000 species)

| Code | Language | IOC | Wikidata |
|------|----------|-----|----------|
| `th` | Thai | ✓ 999 | ✓ 402 |
| `af` | Afrikaans | ✓ 968 | ✓ 897 |
| `is` | Icelandic | ✓ 968 | ✓ 524 |
| `se` | Northern Sami | ✓ 950 | — |
| `ko` | Korean | ✓ 562 | ✓ 795 |
| `ml` | Malayalam | ✓ 538 | ✓ 689 |
| `el` | Greek | ✓ 512 | ✓ 364 |
| `ro` | Romanian | ✓ 412 | ✓ 385 |
| `mk` | Macedonian | ✓ 388 | — |
| `be` | Belarusian | ✓ 325 | — |
| `ms` | Malay | — | ✓ 943 |
| `gl` | Galician | — | ✓ 696 |
| `bn` | Bengali | — | ✓ 605 |
| `hi` | Hindi | — | ✓ 233 |

### Regional Variants

The system accepts regional language codes but treats them as their base language:
- `en-US`, `en-GB`, `en-AU` → `en`
- `es-ES`, `es-MX`, `es-AR` → `es`
- `fr-FR`, `fr-CA`, `fr-CH` → `fr`
- `pt-BR`, `pt-PT` → `pt`

## Database Coverage Details

### IOC World Bird List
- **Languages**: 44 languages with translations
- **Strengths**: Authoritative taxonomic standard, complete English coverage, extensive European language support
- **Coverage**: All ~11,000 species have English names; 21 languages have full coverage (10,000+ species)
- **Best For**: Scientific accuracy, European languages, authoritative common names

### Wikidata
- **Languages**: 57 languages with translations
- **Strengths**: Community-maintained, includes images and conservation status, broader language variety
- **Coverage**: Top languages have 8,000-9,000 species; includes Asian, African, and indigenous languages not in IOC
- **Best For**: Languages not covered by IOC, supplementary species data, images

## How Translation Precedence Works

When you request a bird name in your configured language, the system checks databases in this order:

1. **IOC World Bird List** (highest priority)
   - Most authoritative and scientifically accurate
   - Used when available for your language

2. **Wikidata** (fallback)
   - Comprehensive multilingual coverage
   - Used when IOC doesn't have your language

### Example Translation Flow

For `Turdus migratorius` in Spanish (`es`):
1. Check IOC → Found: "Mirlo Primavera" ✓ (Return this)
2. ~~Check Wikidata~~ (skipped because IOC found)

For `Turdus migratorius` in Hindi (`hi`):
1. Check IOC → Not found
2. Check Wikidata → Found: "अमेरिकी रॉबिन" ✓ (Return this)

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

**German Setup**:
```yaml
language: de
```
Expected results:
- UI in German
- Species names like "Amsel" instead of "Blackbird"
- Sources: Primarily IOC, Wikidata fallback

**French Setup**:
```yaml
language: fr
```
Expected results:
- UI in French
- Species names like "Merle noir" instead of "Blackbird"
- Sources: Primarily IOC, Wikidata fallback

### Asian Languages

**Japanese Setup**:
```yaml
language: ja
```
Expected results:
- UI in Japanese (if UI translations available)
- Species names like "クロウタドリ" instead of "Blackbird"
- Sources: IOC when available, Wikidata fallback

**Chinese Setup**:
```yaml
language: zh
```
Expected results:
- UI in Chinese (if UI translations available)
- Species names like "黑鸫" instead of "Blackbird"
- Sources: IOC when available, Wikidata fallback

## Advanced Configuration

### Custom Language Priorities

While the database precedence is fixed (IOC → Wikidata), you can influence results by:

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
- **Wikidata**: Community-maintained, updated regularly with system releases

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
