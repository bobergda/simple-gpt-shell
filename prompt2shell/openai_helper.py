import json
import os
import sys
import time

from openai import (
    APIConnectionError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    PermissionDeniedError,
    RateLimitError,
)

from .common import colored
from .os_helper import OSHelper


class OpenAIHelper:
    """A class that handles OpenAI Responses API calls."""

    def __init__(
        self,
        model_name="gpt-4o-mini",
        max_output_tokens=1200,
        interaction_logger=None,
        api_key=None,
        chat_language=None,
        max_retries=2,
        retry_base_seconds=1.0,
    ):
        """Initialize OpenAI helper with server-side conversation memory."""
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        if self.api_key == "":
            print(colored("Error: OPENAI_API_KEY is not set", "red"), file=sys.stderr)
            raise SystemExit(1)

        self.client = OpenAI(api_key=self.api_key)
        self.model_name = model_name
        self.max_output_tokens = max_output_tokens
        self.last_response_id = None
        self.interaction_logger = interaction_logger
        self.max_retries = max(0, int(max_retries))
        self.retry_base_seconds = retry_base_seconds if retry_base_seconds > 0 else 1.0
        self.last_usage_summary = None
        self.session_usage_summary = self._empty_usage_summary()
        self._active_usage_summary = None

        self.os_name, self.shell_name = OSHelper.get_os_and_shell_info()
        self.base_instructions = (
            "You are a shell command assistant. Prefer safe, idempotent commands first. "
            "Prefer read-only inspection commands unless change is clearly required. "
            "For any command proposal, return it through the get_commands function. "
            "Include a short description for each command. "
            "If no command is needed, return an empty commands list with a helpful response."
        )
        if chat_language is None:
            chat_language = os.getenv("PROMPT2SHELL_CHAT_LANGUAGE", "english")
        self.chat_language = self._normalize_chat_language(chat_language)
        self.session_once_mode = False
        self.session_has_piped_input = False
        self.session_safe_mode_enabled = True
        self.session_strict_safe_mode = False
        self.session_dry_run = False
        self.session_explain_only = False
        self.session_profile = "safe-edit"

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
                                        "description": "A valid command string",
                                    },
                                    "description": {
                                        "type": "string",
                                        "description": "Description of the command",
                                    },
                                },
                                "required": ["command"],
                                "additionalProperties": False,
                            },
                        },
                        "response": {
                            "type": "string",
                            "description": "Human-readable explanation for the user",
                        },
                    },
                    "required": ["commands", "response"],
                    "additionalProperties": False,
                },
            }
        ]

    def configure_session_context(
        self,
        once_mode=None,
        has_piped_input=None,
        safe_mode_enabled=None,
        strict_safe_mode=None,
        dry_run=None,
        explain_only=None,
        profile=None,
    ):
        if once_mode is not None:
            self.session_once_mode = bool(once_mode)
        if has_piped_input is not None:
            self.session_has_piped_input = bool(has_piped_input)
        if safe_mode_enabled is not None:
            self.session_safe_mode_enabled = bool(safe_mode_enabled)
        if strict_safe_mode is not None:
            self.session_strict_safe_mode = bool(strict_safe_mode)
        if dry_run is not None:
            self.session_dry_run = bool(dry_run)
        if explain_only is not None:
            self.session_explain_only = bool(explain_only)
        if profile is not None:
            self.session_profile = str(profile)

    def _build_instructions(self):
        instructions_parts = [self.base_instructions]

        if self.session_strict_safe_mode:
            instructions_parts.append(
                "Session context: strict safe mode is ON. "
                "Only propose read-only commands and avoid commands that write or modify files."
            )
        elif self.session_safe_mode_enabled:
            instructions_parts.append(
                "Session context: safe mode is ON. "
                "Avoid destructive commands and prefer low-risk alternatives."
            )

        instructions_parts.append(f"Session profile: `{self.session_profile}`.")

        if self.session_has_piped_input:
            instructions_parts.append(
                "Session context: piped command output is already provided. "
                "Analyze provided input first before suggesting extra collection commands."
            )

        if self.session_once_mode:
            instructions_parts.append(
                "Session context: one-shot mode. "
                "Prefer a direct final answer and avoid unnecessary follow-up command proposals."
            )

        if self.session_explain_only:
            instructions_parts.append(
                "Session context: explain-only mode. "
                "The app will not execute commands. Provide clear command rationale and keep follow-up focused on explanation."
            )
        elif self.session_dry_run:
            instructions_parts.append(
                "Session context: dry-run mode. "
                "The app may preview commands, but it will not execute them."
            )

        if self.chat_language == "polish":
            instructions_parts.append(
                "Language policy: respond in Polish for all user-facing text, including command descriptions. "
                "Keep shell command strings unchanged."
            )
        else:
            instructions_parts.append(
                "Language policy: respond in English for all user-facing text, including command descriptions. "
                "Keep shell command strings unchanged."
            )

        return " ".join(instructions_parts)

    @staticmethod
    def _item_value(item, key, default=None):
        if isinstance(item, dict):
            return item.get(key, default)
        return getattr(item, key, default)

    @staticmethod
    def _normalize_chat_language(raw_language):
        normalized = str(raw_language or "").strip().lower()
        if normalized == "polish":
            return "polish"
        return "english"

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

    @staticmethod
    def _retry_delay_for_attempt(attempt_number, base_seconds):
        return base_seconds * (2 ** max(0, attempt_number - 1))

    @staticmethod
    def _is_retryable_error(exc):
        if isinstance(exc, (RateLimitError, APIConnectionError, APITimeoutError, APIResponseValidationError)):
            return True
        if isinstance(exc, APIStatusError):
            return getattr(exc, "status_code", 0) >= 500
        return False

    @staticmethod
    def _format_openai_error(exc):
        if isinstance(exc, AuthenticationError):
            return "OpenAI authentication failed. Check OPENAI_API_KEY."
        if isinstance(exc, PermissionDeniedError):
            return "OpenAI request was denied. Verify project permissions and model access."
        if isinstance(exc, BadRequestError):
            return f"OpenAI rejected the request as invalid: {exc}"
        if isinstance(exc, RateLimitError):
            return "OpenAI rate limit reached. The client retried automatically but still ran out of attempts."
        if isinstance(exc, APITimeoutError):
            return "OpenAI request timed out after multiple attempts."
        if isinstance(exc, APIConnectionError):
            return "OpenAI connection failed after retry attempts."
        if isinstance(exc, APIStatusError):
            status_code = getattr(exc, "status_code", "unknown")
            return f"OpenAI API returned status {status_code}."
        return f"OpenAI request failed: {exc}"

    def _create_response(self, input_data, tool_choice="auto"):
        request = {
            "model": self.model_name,
            "instructions": self._build_instructions(),
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
                "max_retries": self.max_retries,
            },
        )

        response = None
        last_error = None
        for attempt in range(1, self.max_retries + 2):
            try:
                response = self.client.responses.create(**request)
                break
            except Exception as exc:  # pylint: disable=broad-except
                last_error = exc
                retryable = self._is_retryable_error(exc)
                will_retry = retryable and attempt <= self.max_retries
                self._log_api_event(
                    "api_error",
                    {
                        "attempt": attempt,
                        "retryable": retryable,
                        "will_retry": will_retry,
                        "error_type": type(exc).__name__,
                        "message": str(exc),
                    },
                )
                if not will_retry:
                    raise
                delay = self._retry_delay_for_attempt(attempt, self.retry_base_seconds)
                self._log_api_event("api_retry_scheduled", {"attempt": attempt, "delay_seconds": delay})
                time.sleep(delay)
        if response is None:
            raise last_error
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
            calls.append(
                {
                    "name": self._item_value(item, "name"),
                    "arguments": self._item_value(item, "arguments", "{}"),
                    "call_id": call_id,
                }
            )
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
            sanitized.append(
                {
                    "command": command_text,
                    "description": description if isinstance(description, str) else "",
                }
            )

        return {
            "commands": sanitized,
            "response": payload.get("response", "") if isinstance(payload.get("response", ""), str) else "",
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
                    outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call["call_id"],
                            "output": json.dumps({"status": "ignored", "reason": "Unsupported function"}),
                        }
                    )
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
                    outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call["call_id"],
                            "output": json.dumps({"status": "ok", "commands_count": len(parsed["commands"])}),
                        }
                    )
                except Exception as exc:  # pylint: disable=broad-except
                    if not call["call_id"]:
                        continue
                    outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": call["call_id"],
                            "output": json.dumps({"status": "error", "error": str(exc)}),
                        }
                    )

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
        except Exception as exc:  # pylint: disable=broad-except
            print(colored(f"Error: {self._format_openai_error(exc)}", "red"), file=sys.stderr)
            return None
        finally:
            self._finish_usage_capture()

    def send_commands_outputs(self, outputs, execution_summary=None, allow_follow_up_commands=True):
        """Send command outputs for analysis and optional follow-up commands."""
        self._begin_usage_capture()
        execution_payload = {
            "execution_summary": execution_summary if isinstance(execution_summary, list) else [],
            "outputs": outputs if isinstance(outputs, list) else [],
        }
        execution_json = json.dumps(execution_payload, ensure_ascii=False)
        if allow_follow_up_commands:
            prompt_text = (
                "Analyze the following shell execution report and explain what happened. "
                "If useful, propose next steps via get_commands. "
                "If nothing was executed, clearly state that and do not propose follow-up commands.\n\n"
                f"Execution report:\n{execution_json}"
            )
            tool_choice = "auto"
        else:
            prompt_text = (
                "Analyze the following shell execution report and explain what happened. "
                "Do not propose or return any new commands. "
                "Do not call get_commands. "
                "Provide only an explanation for the user.\n\n"
                f"Execution report:\n{execution_json}"
            )
            tool_choice = "none"

        try:
            response = self._create_response(input_data=prompt_text, tool_choice=tool_choice)
            final_response, commands_payload = self._resolve_function_calls(response)

            response_text = self._response_text(final_response)
            if response_text is None and commands_payload is not None:
                response_text = commands_payload.get("response") or None

            next_commands = None
            if allow_follow_up_commands and commands_payload is not None:
                next_commands = commands_payload.get("commands") or None

            return response_text, next_commands
        except Exception as exc:  # pylint: disable=broad-except
            print(colored(f"Error: {self._format_openai_error(exc)}", "red"), file=sys.stderr)
            return None, None
        finally:
            self._finish_usage_capture()
