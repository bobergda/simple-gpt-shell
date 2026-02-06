# Simple GPT Shell

`gpt-shell.py` is a CLI assistant that turns natural-language requests into shell commands, runs them interactively, and explains the results.

This version is migrated to the OpenAI **Responses API** and uses **server-side conversation memory** via `previous_response_id` (instead of keeping full chat history locally).

## Example Session (Text-Only)

Color legend:
- 🟦 User input
- 🟪 Assistant suggestion
- 🟨 Command execution
- 🟩 Result summary

```text
🟦 You: find the 5 biggest files here

🟪 Assistant:
I will run:
1) du -ah . | sort -hr | head -n 5

🟨 Running:
$ du -ah . | sort -hr | head -n 5

🟩 Result:
- 156M ./screen1.png
-  39M ./gpt-shell.py
- ...

🟪 Assistant:
The largest file is `screen1.png` (~156 MB). Want me to suggest cleanup options?
```

## Features

- Function calling for structured command suggestions (`get_commands`)
- Auto mode and manual mode for command execution
- Follow-up analysis of command output
- Server-side context chaining between turns
- JSONL logging in the app folder (`./logs/gpt-shell.log`) with user/assistant messages, API request/response metadata, and command execution events

## Installation

1. Clone the repository.
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Set API key:
   - `export OPENAI_API_KEY='your-api-key'`

Optional model override:
- `export OPENAI_MODEL='gpt-4o-mini'`

Optional log file override:
- `export GPT_SHELL_LOG_FILE="./logs/custom.log"`

Optional safe mode toggle (default: enabled):
- `export GPT_SHELL_SAFE_MODE=1`

Optional token output toggle (default: enabled):
- `export GPT_SHELL_SHOW_TOKENS=1`

Optional max output tokens per API response (default: `1200`):
- `export GPT_SHELL_MAX_OUTPUT_TOKENS=1200`

## Usage

1. Run:
   - `./gpt-shell.sh`
   - first-time or dependency update: `./gpt-shell.sh --install`
2. Enter a task in plain language.
3. For each suggested command choose: run, edit, skip, run-all-remaining, or stop.
4. Use `safe on`, `safe off`, or `safe` to control safe mode.
5. Use `tokens on`, `tokens off`, or `tokens` to control token usage display.
6. Use `e` to enter manual command mode, `q` to quit.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).
