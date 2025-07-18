# Contributing to BirdNET-Pi

First off, thank you for considering contributing to BirdNET-Pi! It's people like you that make BirdNET-Pi such a great tool.

Following these guidelines helps to communicate that you respect the time of the developers managing and developing this open source project. In return, they should reciprocate that respect in addressing your issue, assessing changes, and helping you finalize your pull requests.

## How Can I Contribute?

### Reporting Bugs

This section guides you through submitting a bug report for BirdNET-Pi. Following these guidelines helps maintainers and the community understand your report, reproduce the behavior, and find related reports.

Before creating bug reports, please check the existing [issues](https://github.com/mcguirepr89/BirdNET-Pi/issues) as you might find out that you don't need to create one. When you are creating a bug report, please include as many details as possible.

### Suggesting Enhancements

This section guides you through submitting an enhancement suggestion for BirdNET-Pi, including completely new features and minor improvements to existing functionality. Following these guidelines helps maintainers and the community understand your suggestion and find related suggestions.

### Your First Code Contribution

Unsure where to begin contributing to BirdNET-Pi? You can start by looking through these `good-first-issue` and `help-wanted` issues:

*   [Good first issues](https://github.com/mcguirepr89/BirdNET-Pi/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) - issues which should only require a few lines of code, and a test or two.
*   [Help wanted issues](https://github.com/mcguirepr89/BirdNET-Pi/issues?q=is%3Aissue+is%3Aopen+label%3A%22help+wanted%22) - issues which should be a bit more involved than `good-first-issue` issues.

## Development Setup

To get your development environment set up, please follow the instructions in the [README.md](README.md) under the "For Developers" section.

The key steps are:
1.  Clone the repository.
2.  Install `uv`.
3.  Run `uv sync` to install all dependencies.

## Pull Request Process

1.  Ensure any install or build dependencies are removed before the end of the layer when doing a build.
2.  Update the README.md with details of changes to the interface, this includes new environment variables, exposed ports, useful file locations and container parameters.
3.  Increase the version numbers in any examples files and the README.md to the new version that this Pull Request would represent. The versioning scheme we use is [SemVer](http://semver.org/).
4.  You may merge the Pull Request in once you have the sign-off of two other developers, or if you do not have permission to do that, you may request the second reviewer to merge it for you.

## Code Style

We use `pre-commit` to enforce code style. Please make sure to install the pre-commit hooks with `pre-commit install` before you start working.

The primary tools we use are:
*   `black` for code formatting.
*   `ruff` for linting and import sorting.
*   `shellcheck` for shell scripts.
*   `yamllint` for YAML files.

Running `pre-commit run` before committing will ensure your code meets our style guidelines.

## Commit Messages

We follow the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification. This allows for easier automation of releases and changelogs.

Please format your commit messages like this:

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

Example:
```
feat(web): add new chart to dashboard

This commit adds a new chart to the dashboard that displays the top 10 most detected species over the last 7 days.

Fixes #123
```
