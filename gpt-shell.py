#!/usr/bin/env python3
import os
import subprocess
import openai
from termcolor import colored
import platform
import distro

# define system_prompt as a global variable
global system_prompt


def load_openai_api_key():
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key == "":
        print(colored("Error: OPENAI_API_KEY is not set", "red"))
        exit(1)
    openai.api_key = api_key


def request_chatbot_response(prompt):
    chat_prompt = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ]
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",  # or whichever model you are using
        messages=chat_prompt,
    )
    response_string = response['choices'][0]['message']['content']
    return response_string


def run_shell_command(command):
    result = subprocess.run(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    if result.stdout != "":
        stdout_lines = result.stdout.split("\n")
        for i, line in enumerate(stdout_lines):
            if "KEY" in line:
                post_key_content = line[line.find("KEY") + 3:].strip()
                if "=" in post_key_content:
                    stdout_lines[i] = line.split("=")[0] + "=<API_KEY>"
        result.stdout = "\n".join(stdout_lines)
    return result


def interpret_and_execute_command(user_prompt):
    if user_prompt == "e":
        manual_command_mode()
    else:
        auto_command_mode(user_prompt)


def manual_command_mode():
    print(colored("Manual command mode activated. Please enter your command:", "green"))
    command_str = input()
    command_output = run_shell_command(command_str)
    prompt = f"Analyze command '{command_str}' output:\n" + \
        command_output.stdout
    if command_output.stderr != "":
        prompt += "\nError output:\n" + command_output.stderr
    print_command_output(command_output)

    chatbot_reply = request_chatbot_response(prompt)
    print_chatbot_response(chatbot_reply)
    execute_commands_in_chatbot_response(chatbot_reply)


def auto_command_mode(user_prompt):
    chatbot_reply = request_chatbot_response(user_prompt)
    print_chatbot_response(chatbot_reply)
    execute_commands_in_chatbot_response(chatbot_reply)


def execute_commands_in_chatbot_response(chatbot_reply):
    while "```" in chatbot_reply:
        split_reply = chatbot_reply.split('```')
        commands_list = split_reply[1::2]
        command_str = '\n'.join(command.strip()
                                for command in commands_list if command.strip() != "")
        if command_str == "":
            break

        print(colored(f"=== Command\n{command_str}", "blue"))

        action = input(
            colored(f"Do you want to run (y) or edit (e) the command? (y/e/N): ", "green"))

        if action.lower() == "e":
            command_str = input(
                colored("Enter the modified command: ", "cyan"))
            action = input(
                colored(f"Do you want to run the command? (y/N): ", "green"))

        if action.lower() == "y":
            command_output = run_shell_command(command_str)
            prompt = f"Analyze command output:\n{command_output.stdout}"
            if command_output.stderr != "":
                prompt += "\nError output:\n" + command_output.stderr
            print_command_output(command_output)

            chatbot_reply = request_chatbot_response(prompt)
            print_chatbot_response(chatbot_reply)
        else:
            break


def print_command_output(command_output):
    print(colored(f"=== Command output\n{command_output.stdout}", "magenta"))
    if command_output.stderr != "":
        print(colored(f"=== Command error\n{command_output.stderr}", "red"))


def print_chatbot_response(chatbot_reply):
    print(colored(f"=== Response\n{chatbot_reply}", "yellow"))


def get_os_and_shell_info():
    os_name = platform.system()
    shell_name = os.path.basename(os.environ.get("SHELL", "bash"))
    if os_name == "Linux":
        pass
    elif os_name == "Darwin":
        os_name += " " + platform.mac_ver()[0]
    elif os_name == "Windows":
        os_name += " " + platform.release()
    return os_name, shell_name


def main():
    os_name, shell_name = get_os_and_shell_info()
    # use the global system_prompt variable
    global system_prompt
    system_prompt = f"""Provide {shell_name} commands for {os_name}.
If details are missing, suggest the most logical solution.
Ensure valid shell command output.
For multiple steps, combine them if possible.
Use ``` only to separate commands.
"""
    print(
        colored(f"Your current environment: Shell={shell_name}, OS={os_name}", "green"))
    print(colored("Type 'e' to enter manual command mode\n", "green"))
    load_openai_api_key()

    while True:
        try:
            user_input = input(colored("ChatGPT: ", "green"))
            interpret_and_execute_command(user_input)
        except subprocess.CalledProcessError as e:
            print(colored(
                f"Error: Command failed with exit code {e.returncode}: {e.output}", "red"))
        except KeyboardInterrupt:
            print(colored("Exiting...", "yellow"))
            exit(0)
        except EOFError:
            print(colored("Exiting...", "yellow"))
            exit(0)
        except Exception as e:
            print(colored(f"Error of type {type(e).__name__}: {e}", "red"))


if __name__ == "__main__":
    main()
