# simple-gpt-shell

The `gpt-shell.py` script is a command-line interface for interacting with the OpenAI GPT-3 API. It allows the user to input bash commands for Linux and receive a response from the GPT-3 model with a suggested command to execute. The script uses the `revChatGPT.V3` module to interface with the GPT-3 API and requires an API key to be set as an environment variable. The script is designed to be run in a terminal and provides a system prompt for the user to input commands.

## Installation

1. Clone the repository to your local machine.
2. Install the required dependencies by running `pip install -r requirements.txt`.
3. Set your OpenAI API key as an environment variable named `OPENAI_API_KEY`.

## Usage

1. Open a terminal and navigate to the directory where `gpt-shell.py` is located.
2. Run the script by typing `python gpt-shell.py` and pressing enter.
3. Follow the system prompt to input bash commands for Linux.
4. The script will provide a suggested command to execute based on the input.

Note: The script is designed to be run in a terminal and may not work as expected in other environments.
