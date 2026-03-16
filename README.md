# Prompt2Shell Agent

`Prompt2Shell Agent` is a CLI assistant that turns natural-language requests into shell commands, runs them interactively, and explains the results.

This version uses the OpenAI **Responses API** with server-side conversation chaining via `previous_response_id`.

## Features

- Function calling for structured command suggestions (`get_commands`)
- Manual mode and guided execution mode
- `--dry-run` and `--explain-only` preview modes
- `--json` mode for automation and scripting
- Execution profiles: `inspect`, `safe-edit`, `full`
- Follow-up analysis of command output
- Safe mode with destructive-command detection
- Optional strict safe mode (read-only allowlist)
- Command timeout handling that terminates the full process group
- Opt-in JSONL logging with basic secret redaction and restrictive file permissions (`0600`)
- Optional TOML config file in `~/.config/prompt2shell/config.toml`
- Optional Markdown session reports via `--report`
- Session-aware logging and reports with `session_id`
- Installable Python package with `prompt2shell` console script
- Modular code layout in `prompt2shell/` for easier maintenance and testing
- GitHub Actions workflow for CI
- GitHub release workflow for tagged artifacts

## Usage

1. One-time setup:
   ```shell
   ./prompt2shell.sh --install
   export OPENAI_API_KEY="your-api-key"
   ```
   You can also install it as a regular CLI:
   ```shell
   python -m pip install .
   prompt2shell "find the 3 biggest files in this project"
   ```
   You can also keep local settings in `.env` (auto-loaded by `prompt2shell.sh`):
   ```dotenv
   OPENAI_API_KEY="your-api-key"
   OPENAI_MODEL="gpt-4o-mini"
   PROMPT2SHELL_MAX_OUTPUT_TOKENS=1200
   ```
   Or use a persistent config file:
   ```shell
   mkdir -p ~/.config/prompt2shell
   cp ./prompt2shell.example.toml ~/.config/prompt2shell/config.toml
   ```
2. Run:
   ```shell
   ./prompt2shell.sh
   ```
   Or run immediately with a prompt:
   ```shell
   ./prompt2shell.sh "find the 3 biggest files in this project"
   ```
   One-shot mode (run prompt once and exit):
   ```shell
   ./prompt2shell.sh -o "find the 3 biggest files in this project"
   ```
   Dry-run preview:
   ```shell
   ./prompt2shell.sh --dry-run "show large files and explain why"
   ```
   JSON automation mode:
   ```shell
   ./prompt2shell.sh --json "inspect git status and suggest next command"
   ```
   Explain-only preview:
   ```shell
   ./prompt2shell.sh --explain-only "how would you inspect disk usage here?"
   ```
   Write a Markdown session report:
   ```shell
   ./prompt2shell.sh --report "summarize this repository"
   ./prompt2shell.sh --report ./logs/reports/repo.md "summarize this repository"
   ```
   Pipe mode (stdin is used as prompt):
   ```shell
   ls | ./prompt2shell.sh
   ls | ./prompt2shell.sh "summarize this output"
   ```
   In pipe mode the app also adds an inferred source hint (for example, likely `ls -l`/`ll`, `df -h`, `ps`, JSON).
3. Enter a task in plain language.
4. For each proposed command choose: run, edit, skip, run-all-remaining, stop, or type a command number to run that item.
5. Runtime controls:
   - `safe on`, `safe off`, `safe`
   - `strict on`, `strict off`, `strict`
   - `tokens on`, `tokens off`, `tokens`
   - `e` to enter manual command mode, `q` to quit

Script options:

```shell
./prompt2shell.sh --tests
./prompt2shell.sh --update-requirements
./prompt2shell.sh --add-alias
./prompt2shell.sh -o "find the 3 biggest files in this project"
./prompt2shell.sh --once "find the 3 biggest files in this project"
./prompt2shell.sh --profile=inspect "inspect this repository"
./prompt2shell.sh --dry-run "find the 3 biggest files in this project"
./prompt2shell.sh --json "inspect recent logs"
./prompt2shell.sh --explain-only "find the 3 biggest files in this project"
./prompt2shell.sh --report ./logs/reports/run.md "find the 3 biggest files in this project"
./prompt2shell.sh -m5 "find the 3 biggest files in this project"
./prompt2shell.sh --model=gpt-4o-mini
./prompt2shell.sh --tokens=1200
./prompt2shell.sh --config=~/.config/prompt2shell/config.toml
./prompt2shell.sh --model=gpt-4o-mini --tokens=1200
ls | ./prompt2shell.sh
ls | ./prompt2shell.sh "summarize this output"
./prompt2shell.sh -- "prompt that starts with -"
./prompt2shell.sh --help
```

Optional environment variables:

```shell
export OPENAI_MODEL="gpt-4o-mini"
export PROMPT2SHELL_LOG_ENABLED=1
export PROMPT2SHELL_LOG_FILE="./logs/custom.log"
export PROMPT2SHELL_SAFE_MODE=1
export PROMPT2SHELL_SAFE_MODE_STRICT=0
export PROMPT2SHELL_SHOW_TOKENS=1
export PROMPT2SHELL_MAX_OUTPUT_TOKENS=1200
export PROMPT2SHELL_COMMAND_TIMEOUT=300
export PROMPT2SHELL_PROFILE="safe-edit"
export PROMPT2SHELL_OPENAI_MAX_RETRIES=2
export PROMPT2SHELL_OPENAI_RETRY_BASE_SECONDS=1.0
export PROMPT2SHELL_DRY_RUN=0
export PROMPT2SHELL_EXPLAIN_ONLY=0
export PROMPT2SHELL_JSON=0
export PROMPT2SHELL_SESSION_REPORT_FILE="./logs/reports/latest-session.md"
```

Example config file (`~/.config/prompt2shell/config.toml`):

```toml
[openai]
api_key = ""
model = "gpt-4o-mini"
chat_language = "english"
max_retries = 2
retry_base_seconds = 1.0

[app]
profile = "safe-edit"
max_output_tokens = 1200
safe_mode = true
strict_safe_mode = false
show_tokens = true
command_timeout = 300
dry_run = false
explain_only = false
json_mode = false

[logging]
enabled = false
file = "./logs/prompt2shell.log"

[report]
file = "./logs/reports/latest-session.md"
```

## Example Session

Startup:

```console
Environment: shell=bash | OS=Linux Ubuntu | model=gpt-4o-mini | chat language=english
Safe mode: ON (use `safe on`, `safe off`, `safe`).
Strict safe mode (read-only allowlist): OFF (use `strict on`, `strict off`, `strict`).
Token usage display: ON (use `tokens on`, `tokens off`, `tokens`).
Profile: safe-edit
Dry run: OFF
Explain-only mode: OFF
JSON mode: OFF
Type 'e' for manual mode, or 'q' to quit.
```

Request and command:

```console
Prompt2Shell Agent: find the 3 biggest files in this project
Tokens last: in=..., out=..., total=..., out_left=.../... | session: in=..., out=..., total=..., calls=...
This command will search for files in the current directory, sort them by size, and display the top 3 largest files.
```

```shell
du -ah . | sort -rh | head -n 3
```

```console
Command 1/1 action [r=run, e=edit, s=skip, a=run all remaining, q=end batch, 1-1=run by number, Ctrl+C=exit loop] (default s): a
```

## Development

Run tests:

```shell
./.venv/bin/python -m unittest discover -s tests -v
```

Build the package:

```shell
python -m build
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
