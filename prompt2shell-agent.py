#!/usr/bin/env python3
import json
import os
import re
import subprocess
import sys
import threading
import platform
from datetime import datetime, timezone
import distro
from openai import OpenAI
from termcolor import colored as term_colored
from prompt_toolkit import ANSI, PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory

APP_NAME = "Prompt2Shell Agent"


# Built-in visual theme (no env-based color overrides).
THEME_COLOR_MAP = {
    "green": "cyan",     # prompts and general app info
    "magenta": "white",  # assistant narrative text
    "blue": "blue",      # command lines
    "cyan": "cyan",
    "yellow": "yellow",
    "red": "red",
    "white": "white",
    "grey": "grey",
}

THEME_ATTRS_MAP = {
    "green": ["bold"],
    "blue": ["bold"],
}


def colored(text, color=None, on_color=None, attrs=None):
    mapped_color = color
    if isinstance(color, str):
        color_key = color.lower()
        mapped_color = THEME_COLOR_MAP.get(color_key, color_key)
        if attrs is None:
            attrs = THEME_ATTRS_MAP.get(color_key)
    return term_colored(text, mapped_color, on_color=on_color, attrs=attrs)


def getenv_with_legacy(primary_key, legacy_key, default=None):
    value = os.getenv(primary_key)
    if value is not None:
        return value
    return os.getenv(legacy_key, default)


class OpenAIHelper:
    """A class that handles OpenAI Responses API calls."""

    def __init__(self, model_name="gpt-4o-mini", max_output_tokens=1200, interaction_logger=None):
        """Initialize OpenAI helper with server-side conversation memory."""
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        if self.api_key == "":
            print(colored("Error: OPENAI_API_KEY is not set", "red"), file=sys.stderr)
            exit(1)

        self.client = OpenAI(api_key=self.api_key)
        self.model_name = model_name
        self.max_output_tokens = max_output_tokens
        self.last_response_id = None
        self.interaction_logger = interaction_logger
        self.last_usage_summary = None
        self.session_usage_summary = self._empty_usage_summary()
        self._active_usage_summary = None

        self.os_name, self.shell_name = OSHelper.get_os_and_shell_info()
        self.instructions = (
            "You are a shell command assistant. Prefer safe, idempotent commands first. "
            "For any command proposal, return it through the get_commands function. "
            "Include a short description for each command. "
            "If no command is needed, return an empty commands list with a helpful response."
        )

        self.tools = [
            {
                "type": "function",
                "name": "get_commands",
                "description": (
                    f"Return a list of {self.shell_name} commands for an {self.os_name} machine"
                ),
                "strict": False,
                "parameters": {
                    "type": "object",
                    "properties": {
                        "commands": {
                            "type": "array",
                            "description": "List of shell commands to execute",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "command": {
                                        "type": "string",
                                        "description": "A valid command string"
                                    },
                                    "description": {
                                        "type": "string",
                                        "description": "Description of the command"
                                    }
                                },
                                "required": ["command"],
                                "additionalProperties": False
                            },
                        },
                        "response": {
                            "type": "string",
                            "description": "Human-readable explanation for the user"
                        }
                    },
                    "required": ["commands", "response"],
                    "additionalProperties": False
                },
            }
        ]

    @staticmethod
    def _item_value(item, key, default=None):
        if isinstance(item, dict):
            return item.get(key, default)
        return getattr(item, key, default)

    @staticmethod
    def _empty_usage_summary():
        return {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "api_calls": 0}

    @staticmethod
    def _safe_int(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    def _begin_usage_capture(self):
        self._active_usage_summary = self._empty_usage_summary()

    def _finish_usage_capture(self):
        if self._active_usage_summary is None:
            self.last_usage_summary = None
        else:
            self.last_usage_summary = dict(self._active_usage_summary)
        self._active_usage_summary = None
        return self.last_usage_summary

    def _extract_usage_summary(self, response):
        usage = self._item_value(response, "usage")
        if usage is None:
            return self._empty_usage_summary()
        return {
            "input_tokens": self._safe_int(self._item_value(usage, "input_tokens", 0)),
            "output_tokens": self._safe_int(self._item_value(usage, "output_tokens", 0)),
            "total_tokens": self._safe_int(self._item_value(usage, "total_tokens", 0)),
            "api_calls": 1,
        }

    def _record_usage_summary(self, usage_summary):
        if not isinstance(usage_summary, dict):
            return
        for key in ("input_tokens", "output_tokens", "total_tokens", "api_calls"):
            self.session_usage_summary[key] += self._safe_int(usage_summary.get(key, 0))
            if self._active_usage_summary is not None:
                self._active_usage_summary[key] += self._safe_int(usage_summary.get(key, 0))

    def get_last_usage_summary(self):
        if self.last_usage_summary is None:
            return None
        return dict(self.last_usage_summary)

    def get_session_usage_summary(self):
        return dict(self.session_usage_summary)

    def _log_api_event(self, event_name, payload):
        if self.interaction_logger is None:
            return
        self.interaction_logger.log_event(event_name, payload)

    def _create_response(self, input_data, tool_choice="auto"):
        request = {
            "model": self.model_name,
            "instructions": self.instructions,
            "input": input_data,
            "tools": self.tools,
            "tool_choice": tool_choice,
            "parallel_tool_calls": False,
            "max_output_tokens": self.max_output_tokens,
        }
        if self.last_response_id is not None:
            request["previous_response_id"] = self.last_response_id

        self._log_api_event(
            "api_request",
            {
                "model": request["model"],
                "tool_choice": request["tool_choice"],
                "has_previous_response_id": "previous_response_id" in request,
                "input": input_data,
            },
        )

        response = self.client.responses.create(**request)
        self.last_response_id = response.id
        usage_summary = self._extract_usage_summary(response)
        self._record_usage_summary(usage_summary)
        output_items = []
        for item in self._item_value(response, "output", []) or []:
            output_items.append(
                {
                    "type": self._item_value(item, "type"),
                    "id": self._item_value(item, "id"),
                    "name": self._item_value(item, "name"),
                    "call_id": self._item_value(item, "call_id"),
                }
            )
        self._log_api_event(
            "api_response",
            {
                "response_id": response.id,
                "output_text": self._response_text(response),
                "output_items": output_items,
                "usage": usage_summary,
            },
        )
        return response

    def _extract_function_calls(self, response):
        calls = []
        for item in self._item_value(response, "output", []) or []:
            if self._item_value(item, "type") != "function_call":
                continue
            call_id = self._item_value(item, "call_id") or self._item_value(item, "id")
            calls.append({
                "name": self._item_value(item, "name"),
                "arguments": self._item_value(item, "arguments", "{}"),
                "call_id": call_id,
            })
        return calls

    @staticmethod
    def _sanitize_commands_payload(payload):
        if not isinstance(payload, dict):
            return None

        commands = payload.get("commands")
        if not isinstance(commands, list):
            return None

        sanitized = []
        for command in commands:
            if not isinstance(command, dict):
                continue
            command_text = command.get("command")
            if not isinstance(command_text, str) or command_text.strip() == "":
                continue
            description = command.get("description")
            sanitized.append({
                "command": command_text,
                "description": description if isinstance(description, str) else "",
            })

        return {
            "commands": sanitized,
            "response": payload.get("response", "") if isinstance(payload.get("response", ""), str) else ""
        }

    @staticmethod
    def _response_text(response):
        text = getattr(response, "output_text", None)
        return text.strip() if isinstance(text, str) and text.strip() else None

    def _resolve_function_calls(self, response):
        current_response = response
        commands_payload = None

        for _ in range(3):
            calls = self._extract_function_calls(current_response)
            if not calls:
                break

            outputs = []
            for call in calls:
                if call["name"] != "get_commands":
                    if not call["call_id"]:
                        continue
                    outputs.append({
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": json.dumps({"status": "ignored", "reason": "Unsupported function"}),
                    })
                    continue

                try:
                    parsed = json.loads(call["arguments"])
                    parsed = self._sanitize_commands_payload(parsed)
                    if parsed is None:
                        raise ValueError("Invalid get_commands payload")
                    commands_payload = parsed
                    self._log_api_event("get_commands_payload", parsed)
                    if not call["call_id"]:
                        continue
                    outputs.append({
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": json.dumps({"status": "ok", "commands_count": len(parsed["commands"])}),
                    })
                except Exception as exc:
                    if not call["call_id"]:
                        continue
                    outputs.append({
                        "type": "function_call_output",
                        "call_id": call["call_id"],
                        "output": json.dumps({"status": "error", "error": str(exc)}),
                    })

            current_response = self._create_response(outputs, tool_choice="none")

        return current_response, commands_payload

    def get_commands(self, prompt):
        """Return command suggestions using forced function calling."""
        self._begin_usage_capture()
        try:
            response = self._create_response(
                input_data=prompt,
                tool_choice={"type": "function", "name": "get_commands"},
            )
            _, commands_payload = self._resolve_function_calls(response)
            return commands_payload
        except Exception as e:
            print(colored(f"Error: {e}", "red"), file=sys.stderr)
            return None
        finally:
            self._finish_usage_capture()

    def send_commands_outputs(self, outputs, execution_summary=None):
        """Send command outputs for analysis and optional follow-up commands."""
        self._begin_usage_capture()
        execution_payload = {
            "execution_summary": execution_summary if isinstance(execution_summary, list) else [],
            "outputs": outputs if isinstance(outputs, list) else [],
        }
        execution_json = json.dumps(execution_payload, ensure_ascii=False)
        prompt_text = (
            "Analyze the following shell execution report and explain what happened. "
            "If useful, propose next steps via get_commands. "
            "If nothing was executed, clearly state that and do not propose follow-up commands.\n\n"
            f"Execution report:\n{execution_json}"
        )

        try:
            response = self._create_response(input_data=prompt_text, tool_choice="auto")
            final_response, commands_payload = self._resolve_function_calls(response)

            response_text = self._response_text(final_response)
            if response_text is None and commands_payload is not None:
                response_text = commands_payload.get("response") or None

            next_commands = None
            if commands_payload is not None:
                next_commands = commands_payload.get("commands") or None

            return response_text, next_commands
        except Exception as e:
            print(colored(f"Error: {e}", "red"), file=sys.stderr)
            return None, None
        finally:
            self._finish_usage_capture()


class InteractionLogger:
    """Helper class for logging user queries and assistant responses."""

    def __init__(self, log_file=None):
        app_dir = os.path.dirname(os.path.abspath(__file__))
        default_path = os.path.join(app_dir, "logs", "prompt2shell-agent.log")
        configured_path = log_file or getenv_with_legacy(
            "PROMPT2SHELL_LOG_FILE",
            "GPT_SHELL_LOG_FILE",
            default_path,
        )
        resolved_path = os.path.expanduser(configured_path)
        if not os.path.isabs(resolved_path):
            resolved_path = os.path.join(app_dir, resolved_path)
        self.log_file = resolved_path
        log_dir = os.path.dirname(self.log_file)
        self._lock = threading.Lock()
        if log_dir:
            try:
                os.makedirs(log_dir, exist_ok=True)
            except OSError as exc:
                print(colored(f"Warning: unable to create log directory: {exc}", "yellow"), file=sys.stderr)

    @staticmethod
    def _sanitize_for_log(value):
        if isinstance(value, str):
            return CommandHelper.redact_sensitive_text(value)
        if isinstance(value, dict):
            return {str(key): InteractionLogger._sanitize_for_log(item) for key, item in value.items()}
        if isinstance(value, list):
            return [InteractionLogger._sanitize_for_log(item) for item in value]
        if isinstance(value, tuple):
            return [InteractionLogger._sanitize_for_log(item) for item in value]
        return value

    def _write_entry(self, entry):
        with self._lock:
            with open(self.log_file, "a", encoding="utf-8") as file:
                file.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def log(self, role, text):
        if not isinstance(text, str) or text.strip() == "":
            return

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "role": role,
            "text": self._sanitize_for_log(text),
        }

        try:
            self._write_entry(entry)
        except OSError as exc:
            print(colored(f"Warning: unable to write log: {exc}", "yellow"), file=sys.stderr)

    def log_event(self, event_name, data=None):
        if not isinstance(event_name, str) or event_name.strip() == "":
            return

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "type": "event",
            "event": event_name,
            "data": self._sanitize_for_log(data),
        }

        try:
            self._write_entry(entry)
        except OSError as exc:
            print(colored(f"Warning: unable to write log: {exc}", "yellow"), file=sys.stderr)


class CommandHelper:
    """Helper class for executing commands."""
    DESTRUCTIVE_COMMAND_PATTERNS = (
        (re.compile(r"(^|[;&|]\s*)\s*rm\s+.*(--no-preserve-root|--preserve-root=0)\b", re.IGNORECASE),
         "rm with preserve-root disabled"),
        (re.compile(
            r"(^|[;&|]\s*)\s*(sudo\s+)?rm\b(?=[^\n]*(?:\s|^)(?:-rf|-fr|--recursive|--force|-r|-f)(?:\s|$))",
            re.IGNORECASE,
        ),
         "rm with recursive/force options"),
        (re.compile(r"(^|[;&|]\s*)\s*mkfs(\.\w+)?\b", re.IGNORECASE), "filesystem format command"),
        (re.compile(r"(^|[;&|]\s*)\s*dd\s+.*\bof=/dev/", re.IGNORECASE), "dd write to block device"),
        (re.compile(r"(^|[;&|]\s*)\s*shred\b", re.IGNORECASE), "secure delete command"),
        (re.compile(r"(^|[;&|]\s*)\s*wipefs\b", re.IGNORECASE), "filesystem wipe command"),
        (re.compile(r"(^|[;&|]\s*)\s*git\s+reset\s+--hard\b", re.IGNORECASE), "git hard reset"),
        (re.compile(r"(^|[;&|]\s*)\s*git\s+clean\s+-[^\n]*f", re.IGNORECASE), "git clean with force"),
        (re.compile(r"(^|[;&|]\s*)\s*docker\s+system\s+prune\b", re.IGNORECASE), "docker prune"),
        (re.compile(r":\(\)\s*\{\s*:\|:&\s*\};:", re.IGNORECASE), "fork bomb pattern"),
    )

    @staticmethod
    def _command_timeout_seconds():
        raw_timeout = getenv_with_legacy(
            "PROMPT2SHELL_COMMAND_TIMEOUT",
            "GPT_SHELL_COMMAND_TIMEOUT",
            "300",
        )
        try:
            timeout = int(raw_timeout)
        except (TypeError, ValueError):
            timeout = 300
        return timeout if timeout > 0 else None

    @staticmethod
    def detect_destructive_command(command):
        if not isinstance(command, str) or command.strip() == "":
            return None
        normalized = command.strip()
        for pattern, reason in CommandHelper.DESTRUCTIVE_COMMAND_PATTERNS:
            if pattern.search(normalized):
                return reason
        return None

    @staticmethod
    def redact_sensitive_text(text):
        if not isinstance(text, str) or text == "":
            return text

        redacted = text
        redacted = re.sub(
            r"(?i)\b(Authorization)\b(\s*[:=]\s*)Bearer\s+[A-Za-z0-9\-._~+/]+=*",
            r"\1\2Bearer <REDACTED>",
            redacted,
        )
        redacted = re.sub(
            r"(?i)\b([A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|PASSWD)[A-Z0-9_]*)\b(\s*[:=]\s*)([^\s\"']+|\"[^\"]*\"|'[^']*')",
            r"\1\2<REDACTED>",
            redacted,
        )
        redacted = re.sub(
            r"(?i)\b(Bearer)\s+[A-Za-z0-9\-._~+/]+=*",
            r"\1 <REDACTED>",
            redacted,
        )
        redacted = re.sub(r"\bsk-[A-Za-z0-9]{12,}\b", "<REDACTED_OPENAI_KEY>", redacted)
        redacted = re.sub(
            r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9._-]+\.[A-Za-z0-9._-]+\b",
            "<REDACTED_JWT>",
            redacted,
        )
        redacted = re.sub(r"\bAKIA[0-9A-Z]{16}\b", "<REDACTED_AWS_ACCESS_KEY_ID>", redacted)
        return redacted

    @staticmethod
    def _read_stream(stream, sink, color=None):
        try:
            for line in iter(stream.readline, ""):
                sink.append(line)
                if color:
                    print(colored(line.rstrip("\n"), color))
                else:
                    print(line, end="")
        finally:
            stream.close()

    @staticmethod
    def run_shell_command(command):
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            universal_newlines=True,
        )
        stdout_lines = []
        stderr_lines = []

        stdout_thread = threading.Thread(
            target=CommandHelper._read_stream,
            args=(process.stdout, stdout_lines),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=CommandHelper._read_stream,
            args=(process.stderr, stderr_lines, "red"),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        timeout_seconds = CommandHelper._command_timeout_seconds()
        timed_out = False
        interrupted = False

        try:
            if timeout_seconds is None:
                returncode = process.wait()
            else:
                returncode = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            returncode = process.wait()
            print(
                colored(
                    f"Error: Command timed out after {timeout_seconds}s",
                    "red",
                )
            )
        except KeyboardInterrupt:
            interrupted = True
            process.kill()
            returncode = process.wait()
            print(colored("Command interrupted by user", "yellow"))
        finally:
            stdout_thread.join()
            stderr_thread.join()

        output = {
            "command": command,
            "stdout": CommandHelper.redact_sensitive_text("".join(stdout_lines)),
            "stderr": CommandHelper.redact_sensitive_text("".join(stderr_lines)),
            "returncode": returncode,
            "timed_out": timed_out,
            "interrupted": interrupted,
        }
        return output


class OSHelper:
    """Helper class for getting OS and shell information."""

    @staticmethod
    def get_os_and_shell_info():
        """Returns the OS and shell information."""
        os_name = platform.system()
        shell_name = os.path.basename(os.environ.get("SHELL", ""))
        if os_name == "Linux":
            os_name += f" {distro.name()}"
        elif os_name == "Darwin":
            os_name += f" {platform.mac_ver()[0]}"
        elif os_name == "Windows":
            os_name += f" {platform.release()}"
        return os_name, shell_name


class Application:
    """Main application class."""

    def __init__(
        self,
        openai_helper: OpenAIHelper,
        command_helper: CommandHelper,
        interaction_logger: InteractionLogger,
    ):
        """Initializes the application."""
        self.openai_helper = openai_helper
        self.command_helper = command_helper
        self.interaction_logger = interaction_logger
        self.safe_mode_enabled = self._read_safe_mode_from_env()
        self.show_tokens = self._read_show_tokens_from_env()
        default_history_path = os.path.expanduser("~/.prompt2shell_history")
        legacy_history_path = os.path.expanduser("~/.gpts_history")
        history_path = default_history_path
        if not os.path.exists(default_history_path) and os.path.exists(legacy_history_path):
            history_path = legacy_history_path
        self.session = PromptSession(
            history=FileHistory(history_path),
            auto_suggest=AutoSuggestFromHistory(),
        )

    @staticmethod
    def _read_safe_mode_from_env():
        raw_value = getenv_with_legacy("PROMPT2SHELL_SAFE_MODE", "GPT_SHELL_SAFE_MODE", "1").strip().lower()
        return raw_value not in {"0", "false", "off", "no"}

    @staticmethod
    def _read_show_tokens_from_env():
        raw_value = getenv_with_legacy("PROMPT2SHELL_SHOW_TOKENS", "GPT_SHELL_SHOW_TOKENS", "1").strip().lower()
        return raw_value not in {"0", "false", "off", "no"}

    def _safe_mode_status_text(self):
        return "ON" if self.safe_mode_enabled else "OFF"

    def _show_tokens_status_text(self):
        return "ON" if self.show_tokens else "OFF"

    def _set_safe_mode(self, enabled):
        self.safe_mode_enabled = enabled
        print(colored(f"Safe mode: {self._safe_mode_status_text()}", "green" if enabled else "yellow"))
        self.interaction_logger.log_event("safe_mode_changed", {"enabled": enabled})

    def _set_show_tokens(self, enabled):
        self.show_tokens = enabled
        print(colored(f"Token usage display: {self._show_tokens_status_text()}", "green" if enabled else "yellow"))
        self.interaction_logger.log_event("token_usage_display_changed", {"enabled": enabled})

    def _print_token_usage(self):
        if not self.show_tokens:
            return

        usage = self.openai_helper.get_last_usage_summary()
        if usage is None:
            return

        session_usage = self.openai_helper.get_session_usage_summary()
        max_output_tokens = self.openai_helper.max_output_tokens
        output_left = max(0, max_output_tokens - usage.get("output_tokens", 0))

        usage_text = (
            f"Tokens last: in={usage.get('input_tokens', 0)}, "
            f"out={usage.get('output_tokens', 0)}, total={usage.get('total_tokens', 0)}, "
            f"out_left={output_left}/{max_output_tokens} | "
            f"session: in={session_usage.get('input_tokens', 0)}, "
            f"out={session_usage.get('output_tokens', 0)}, "
            f"total={session_usage.get('total_tokens', 0)}, "
            f"calls={session_usage.get('api_calls', 0)}"
        )
        print(colored(usage_text, "cyan"))

    def _print_assistant_response(self, response):
        if not isinstance(response, str) or response.strip() == "":
            return
        print(colored(response, "magenta"))
        self.interaction_logger.log("assistant", response)

    def _print_commands_batch(self, commands):
        print(colored("\nProposed commands:", "green"))
        for index, command in enumerate(commands, start=1):
            command_str = command.get("command", "").strip()
            description = command.get("description", "").strip()
            print(colored(f"[{index}] {command_str}", "blue"))
            if description:
                print(colored(f"    {description}", "grey"))

    def _prompt_command_action(self, index, total):
        prompt_text = (
            f"Command {index}/{total} action "
            "[r=run, e=edit, s=skip, a=run all remaining, q=stop] (default s): "
        )
        while True:
            action = self.session.prompt(ANSI(colored(prompt_text, "green"))).strip().lower()
            if action == "":
                return "s"
            if action in {"r", "e", "s", "a", "q", "y", "n"}:
                return {"y": "r", "n": "s"}.get(action, action)
            print(colored("Invalid choice. Use r/e/s/a/q.", "yellow"))

    def _prompt_yes_no(self, text):
        while True:
            answer = self.session.prompt(ANSI(colored(text, "green"))).strip().lower()
            if answer in {"", "n", "no"}:
                return False
            if answer in {"y", "yes"}:
                return True
            print(colored("Please answer with y or n.", "yellow"))

    def _guard_command_with_safe_mode(self, command_str):
        candidate = command_str
        while True:
            if not self.safe_mode_enabled:
                return candidate, None

            reason = self.command_helper.detect_destructive_command(candidate)
            if reason is None:
                return candidate, None

            warning = f"Safe mode blocked high-risk command ({reason}): {candidate}"
            print(colored(warning, "red"))
            self.interaction_logger.log_event(
                "safe_mode_blocked_command",
                {"command": candidate, "reason": reason},
            )
            prompt_text = (
                "Safe mode action [run=execute once, e=edit, s=skip] (default s): "
            )
            action = self.session.prompt(ANSI(colored(prompt_text, "yellow"))).strip().lower()

            if action in {"run", "r"}:
                self.interaction_logger.log_event(
                    "safe_mode_override",
                    {"command": candidate, "reason": reason},
                )
                return candidate, None

            if action in {"e", "edit"}:
                edited = self.session.prompt(
                    ANSI(colored("Enter the modified command: ", "cyan")),
                    default=candidate,
                ).strip()
                if edited == "":
                    return None, "safe_mode_empty_after_edit"
                candidate = edited
                continue

            return None, "blocked_by_safe_mode"

    def _handle_runtime_command(self, user_input):
        normalized = user_input.strip().lower()
        if normalized in {"safe", "/safe"}:
            print(colored(f"Safe mode is {self._safe_mode_status_text()}", "green" if self.safe_mode_enabled else "yellow"))
            return True

        if normalized in {"safe on", "/safe on"}:
            self._set_safe_mode(True)
            return True

        if normalized in {"safe off", "/safe off"}:
            if self._prompt_yes_no("Disable safe mode? This can execute destructive commands. (y/N): "):
                self._set_safe_mode(False)
            else:
                print(colored("Safe mode stays ON.", "yellow"))
            return True

        if normalized in {"tokens", "/tokens"}:
            print(colored(
                f"Token usage display: {self._show_tokens_status_text()}",
                "green" if self.show_tokens else "yellow",
            ))
            return True

        if normalized in {"tokens on", "/tokens on"}:
            self._set_show_tokens(True)
            return True

        if normalized in {"tokens off", "/tokens off"}:
            self._set_show_tokens(False)
            return True

        return False

    def interpret_and_execute_command(self, user_prompt):
        """Interprets and executes the command."""
        if user_prompt == "e":
            self.manual_command_mode()
        else:
            self.auto_command_mode(user_prompt)

    def manual_command_mode(self):
        """Manual command mode."""
        print(colored("Manual command mode activated. Please enter your command:", "green"))
        command_str = self.session.prompt("").strip()
        if command_str == "":
            print(colored("No command entered.", "yellow"))
            return

        if not self._prompt_yes_no(f"Run command `{command_str}`? (y/N): "):
            print(colored("Command canceled.", "yellow"))
            self.interaction_logger.log_event("command_skipped", {"command": command_str, "reason": "manual_mode_cancel"})
            return

        guarded_command, skip_reason = self._guard_command_with_safe_mode(command_str)
        if guarded_command is None:
            print(colored("Command canceled by safe mode.", "yellow"))
            self.interaction_logger.log_event(
                "command_skipped",
                {"command": command_str, "reason": skip_reason},
            )
            return

        command_output = self.command_helper.run_shell_command(guarded_command)
        self.interaction_logger.log_event("command_executed", command_output)
        outputs = [command_output]
        execution_summary = [{"command": guarded_command, "status": "executed"}]

        response, commands = self.openai_helper.send_commands_outputs(outputs, execution_summary=execution_summary)
        self._print_assistant_response(response)
        self._print_token_usage()
        if commands:
            self.execute_commands(commands)

    def auto_command_mode(self, user_prompt):
        """Auto command mode."""
        commands_payload = self.openai_helper.get_commands(user_prompt)
        self._print_token_usage()
        self.interaction_logger.log_event("auto_mode_commands_payload", commands_payload)
        if commands_payload and commands_payload.get("response"):
            self._print_assistant_response(commands_payload["response"])

        commands = commands_payload.get("commands") if commands_payload else None
        if commands:
            self.execute_commands(commands)
        elif commands_payload and commands_payload.get("response"):
            print(colored("No commands proposed.", "yellow"))
        else:
            print(colored("No commands found", "red"))

    def execute_commands(self, commands):
        """Executes the commands."""
        while commands:
            self._print_commands_batch(commands)
            self.interaction_logger.log_event("commands_batch", commands)

            outputs = []
            execution_summary = []
            run_all_remaining = False
            stop_after_batch = False

            for index, command in enumerate(commands, start=1):
                command_str = command.get("command", "").strip()
                if command_str == "":
                    execution_summary.append({"command": "", "status": "skipped_empty"})
                    continue

                action = "r" if run_all_remaining else self._prompt_command_action(index, len(commands))

                if action == "q":
                    stop_after_batch = True
                    execution_summary.append({"command": command_str, "status": "stopped_by_user"})
                    break

                if action == "a":
                    run_all_remaining = True
                    action = "r"

                if action == "e":
                    edited_command = self.session.prompt(
                        ANSI(colored("Enter the modified command: ", "cyan")),
                        default=command_str,
                    ).strip()
                    if edited_command == "":
                        print(colored("Empty command after edit, skipping.", "yellow"))
                        execution_summary.append({"command": command_str, "status": "skipped_empty_after_edit"})
                        self.interaction_logger.log_event(
                            "command_skipped",
                            {"command": command_str, "reason": "empty_after_edit"},
                        )
                        continue
                    command_str = edited_command
                    if not self._prompt_yes_no("Run the edited command? (y/N): "):
                        print(colored("Skipping command", "yellow"))
                        execution_summary.append({"command": command_str, "status": "skipped_after_edit"})
                        self.interaction_logger.log_event(
                            "command_skipped",
                            {"command": command_str, "reason": "skipped_after_edit"},
                        )
                        continue
                    action = "r"

                if action == "s":
                    print(colored("Skipping command", "yellow"))
                    execution_summary.append({"command": command_str, "status": "skipped"})
                    self.interaction_logger.log_event("command_skipped", {"command": command_str})
                    continue

                guarded_command, skip_reason = self._guard_command_with_safe_mode(command_str)
                if guarded_command is None:
                    print(colored("Skipping command (safe mode).", "yellow"))
                    execution_summary.append({"command": command_str, "status": "blocked_by_safe_mode"})
                    self.interaction_logger.log_event(
                        "command_skipped",
                        {"command": command_str, "reason": skip_reason},
                    )
                    continue

                output = self.command_helper.run_shell_command(guarded_command)
                outputs.append(output)
                execution_summary.append(
                    {
                        "command": guarded_command,
                        "status": "executed",
                        "returncode": output.get("returncode"),
                        "timed_out": output.get("timed_out"),
                        "interrupted": output.get("interrupted"),
                    }
                )
                self.interaction_logger.log_event("command_executed", output)

            self.interaction_logger.log_event("commands_execution_summary", execution_summary)

            if not outputs:
                print(colored("No commands were executed.", "yellow"))
                break

            response, next_commands = self.openai_helper.send_commands_outputs(
                outputs,
                execution_summary=execution_summary,
            )
            self._print_assistant_response(response)
            self._print_token_usage()
            if stop_after_batch:
                break
            commands = next_commands

    def run(self):
        """Runs the application."""
        os_name, shell_name = OSHelper.get_os_and_shell_info()
        print(
            colored(f"Your current environment: Shell={shell_name}, OS={os_name}", "green"))
        print(colored(
            f"Safe mode: {self._safe_mode_status_text()} (use `safe on`, `safe off`, `safe`).", "green"))
        print(colored(
            f"Token usage display: {self._show_tokens_status_text()} (use `tokens on`, `tokens off`, `tokens`).", "green"))
        print(colored("Type 'e' to enter manual command mode or 'q' to quit.\n", "green"))

        while True:
            try:
                user_input = self.session.prompt(
                    ANSI(colored(f"{APP_NAME}: ", "green")))
                if user_input.lower() == 'q':
                    break
                self.interaction_logger.log("user", user_input)
                if self._handle_runtime_command(user_input):
                    continue
                self.interpret_and_execute_command(user_input)
            except subprocess.CalledProcessError as e:
                print(colored(
                    f"Error: Command failed with exit code {e.returncode}: {e.output}", "red"), file=sys.stderr)
            except KeyboardInterrupt:
                continue
            except EOFError:
                break
            except Exception as e:
                print(
                    colored(f"Error of type {type(e).__name__}: {e}", "red"), file=sys.stderr)
                print(colored("Exiting...", "yellow"))


if __name__ == "__main__":
    """Main entry point."""
    max_output_tokens_raw = getenv_with_legacy(
        "PROMPT2SHELL_MAX_OUTPUT_TOKENS",
        "GPT_SHELL_MAX_OUTPUT_TOKENS",
        "1200",
    )
    try:
        max_output_tokens = int(max_output_tokens_raw)
        if max_output_tokens <= 0:
            max_output_tokens = 1200
    except (TypeError, ValueError):
        max_output_tokens = 1200

    interaction_logger = InteractionLogger()
    openai_helper = OpenAIHelper(
        model_name=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
        max_output_tokens=max_output_tokens,
        interaction_logger=interaction_logger,
    )
    command_helper = CommandHelper()
    application = Application(openai_helper, command_helper, interaction_logger)
    application.run()
