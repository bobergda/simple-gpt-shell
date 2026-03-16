import os
import tempfile
import unittest
from pathlib import Path

from prompt2shell.interaction_logger import InteractionLogger


class SessionReportTests(unittest.TestCase):
    def test_export_session_report_writes_markdown_summary(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            report_path = os.path.join(tmp_dir, "session.md")
            logger = InteractionLogger(log_file=os.path.join(tmp_dir, "session.log"), enabled=False)
            logger.log("user", "show git status")
            logger.log("assistant", "I will inspect the repository.")
            logger.log_event("command_previewed", {"command": "git status", "mode": "dry_run"})

            exported_path = logger.export_session_report(
                report_file=report_path,
                metadata={
                    "model_name": "gpt-test",
                    "shell_name": "zsh",
                    "os_name": "Darwin",
                    "chat_language": "polish",
                    "safe_mode": True,
                    "safe_mode_strict": False,
                    "dry_run": True,
                    "explain_only": False,
                    "usage_summary": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3, "api_calls": 1},
                },
            )

            self.assertEqual(exported_path, str(Path(report_path).resolve()))
            with open(report_path, "r", encoding="utf-8") as handle:
                content = handle.read()

        self.assertIn("# Prompt2Shell Agent Session Report", content)
        self.assertIn("## Timeline", content)
        self.assertIn("show git status", content)
        self.assertIn("command_previewed", content)
        self.assertIn("## Usage", content)


if __name__ == "__main__":
    unittest.main()
