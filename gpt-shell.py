#!/usr/bin/env python3
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


class OpenAIHelper:
    def __init__(self, system_prompt, model_name="gpt-3.5-turbo", max_tokens=4096):
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.model_name = model_name
        self.chat_message = [{"role": "system", "content": self.system_prompt}]
        self.get_model_for_encoding(model_name)

        if self.api_key == "":
            print(colored("Error: OPENAI_API_KEY is not set", "red"), file=sys.stderr)
            exit(1)
        openai.api_key = self.api_key

    def get_model_for_encoding(self, model):
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
        self.system_prompt_tokens = len(
            self.encoding.encode(self.system_prompt))

    def num_tokens_from_messages(self, messages):
        """Returns the number of tokens used by a list of messages."""
        num_tokens = 0
        for message in messages:
            num_tokens += self.tokens_per_message
            for key, value in message.items():
                num_tokens += len(self.encoding.encode(value))
                if key == "name":
                    num_tokens += self.tokens_per_name
        num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
        return num_tokens

    def truncate_prompt(self, prompt):
        prompt_tokens = self.encoding.encode(prompt)
        count_prompt_tokens = len(prompt_tokens)
        max_prompt_tokens = self.max_tokens - 512 - \
            self.system_prompt_tokens - self.tokens_per_message

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
        chat_message_tokens = self.num_tokens_from_messages(self.chat_message)
        # print(colored(
        #     f"before truncate_chat_message() chat message tokens: {chat_message_tokens}", "green"))
        while chat_message_tokens > self.max_tokens - 300:
            try:
                self.chat_message.pop(1)
                chat_message_tokens = self.num_tokens_from_messages(
                    self.chat_message)
                # print(colored(
                #     f"truncate_chat_message() chat message tokens: {chat_message_tokens}", "green"))
            except IndexError:
                break

    def request_chatbot_response(self, prompt):
        prompt = self.truncate_prompt(prompt)
        user_message = {"role": "user", "content": prompt}
        self.chat_message.append(user_message)

        self.truncate_chat_message()

        response = openai.ChatCompletion.create(
            model=self.model_name,
            messages=self.chat_message,
        )
        # print(colored(
        #     f'API resonse - total tokens: {response["usage"]["total_tokens"]} prompt tokens: {response["usage"]["prompt_tokens"]} completion tokens: {response["usage"]["completion_tokens"]}', "blue"))
        print(colored(
            f"Remaining tokens: {self.max_tokens - response['usage']['total_tokens']}", "green"))

        response_string = response['choices'][0]['message']['content']
        ai_message = {"role": "assistant", "content": response_string}
        self.chat_message.append(ai_message)

        return response_string


class CommandHelper:
    @staticmethod
    def run_shell_command(command):
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, universal_newlines=True)
        stdout = []

        print(f"=== Command output")
        for line in process.stdout:
            print(line, end="")
            stdout.append(line)

        stderr_data = process.stderr.read()
        if stderr_data:
            print(colored(f"=== Command error\n{stderr_data}", "red"))

        process.wait()

        result = {"stdout": ''.join(stdout), "stderr": stderr_data}

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
    def __init__(self, openai_helper, command_helper):
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
        prompt = self.generate_prompt(command_str, command_output)

        chatbot_reply = self.openai_helper.request_chatbot_response(prompt)
        self.print_chatbot_response(chatbot_reply)
        self.execute_commands_in_chatbot_response(chatbot_reply)

    def auto_command_mode(self, user_prompt):
        chatbot_reply = self.openai_helper.request_chatbot_response(
            user_prompt)
        self.print_chatbot_response(chatbot_reply)
        self.execute_commands_in_chatbot_response(chatbot_reply)

    def execute_commands_in_chatbot_response(self, chatbot_reply):
        while "```" in chatbot_reply:
            split_reply = chatbot_reply.split('```')
            commands_list = split_reply[1::2]
            command_str = '\n'.join(command.strip()
                                    for command in commands_list if command.strip() != "")
            if command_str == "":
                break

            print(colored(f"=== Command\n{command_str}", "blue"))

            action = self.session.prompt(ANSI(
                colored(f"Do you want to run (y) or edit (e) the command? (y/e/N): ", "green")))

            if action.lower() == "e":
                command_str = self.session.prompt(ANSI(
                    colored("Enter the modified command: ", "cyan")), default=command_str)
                action = self.session.prompt(ANSI(
                    colored(f"Do you want to run the command? (y/N): ", "green")))

            if action.lower() == "y":
                command_output = self.command_helper.run_shell_command(
                    command_str)
                prompt = self.generate_prompt(command_str, command_output)

                chatbot_reply = self.openai_helper.request_chatbot_response(
                    prompt)
                self.print_chatbot_response(chatbot_reply)
            else:
                break

    @staticmethod
    def print_chatbot_response(chatbot_reply):
        print(colored(f"=== Response\n{chatbot_reply}", "magenta"))

    @staticmethod
    def generate_prompt(command_str, command_output):
        prompt = f"Analyze command '{command_str}' output:\n{command_output['stdout']}"
        if command_output['stderr'] != "":
            prompt += f"\nError output:\n{command_output['stderr']}"
        # print(colored(f"=== Prompt\n{prompt}", "blue"))
        return prompt

    def run(self):
        os_name, shell_name = OSHelper.get_os_and_shell_info()
        print(
            colored(f"Your current environment: Shell={shell_name}, OS={os_name}", "green"))
        print(colored("Type 'e' to enter manual command mode or 'q' to quit\n", "green"))

        while True:
            try:
                user_input = self.session.prompt(
                    ANSI(colored("ChatGPT: ", "green")))
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
            except Exception as e:
                print(
                    colored(f"Error of type {type(e).__name__}: {e}", "red"), file=sys.stderr)
        print(colored("Exiting...", "yellow"))


if __name__ == "__main__":
    os_name, shell_name = OSHelper.get_os_and_shell_info()
    system_prompt = f"""Provide {shell_name} commands for {os_name}.
    If details are missing, suggest the most logical solution.
    Don't show example output.
    Don't add shell interpreter (e.g. bash).
    Use ``` only to separate commands.
    """
    openai_helper = OpenAIHelper(system_prompt,
                                 model_name="gpt-3.5-turbo"
                                 # model_name="gpt-3.5-turbo-0613"
                                 )
    command_helper = CommandHelper()
    application = Application(openai_helper, command_helper)
    application.run()
