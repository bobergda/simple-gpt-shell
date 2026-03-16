import unittest
from unittest import mock

from prompt2shell import main as main_module


class MainEntrypointTests(unittest.TestCase):
    @staticmethod
    def _stdin_patch(is_tty=True, text=""):
        fake_stdin = mock.Mock()
        fake_stdin.isatty.return_value = is_tty
        fake_stdin.read.return_value = text
        return mock.patch("prompt2shell.main.sys.stdin", fake_stdin)

    def test_main_runs_without_initial_prompt_when_no_argv(self):
        fake_app = mock.Mock()
        with self._stdin_patch(is_tty=True):
            with mock.patch("prompt2shell.main.build_application", return_value=fake_app):
                main_module.main([])

        fake_app.run.assert_called_once_with(initial_prompt=None, exit_after_initial_prompt=False)

    def test_main_passes_joined_argv_as_initial_prompt(self):
        fake_app = mock.Mock()
        with self._stdin_patch(is_tty=True):
            with mock.patch("prompt2shell.main.build_application", return_value=fake_app):
                main_module.main(["find", "largest", "files"])

        fake_app.run.assert_called_once_with(
            initial_prompt="find largest files",
            exit_after_initial_prompt=False,
        )

    def test_main_ignores_blank_initial_prompt(self):
        fake_app = mock.Mock()
        with self._stdin_patch(is_tty=True):
            with mock.patch("prompt2shell.main.build_application", return_value=fake_app):
                main_module.main(["   "])

        fake_app.run.assert_called_once_with(initial_prompt=None, exit_after_initial_prompt=False)

    def test_main_enables_once_mode_from_environment(self):
        fake_app = mock.Mock()
        with self._stdin_patch(is_tty=True):
            with mock.patch.dict("os.environ", {"PROMPT2SHELL_ONCE": "1"}, clear=False):
                with mock.patch("prompt2shell.main.build_application", return_value=fake_app):
                    main_module.main(["quick check"])

        fake_app.run.assert_called_once_with(
            initial_prompt="quick check",
            exit_after_initial_prompt=True,
        )

    def test_main_uses_piped_input_as_initial_prompt_without_auto_once(self):
        fake_app = mock.Mock()
        with self._stdin_patch(is_tty=False, text="file1\nfile2\n"):
            with mock.patch("prompt2shell.main.build_application", return_value=fake_app):
                main_module.main([])

        call_kwargs = fake_app.run.call_args.kwargs
        self.assertEqual(call_kwargs["exit_after_initial_prompt"], False)
        self.assertIn("Inferred source:", call_kwargs["initial_prompt"])
        self.assertIn("Piped input:\nfile1\nfile2", call_kwargs["initial_prompt"])

    def test_main_combines_prompt_args_with_piped_input(self):
        fake_app = mock.Mock()
        with self._stdin_patch(is_tty=False, text="a.txt\nb.txt\n"):
            with mock.patch("prompt2shell.main.build_application", return_value=fake_app):
                main_module.main(["summarize"])

        call_kwargs = fake_app.run.call_args.kwargs
        self.assertEqual(call_kwargs["exit_after_initial_prompt"], False)
        self.assertTrue(call_kwargs["initial_prompt"].startswith("summarize\n\nPipeline context:"))
        self.assertIn("Piped input:\na.txt\nb.txt", call_kwargs["initial_prompt"])

    def test_main_respects_explicit_once_env_value_when_piped(self):
        fake_app = mock.Mock()
        with self._stdin_patch(is_tty=False, text="hello\n"):
            with mock.patch.dict("os.environ", {"PROMPT2SHELL_ONCE": "0"}, clear=False):
                with mock.patch("prompt2shell.main.build_application", return_value=fake_app):
                    main_module.main([])

        call_kwargs = fake_app.run.call_args.kwargs
        self.assertEqual(call_kwargs["exit_after_initial_prompt"], False)
        self.assertIn("Piped input:\nhello", call_kwargs["initial_prompt"])

    def test_main_passes_mode_context_to_openai_helper(self):
        fake_openai_helper = mock.Mock()
        fake_app = mock.Mock()
        fake_app.openai_helper = fake_openai_helper

        with self._stdin_patch(is_tty=False, text="hello\n"):
            with mock.patch.dict("os.environ", {"PROMPT2SHELL_ONCE": "1"}, clear=False):
                with mock.patch("prompt2shell.main.build_application", return_value=fake_app):
                    main_module.main([])

        fake_openai_helper.configure_session_context.assert_called_once_with(
            once_mode=True,
            has_piped_input=True,
            profile="safe-edit",
        )

    def test_main_routes_json_mode_to_run_json(self):
        fake_app = mock.Mock()
        with self._stdin_patch(is_tty=True):
            with mock.patch("prompt2shell.main.build_application", return_value=fake_app):
                main_module.main(["--json", "summarize", "status"])

        fake_app.run_json.assert_called_once_with(initial_prompt="summarize status")
        fake_app.run.assert_not_called()

    def test_infer_piped_source_description_detects_ls_long_listing(self):
        piped_text = (
            "total 8\n"
            "-rw-r--r-- 1 user group 100 Jan 1 00:00 a.txt\n"
            "drwxr-xr-x 2 user group 4096 Jan 1 00:00 dir\n"
        )

        description = main_module.infer_piped_source_description(piped_text)
        self.assertIn("ls -l", description)


if __name__ == "__main__":
    unittest.main()
