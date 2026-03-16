# Roadmap

## v0.3

### Reliability
- Add configurable network timeout settings for OpenAI calls, separate from retry count/backoff.
- Add richer classification of retriable versus terminal API failures in user-facing output and logs.
- Add a small offline fallback path for obvious local-only prompts when the API is unavailable.

### Safety
- Expand command analysis to understand more shell forms such as subshells, grouped commands, and more destructive wrappers.
- Add optional command allowlists/denylists in config for team-specific environments.
- Add a confirmation policy layer that can require a second approval for specific risky patterns.

### Automation
- Extend `--json` output with stable status codes and optional schema versioning.
- Add a `--json-out FILE` option for pipeline-friendly automation.
- Add non-interactive execution mode for trusted CI scenarios with explicit `--yes`.

## v0.4

### Product
- Add session resume and history browsing by `session_id`.
- Add export/import of session bundles for debugging and support.
- Add a richer report mode with summaries grouped by prompt, command batch, and API usage.

### Developer Experience
- Add linting and formatting automation in CI.
- Add coverage reporting and per-module quality gates for high-risk code paths.
- Add release note checks that verify the tagged version is present in `CHANGELOG.md`.

### Packaging
- Publish packages automatically to GitHub Releases and optionally PyPI.
- Add `pipx`-oriented install docs and smoke tests for the console script.
