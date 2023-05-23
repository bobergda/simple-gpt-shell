import os
import subprocess
from revChatGPT.V3 import Chatbot
from termcolor import colored


def get_api_key():
    api_key = os.getenv("OPENAI_API_KEY", "")
    if api_key == "":
        print(colored("Error: OPENAI_API_KEY is not set", "red"))
        exit(1)
    return api_key


def truncate_prompt(prompt, max_tokens):
    num_tokens = len(prompt.split())
    if num_tokens > max_tokens:
        print(colored("Input prompt is too long, truncating...", "yellow"))
        prompt = " ".join(prompt.split()[:max_tokens])
    return prompt


def run_command(command):
    process = subprocess.Popen(
        command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output, errors = process.communicate()
    exit_code = process.wait()

    print(
        colored(f"=== Command output - exit({exit_code})\n{output.decode()}", "magenta"))
    if errors.decode() != "":
        print(
            colored(f"{errors.decode()}", "red"))

    prompt = f"Analyze command output\n{output.decode()}"
    if errors.decode() != "":
        prompt += f"\nstderr:\n{errors.decode()}"

    return prompt


def analyze_command(chatbot, input_prompt):
    chatbot_response = chatbot.ask(input_prompt)
    print(colored(f"=== Response\n{chatbot_response}", "yellow"))

    while "```" in chatbot_response:
        split_response = chatbot_response.split('```')
        extracted_commands = split_response[1::2]
        commands_string = '\n'.join(command.strip()
                                    for command in extracted_commands if command.strip() != "")
        if commands_string == "":
            break

        print(colored(f"=== Command\n{commands_string}", "blue"))
        user_input = input(
            colored(f"Do you want to run the command? (y/N): ", "green"))

        if user_input.lower() == "y":
            input_prompt = run_command(commands_string)

            chatbot_response = chatbot.ask(input_prompt)
            print(colored(f"=== Response\n{chatbot_response}", "yellow"))
        else:
            break


def main():
    system_prompt = """Provide bash commands for Linux.
If there is a lack of details, provide most logical solution.
Ensure the output is a valid shell command.
If multiple steps required try to combine them together.
"""
# Before command add "CMD: ".

    api_key = get_api_key()
    chatbot = Chatbot(api_key=api_key, system_prompt=system_prompt,
                      max_tokens=1024, truncate_limit=1024)

    while True:
        try:
            prompt = input(colored("ChatGPT: ", "green"))
            # prompt = truncate_prompt(prompt, max_tokens=2048)
            analyze_command(chatbot, prompt)
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
