# Simple GPT Shell

`gpt-shell.py` is a CLI assistant that turns natural-language requests into shell commands, runs them interactively, and explains the results.

This version is migrated to the OpenAI **Responses API** and uses **server-side conversation memory** via `previous_response_id` (instead of keeping full chat history locally).

## Features

- Function calling for structured command suggestions (`get_commands`)
- Auto mode and manual mode for command execution
- Follow-up analysis of command output
- Server-side context chaining between turns
- JSONL logging in the app folder (`./logs/gpt-shell.log`) with user/assistant messages, API request/response metadata, and command execution events

## Usage

1. One-time setup:
   ```shell
   ./gpt-shell.sh --install
   export OPENAI_API_KEY="your-api-key"
   ```
2. Run:
   ```shell
   ./gpt-shell.sh
   ```
3. Enter a task in plain language.
4. For each suggested command choose: run, edit, skip, run-all-remaining, or stop.
5. Use `safe on`, `safe off`, or `safe` to control safe mode.
6. Use `tokens on`, `tokens off`, or `tokens` to control token usage display.
7. Use `e` to enter manual command mode, `q` to quit.

Optional environment variables:
```shell
export OPENAI_MODEL="gpt-4o-mini"
export GPT_SHELL_LOG_FILE="./logs/custom.log"
export GPT_SHELL_SAFE_MODE=1
export GPT_SHELL_SHOW_TOKENS=1
export GPT_SHELL_MAX_OUTPUT_TOKENS=1200
```

## Example Session

### 1. Startup
```console
Your current environment: Shell=bash, OS=Linux Ubuntu
Safe mode: ON (use `safe on`, `safe off`, `safe`).
Token usage display: ON (use `tokens on`, `tokens off`, `tokens`).
Type 'e' to enter manual command mode or 'q' to quit.
```

### 2. User prompt
```console
ChatGPT: find the 3 biggest files in this project
Tokens last: in=..., out=..., total=..., out_left=.../... | session: in=..., out=..., total=..., calls=...
This command will search for files in the current directory, sort them by size, and display the top 3 largest files.
```

### 3. Proposed command
```shell
du -ah . | sort -rh | head -n 3
```

```console
Command 1/1 action [r=run, e=edit, s=skip, a=run all remaining, q=stop] (default s): a
```

### 4. Command output
```console
50M    .
48M    ./.venv/lib/python3.12/site-packages
48M    ./.venv/lib/python3.12
```

### 5. Assistant summary
```console
The command ran successfully and returned the top entries by size.
```

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
