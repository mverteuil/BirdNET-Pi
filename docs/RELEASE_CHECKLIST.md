# BirdNET-Pi Release Checklist

This document outlines the steps required to prepare and publish a new release of BirdNET-Pi.

## Pre-Release Verification

- [ ] All CI checks passing on main branch
- [ ] Test coverage meets threshold (≥77%)
- [ ] No outstanding critical/blocking issues

```bash
# Verify CI status
gh run list --branch main --limit 3

# Check for blocking issues
gh issue list --label "blocking"
gh issue list --label "critical"
```

## Version Updates

Update version numbers in the following files:

| File | Location | Example |
|------|----------|---------|
| `pyproject.toml` | Line ~35 | `version = "X.Y.Z"` |
| `src/birdnetpi/config/manager.py` | Line ~19 | `CURRENT_VERSION = "X.Y.Z"` |
| `src/birdnetpi/cli/manage_translations.py` | Line ~74 | `--version=X.Y.Z` |

## Translations

Run the translation workflow to ensure all strings are extracted and compiled:

```bash
# Extract translatable strings from source
uv run manage-translations extract

# Update PO files with new strings
uv run manage-translations update

# Verify all locales are complete
uv run manage-translations check

# Compile PO files to MO
uv run manage-translations compile
```

### Expected Output
- All production locales (af, de, es, fr) should be 100% translated
- Test locales (xx, yy) are skipped (fuzzy header)
- en locale is skipped (source language)

## Testing

### Full Test Suite
```bash
uv run pytest --cov=src --cov-fail-under=77 -m "not expensive and not ci_issue" --blocking-threshold=10.0
```

### Expensive Tests (Optional)
```bash
uv run pytest -m "expensive"
```

### Docker Verification
```bash
# Build images
docker compose build --parallel

# Verify containers start (optional)
docker compose up -d
docker compose ps
docker compose down
```

## Create Release

### Commit Changes
```bash
# Stage all release-related changes
git add pyproject.toml src/birdnetpi/config/manager.py src/birdnetpi/cli/manage_translations.py
git add locales/

# Create release commit
git commit -m "release: vX.Y.Z"
```

### Tag and Push
```bash
# Create annotated tag
git tag -a vX.Y.Z -m "Release vX.Y.Z"

# Push commit and tags
git push && git push --tags
```

### GitHub Release
```bash
# Create GitHub release (interactive)
gh release create vX.Y.Z --generate-notes

# Or with custom notes
gh release create vX.Y.Z --title "vX.Y.Z" --notes "Release notes here"
```

## Post-Release

- [ ] Verify release artifacts on GitHub
- [ ] Test installation from release
- [ ] Update documentation if needed
- [ ] Announce release (if applicable)

## Automation

The release checklist can be executed using task agents:

```bash
# In Claude Code, the following agents can be used:
# - Pre-release verification agent
# - Version update agent
# - Translation workflow agent
# - Test runner agent
# - Docker build agent
# - Release commit agent
```

## Troubleshooting

### Coverage Below Threshold
If local coverage is slightly below threshold but CI passes, this is often due to environment differences. The CI environment is authoritative.

### Translation Check Failures
Run `uv run manage-translations check --warn-only` to see issues without failing, then address them individually.

### Docker Build Failures
Check for uncommitted changes that might affect the build context:
```bash
git status
git stash  # if needed
docker compose build --no-cache
```
