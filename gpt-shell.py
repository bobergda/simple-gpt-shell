import os
import subprocess
from revChatGPT.V3 import Chatbot

system_prompt = """Provide only bash commands for Linux without any description.
If there is a lack of details, provide most logical solution.
Ensure the output is a valid shell command.
If multiple steps required try to combine them together.
Before command add "CMD: ".
"""

api_key = os.getenv("OPENAI_API_KEY", "")
if api_key == "":
    print("Error: OPENAI_API_KEY is not set")
    exit(1)

chatbot = Chatbot(api_key=api_key, system_prompt=system_prompt)

while True:
    try:
        prompt = input("ChatGPT: ")
        print(f"=== Prompt\n{prompt}")

        response = chatbot.ask(prompt)
        print(f"=== Response\n{response}")

        while "CMD: " in response:
            command = response[5:]

            print(f"=== Run command\n{command}")
            process = subprocess.Popen(
                command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output, errors = process.communicate()
            exit_code = process.wait()

            prompt = f"Analyze command output:\n{output.decode()}"
            print(f"=== Prompt\n{prompt}")

            response = chatbot.ask(prompt)
            print(f"=== Response\n{response}")
            
    except subprocess.CalledProcessError as e:
        print(
            f"Error: Command failed with exit code {e.returncode}: {e.output}")
    except KeyboardInterrupt:
        print("Exiting...")
        exit(0)
    except EOFError:
        print("Exiting...")
        exit(0)
    except Exception as e:
        print(f"Error of type {type(e).__name__}: {e}")
