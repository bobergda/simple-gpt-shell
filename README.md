# Simple GPT Shell
The gpt-shell.py script is a powerful Python command-line interface leveraging OpenAI's GPT models to provide insightful suggestions for shell commands. Whether you input a specific command or describe a task, the application generates an appropriate command as interpreted by the selected GPT model. This script communicates with the chosen GPT model through the OpenAI API, enriching user interaction. To ensure the script's functionality, you must set an API key as an environment variable.

Designed for terminal environments, the script offers a user-friendly system prompt for input. It sends the command output to both the terminal and the OpenAI GPT chat, potentially offering additional suggestions for subsequent commands to execute. The script excels at simplifying complex multi-step commands into a single-line command. It further includes an analysis of the command's output conducted by the GPT model, providing an in-depth execution explanation alongside the suggested command.

A key feature of the gpt-shell.py script is its use of function calling. It employs the latest GPT models (like gpt-3.5-turbo-0613 and gpt-4-0613) which have been fine-tuned to detect when a function should be called based on the input. The model then returns a JSON object adhering to the function signature, which can be used to call the function in your code. This results in more reliable retrieval of structured data and offers potential for further functionality, such as creating chatbots that answer questions by calling external APIs. 

The script also employs effective token management, truncating the chat history when necessary to adhere to the model's token limitations. The Application code includes manual and auto modes for command execution, enhancing user control.

![Screen 1](screen1.png "Screen 1")

[![Wideo](https://img.youtube.com/vi/dNrxlJfLHkQ/maxresdefault.jpg)](https://www.youtube.com/watch?v=dNrxlJfLHkQ)

## Installation

1. Clone the repository to your local machine.
2. Install the required dependencies by running `pip install -r requirements.txt`.
3. Set your OpenAI API key as an environment variable `export OPENAI_API_KEY='your-api-key'`.

## Usage

1. Open a terminal and navigate to the directory where `gpt-shell.py` is located.
2. Run the script by typing `python gpt-shell.py` and pressing enter.
3. Follow the system prompt to input commands.
4. The script will provide a suggested command to execute based on the input.

## Contributing

Contributions are welcome! If you find a bug or have an idea for a new feature, please open an issue or submit a pull request.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
