import io
import os
import re
import shlex
import signal
import sys
import time
import unittest
from unittest import mock

from prompt2shell.command_helper import CommandHelper


class CommandRuntimeTests(unittest.TestCase):
    def test_timeout_terminates_child_process_group(self):
        previous_timeout = os.environ.get("PROMPT2SHELL_COMMAND_TIMEOUT")
        os.environ["PROMPT2SHELL_COMMAND_TIMEOUT"] = "1"

        try:
            python_executable = shlex.quote(sys.executable)
            command = (
                f'{python_executable} -c "import subprocess,time,sys; '
                "p=subprocess.Popen(['sleep','30']); "
                'print(p.pid); sys.stdout.flush(); time.sleep(30)"'
            )
            result = CommandHelper(timeout_seconds=1).run_shell_command(command)
        finally:
            if previous_timeout is None:
                os.environ.pop("PROMPT2SHELL_COMMAND_TIMEOUT", None)
            else:
                os.environ["PROMPT2SHELL_COMMAND_TIMEOUT"] = previous_timeout

        self.assertTrue(result["timed_out"])
        self.assertFalse(result["interrupted"])

        match = re.search(r"^([0-9]+)$", result["stdout"], re.MULTILINE)
        self.assertIsNotNone(match, "child PID should be captured before timeout")
        child_pid = int(match.group(1))

        time.sleep(0.15)
        child_alive = True
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            child_alive = False
        except PermissionError:
            child_alive = True

        if child_alive:
            os.kill(child_pid, signal.SIGKILL)

        self.assertFalse(child_alive, "child process should be terminated after timeout")

    def test_keyboard_interrupt_sets_interrupted_flag(self):
        class FakeProcess:
            def __init__(self):
                self.stdout = io.StringIO("")
                self.stderr = io.StringIO("")
                self.pid = 999999
                self._wait_calls = 0

            def wait(self, timeout=None):
                self._wait_calls += 1
                if self._wait_calls == 1:
                    raise KeyboardInterrupt
                return 130

            def poll(self):
                if self._wait_calls < 2:
                    return None
                return 130

            def kill(self):
                return None

        fake_process = FakeProcess()

        with mock.patch("prompt2shell.command_helper.subprocess.Popen", return_value=fake_process):
            with mock.patch.object(CommandHelper, "_terminate_process_tree") as terminate_process_tree:
                result = CommandHelper(timeout_seconds=300).run_shell_command("echo hello")

        terminate_process_tree.assert_called_once_with(fake_process)
        self.assertTrue(result["interrupted"])
        self.assertFalse(result["timed_out"])
        self.assertEqual(result["returncode"], 130)


if __name__ == "__main__":
    unittest.main()
