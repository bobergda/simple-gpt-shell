import os
import tempfile
import textwrap
import unittest
from unittest import mock

from prompt2shell.config import load_app_config


class AppConfigTests(unittest.TestCase):
    def test_load_app_config_reads_toml_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.toml")
            with open(config_path, "w", encoding="utf-8") as handle:
                handle.write(
                    textwrap.dedent(
                        """\
                        [openai]
                        model = "gpt-5-mini"
                        chat_language = "polish"

                        [app]
                        max_output_tokens = 2048
                        safe_mode = false
                        dry_run = true

                        [logging]
                        enabled = true
                        file = "./custom.log"

                        [report]
                        file = "./report.md"
                        """
                    )
                )

            config = load_app_config({"config_file": config_path})

        self.assertEqual(config.openai_model, "gpt-5-mini")
        self.assertEqual(config.chat_language, "polish")
        self.assertEqual(config.max_output_tokens, 2048)
        self.assertFalse(config.safe_mode)
        self.assertTrue(config.dry_run)
        self.assertTrue(config.log_enabled)
        self.assertTrue(config.log_file.endswith("custom.log"))
        self.assertTrue(config.session_report_file.endswith("report.md"))

    def test_cli_overrides_env_and_file_values(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = os.path.join(tmp_dir, "config.toml")
            with open(config_path, "w", encoding="utf-8") as handle:
                handle.write(
                    textwrap.dedent(
                        """\
                        [openai]
                        model = "gpt-4o-mini"

                        [app]
                        dry_run = false
                        """
                    )
                )

            with mock.patch.dict(
                os.environ,
                {
                    "OPENAI_MODEL": "gpt-env",
                    "PROMPT2SHELL_DRY_RUN": "0",
                },
                clear=False,
            ):
                config = load_app_config(
                    {
                        "config_file": config_path,
                        "openai_model": "gpt-cli",
                        "dry_run": True,
                    }
                )

        self.assertEqual(config.openai_model, "gpt-cli")
        self.assertTrue(config.dry_run)


if __name__ == "__main__":
    unittest.main()
