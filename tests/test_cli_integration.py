import types
import unittest
from unittest import mock

from prompt2shell.application import Application


class FullCliFlowTests(unittest.TestCase):
    def test_run_initial_prompt_executes_single_command_flow(self):
        app = Application.__new__(Application)
        app.openai_helper = types.SimpleNamespace(
            os_name="Linux",
            shell_name="bash",
            model_name="gpt-test",
            chat_language="english",
            get_commands=mock.Mock(
                return_value={
                    "response": "I will inspect the repository.",
                    "commands": [{"command": "ls -la", "description": "List files"}],
                }
            ),
            send_commands_outputs=mock.Mock(
                side_effect=[
                    ("The command listed files.", None),
                    ("Inspection complete.", None),
                ]
            ),
            get_last_usage_summary=mock.Mock(return_value=None),
            get_session_usage_summary=mock.Mock(return_value={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "api_calls": 0}),
        )
        app.command_helper = mock.Mock()
        app.command_helper.detect_destructive_command.return_value = None
        app.command_helper.detect_non_readonly_command.return_value = None
        app.command_helper.run_shell_command.return_value = {
            "command": "ls -la",
            "stdout": "file1\nfile2\n",
            "stderr": "",
            "returncode": 0,
            "timed_out": False,
            "interrupted": False,
        }
        app.interaction_logger = mock.Mock()
        app.interaction_logger.session_id = "session-1"
        app.session = mock.Mock()
        app.session.prompt.side_effect = ["r"]
        app.settings = None
        app.safe_mode_enabled = True
        app.safe_mode_strict = False
        app.show_tokens = True
        app.profile = "safe-edit"
        app.dry_run = False
        app.explain_only = False
        app.json_mode = False
        app.session_report_file = None

        with mock.patch("prompt2shell.application.colored", side_effect=lambda text, *_a, **_k: text):
            with mock.patch("builtins.print"):
                app.run(initial_prompt="show files", exit_after_initial_prompt=True)

        app.openai_helper.get_commands.assert_called_once_with("show files")
        app.command_helper.run_shell_command.assert_called_once_with("ls -la")
        self.assertEqual(app.openai_helper.send_commands_outputs.call_count, 2)


if __name__ == "__main__":
    unittest.main()
