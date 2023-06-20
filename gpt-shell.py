#!/usr/bin/env python3
import json
import os
import subprocess
import sys
import openai
from termcolor import colored
import platform
import distro
import tiktoken
from prompt_toolkit import ANSI, PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
import ast


class OpenAIHelper:
    def __init__(self, model_name="gpt-3.5-turbo", max_tokens=4096):
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        if self.api_key == "":
            print(colored("Error: OPENAI_API_KEY is not set", "red"), file=sys.stderr)
            exit(1)
        openai.api_key = self.api_key

        self.max_tokens = max_tokens
        self.remaning_tokens = max_tokens
        self.model_name = model_name
        # self.chat_message = [{"role": "system", "content": self.system_prompt}]
        self.chat_messages = []
        self.get_model_for_encoding(model_name)
        self.os_name, self.shell_name = OSHelper.get_os_and_shell_info()

        self.functions = [
            {
                "name": "get_commands",
                "description": f"Get a list of {self.shell_name} commands on an {self.os_name} machine",
                "parameters": {
                        "type": "object",
                        "properties": {
                            "commands": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "description": "A terminal command string"
                                },
                                "description": "List of terminal command strings to be executed"
                            }
                        },
                    "required": ["commands"]
                }
            }
        ]

    def get_model_for_encoding(self, model: str):
        if "gpt-3.5-turbo" in model:
            # model = "gpt-3.5-turbo-0301"
            # every message follows <|start|>{role/name}\n{content}<|end|>\n
            self.tokens_per_message = 4
            self.tokens_per_name = -1  # if there's a name, the role is omitted
        elif "gpt-4" in model:
            # model = "gpt-4-0301"
            self.tokens_per_message = 3
            self.tokens_per_name = 1
        else:
            print(colored(
                f"get_model_for_encoding() is not implemented for model {model}.", "red"), file=sys.stderr)
        try:
            self.encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            print(
                colored("Warning: model not found. Using cl100k_base encoding.", "yellow"))
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def get_chat_message_tokens(self):
        """Returns the number of tokens used by a list of messages."""
        num_tokens = 0
        for message in self.chat_messages:
            num_tokens += self.tokens_per_message
            for key, value in message.items():
                if key == "name":
                    num_tokens += self.tokens_per_name
                if value is None:
                    continue
                if type(value) == dict:
                    for k, v in value.items():
                        num_tokens += len(self.encoding.encode(v))
                    continue
                num_tokens += len(self.encoding.encode(value))

        num_tokens += 2  # every reply is primed with <|start|>assistant<|message|>
        return num_tokens

    def truncate_prompt(self, prompt):
        prompt_tokens = self.encoding.encode(prompt)
        count_prompt_tokens = len(prompt_tokens)
        max_prompt_tokens = self.max_tokens - 512 - self.tokens_per_message

        if count_prompt_tokens > max_prompt_tokens:
            prompt = self.encoding.decode(prompt_tokens[:max_prompt_tokens])
            # remove last line to avoid incomplete output
            prompt = prompt[:prompt.rfind("\n")]
            count_prompt_tokens = len(self.encoding.encode(prompt))
            print(colored(
                f"Warning: prompt was truncated to {count_prompt_tokens} tokens:\n", "yellow"),
                colored(f"{prompt}", "blue"), sep="")
        return prompt

    def truncate_chat_message(self):
        chat_message_tokens = self.get_chat_message_tokens()
        print(colored(
            f"before truncate_chat_message() chat message tokens: {chat_message_tokens}", "green"))
        while chat_message_tokens > self.max_tokens - 300:
            try:
                self.chat_messages.pop(0)
                chat_message_tokens = self.get_chat_message_tokens()
                print(colored(
                    f"truncate_chat_message() chat message tokens: {chat_message_tokens}", "green"))
            except IndexError:
                break

    def get_commands(self, prompt):
        user_message = {"role": "user", "content": prompt}
        self.chat_messages.append(user_message)

        self.truncate_chat_message()

        response = openai.ChatCompletion.create(
            model=self.model_name,
            messages=self.chat_messages,
            functions=self.functions,
            function_call={"name": "get_commands"},
        )

        commands = None
        if response is not None:
            if isinstance(response, dict):
                self.remaning_tokens = self.max_tokens - \
                    response['usage']['total_tokens']

                response_message = response['choices'][0].message
                if response_message.get("function_call"):
                    function_name = response_message["function_call"]["name"]

                    if function_name == "get_commands":
                        message_to_add = response_message.to_dict()
                        message_to_add["function_call"] = response_message["function_call"].to_dict(
                        )
                        self.chat_messages.append(message_to_add)
                        commands = json.loads(
                            response_message["function_call"]["arguments"])
                    else:
                        print(colored(
                            f"Warning: function {function_name} is not implemented.", "yellow"))

        return commands

    def send_commands_outputs(self, outputs):
        outputs = json.dumps(outputs)
        message = {
            "role": "function",
            "name": "get_commands",
            "content": outputs}
        self.chat_messages.append(message)

        self.truncate_chat_message()

        response = openai.ChatCompletion.create(
            model=self.model_name,
            messages=self.chat_messages,
            functions=self.functions,
            function_call='auto',
        )

        response_content = None
        commands = None
        if response is not None:
            if isinstance(response, dict):
                self.remaning_tokens = self.max_tokens - \
                    response['usage']['total_tokens']

                response_message = response['choices'][0].message
                response_message = response_message.to_dict()
                self.chat_messages.append(response_message)

                response_content = response_message['content']

                if response_message.get("function_call"):
                    function_name = response_message["function_call"]["name"]

                    if function_name == "get_commands":
                        message_to_add = response_message.to_dict()
                        message_to_add["function_call"] = response_message["function_call"].to_dict(
                        )
                        self.chat_messages.append(message_to_add)
                        commands = json.loads(
                            response_message["function_call"]["arguments"])
                    else:
                        print(colored(
                            f"Warning: function {function_name} is not implemented.", "yellow"))

        return response_content, commands


class CommandHelper:
    @staticmethod
    def run_shell_command(command):
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, universal_newlines=True)
        stdout = []

        # print(f"Output")
        for line in process.stdout:
            print(line, end="")
            stdout.append(line)

        stderr_data = process.stderr.read()
        if stderr_data:
            print(colored(f"Error\n{stderr_data}", "red"))

        process.wait()

        result = {"command": command, "stdout": ''.join(
            stdout), "stderr": stderr_data}

        if result["stdout"] != "":
            stdout_lines = result["stdout"].split("\n")
            for i, line in enumerate(stdout_lines):
                if "KEY" in line:
                    post_key_content = line[line.find("KEY") + 3:].strip()
                    if "=" in post_key_content:
                        stdout_lines[i] = line.split("=")[0] + "=<API_KEY>"
            result["stdout"] = "\n".join(stdout_lines)
        return result


class OSHelper:
    @staticmethod
    def get_os_and_shell_info():
        os_name = platform.system()
        shell_name = os.path.basename(os.environ.get("SHELL", ""))
        if os_name == "Linux":
            os_name += f" {distro.name()}"
        elif os_name == "Darwin":
            os_name += f" {platform.mac_ver()[0]}"
        elif os_name == "Windows":
            os_name += f" {platform.release()}"
        return os_name, shell_name


class Application:
    def __init__(self, openai_helper: OpenAIHelper, command_helper: CommandHelper):
        self.openai_helper = openai_helper
        self.command_helper = command_helper
        self.session = PromptSession(history=FileHistory(os.path.expanduser(
            '~') + "/.gpts_history"), auto_suggest=AutoSuggestFromHistory())

    def interpret_and_execute_command(self, user_prompt):
        if user_prompt == "e":
            self.manual_command_mode()
        else:
            self.auto_command_mode(user_prompt)

    def manual_command_mode(self):
        print(colored("Manual command mode activated. Please enter your command:", "green"))
        command_str = self.session.prompt("")
        command_output = self.command_helper.run_shell_command(command_str)
        # prompt = self.generate_prompt(command_str, command_output)

        # chatbot_reply = self.openai_helper.request_chatbot_response(prompt)
        # self.print_chatbot_response(chatbot_reply)
        # self.execute_commands_in_chatbot_response(chatbot_reply)

    def auto_command_mode(self, user_prompt):
        commands = self.openai_helper.get_commands(
            user_prompt)
        if commands is not None:
            self.execute_commands(commands)
        else:
            print(colored("No commands found", "red"))

    def execute_commands(self, commands):
        commands = commands["commands"]
        outputs = []
        while commands is not None:
            for command in commands:
                print(colored(f"{command}", "blue"))

                action = self.session.prompt(ANSI(
                    colored(f"Do you want to run (y) or edit (e) the command? (y/e/N): ", "green")))

                if action.lower() == "e":
                    command = self.session.prompt(ANSI(
                        colored("Enter the modified command: ", "cyan")), default=command)
                    action = self.session.prompt(ANSI(
                        colored(f"Do you want to run the command? (y/N): ", "green")))

                if action.lower() == "y":
                    output = self.command_helper.run_shell_command(command)
                    outputs.append(output)
                    # prompt = self.generate_prompt(command, command_output)

                    # chatbot_reply = self.openai_helper.request_chatbot_response(
                    #     prompt)
                    # self.print_chatbot_response(chatbot_reply)
                else:
                    print(colored("Skipping command", "yellow"))
                    break

            if len(outputs) > 0:
                response, commands = self.openai_helper.send_commands_outputs(
                    outputs)
                print(colored(f"Response\n{response}", "magenta"))

    def run(self):
        os_name, shell_name = OSHelper.get_os_and_shell_info()
        print(
            colored(f"Your current environment: Shell={shell_name}, OS={os_name}", "green"))
        print(colored(
            "Type 'e' to enter manual command mode or 'q' to quit, (tokens left)\n", "green"))

        while True:
            try:
                user_input = self.session.prompt(
                    ANSI(colored(f"ChatGPT ({self.openai_helper.remaning_tokens}) ({self.openai_helper.max_tokens - self.openai_helper.get_chat_message_tokens()})app: ", "green")))
                if user_input.lower() == 'q':
                    break
                self.interpret_and_execute_command(user_input)
            except subprocess.CalledProcessError as e:
                print(colored(
                    f"Error: Command failed with exit code {e.returncode}: {e.output}", "red"), file=sys.stderr)
            except KeyboardInterrupt:
                continue
            except EOFError:
                break
            # except Exception as e:
            #     print(
            #         colored(f"Error of type {type(e).__name__}: {e}", "red"), file=sys.stderr)
        print(colored("Exiting...", "yellow"))


if __name__ == "__main__":
    openai_helper = OpenAIHelper(  # model_name="gpt-3.5-turbo"
        model_name="gpt-3.5-turbo-0613"
    )
    command_helper = CommandHelper()
    application = Application(openai_helper, command_helper)
    application.run()
