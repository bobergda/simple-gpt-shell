import os
import subprocess
from revChatGPT.V3 import Chatbot
from termcolor import colored

system_prompt = """Provide only bash commands for Linux without any description.
If there is a lack of details, provide most logical solution.
Ensure the output is a valid shell command.
If multiple steps required try to combine them together.
Before command add "CMD: ".
"""

api_key = os.getenv("OPENAI_API_KEY", "")
if api_key == "":
    print(colored("Error: OPENAI_API_KEY is not set", "red"))
    exit(1)

chatbot = Chatbot(api_key=api_key, system_prompt=system_prompt)

while True:
    try:
        prompt = input(colored("ChatGPT: ", "green"))
        response = chatbot.ask(prompt)
        print(colored(f"=== Response\n{response}", "yellow"))

        while "CMD: " in response:
            commands = [line.replace(
                "CMD: ", "") for line in response.splitlines() if line.startswith("CMD: ")]
            command = "; ".join(commands)
            if command == "":
                break

            print(colored(f"=== Command\n{command}", "blue"))
            run_command = input(
                colored(f"Do you want to run the command? (y/N): ", "green"))

            if run_command.lower() == "y":
                process = subprocess.Popen(
                    command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                output, errors = process.communicate()
                exit_code = process.wait()

                if exit_code != 0:
                    print(colored(
                        f"=== Error: Command failed - exit({exit_code}):\n{errors.decode()}"
                        + (f"{output.decode()}" if output else ""), "red"))
                    prompt = f"Analyze command error:\n{errors.decode()}\n{output.decode()}"
                else:
                    print(
                        colored(f"=== Command output\n{output.decode()}", "magenta"))
                    prompt = f"Analyze command output:\n{output.decode()}"

                response = chatbot.ask(prompt)
                if exit_code != 0:
                    print(
                        colored(f"=== Response for error\n{response}", "yellow"))
                else:
                    print(
                        colored(f"=== Response for output\n{response}", "yellow"))
            else:
                break

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
