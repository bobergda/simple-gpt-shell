# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Execution profiles: `inspect`, `safe-edit`, and `full`.
- Machine-readable `--json` mode for automation.
- Session IDs in logs and reports.
- API retry/backoff configuration for Responses API calls.
- Release workflow that builds artifacts and publishes GitHub releases from tags.

### Changed
- Stronger command safety analysis for strict mode and high-risk detection.
- CLI and logging flows now support session-aware reporting and structured output.
