import types
import unittest
from unittest import mock

from prompt2shell.application import Application


class ApplicationRunBannerTests(unittest.TestCase):
    def _build_app(self):
        app = Application.__new__(Application)
        app.openai_helper = types.SimpleNamespace(
            os_name="Linux",
            shell_name="bash",
            model_name="gpt-test",
            chat_language="polish",
            get_session_usage_summary=lambda: {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0, "api_calls": 0},
        )
        app.interaction_logger = mock.Mock()
        app.session = mock.Mock()
        app._process_user_input = mock.Mock(return_value=False)
        app.safe_mode_enabled = True
        app.safe_mode_strict = False
        app.show_tokens = True
        app.dry_run = False
        app.explain_only = False
        app.session_report_file = None
        return app

    def test_run_shows_interactive_hint_without_initial_prompt(self):
        app = self._build_app()
        app.session.prompt.return_value = "q"

        with mock.patch("prompt2shell.application.colored", side_effect=lambda text, *_a, **_k: text):
            with mock.patch("builtins.print") as print_mock:
                app.run(initial_prompt=None)

        printed_lines = [str(call.args[0]) for call in print_mock.call_args_list if call.args]
        self.assertTrue(
            any(
                "Environment: shell=bash | OS=Linux | model=gpt-test | chat language=polish" in line
                for line in printed_lines
            )
        )
        self.assertTrue(any("Type 'e' for manual mode, or 'q' to quit." in line for line in printed_lines))

    def test_run_hides_interactive_hint_with_initial_prompt(self):
        app = self._build_app()
        app._process_user_input = mock.Mock(return_value=True)

        with mock.patch("prompt2shell.application.colored", side_effect=lambda text, *_a, **_k: text):
            with mock.patch("builtins.print") as print_mock:
                app.run(initial_prompt="show files", exit_after_initial_prompt=True)

        printed_lines = [str(call.args[0]) for call in print_mock.call_args_list if call.args]
        self.assertFalse(any("Type 'e' for manual mode, or 'q' to quit." in line for line in printed_lines))
        self.assertTrue(any("Initial prompt:" in line for line in printed_lines))
        self.assertTrue(any(line.strip() == "show files" for line in printed_lines))
        app._process_user_input.assert_called_once_with("show files")

    def test_run_shows_compact_preview_for_piped_initial_prompt(self):
        app = self._build_app()
        app._process_user_input = mock.Mock(return_value=True)
        initial_prompt = "summarize\n\nPipeline context: likely ls.\n\nPiped input:\nfile1\nfile2"

        with mock.patch("prompt2shell.application.colored", side_effect=lambda text, *_a, **_k: text):
            with mock.patch("builtins.print") as print_mock:
                app.run(initial_prompt=initial_prompt, exit_after_initial_prompt=True)

        printed_lines = [str(call.args[0]) for call in print_mock.call_args_list if call.args]
        self.assertTrue(any("Initial prompt:" in line for line in printed_lines))
        self.assertTrue(any("[stdin attached]" in line for line in printed_lines))
        self.assertFalse(any("file1" in line for line in printed_lines))
        app._process_user_input.assert_called_once_with(initial_prompt)


class ApplicationInitTests(unittest.TestCase):
    def test_init_prefers_tty_io_for_prompt_session(self):
        fake_history = mock.Mock()
        fake_auto = mock.Mock()
        fake_input = mock.Mock()
        fake_output = mock.Mock()
        fake_session = mock.Mock()

        openai_helper = types.SimpleNamespace(os_name="Linux", shell_name="bash", model_name="gpt-test")
        command_helper = mock.Mock()
        interaction_logger = mock.Mock()

        with mock.patch("prompt2shell.application.FileHistoryPath.default", return_value="/tmp/default.hist"):
            with mock.patch("prompt2shell.application.FileHistoryPath.legacy", return_value="/tmp/legacy.hist"):
                with mock.patch("prompt2shell.application.FileHistoryPath.exists", return_value=True):
                    with mock.patch("prompt2shell.application.FileHistory", return_value=fake_history):
                        with mock.patch("prompt2shell.application.AutoSuggestFromHistory", return_value=fake_auto):
                            with mock.patch("prompt2shell.application.create_input", return_value=fake_input) as create_input_mock:
                                with mock.patch("prompt2shell.application.create_output", return_value=fake_output) as create_output_mock:
                                    with mock.patch("prompt2shell.application.PromptSession", return_value=fake_session) as prompt_session_mock:
                                        app = Application(openai_helper, command_helper, interaction_logger)

        create_input_mock.assert_called_once_with(always_prefer_tty=True)
        create_output_mock.assert_called_once_with(always_prefer_tty=True)
        prompt_session_mock.assert_called_once_with(
            history=fake_history,
            auto_suggest=fake_auto,
            input=fake_input,
            output=fake_output,
        )
        self.assertIs(app.session, fake_session)


class ApplicationCommandSelectionTests(unittest.TestCase):
    def _build_exec_app(self):
        app = Application.__new__(Application)
        app.openai_helper = mock.Mock()
        app.openai_helper.send_commands_outputs.return_value = (None, None)
        app.command_helper = mock.Mock()
        app.command_helper.run_shell_command.return_value = {
            "returncode": 0,
            "timed_out": False,
            "interrupted": False,
        }
        app.interaction_logger = mock.Mock()
        app.session = mock.Mock()
        app._guard_command_with_safe_mode = mock.Mock(side_effect=lambda command: (command, None))
        app._print_commands_batch = mock.Mock()
        app._sync_openai_session_context = mock.Mock()
        app._print_assistant_response = mock.Mock()
        app._print_token_usage = mock.Mock()
        app.safe_mode_enabled = True
        app.safe_mode_strict = False
        app.show_tokens = True
        app.dry_run = False
        app.explain_only = False
        app.session_report_file = None
        return app

    def test_prompt_command_action_accepts_numeric_selection(self):
        app = self._build_exec_app()
        app.session.prompt.return_value = "2"

        with mock.patch("prompt2shell.application.colored", side_effect=lambda text, *_a, **_k: text):
            action = app._prompt_command_action(index=1, total=3)

        self.assertEqual(action, "2")

    def test_execute_commands_runs_selected_command_by_number(self):
        app = self._build_exec_app()
        app._prompt_command_action = mock.Mock(side_effect=["2"])

        commands = [
            {"command": "echo one", "description": "first"},
            {"command": "echo two", "description": "second"},
        ]
        with mock.patch("builtins.print"):
            app.execute_commands(commands)

        app._prompt_command_action.assert_called_once_with(1, 2)
        app.command_helper.run_shell_command.assert_called_once_with("echo two")
        self.assertEqual(app.openai_helper.send_commands_outputs.call_count, 2)
        first_call, second_call = app.openai_helper.send_commands_outputs.call_args_list
        self.assertEqual(len(first_call.args), 1)
        self.assertEqual(len(first_call.args[0]), 1)
        self.assertEqual(first_call.kwargs.get("allow_follow_up_commands"), False)
        self.assertEqual(len(second_call.args), 1)
        self.assertEqual(len(second_call.args[0]), 1)
        self.assertEqual(second_call.kwargs.get("allow_follow_up_commands"), True)

    def test_execute_commands_analyzes_each_executed_command_immediately(self):
        app = self._build_exec_app()
        app._prompt_command_action = mock.Mock(side_effect=["r", "r"])
        app.command_helper.run_shell_command.side_effect = [
            {"returncode": 0, "timed_out": False, "interrupted": False, "stdout": "one"},
            {"returncode": 0, "timed_out": False, "interrupted": False, "stdout": "two"},
        ]

        commands = [
            {"command": "echo one", "description": "first"},
            {"command": "echo two", "description": "second"},
        ]
        with mock.patch("builtins.print"):
            app.execute_commands(commands)

        self.assertEqual(app.openai_helper.send_commands_outputs.call_count, 3)
        for call in app.openai_helper.send_commands_outputs.call_args_list[:-1]:
            self.assertEqual(len(call.args), 1)
            self.assertEqual(len(call.args[0]), 1)
            self.assertEqual(call.kwargs.get("allow_follow_up_commands"), False)
        final_call = app.openai_helper.send_commands_outputs.call_args_list[-1]
        self.assertEqual(len(final_call.args), 1)
        self.assertEqual(len(final_call.args[0]), 2)
        self.assertEqual(final_call.kwargs.get("allow_follow_up_commands"), True)
        self.assertEqual(app._print_token_usage.call_count, 3)

    def test_execute_commands_run_all_waits_for_single_final_ai_call(self):
        app = self._build_exec_app()
        app._prompt_command_action = mock.Mock(side_effect=["a"])
        app.command_helper.run_shell_command.side_effect = [
            {"returncode": 0, "timed_out": False, "interrupted": False, "stdout": "one"},
            {"returncode": 0, "timed_out": False, "interrupted": False, "stdout": "two"},
        ]

        commands = [
            {"command": "echo one", "description": "first"},
            {"command": "echo two", "description": "second"},
        ]
        with mock.patch("builtins.print"):
            app.execute_commands(commands)

        self.assertEqual(app.command_helper.run_shell_command.call_count, 2)
        app._prompt_command_action.assert_called_once_with(1, 2)
        app.openai_helper.send_commands_outputs.assert_called_once()
        call = app.openai_helper.send_commands_outputs.call_args
        self.assertEqual(len(call.args), 1)
        self.assertEqual(len(call.args[0]), 2)
        self.assertEqual(call.kwargs.get("allow_follow_up_commands"), True)
        self.assertEqual(app._print_token_usage.call_count, 1)

    def test_execute_commands_runs_follow_up_batch_returned_by_ai(self):
        app = self._build_exec_app()
        app._prompt_command_action = mock.Mock(side_effect=["a", "a"])
        app.command_helper.run_shell_command.side_effect = [
            {"returncode": 0, "timed_out": False, "interrupted": False, "stdout": "one"},
            {"returncode": 0, "timed_out": False, "interrupted": False, "stdout": "next"},
        ]
        app.openai_helper.send_commands_outputs.side_effect = [
            ("first done", [{"command": "echo next", "description": "next step"}]),
            ("second done", None),
        ]

        commands = [{"command": "echo one", "description": "first"}]
        with mock.patch("builtins.print"):
            app.execute_commands(commands)

        self.assertEqual(app.command_helper.run_shell_command.call_count, 2)
        self.assertEqual(
            [call.args[0] for call in app.command_helper.run_shell_command.call_args_list],
            ["echo one", "echo next"],
        )
        self.assertEqual(app.openai_helper.send_commands_outputs.call_count, 2)
        for call in app.openai_helper.send_commands_outputs.call_args_list:
            self.assertEqual(call.kwargs.get("allow_follow_up_commands"), True)

    def test_auto_command_mode_in_explain_only_previews_without_execution(self):
        app = self._build_exec_app()
        app.explain_only = True
        app.openai_helper.get_commands.return_value = {
            "response": "Preview only.",
            "commands": [{"command": "ls -la", "description": "inspect files"}],
        }
        app.execute_commands = mock.Mock()

        with mock.patch("builtins.print"):
            app.auto_command_mode("show files")

        app.execute_commands.assert_not_called()
        app._print_commands_batch.assert_called_once()

    def test_manual_command_mode_dry_run_skips_execution(self):
        app = self._build_exec_app()
        app.dry_run = True
        app.session.prompt.side_effect = ["echo hello"]
        app._prompt_yes_no = mock.Mock(return_value=True)
        app._guard_command_with_safe_mode = mock.Mock(return_value=("echo hello", None))

        with mock.patch("builtins.print"):
            app.manual_command_mode()

        app.command_helper.run_shell_command.assert_not_called()
        app.interaction_logger.log_event.assert_any_call("command_previewed", {"command": "echo hello", "mode": "manual"})


if __name__ == "__main__":
    unittest.main()
