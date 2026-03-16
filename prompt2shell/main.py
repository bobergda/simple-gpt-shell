import argparse
import json
import re
import sys

from .application import Application
from .command_helper import CommandHelper
from .config import load_app_config
from .interaction_logger import InteractionLogger
from .openai_helper import OpenAIHelper


LS_LONG_ENTRY_PATTERN = re.compile(r"^[bcdlps-][rwxstST-]{9}\s+")


def build_argument_parser():
    parser = argparse.ArgumentParser(
        prog="prompt2shell",
        description="Turn natural-language requests into reviewed shell commands.",
    )
    parser.add_argument("prompt", nargs="*", help="Initial prompt to send to the assistant.")
    parser.add_argument("-o", "--once", action="store_true", default=None, help="Exit after processing the initial prompt.")
    parser.add_argument("--model", dest="openai_model", help="Override the OpenAI model for this run.")
    parser.add_argument("--tokens", dest="max_output_tokens", type=int, help="Set max output tokens for this run.")
    parser.add_argument("--config", dest="config_file", help="Path to a TOML config file.")
    parser.add_argument("--dry-run", action="store_true", default=None, help="Preview commands without executing them.")
    parser.add_argument(
        "--explain-only",
        action="store_true",
        default=None,
        help="Explain and print proposed commands without entering execution prompts.",
    )
    parser.add_argument(
        "--report",
        nargs="?",
        const="AUTO",
        dest="session_report_file",
        help="Write a Markdown session report. Optionally provide a custom file path.",
    )
    return parser


def parse_runtime_args(argv=None):
    parser = build_argument_parser()
    parsed = parser.parse_args(argv)
    cli_overrides = {
        "config_file": parsed.config_file,
        "openai_model": parsed.openai_model,
        "max_output_tokens": parsed.max_output_tokens,
        "once_mode": parsed.once,
        "dry_run": parsed.dry_run,
        "explain_only": parsed.explain_only,
    }

    if parsed.session_report_file == "AUTO":
        cli_overrides["session_report_file"] = "./logs/reports/latest-session.md"
    elif parsed.session_report_file:
        cli_overrides["session_report_file"] = parsed.session_report_file

    return parsed, cli_overrides


def read_piped_input():
    stdin = getattr(sys, "stdin", None)
    if stdin is None:
        return None
    try:
        if stdin.isatty():
            return None
    except (AttributeError, OSError):
        return None

    try:
        piped_text = stdin.read()
    except OSError:
        return None

    if not isinstance(piped_text, str):
        return None
    piped_text = piped_text.strip()
    if piped_text == "":
        return None
    return piped_text


def infer_piped_source_description(piped_text):
    lines = [line.strip() for line in piped_text.splitlines() if line.strip()]
    if not lines:
        return "shell command output"

    first_line = lines[0]

    try:
        parsed = json.loads(piped_text)
        if isinstance(parsed, (dict, list)):
            return "JSON data"
    except (json.JSONDecodeError, TypeError, ValueError):
        pass

    long_ls_entries = sum(1 for line in lines if LS_LONG_ENTRY_PATTERN.match(line))
    if first_line.startswith("total ") and long_ls_entries >= 1:
        return "likely `ls -l` or `ll` output (detailed directory listing)"

    if first_line.startswith("Filesystem") and ("Mounted on" in first_line or "Use%" in first_line):
        return "likely `df -h` output (filesystem usage)"

    if (first_line.startswith("PID") or first_line.startswith("USER")) and ("CMD" in first_line or "COMMAND" in first_line):
        return "likely `ps` output (process list)"

    if first_line.startswith("On branch ") or "nothing to commit" in piped_text:
        return "likely `git status` output"

    simple_name_lines = 0
    for line in lines:
        if " " in line or "\t" in line:
            continue
        simple_name_lines += 1
    if len(lines) >= 3 and simple_name_lines / len(lines) >= 0.7:
        return "likely `ls` output (list of names)"

    return "shell command output"


def build_prompt_from_pipe(user_prompt, piped_input):
    source_description = infer_piped_source_description(piped_input)

    if isinstance(user_prompt, str) and user_prompt.strip() != "":
        return (
            f"{user_prompt}\n\n"
            f"Pipeline context: {source_description}.\n"
            "Use the piped command output below as primary input.\n\n"
            f"Piped input:\n{piped_input}"
        )

    return (
        "Describe and analyze the following piped command output. "
        f"Inferred source: {source_description}.\n\n"
        f"Piped input:\n{piped_input}"
    )


def build_application(config):
    interaction_logger = InteractionLogger(log_file=config.log_file, enabled=config.log_enabled)
    openai_helper = OpenAIHelper(
        model_name=config.openai_model,
        max_output_tokens=config.max_output_tokens,
        interaction_logger=interaction_logger,
        api_key=config.openai_api_key,
        chat_language=config.chat_language,
    )
    command_helper = CommandHelper(timeout_seconds=config.command_timeout)
    return Application(openai_helper, command_helper, interaction_logger, settings=config)


def main(argv=None):
    parsed_args, cli_overrides = parse_runtime_args(argv if argv is not None else sys.argv[1:])
    config = load_app_config(cli_overrides)

    initial_prompt = " ".join(parsed_args.prompt).strip() if parsed_args.prompt else None
    if initial_prompt == "":
        initial_prompt = None

    piped_input = read_piped_input()
    if piped_input is not None:
        initial_prompt = build_prompt_from_pipe(initial_prompt, piped_input)

    app = build_application(config)
    configure_context = getattr(getattr(app, "openai_helper", None), "configure_session_context", None)
    if callable(configure_context):
        context_kwargs = {
            "once_mode": config.once_mode,
            "has_piped_input": piped_input is not None,
        }
        if config.dry_run:
            context_kwargs["dry_run"] = True
        if config.explain_only:
            context_kwargs["explain_only"] = True
        configure_context(
            **context_kwargs,
        )

    app.run(initial_prompt=initial_prompt, exit_after_initial_prompt=config.once_mode)


if __name__ == "__main__":
    main()
