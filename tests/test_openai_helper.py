import json
import os
import types
import unittest
from unittest import mock

from openai import RateLimitError

from prompt2shell.openai_helper import OpenAIHelper


class OpenAIHelperTests(unittest.TestCase):
    def test_get_commands_parses_function_call_payload(self):
        fake_responses = [
            types.SimpleNamespace(
                id="resp_1",
                usage=types.SimpleNamespace(input_tokens=10, output_tokens=20, total_tokens=30),
                output=[
                    types.SimpleNamespace(
                        type="function_call",
                        name="get_commands",
                        arguments=json.dumps(
                            {
                                "commands": [{"command": "ls -la", "description": "List files"}],
                                "response": "Here is the command.",
                            }
                        ),
                        call_id="call_1",
                        id="item_1",
                    )
                ],
                output_text=None,
            ),
            types.SimpleNamespace(
                id="resp_2",
                usage=types.SimpleNamespace(input_tokens=2, output_tokens=3, total_tokens=5),
                output=[],
                output_text="Done",
            ),
        ]

        class FakeResponsesAPI:
            def __init__(self, queue):
                self.queue = queue
                self.calls = []

            def create(self, **kwargs):
                self.calls.append(kwargs)
                return self.queue.pop(0)

        fake_api = FakeResponsesAPI(fake_responses)
        fake_client = types.SimpleNamespace(responses=fake_api)

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            with mock.patch("prompt2shell.openai_helper.OpenAI", return_value=fake_client):
                helper = OpenAIHelper(model_name="gpt-test", max_output_tokens=200)
                payload = helper.get_commands("show files")

        self.assertIsNotNone(payload)
        self.assertEqual(payload["commands"][0]["command"], "ls -la")
        self.assertEqual(payload["response"], "Here is the command.")
        self.assertEqual(helper.last_response_id, "resp_2")

        self.assertEqual(fake_api.calls[0]["tool_choice"], {"type": "function", "name": "get_commands"})
        self.assertEqual(fake_api.calls[1]["tool_choice"], "none")

    def test_instructions_include_session_mode_context(self):
        fake_responses = [
            types.SimpleNamespace(
                id="resp_1",
                usage=types.SimpleNamespace(input_tokens=10, output_tokens=20, total_tokens=30),
                output=[
                    types.SimpleNamespace(
                        type="function_call",
                        name="get_commands",
                        arguments=json.dumps(
                            {
                                "commands": [],
                                "response": "No commands needed.",
                            }
                        ),
                        call_id="call_1",
                        id="item_1",
                    )
                ],
                output_text=None,
            ),
            types.SimpleNamespace(
                id="resp_2",
                usage=types.SimpleNamespace(input_tokens=2, output_tokens=3, total_tokens=5),
                output=[],
                output_text="Done",
            ),
        ]

        class FakeResponsesAPI:
            def __init__(self, queue):
                self.queue = queue
                self.calls = []

            def create(self, **kwargs):
                self.calls.append(kwargs)
                return self.queue.pop(0)

        fake_api = FakeResponsesAPI(fake_responses)
        fake_client = types.SimpleNamespace(responses=fake_api)

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            with mock.patch("prompt2shell.openai_helper.OpenAI", return_value=fake_client):
                helper = OpenAIHelper(model_name="gpt-test", max_output_tokens=200)
                helper.configure_session_context(
                    once_mode=True,
                    has_piped_input=True,
                    safe_mode_enabled=True,
                    strict_safe_mode=True,
                )
                helper.get_commands("show files")

        instructions = fake_api.calls[0]["instructions"]
        self.assertIn("strict safe mode is ON", instructions)
        self.assertIn("piped command output is already provided", instructions)
        self.assertIn("one-shot mode", instructions)

    def test_instructions_include_polish_language_policy(self):
        fake_responses = [
            types.SimpleNamespace(
                id="resp_1",
                usage=types.SimpleNamespace(input_tokens=1, output_tokens=1, total_tokens=2),
                output=[
                    types.SimpleNamespace(
                        type="function_call",
                        name="get_commands",
                        arguments=json.dumps({"commands": [], "response": "Brak komend."}),
                        call_id="call_1",
                        id="item_1",
                    )
                ],
                output_text=None,
            ),
            types.SimpleNamespace(
                id="resp_2",
                usage=types.SimpleNamespace(input_tokens=1, output_tokens=1, total_tokens=2),
                output=[],
                output_text="Done",
            ),
        ]

        class FakeResponsesAPI:
            def __init__(self, queue):
                self.queue = queue
                self.calls = []

            def create(self, **kwargs):
                self.calls.append(kwargs)
                return self.queue.pop(0)

        fake_api = FakeResponsesAPI(fake_responses)
        fake_client = types.SimpleNamespace(responses=fake_api)

        with mock.patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "test-key",
                "PROMPT2SHELL_CHAT_LANGUAGE": "polish",
            },
            clear=False,
        ):
            with mock.patch("prompt2shell.openai_helper.OpenAI", return_value=fake_client):
                helper = OpenAIHelper(model_name="gpt-test", max_output_tokens=200)
                helper.get_commands("show files")

        instructions = fake_api.calls[0]["instructions"]
        self.assertIn("respond in Polish", instructions)
        self.assertNotIn("respond in English", instructions)

    def test_send_commands_outputs_analysis_only_disables_follow_up_commands(self):
        fake_responses = [
            types.SimpleNamespace(
                id="resp_1",
                usage=types.SimpleNamespace(input_tokens=5, output_tokens=7, total_tokens=12),
                output=[],
                output_text="The command listed files successfully.",
            )
        ]

        class FakeResponsesAPI:
            def __init__(self, queue):
                self.queue = queue
                self.calls = []

            def create(self, **kwargs):
                self.calls.append(kwargs)
                return self.queue.pop(0)

        fake_api = FakeResponsesAPI(fake_responses)
        fake_client = types.SimpleNamespace(responses=fake_api)

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            with mock.patch("prompt2shell.openai_helper.OpenAI", return_value=fake_client):
                helper = OpenAIHelper(model_name="gpt-test", max_output_tokens=200)
                response_text, next_commands = helper.send_commands_outputs(
                    outputs=[{"returncode": 0, "stdout": "file1\nfile2"}],
                    execution_summary=[{"command": "ls", "status": "executed"}],
                    allow_follow_up_commands=False,
                )

        self.assertEqual(response_text, "The command listed files successfully.")
        self.assertIsNone(next_commands)
        self.assertEqual(fake_api.calls[0]["tool_choice"], "none")
        self.assertIn("Do not propose or return any new commands.", fake_api.calls[0]["input"])

    def test_create_response_retries_rate_limit_errors(self):
        final_response = types.SimpleNamespace(
            id="resp_1",
            usage=types.SimpleNamespace(input_tokens=1, output_tokens=1, total_tokens=2),
            output=[
                types.SimpleNamespace(
                    type="function_call",
                    name="get_commands",
                    arguments=json.dumps({"commands": [], "response": "done"}),
                    call_id="call_1",
                    id="item_1",
                )
            ],
            output_text=None,
        )
        follow_up_response = types.SimpleNamespace(
            id="resp_2",
            usage=types.SimpleNamespace(input_tokens=1, output_tokens=1, total_tokens=2),
            output=[],
            output_text="Done",
        )

        response_stub = mock.Mock()
        response_stub.request = mock.Mock()
        response_stub.status_code = 429
        rate_limit_error = RateLimitError("slow down", response=response_stub, body=None)

        class FakeResponsesAPI:
            def __init__(self):
                self.calls = []
                self.attempts = 0

            def create(self, **kwargs):
                self.calls.append(kwargs)
                self.attempts += 1
                if self.attempts == 1:
                    raise rate_limit_error
                if self.attempts == 2:
                    return final_response
                return follow_up_response

        fake_api = FakeResponsesAPI()
        fake_client = types.SimpleNamespace(responses=fake_api)

        with mock.patch.dict(os.environ, {"OPENAI_API_KEY": "test-key"}, clear=False):
            with mock.patch("prompt2shell.openai_helper.OpenAI", return_value=fake_client):
                with mock.patch("prompt2shell.openai_helper.time.sleep") as sleep_mock:
                    helper = OpenAIHelper(model_name="gpt-test", max_output_tokens=200, max_retries=2, retry_base_seconds=0.1)
                    payload = helper.get_commands("show files")

        self.assertEqual(payload["response"], "done")
        sleep_mock.assert_called_once()
        self.assertEqual(fake_api.attempts, 3)


if __name__ == "__main__":
    unittest.main()
