import unittest

from prompt2shell.command_helper import CommandHelper


class CommandHelperDetectionTests(unittest.TestCase):
    def test_detect_destructive_command(self):
        reason = CommandHelper.detect_destructive_command("rm -rf ./tmp")
        self.assertIsNotNone(reason)
        self.assertIn("rm", reason)

    def test_non_destructive_command_not_flagged(self):
        self.assertIsNone(CommandHelper.detect_destructive_command("ls -la"))

    def test_detects_xargs_destructive_pipeline(self):
        reason = CommandHelper.detect_destructive_command("find . -print0 | xargs -0 rm -rf")
        self.assertIsNotNone(reason)
        self.assertIn("xargs", reason)

    def test_detects_recursive_chmod_as_high_risk(self):
        reason = CommandHelper.detect_destructive_command("sudo chmod -R 777 /tmp/demo")
        self.assertIsNotNone(reason)
        self.assertIn("chmod", reason)

    def test_redacts_common_secret_patterns(self):
        text = (
            "Authorization: Bearer super-secret-token\n"
            "OPENAI_API_KEY=sk-1234567890abcdef\n"
            "jwt=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc.def\n"
        )
        redacted = CommandHelper.redact_sensitive_text(text)
        self.assertIn("Bearer <REDACTED>", redacted)
        self.assertIn("<REDACTED>", redacted)
        self.assertIn("<REDACTED_JWT>", redacted)
        self.assertNotIn("super-secret-token", redacted)


class StrictSafeModeTests(unittest.TestCase):
    def test_allows_read_only_pipeline(self):
        reason = CommandHelper.detect_non_readonly_command("ls -la | head -n 5")
        self.assertIsNone(reason)

    def test_blocks_non_allowlisted_binary(self):
        reason = CommandHelper.detect_non_readonly_command("python -c 'print(1)'")
        self.assertIsNotNone(reason)
        self.assertIn("not in strict read-only allowlist", reason)

    def test_blocks_find_delete(self):
        reason = CommandHelper.detect_non_readonly_command("find . -delete")
        self.assertIsNotNone(reason)
        self.assertIn("-delete", reason)

    def test_blocks_sed_in_place(self):
        reason = CommandHelper.detect_non_readonly_command("sed -i 's/a/b/' file.txt")
        self.assertIsNotNone(reason)
        self.assertIn("in-place", reason)

    def test_blocks_tee_file_output(self):
        reason = CommandHelper.detect_non_readonly_command("echo hi | tee output.txt")
        self.assertIsNotNone(reason)
        self.assertIn("tee", reason)

    def test_blocks_control_operators(self):
        reason = CommandHelper.detect_non_readonly_command("ls && pwd")
        self.assertIsNotNone(reason)
        self.assertIn("chaining", reason)

    def test_allows_separator_inside_quotes(self):
        reason = CommandHelper.detect_non_readonly_command("printf 'a && b'")
        self.assertIsNone(reason)

    def test_blocks_sudo_wrapped_non_allowlisted_binary(self):
        reason = CommandHelper.detect_non_readonly_command("sudo python -c 'print(1)'")
        self.assertIsNotNone(reason)
        self.assertIn("not in strict read-only allowlist", reason)


if __name__ == "__main__":
    unittest.main()
