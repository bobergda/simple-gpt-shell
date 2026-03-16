import subprocess
import sys
from datetime import datetime, timezone

from prompt_toolkit import ANSI, PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.history import FileHistory
from prompt_toolkit.input.defaults import create_input
from prompt_toolkit.output.defaults import create_output

from .common import APP_NAME, colored, env_flag


class Application:
    """Main application class."""

    def __init__(self, openai_helper, command_helper, interaction_logger, settings=None):
        """Initializes the application."""
        self.settings = settings
        self.openai_helper = openai_helper
        self.command_helper = command_helper
        self.interaction_logger = interaction_logger
        self.safe_mode_enabled = self._read_safe_mode_default()
        self.safe_mode_strict = self._read_safe_mode_strict_default()
        self.show_tokens = self._read_show_tokens_default()
        self.dry_run = bool(getattr(self.settings, "dry_run", env_flag("PROMPT2SHELL_DRY_RUN", False)))
        self.explain_only = bool(getattr(self.settings, "explain_only", env_flag("PROMPT2SHELL_EXPLAIN_ONLY", False)))
        self.session_report_file = getattr(self.settings, "session_report_file", None)

        default_history_path = FileHistoryPath.default()
        legacy_history_path = FileHistoryPath.legacy()
        history_path = default_history_path
        if not FileHistoryPath.exists(default_history_path) and FileHistoryPath.exists(legacy_history_path):
            history_path = legacy_history_path

        # Prefer terminal TTY for interactive prompts, even when stdin/stdout are piped.
        # This avoids prompt glitches and EOF behavior after using pipe mode.
        prompt_input = create_input(always_prefer_tty=True)
        prompt_output = create_output(always_prefer_tty=True)
        self.session = PromptSession(
            history=FileHistory(history_path),
            auto_suggest=AutoSuggestFromHistory(),
            input=prompt_input,
            output=prompt_output,
        )

    def _read_safe_mode_default(self):
        if self.settings is not None and getattr(self.settings, "safe_mode", None) is not None:
            return bool(self.settings.safe_mode)
        return env_flag("PROMPT2SHELL_SAFE_MODE", True)

    def _read_safe_mode_strict_default(self):
        if self.settings is not None and getattr(self.settings, "safe_mode_strict", None) is not None:
            return bool(self.settings.safe_mode_strict)
        return env_flag("PROMPT2SHELL_SAFE_MODE_STRICT", False)

    def _read_show_tokens_default(self):
        if self.settings is not None and getattr(self.settings, "show_tokens", None) is not None:
            return bool(self.settings.show_tokens)
        return env_flag("PROMPT2SHELL_SHOW_TOKENS", True)

    def _safe_mode_status_text(self):
        return "ON" if self.safe_mode_enabled else "OFF"

    def _safe_mode_strict_status_text(self):
        return "ON" if self.safe_mode_strict else "OFF"

    def _show_tokens_status_text(self):
        return "ON" if self.show_tokens else "OFF"

    def _set_safe_mode(self, enabled):
        self.safe_mode_enabled = enabled
        print(colored(f"Safe mode: {self._safe_mode_status_text()}", "green" if enabled else "yellow"))
        self._sync_openai_session_context()
        self.interaction_logger.log_event("safe_mode_changed", {"enabled": enabled})

    def _set_safe_mode_strict(self, enabled):
        self.safe_mode_strict = enabled
        print(colored(
            f"Strict safe mode (read-only allowlist): {self._safe_mode_strict_status_text()}",
            "green" if enabled else "yellow",
        ))
        self._sync_openai_session_context()
        self.interaction_logger.log_event("safe_mode_strict_changed", {"enabled": enabled})

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

    def _sync_openai_session_context(self):
        configure_context = getattr(self.openai_helper, "configure_session_context", None)
        if not callable(configure_context):
            return
        configure_context(
            safe_mode_enabled=self.safe_mode_enabled,
            strict_safe_mode=self.safe_mode_strict,
            dry_run=getattr(self, "dry_run", False),
            explain_only=getattr(self, "explain_only", False),
        )

    def _build_report_metadata(self):
        return {
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "model_name": getattr(self.openai_helper, "model_name", "unknown"),
            "shell_name": getattr(self.openai_helper, "shell_name", "unknown"),
            "os_name": getattr(self.openai_helper, "os_name", "unknown"),
            "chat_language": getattr(self.openai_helper, "chat_language", "english"),
            "safe_mode": self.safe_mode_enabled,
            "safe_mode_strict": self.safe_mode_strict,
            "show_tokens": self.show_tokens,
            "dry_run": getattr(self, "dry_run", False),
            "explain_only": getattr(self, "explain_only", False),
            "session_report_file": getattr(self, "session_report_file", None),
            "usage_summary": self.openai_helper.get_session_usage_summary(),
        }

    def _finalize_session_report(self):
        if not getattr(self, "session_report_file", None):
            return
        report_path = self.interaction_logger.export_session_report(
            report_file=self.session_report_file,
            metadata=self._build_report_metadata(),
        )
        if report_path:
            print(colored(f"Session report saved to: {report_path}", "cyan"))
            self.interaction_logger.log_event("session_report_exported", {"path": report_path})

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
            f"[r=run, e=edit, s=skip, a=run all remaining, q=end batch, 1-{total}=run by number, Ctrl+C=exit loop] "
            "(default s): "
        )
        while True:
            action = self.session.prompt(ANSI(colored(prompt_text, "green"))).strip().lower()
            if action == "":
                return "s"
            if action in {"r", "e", "s", "a", "q", "y", "n"}:
                return {"y": "r", "n": "s"}.get(action, action)
            if action.isdigit():
                selected_index = int(action)
                if 1 <= selected_index <= total:
                    return action
            print(colored(f"Invalid choice. Use r/e/s/a/q, number 1-{total}, or Ctrl+C.", "yellow"))

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

            if self.safe_mode_strict:
                strict_reason = self.command_helper.detect_non_readonly_command(candidate)
                if strict_reason is not None:
                    warning = f"Strict safe mode blocked command ({strict_reason}): {candidate}"
                    print(colored(warning, "red"))
                    self.interaction_logger.log_event(
                        "strict_safe_mode_blocked_command",
                        {"command": candidate, "reason": strict_reason},
                    )
                    prompt_text = "Strict safe mode action [e=edit, s=skip] (default s): "
                    action = self.session.prompt(ANSI(colored(prompt_text, "yellow"))).strip().lower()

                    if action in {"e", "edit"}:
                        edited = self.session.prompt(
                            ANSI(colored("Enter the modified command: ", "cyan")),
                            default=candidate,
                        ).strip()
                        if edited == "":
                            return None, "safe_mode_empty_after_edit"
                        candidate = edited
                        continue

                    return None, "blocked_by_strict_safe_mode"

            reason = self.command_helper.detect_destructive_command(candidate)
            if reason is None:
                return candidate, None

            warning = f"Safe mode blocked high-risk command ({reason}): {candidate}"
            print(colored(warning, "red"))
            self.interaction_logger.log_event(
                "safe_mode_blocked_command",
                {"command": candidate, "reason": reason},
            )
            prompt_text = "Safe mode action [run=execute once, e=edit, s=skip] (default s): "
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
            print(colored(
                f"Safe mode is {self._safe_mode_status_text()} | strict read-only mode is {self._safe_mode_strict_status_text()}",
                "green" if self.safe_mode_enabled else "yellow",
            ))
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

        if normalized in {"strict", "/strict"}:
            print(colored(
                f"Strict safe mode (read-only allowlist) is {self._safe_mode_strict_status_text()}",
                "green" if self.safe_mode_strict else "yellow",
            ))
            return True

        if normalized in {"strict on", "/strict on"}:
            self._set_safe_mode_strict(True)
            return True

        if normalized in {"strict off", "/strict off"}:
            self._set_safe_mode_strict(False)
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

        if getattr(self, "dry_run", False):
            print(colored(f"Dry run: command not executed: {guarded_command}", "yellow"))
            self.interaction_logger.log_event("command_previewed", {"command": guarded_command, "mode": "manual"})
            return

        command_output = self.command_helper.run_shell_command(guarded_command)
        self.interaction_logger.log_event("command_executed", command_output)
        outputs = [command_output]
        execution_summary = [{"command": guarded_command, "status": "executed"}]

        self._sync_openai_session_context()
        response, commands = self.openai_helper.send_commands_outputs(outputs, execution_summary=execution_summary)
        self._print_assistant_response(response)
        self._print_token_usage()
        if commands:
            self.execute_commands(commands)

    def auto_command_mode(self, user_prompt):
        """Auto command mode."""
        self._sync_openai_session_context()
        commands_payload = self.openai_helper.get_commands(user_prompt)
        self._print_token_usage()
        self.interaction_logger.log_event("auto_mode_commands_payload", commands_payload)
        if commands_payload and commands_payload.get("response"):
            self._print_assistant_response(commands_payload["response"])

        commands = commands_payload.get("commands") if commands_payload else None
        if commands:
            if getattr(self, "explain_only", False):
                self._print_commands_batch(commands)
                print(colored("Explain-only mode: commands were not executed.", "yellow"))
                self.interaction_logger.log_event("commands_previewed", {"count": len(commands), "mode": "explain_only"})
                return
            self.execute_commands(commands)
        elif commands_payload and commands_payload.get("response"):
            print(colored("No commands proposed.", "yellow"))
        else:
            print(colored("No commands found", "red"))

    def execute_commands(self, commands):
        """Executes the commands."""
        while commands:
            try:
                self._print_commands_batch(commands)
                self.interaction_logger.log_event("commands_batch", commands)

                executed_any = False
                execution_summary = []
                outputs = []
                run_all_remaining = False
                selected_command_index = None

                for index, command in enumerate(commands, start=1):
                    command_str = command.get("command", "").strip()
                    if command_str == "":
                        execution_summary.append({"command": "", "status": "skipped_empty"})
                        continue

                    if run_all_remaining:
                        action = "r"
                    elif selected_command_index is not None and index < selected_command_index:
                        action = "s"
                    elif selected_command_index is not None and index == selected_command_index:
                        action = "r"
                        selected_command_index = None
                    else:
                        action = self._prompt_command_action(index, len(commands))

                    while action.isdigit():
                        selected_index = int(action)
                        if selected_index < index:
                            print(colored(f"Command {selected_index} was already processed; choose current or later.", "yellow"))
                            action = self._prompt_command_action(index, len(commands))
                            continue
                        if selected_index > index:
                            selected_command_index = selected_index
                            print(colored(f"Selecting command {selected_index}; skipping command {index}.", "yellow"))
                            action = "s"
                        else:
                            action = "r"
                        break

                    if action == "q":
                        print(colored("Ending current command batch.", "yellow"))
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

                    if getattr(self, "dry_run", False):
                        print(colored(f"Dry run: command not executed: {guarded_command}", "yellow"))
                        execution_record = {
                            "command": guarded_command,
                            "status": "dry_run",
                            "returncode": None,
                            "timed_out": False,
                            "interrupted": False,
                        }
                        execution_summary.append(execution_record)
                        outputs.append(
                            {
                                "command": guarded_command,
                                "stdout": "",
                                "stderr": "",
                                "returncode": None,
                                "timed_out": False,
                                "interrupted": False,
                                "dry_run": True,
                            }
                        )
                        self.interaction_logger.log_event("command_previewed", execution_record)
                        executed_any = True
                        continue

                    output = self.command_helper.run_shell_command(guarded_command)
                    execution_record = {
                        "command": guarded_command,
                        "status": "executed",
                        "returncode": output.get("returncode"),
                        "timed_out": output.get("timed_out"),
                        "interrupted": output.get("interrupted"),
                    }
                    execution_summary.append(execution_record)
                    outputs.append(output)
                    self.interaction_logger.log_event("command_executed", output)
                    executed_any = True

                    # In run-all mode (action "a"), execute remaining commands first
                    # and send one combined report to the assistant at the end.
                    if run_all_remaining:
                        continue

                    self._sync_openai_session_context()
                    response, _ = self.openai_helper.send_commands_outputs(
                        [output],
                        execution_summary=[execution_record],
                        allow_follow_up_commands=False,
                    )
                    self._print_assistant_response(response)
                    self._print_token_usage()

                self.interaction_logger.log_event("commands_execution_summary", execution_summary)
                if not executed_any:
                    print(colored("No commands were executed.", "yellow"))
                    break

                if getattr(self, "dry_run", False):
                    print(colored("Dry run completed. No commands were executed.", "yellow"))
                    break

                self._sync_openai_session_context()
                response, next_commands = self.openai_helper.send_commands_outputs(
                    outputs,
                    execution_summary=execution_summary,
                    allow_follow_up_commands=True,
                )
                self._print_assistant_response(response)
                self._print_token_usage()
                commands = next_commands
            except KeyboardInterrupt:
                print(colored("Command loop interrupted (Ctrl+C). Returning to main prompt.", "yellow"))
                self.interaction_logger.log_event("commands_loop_interrupted", {"reason": "keyboard_interrupt"})
                return

    def _process_user_input(self, user_input):
        if user_input.lower() == "q":
            return False
        self.interaction_logger.log("user", user_input)
        if self._handle_runtime_command(user_input):
            return True
        self.interpret_and_execute_command(user_input)
        return True

    def run(self, initial_prompt=None, exit_after_initial_prompt=False):
        """Runs the application."""
        os_name, shell_name = self.openai_helper.os_name, self.openai_helper.shell_name
        model_name = getattr(self.openai_helper, "model_name", "unknown")
        chat_language = getattr(self.openai_helper, "chat_language", "english")
        has_initial_prompt = isinstance(initial_prompt, str) and initial_prompt.strip() != ""
        self.interaction_logger.log_event(
            "session_started",
            {
                "shell_name": shell_name,
                "os_name": os_name,
                "model_name": model_name,
                "chat_language": chat_language,
                "dry_run": getattr(self, "dry_run", False),
                "explain_only": getattr(self, "explain_only", False),
            },
        )
        try:
            print(
                colored(
                    f"Environment: shell={shell_name} | OS={os_name} | model={model_name} | chat language={chat_language}",
                    "green",
                )
            )
            print(colored(f"Safe mode: {self._safe_mode_status_text()}", "green" if self.safe_mode_enabled else "yellow"))
            print(
                colored(
                    f"Strict safe mode (read-only allowlist): {self._safe_mode_strict_status_text()}",
                    "green" if self.safe_mode_strict else "yellow",
                )
            )
            print(colored(f"Token usage display: {self._show_tokens_status_text()}", "green" if self.show_tokens else "yellow"))
            dry_run_enabled = getattr(self, "dry_run", False)
            explain_only_enabled = getattr(self, "explain_only", False)
            print(colored(f"Dry run: {'ON' if dry_run_enabled else 'OFF'}", "yellow" if dry_run_enabled else "green"))
            print(
                colored(
                    f"Explain-only mode: {'ON' if explain_only_enabled else 'OFF'}",
                    "yellow" if explain_only_enabled else "green",
                )
            )
            if getattr(self, "session_report_file", None):
                print(colored(f"Session report: {self.session_report_file}", "cyan"))
            if not has_initial_prompt:
                print(colored("Type 'e' for manual mode, or 'q' to quit.\n", "green"))

            if has_initial_prompt:
                prompt_preview = initial_prompt
                piped_marker = "\n\nPiped input:\n"
                if piped_marker in prompt_preview:
                    prompt_preview = f"{prompt_preview.split(piped_marker, 1)[0]}\n\n[stdin attached]"
                print(colored("Initial prompt:", "cyan"))
                print(colored(prompt_preview, "white"))
                print()
                try:
                    if not self._process_user_input(initial_prompt):
                        return
                except subprocess.CalledProcessError as exc:
                    print(
                        colored(f"Error: Command failed with exit code {exc.returncode}: {exc.output}", "red"),
                        file=sys.stderr,
                    )
                except KeyboardInterrupt:
                    if exit_after_initial_prompt:
                        return
                except EOFError:
                    return
                except Exception as exc:  # pylint: disable=broad-except
                    print(colored(f"Error of type {type(exc).__name__}: {exc}", "red"))
                    print(colored("Exiting...", "yellow"))
                    return

                if exit_after_initial_prompt:
                    return

            while True:
                try:
                    user_input = self.session.prompt(ANSI(colored(f"{APP_NAME}: ", "green")))
                    if not self._process_user_input(user_input):
                        break
                except subprocess.CalledProcessError as exc:
                    print(
                        colored(f"Error: Command failed with exit code {exc.returncode}: {exc.output}", "red"),
                        file=sys.stderr,
                    )
                except KeyboardInterrupt:
                    continue
                except EOFError:
                    break
                except Exception as exc:  # pylint: disable=broad-except
                    print(colored(f"Error of type {type(exc).__name__}: {exc}", "red"))
                    print(colored("Exiting...", "yellow"))
                    break
        finally:
            self._finalize_session_report()


class FileHistoryPath:
    @staticmethod
    def default():
        from os.path import expanduser

        return expanduser("~/.prompt2shell_history")

    @staticmethod
    def legacy():
        from os.path import expanduser

        return expanduser("~/.gpts_history")

    @staticmethod
    def exists(path):
        from os.path import exists

        return exists(path)
