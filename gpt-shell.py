import os
import subprocess
from revChatGPT.V3 import Chatbot
from termcolor import colored
import platform
import distro


def get_api_key():
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key == "":
        print(colored("Error: OPENAI_API_KEY is not set", "red"))
        exit(1)
    return api_key


def execute_command(command):
    result = subprocess.run(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return result.stdout


def interpret_command(chatbot, user_prompt):
    chatbot_reply = chatbot.ask(user_prompt)
    print(colored(f"=== Response\n{chatbot_reply}", "yellow"))

    while "```" in chatbot_reply:
        split_reply = chatbot_reply.split('```')
        commands_list = split_reply[1::2]
        commands_str = '\n'.join(command.strip()
                                 for command in commands_list if command.strip() != "")
        if commands_str == "":
            break

        print(colored(f"=== Command\n{commands_str}", "blue"))
        run_confirmation = input(
            colored(f"Do you want to run the command? (y/N): ", "green"))

        if run_confirmation.lower() == "y":
            command_output = execute_command(commands_str)
            print(
                colored(f"=== Command output\n{command_output}", "magenta"))
            prompt = f"Analyze command output\n{command_output}"

            chatbot_reply = chatbot.ask(prompt)
            print(colored(f"=== Response\n{chatbot_reply}", "yellow"))
        else:
            break


def get_os_and_shell_names():
    os_name = platform.system()
    shell_name = os.path.basename(os.environ.get("SHELL", "bash"))
    if os_name == "Linux":
        os_name += " " + distro.name(pretty=True)
    return os_name, shell_name


def main():
    os_name, shell_name = get_os_and_shell_names()

    chatbot_prompt = f"""Provide {shell_name} commands for {os_name}.
If details are missing, suggest the most logical solution.
Ensure valid shell command output.
For multiple steps, combine them if possible.
Use ``` only to separate commands.
"""
    print(colored(f"=== ChatGPT system_prompt\n{chatbot_prompt}", "yellow"))
    api_key = get_api_key()
    chatbot_instance = Chatbot(
        api_key=api_key, system_prompt=chatbot_prompt, truncate_limit=1024)

    while True:
        try:
            user_input = input(colored("ChatGPT: ", "green"))
            interpret_command(chatbot_instance, user_input)
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
