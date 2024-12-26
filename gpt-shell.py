#!/usr/bin/env python3
import json
import os
import subprocess
import sys
from openai import OpenAI
from termcolor import colored
import platform
import distro
import tiktoken
from prompt_toolkit import ANSI, PromptSession, prompt
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory


class OpenAIHelper:
    """A class that handles the OpenAI API calls."""

    def __init__(self, model_name="gpt-4", max_tokens=4096):
        """Initializes the OpenAIHelper class."""
        self.api_key = os.getenv("OPENAI_API_KEY", "")
        if self.api_key == "":
            print(colored("Error: OPENAI_API_KEY is not set", "red"), file=sys.stderr)
            exit(1)
        self.client = OpenAI(api_key=self.api_key)

        self.max_tokens = max_tokens
        self.remaning_tokens = max_tokens
        self.model_name = model_name
        self.all_messages = []
        self.get_model_for_encoding(model_name)
        self.os_name, self.shell_name = OSHelper.get_os_and_shell_info()

        self.tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_commands",
                    "description": f"Get a list of {self.shell_name} commands on an {self.os_name} machine",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "commands": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "command": {
                                            "type": "string",
                                            "description": "A valid command string"
                                        },
                                        "description": {
                                            "type": "string",
                                            "description": "Description of the command"
                                        }
                                    },
                                    "required": ["command"]
                                },
                                "description": "List of terminal command objects to be executed"
                            },
                            "response": {
                                "type": "string",
                                "description": "Give me a detailed description of what you want to do",
                            }
                        },
                        "required": ["commands", "response"]
                    }
                }
            }
        ]

    def get_model_for_encoding(self, model: str):
        """
        Configures encoding settings and token counts for a given model.

        Args:
            model (str): The name of the model.

        Raises:
            ValueError: If the model is not supported.
        """
        try:
            # Token settings for known models
            if "gpt-3.5-turbo" in model:
                self.tokens_per_message = 4
                self.tokens_per_name = -1  # If there's a name, the role is omitted.
            elif "gpt-4" in model:
                self.tokens_per_message = 3
                self.tokens_per_name = 1
            elif "gpt-4o" in model:
                self.tokens_per_message = 6
                self.tokens_per_name = 2
            elif "gpt-4o-mini" in model:
                self.tokens_per_message = 5
                self.tokens_per_name = 1
            else:
                raise ValueError(f"Model {model} is not supported.")

            # Attempt to fetch encoding for the model
            self.encoding = tiktoken.encoding_for_model(model)

        except ValueError as e:
            print(colored(f"Error: {e}", "red"), file=sys.stderr)
            raise

        except KeyError:
            print(colored(f"Warning: Model {model} not found. Using 'cl100k_base' encoding.", "yellow"))
            self.encoding = tiktoken.get_encoding("cl100k_base")

    def get_all_message_tokens(self):
        """Returns the number of tokens used by a list of messages."""
        num_tokens = 0
        for message in self.all_messages:
            num_tokens += self.tokens_per_message
            for key, value in message.items():
                if key == "name":
                    num_tokens += self.tokens_per_name
                if value is None:
                    continue
                if isinstance(value, dict):
                    for k, v in value.items():
                        if isinstance(v, str):
                            num_tokens += len(self.encoding.encode(v))
                    continue
                if isinstance(value, list):
                    for item in value:
                        if isinstance(item, str):  # Encode each string item in the list
                            num_tokens += len(self.encoding.encode(item))
                elif isinstance(value, str):  # Encode only if it's a string
                    num_tokens += len(self.encoding.encode(value))

        num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
        return num_tokens


    def truncate_outputs(self, outputs):
        """Truncates the outputs list so that the total tokens fit the max_tokens limit."""
        max_tokens = self.max_tokens - self.max_tokens // 2
        outputs_tokens = []
        total_tokens = 0
        for i in range(len(outputs)):
            tokens = {"index": i,
                      "command": self.encoding.encode(outputs[i]["command"]),
                      "stdout": self.encoding.encode(outputs[i]["stdout"]),
                      "stderr": self.encoding.encode(outputs[i]["stderr"])}

            tokens["total"] = len(tokens["command"]) + \
                len(tokens["stdout"]) + len(tokens["stderr"])
            total_tokens += tokens["total"]

            outputs_tokens.append(tokens)

        if total_tokens <= max_tokens:
            return outputs
        tokens_to_remove = total_tokens - max_tokens

        # Sort by the length of tokens in ascending order
        outputs_tokens.sort(key=lambda x: x["total"])

        half_max_tokens = max_tokens // 2
        total_tokens_half = 0
        index_to_start_truncate = 0

        for tokens in outputs_tokens:
            if total_tokens_half + tokens["total"] > half_max_tokens:
                break
            total_tokens_half += tokens["total"]
            index_to_start_truncate += 1

        remaining_tokens = total_tokens - total_tokens_half

        for i in range(index_to_start_truncate, len(outputs_tokens)):
            # count procent of remaining tokens
            procent = outputs_tokens[i]["total"] / remaining_tokens
            tokens_to_remove_in_this_iteration = int(
                tokens_to_remove * procent)

            if tokens_to_remove_in_this_iteration > 0:
                tokens_to_remove -= tokens_to_remove_in_this_iteration
                total_tokens -= tokens_to_remove_in_this_iteration
                outputs_tokens[i]["stdout"] = outputs_tokens[i]["stdout"][:-
                                                                          tokens_to_remove_in_this_iteration]

                outputs_tokens[i]["total"] = len(outputs_tokens[i]["command"]) + \
                    len(outputs_tokens[i]["stdout"]) + \
                    len(outputs_tokens[i]["stderr"])

                outputs[outputs_tokens[i]["index"]]["stdout"] = self.encoding.decode(
                    outputs_tokens[i]["stdout"])

        return outputs

    def truncate_chat_message(self):
        """Truncates the chat message list so that the total tokens fit the max_tokens limit."""
        max_tokens = self.max_tokens - 400
        all_message_tokens = self.get_all_message_tokens()

        while all_message_tokens > max_tokens:
            try:
                message = self.all_messages.pop(0)
                all_message_tokens = self.get_all_message_tokens()
            except IndexError:
                break
            pass

    def get_commands(self, prompt):
        """Returns a list of commands to be executed."""
        message = {
            "role": "user",
            "content": prompt
        }
        self.all_messages.append(message)

        self.truncate_chat_message()

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=self.all_messages,
            tools=self.tools,
            tool_choice={"type": "function", "function": {"name": "get_commands"}},
        )

        commands = None
        try:
            response_message = response.choices[0].message
            if response_message.tool_calls:
                for tool_call in response_message.tool_calls:
                    function_call = tool_call.function
                    tool_call_id = tool_call.id

                    # Append a tool response for each tool_call
                    tool_response = {
                        "role": "function",
                        "name": function_call.name,
                        "content": f"Tool response for {tool_call_id}",
                    }
                    self.all_messages.append(tool_response)

                    commands = json.loads(function_call.arguments)

                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": response_message.tool_calls
                }
                self.all_messages.append(message)
        except Exception as e:
            print(colored(f"Error: {e}", "red"), file=sys.stderr)
            return None

        return commands

    def send_commands_outputs(self, outputs):
        """Sends the outputs of executed commands back to OpenAI and retrieves the response."""
        # Truncate outputs to fit within the token limit
        outputs = self.truncate_outputs(outputs)

        # Create a tool response message
        outputs_json = json.dumps(outputs)
        tool_response_message = {
            "role": "tool",
            "name": "get_commands",
            "content": outputs_json,
            "tool_call_id": self.last_tool_call_id if hasattr(self, 'last_tool_call_id') else None
        }
        if hasattr(self, 'last_tool_call_id'):
            self.all_messages.append(tool_response_message)

        # Add a user prompt for detailed explanation
        prompt_message = {
            "role": "user",
            "content": "Explain the result in detail."
        }
        self.all_messages.append(prompt_message)

        # Truncate chat messages to fit token limits
        self.truncate_chat_message()

        try:
            # Send the updated conversation to the OpenAI API
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=self.all_messages,
                tools=self.tools,
                tool_choice='auto',
            )

            # Parse the response
            response_content = None
            commands = None
            response_message = response.choices[0].message
            
            # Add the assistant's response to messages
            self.all_messages.append({
                "role": "assistant",
                "content": response_message.content if response_message.content else None,
                "tool_calls": [tool_call.model_dump() for tool_call in response_message.tool_calls] if response_message.tool_calls else None
            })

            # If there are tool calls, handle them
            if response_message.tool_calls:
                for tool_call in response_message.tool_calls:
                    self.last_tool_call_id = tool_call.id
                    # Add tool response message
                    if tool_call.function.name == "get_commands":
                        commands = json.loads(tool_call.function.arguments)

            response_content = response_message.content
            return response_content, commands

        except Exception as e:
            print(colored(f"Error: {e}", "red"), file=sys.stderr)
            return None


class CommandHelper:
    """Helper class for executing commands."""

    @staticmethod
    def run_shell_command(command):
        process = subprocess.Popen(command, shell=True, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, universal_newlines=True)
        stdout = []

        for line in process.stdout:
            print(line, end="")
            stdout.append(line)

        stderr_data = process.stderr.read()
        if stderr_data:
            print(colored(f"Error\n{stderr_data}", "red"))

        process.wait()

        output = {"command": command, "stdout": ''.join(
            stdout), "stderr": stderr_data}

        if output["stdout"] != "":
            stdout_lines = output["stdout"].split("\n")
            for i, line in enumerate(stdout_lines):
                if "KEY" in line:
                    post_key_content = line[line.find("KEY") + 3:].strip()
                    if "=" in post_key_content:
                        stdout_lines[i] = line.split("=")[0] + "=<API_KEY>"
            output["stdout"] = "\n".join(stdout_lines)
        return output


class OSHelper:
    """Helper class for getting OS and shell information."""

    @staticmethod
    def get_os_and_shell_info():
        """Returns the OS and shell information."""
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
    """Main application class."""

    def __init__(self, openai_helper: OpenAIHelper, command_helper: CommandHelper):
        """Initializes the application."""
        self.openai_helper = openai_helper
        self.command_helper = command_helper
        self.session = PromptSession(history=FileHistory(os.path.expanduser(
            '~') + "/.gpts_history"), auto_suggest=AutoSuggestFromHistory())

    def interpret_and_execute_command(self, user_prompt):
        """Interprets and executes the command."""
        if user_prompt == "e":
            self.manual_command_mode()
        else:
            self.auto_command_mode(user_prompt)

    def manual_command_mode(self):
        """Manual command mode."""
        print(colored("Manual command mode activated. Please enter your command:", "green"))
        command_str = self.session.prompt("")
        command_output = self.command_helper.run_shell_command(command_str)
        outputs = [command_output]

        response, commands = self.openai_helper.send_commands_outputs(outputs)
        print(colored(f"{response}", "magenta"))

        if commands is not None:
            self.execute_commands(commands)

    def auto_command_mode(self, user_prompt):
        """Auto command mode."""
        commands = self.openai_helper.get_commands(user_prompt)
        if commands is not None:
            self.execute_commands(commands["commands"])
        else:
            print(colored("No commands found", "red"))

    def execute_commands(self, commands):
        """Executes the commands."""
        outputs = []
        action = ""
        while commands is not None:
            commands_list = [command["command"] for command in commands]
            print(colored(f"List of commands {commands_list}", "magenta"))
            for command in commands:
                command_str = command["command"]
                print(colored(f"{command['description']}", "magenta"))
                print(colored(f"{command_str}", "blue"))

                if action.lower() != "a":
                    action = prompt(ANSI(
                        colored(f"Do you want to run (y), edit (e), or execute all (a) commands? (y/e/a/N): ", "green")))

                if action.lower() == "e":
                    command_str = self.session.prompt(ANSI(
                        colored("Enter the modified command: ", "cyan")), default=command_str)
                    action = prompt(ANSI(
                        colored(f"Do you want to run the command? (y/N): ", "green")))

                if action.lower() in ["y", "a"]:
                    output = self.command_helper.run_shell_command(command_str)
                    outputs.append(output)
                else:
                    print(colored("Skipping command", "yellow"))

            if len(outputs) > 0:
                response, commands = self.openai_helper.send_commands_outputs(
                    outputs)
                print(colored(f"{response}", "magenta"))
                outputs = []
                action = ""
            else:
                commands = None

    def run(self):
        """Runs the application."""
        os_name, shell_name = OSHelper.get_os_and_shell_info()
        print(
            colored(f"Your current environment: Shell={shell_name}, OS={os_name}", "green"))
        print(colored(
            "Type 'e' to enter manual command mode or 'q' to quit, (tokens left)\n", "green"))

        while True:
            try:
                user_input = self.session.prompt(
                    ANSI(colored(f"ChatGPT ({self.openai_helper.remaning_tokens}): ", "green")))
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
    """Main entry point."""
    openai_helper = OpenAIHelper(model_name="gpt-4o",
                                  max_tokens=16 * 1024
                                  )
    command_helper = CommandHelper()
    application = Application(openai_helper, command_helper)
    application.run()
