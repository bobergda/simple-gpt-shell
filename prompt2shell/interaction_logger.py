import json
import os
import sys
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .command_helper import CommandHelper
from .common import APP_NAME, colored, env_flag


class InteractionLogger:
    """Helper class for logging user queries and assistant responses."""

    def __init__(self, log_file=None, enabled=None):
        app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        default_path = os.path.join(app_dir, "logs", "prompt2shell.log")
        configured_path = log_file or os.getenv("PROMPT2SHELL_LOG_FILE", default_path)
        resolved_path = os.path.expanduser(configured_path)
        if not os.path.isabs(resolved_path):
            resolved_path = os.path.join(app_dir, resolved_path)

        if enabled is None:
            self.enabled = env_flag("PROMPT2SHELL_LOG_ENABLED", False)
        else:
            self.enabled = bool(enabled)

        self.log_file = resolved_path
        self._lock = threading.Lock()
        self.session_entries = []
        self.session_started_at = datetime.now(timezone.utc).isoformat()
        self.session_id = uuid.uuid4().hex

        if not self.enabled:
            return

        log_dir = os.path.dirname(self.log_file)
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
        self.session_entries.append(entry)
        if not self.enabled:
            return

        flags = os.O_APPEND | os.O_CREAT | os.O_WRONLY
        with self._lock:
            file_descriptor = os.open(self.log_file, flags, 0o600)
            try:
                os.fchmod(file_descriptor, 0o600)
            except OSError:
                pass
            try:
                file_handle = os.fdopen(file_descriptor, "a", encoding="utf-8")
            except Exception:
                os.close(file_descriptor)
                raise
            with file_handle:
                file_handle.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def log(self, role, text):
        if not isinstance(text, str) or text.strip() == "":
            return

        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
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
            "session_id": self.session_id,
            "type": "event",
            "event": event_name,
            "data": self._sanitize_for_log(data),
        }

        try:
            self._write_entry(entry)
        except OSError as exc:
            print(colored(f"Warning: unable to write log: {exc}", "yellow"), file=sys.stderr)

    def get_session_entries(self, session_id=None, role=None, event_name=None):
        entries = list(self.session_entries)
        if session_id is not None:
            entries = [entry for entry in entries if entry.get("session_id") == session_id]
        if role is not None:
            entries = [entry for entry in entries if entry.get("role") == role]
        if event_name is not None:
            entries = [entry for entry in entries if entry.get("event") == event_name]
        return entries

    def export_session_report(self, report_file=None, metadata=None):
        metadata = self._sanitize_for_log(metadata or {})
        output_path = report_file or metadata.get("session_report_file")
        if not output_path:
            return None

        report_path = Path(os.path.expanduser(output_path))
        report_path.parent.mkdir(parents=True, exist_ok=True)

        lines = [
            f"# {APP_NAME} Session Report",
            "",
            f"- Session ID: `{self.session_id}`",
            f"- Started: {self.session_started_at}",
        ]
        if metadata.get("ended_at"):
            lines.append(f"- Ended: {metadata['ended_at']}")
        if metadata.get("model_name"):
            lines.append(f"- Model: `{metadata['model_name']}`")
        if metadata.get("shell_name"):
            lines.append(f"- Shell: `{metadata['shell_name']}`")
        if metadata.get("os_name"):
            lines.append(f"- OS: `{metadata['os_name']}`")
        if metadata.get("chat_language"):
            lines.append(f"- Chat language: `{metadata['chat_language']}`")
        if metadata.get("profile"):
            lines.append(f"- Profile: `{metadata['profile']}`")
        lines.extend(
            [
                f"- Safe mode: `{metadata.get('safe_mode', False)}`",
                f"- Strict safe mode: `{metadata.get('safe_mode_strict', False)}`",
                f"- Dry run: `{metadata.get('dry_run', False)}`",
                f"- Explain only: `{metadata.get('explain_only', False)}`",
                f"- JSON mode: `{metadata.get('json_mode', False)}`",
                "",
                "## Timeline",
                "",
            ]
        )

        for entry in self.session_entries:
            timestamp = entry.get("timestamp", "")
            if entry.get("type") == "event":
                lines.append(f"### Event `{entry.get('event', 'unknown')}`")
                lines.append("")
                lines.append(f"- Time: {timestamp}")
                data = entry.get("data")
                if data is not None:
                    lines.append("")
                    lines.append("```json")
                    lines.append(json.dumps(data, ensure_ascii=False, indent=2))
                    lines.append("```")
                lines.append("")
                continue

            role = entry.get("role", "unknown")
            lines.append(f"### {role.title()}")
            lines.append("")
            lines.append(f"- Time: {timestamp}")
            lines.append("")
            lines.append("```text")
            lines.append(str(entry.get("text", "")))
            lines.append("```")
            lines.append("")

        usage_summary = metadata.get("usage_summary")
        if isinstance(usage_summary, dict):
            lines.extend(
                [
                    "## Usage",
                    "",
                    "```json",
                    json.dumps(usage_summary, ensure_ascii=False, indent=2),
                    "```",
                    "",
                ]
            )

        report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return str(report_path.resolve())
