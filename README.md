# Simple GPT Shell

`gpt-shell.py` is a CLI assistant that turns natural-language requests into shell commands, runs them interactively, and explains the results.

This version is migrated to the OpenAI **Responses API** and uses **server-side conversation memory** via `previous_response_id` (instead of keeping full chat history locally).

## Example Session

```text
You: find the 3 biggest files in this project

Assistant:
Plan:
1) du -ah . | sort -hr | head -n 3
Run this command? [run/edit/skip/stop]: run

Running:
$ du -ah . | sort -hr | head -n 3

Result:
- 156M ./screen1.png
-  39M ./gpt-shell.py
-  12M ./logs/session-2026-02-06.jsonl

Assistant:
Top file is `screen1.png` (~156 MB). Want cleanup suggestions?
```

## Features

- Function calling for structured command suggestions (`get_commands`)
- Auto mode and manual mode for command execution
- Follow-up analysis of command output
- Server-side context chaining between turns
- JSONL logging in the app folder (`./logs/gpt-shell.log`) with user/assistant messages, API request/response metadata, and command execution events

## Usage

1. One-time setup:
   - `./gpt-shell.sh --install`
   - `export OPENAI_API_KEY='your-api-key'`
2. Run:
   - `./gpt-shell.sh`
3. Enter a task in plain language.
4. For each suggested command choose: run, edit, skip, run-all-remaining, or stop.
5. Use `safe on`, `safe off`, or `safe` to control safe mode.
6. Use `tokens on`, `tokens off`, or `tokens` to control token usage display.
7. Use `e` to enter manual command mode, `q` to quit.

Optional environment variables:
- `export OPENAI_MODEL='gpt-4o-mini'`
- `export GPT_SHELL_LOG_FILE="./logs/custom.log"`
- `export GPT_SHELL_SAFE_MODE=1`
- `export GPT_SHELL_SHOW_TOKENS=1`
- `export GPT_SHELL_MAX_OUTPUT_TOKENS=1200`

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
