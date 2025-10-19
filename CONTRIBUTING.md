# Contributing to BirdNET-Pi

First off, thank you for considering contributing to BirdNET-Pi! It's people like you that make BirdNET-Pi such a great tool.

Following these guidelines helps to communicate that you respect the time of the developers managing and developing this open source project. In return, they should reciprocate that respect in addressing your issue, assessing changes, and helping you finalize your pull requests.

## How Can I Contribute?

### Reporting Bugs

This section guides you through submitting a bug report for BirdNET-Pi. Following these guidelines helps maintainers and the community understand your report, reproduce the behavior, and find related reports.

Before creating bug reports, please check the existing [issues](https://github.com/mverteuil/BirdNET-Pi/issues) as you might find out that you don't need to create one. When you are creating a bug report, please include as many details as possible.

### Suggesting Enhancements

This section guides you through submitting an enhancement suggestion for BirdNET-Pi, including completely new features and minor improvements to existing functionality. Following these guidelines helps maintainers and the community understand your suggestion and find related suggestions.

### Your First Code Contribution

Unsure where to begin contributing to BirdNET-Pi? You can start by looking through these `good-first-issue` and `help-wanted` issues:

*   [Good first issues](https://github.com/mverteuil/BirdNET-Pi/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) - issues which should only require a few lines of code, and a test or two.
*   [Help wanted issues](https://github.com/mverteuil/BirdNET-Pi/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22) - issues which should be a bit more involved than `good-first-issue` issues.

## Development Setup

### Docker-Based Development
This project uses Docker for development:
```bash
docker-compose up  # Start development environment
```

### Local CLI Tools
Only these commands run outside Docker (use inline env vars):
```bash
# Download models locally
BIRDNETPI_DATA=./data uv run install-assets install latest

# Create releases
BIRDNETPI_DATA=./data uv run manage-releases create
```

**WARNING**: Never use `export BIRDNETPI_DATA` as it will persist and break tests!

### Running Tests
```bash
uv run pytest  # Tests use fixtures, not env vars
```

**Note**: Tests automatically handle paths via fixtures:
- `repo_root`: Provides repository root path
- `path_resolver`: Provides test-configured PathResolver
- `app_with_temp_data`: Provides test-configured FastAPI app

To get your development environment set up, please also follow the instructions in the [README.md](README.md) under the "For Developers" section.

The key steps are:
1.  Clone the repository.
2.  Install `uv`.
3.  Run `uv sync` to install all dependencies.

## Pull Request Process

Please be advised that we have a few guidelines for contributing to this project. Please follow them so that we can have a better chance of accepting your pull request.
Changes that violate the philosophy of this project will be rejected. Changes that are not in line with the project's goals will also be rejected. If you are unsure whether your change is in line with the project's goals, please open an issue first to discuss it.

1.  Fork the repository and create your branch from `main`.
2.  If you've added code that should be tested, add tests.
3.  Make sure your code passes the tests and adheres to the code style.
4.  Coverage cannot drop below 80% or actions will fail.
5.  Ensure your pull request adheres to the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification.
6.  Open a pull request.
7.  If your pull request is accepted, it will be merged into the main branch.

## Code Style

We use `pre-commit` to enforce code style. Please make sure to install the pre-commit hooks with `pre-commit install` before you start working.

The primary tools we use are:
*   `actionlint` for GitHub Actions workflows.
*   `hadolint` for Dockerfiles.
*   `prettier` for formatting HTML, CSS, and JavaScript files.
*   `pyright` for type checking Python code.
*   `ruff` for linting and import sorting.
*   `shellcheck` for shell scripts.
*   `yamllint` for YAML files.

Running `pre-commit run` before committing will ensure your code meets our style guidelines.

## Commit Messages

We follow the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification. This allows for easier automation of releases and changelogs.

Please format your commit messages like this:

```
<type>([optional scope]): <description>

[optional body]

[optional footer(s)]
```

Example:
```
feat(web): add new chart to dashboard

This commit adds a new chart to the dashboard that displays the top 10 most detected species over the last 7 days.

Fixes #123
```
