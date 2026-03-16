import os
import re
import shlex
import signal
import subprocess
import threading

from .common import colored


class CommandHelper:
    """Helper class for executing commands."""

    DESTRUCTIVE_COMMAND_PATTERNS = (
        (
            re.compile(r"(^|[;&|]\s*)\s*rm\s+.*(--no-preserve-root|--preserve-root=0)\b", re.IGNORECASE),
            "rm with preserve-root disabled",
        ),
        (
            re.compile(
                r"(^|[;&|]\s*)\s*(sudo\s+)?rm\b(?=[^\n]*(?:\s|^)(?:-rf|-fr|--recursive|--force|-r|-f)(?:\s|$))",
                re.IGNORECASE,
            ),
            "rm with recursive/force options",
        ),
        (re.compile(r"(^|[;&|]\s*)\s*mkfs(\.\w+)?\b", re.IGNORECASE), "filesystem format command"),
        (re.compile(r"(^|[;&|]\s*)\s*dd\s+.*\bof=/dev/", re.IGNORECASE), "dd write to block device"),
        (re.compile(r"(^|[;&|]\s*)\s*shred\b", re.IGNORECASE), "secure delete command"),
        (re.compile(r"(^|[;&|]\s*)\s*wipefs\b", re.IGNORECASE), "filesystem wipe command"),
        (re.compile(r"(^|[;&|]\s*)\s*git\s+reset\s+--hard\b", re.IGNORECASE), "git hard reset"),
        (re.compile(r"(^|[;&|]\s*)\s*git\s+clean\s+-[^\n]*f", re.IGNORECASE), "git clean with force"),
        (re.compile(r"(^|[;&|]\s*)\s*docker\s+system\s+prune\b", re.IGNORECASE), "docker prune"),
        (re.compile(r":\(\)\s*\{\s*:\|:&\s*\};:", re.IGNORECASE), "fork bomb pattern"),
    )

    STRICT_SAFE_MODE_READ_ONLY_COMMANDS = {
        "basename",
        "cat",
        "cut",
        "date",
        "df",
        "diff",
        "dirname",
        "du",
        "echo",
        "env",
        "file",
        "find",
        "git",
        "grep",
        "head",
        "hostname",
        "id",
        "jq",
        "less",
        "ls",
        "md5sum",
        "nl",
        "printf",
        "ps",
        "pwd",
        "readlink",
        "realpath",
        "rg",
        "sed",
        "sha1sum",
        "sha256sum",
        "sort",
        "stat",
        "tail",
        "tee",
        "tr",
        "uname",
        "uniq",
        "wc",
        "whoami",
    }

    STRICT_SAFE_MODE_READ_ONLY_GIT_SUBCOMMANDS = {
        "branch",
        "diff",
        "log",
        "remote",
        "rev-parse",
        "show",
        "status",
        "tag",
    }

    STRICT_SAFE_MODE_FORBIDDEN_FIND_FLAGS = {
        "-delete",
        "-exec",
        "-execdir",
        "-ok",
        "-okdir",
        "-fprint",
        "-fprint0",
        "-fprintf",
        "-fls",
    }

    PIPELINE_SEPARATORS = {"|", ";", "&&", "||"}

    def __init__(self, timeout_seconds=None):
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else self._command_timeout_seconds_from_env()

    @staticmethod
    def _split_unquoted(text, delimiter):
        parts = []
        current = []
        single_quote = False
        double_quote = False
        index = 0
        while index < len(text):
            char = text[index]
            if char == "'" and not double_quote:
                single_quote = not single_quote
            elif char == '"' and not single_quote:
                double_quote = not double_quote
            if not single_quote and not double_quote and text.startswith(delimiter, index):
                parts.append("".join(current).strip())
                current = []
                index += len(delimiter)
                continue
            current.append(char)
            index += 1
        parts.append("".join(current).strip())
        return parts

    @staticmethod
    def _contains_unquoted_sequence(text, sequence):
        single_quote = False
        double_quote = False
        index = 0
        while index < len(text):
            char = text[index]
            if char == "'" and not double_quote:
                single_quote = not single_quote
            elif char == '"' and not single_quote:
                double_quote = not double_quote
            if not single_quote and not double_quote and text.startswith(sequence, index):
                return True
            index += 1
        return False

    @staticmethod
    def _command_timeout_seconds_from_env():
        raw_timeout = os.getenv("PROMPT2SHELL_COMMAND_TIMEOUT", "300")
        try:
            timeout = int(raw_timeout)
        except (TypeError, ValueError):
            timeout = 300
        return timeout if timeout > 0 else None

    @staticmethod
    def detect_destructive_command(command):
        if not isinstance(command, str) or command.strip() == "":
            return None
        normalized = command.strip()
        tokenized_reason = CommandHelper._detect_destructive_command_tokenized(normalized)
        if tokenized_reason is not None:
            return tokenized_reason
        for pattern, reason in CommandHelper.DESTRUCTIVE_COMMAND_PATTERNS:
            if pattern.search(normalized):
                return reason
        return None

    @staticmethod
    def _is_env_assignment(token):
        return bool(re.match(r"^[A-Za-z_][A-Za-z0-9_]*=.*$", token))

    @staticmethod
    def _extract_executable(segment):
        try:
            tokens = shlex.split(segment, posix=True)
        except ValueError:
            return None, None, "unable to parse command segment"

        if not tokens:
            return None, None, "empty command segment"

        index = 0
        while index < len(tokens) and CommandHelper._is_env_assignment(tokens[index]):
            index += 1

        if index >= len(tokens):
            return None, None, "missing executable"

        executable = os.path.basename(tokens[index])
        args = tokens[index + 1:]
        return executable, args, None

    @staticmethod
    def _unwrap_wrappers(executable, args):
        lowered_exec = executable.lower()
        remaining_args = list(args)
        wrapper_commands = {"sudo", "command", "builtin", "env"}

        while lowered_exec in wrapper_commands:
            if lowered_exec == "env":
                while remaining_args and CommandHelper._is_env_assignment(remaining_args[0]):
                    remaining_args.pop(0)
            if not remaining_args:
                break
            executable = os.path.basename(remaining_args[0])
            remaining_args = remaining_args[1:]
            lowered_exec = executable.lower()

        return executable, remaining_args

    @staticmethod
    def _detect_destructive_command_tokenized(command):
        if CommandHelper._contains_unquoted_sequence(command, ">|"):
            return "shell redirection overwrite"

        segments = CommandHelper._split_unquoted(command, "|")
        for segment in segments:
            executable, args, parse_error = CommandHelper._extract_executable(segment)
            if parse_error is not None:
                continue

            executable, args = CommandHelper._unwrap_wrappers(executable, args)
            lowered_exec = executable.lower()
            lowered_args = [arg.lower() for arg in args]

            if lowered_exec == "rm":
                if "--no-preserve-root" in lowered_args or "--preserve-root=0" in lowered_args:
                    return "rm with preserve-root disabled"
                if any(arg in {"-rf", "-fr", "-r", "-f", "--recursive", "--force"} for arg in lowered_args):
                    return "rm with recursive/force options"

            if lowered_exec == "find":
                if any(arg in {"-delete", "-exec", "-execdir", "-ok", "-okdir"} for arg in lowered_args):
                    return "find with destructive action"

            if lowered_exec == "xargs" and any(arg in {"rm", "shred", "wipefs"} for arg in lowered_args):
                return "xargs invoking destructive command"

            if lowered_exec.startswith("mkfs"):
                return "filesystem format command"
            if lowered_exec == "dd" and any(arg.startswith("of=/dev/") for arg in lowered_args):
                return "dd write to block device"
            if lowered_exec in {"shred", "wipefs"}:
                return f"{lowered_exec} destructive command"
            if lowered_exec == "git" and args:
                git_subcommand = args[0].lower()
                git_args = [arg.lower() for arg in args[1:]]
                if git_subcommand == "reset" and "--hard" in git_args:
                    return "git hard reset"
                if git_subcommand == "clean" and any("f" in arg and arg.startswith("-") for arg in git_args):
                    return "git clean with force"
            if lowered_exec == "docker" and len(args) >= 2:
                docker_command = f"{args[0].lower()} {args[1].lower()}"
                if docker_command == "system prune":
                    return "docker prune"
            if lowered_exec in {"chmod", "chown"} and any(arg in {"-r", "-R", "--recursive"} for arg in lowered_args):
                return f"{lowered_exec} recursive permissions change"

        return None

    @staticmethod
    def detect_non_readonly_command(command):
        if not isinstance(command, str) or command.strip() == "":
            return "empty command"

        normalized = command.strip()

        if "\n" in normalized:
            return "multiline commands are blocked in strict safe mode"
        if CommandHelper._contains_unquoted_sequence(normalized, "&&") or CommandHelper._contains_unquoted_sequence(normalized, "||") or CommandHelper._contains_unquoted_sequence(normalized, ";"):
            return "command chaining operators are blocked in strict safe mode"
        if CommandHelper._contains_unquoted_sequence(normalized, "`") or CommandHelper._contains_unquoted_sequence(normalized, "$("):
            return "command substitution is blocked in strict safe mode"
        if CommandHelper._contains_unquoted_sequence(normalized, "|&"):
            return "stderr pipe redirection is blocked in strict safe mode"
        if CommandHelper._contains_unquoted_sequence(normalized, ">"):
            return "output redirection is blocked in strict safe mode"
        if (
            CommandHelper._contains_unquoted_sequence(normalized, "<&")
            or CommandHelper._contains_unquoted_sequence(normalized, "<>")
            or CommandHelper._contains_unquoted_sequence(normalized, "<<")
            or CommandHelper._contains_unquoted_sequence(normalized, "<")
        ):
            return "advanced redirection is blocked in strict safe mode"

        for segment in CommandHelper._split_unquoted(normalized, "|"):
            executable, args, parse_error = CommandHelper._extract_executable(segment)
            if parse_error is not None:
                return parse_error

            executable, args = CommandHelper._unwrap_wrappers(executable, args)
            lowered_exec = executable.lower()
            if lowered_exec not in CommandHelper.STRICT_SAFE_MODE_READ_ONLY_COMMANDS:
                return f"command `{executable}` is not in strict read-only allowlist"

            if lowered_exec == "find":
                lowered_args = {arg.lower() for arg in args}
                forbidden = lowered_args.intersection(CommandHelper.STRICT_SAFE_MODE_FORBIDDEN_FIND_FLAGS)
                if forbidden:
                    return f"find flag `{sorted(forbidden)[0]}` is blocked in strict safe mode"

            if lowered_exec == "sed":
                lowered_args = [arg.lower() for arg in args]
                if any(
                    arg == "-i" or arg.startswith("-i") or arg == "--in-place" or arg.startswith("--in-place=")
                    for arg in lowered_args
                ):
                    return "sed in-place editing is blocked in strict safe mode"

            if lowered_exec == "tee" and args:
                return "tee file output is blocked in strict safe mode"

            if lowered_exec == "git":
                if not args:
                    return "git requires an explicit read-only subcommand in strict safe mode"
                lowered_subcommand = args[0].lower()
                if lowered_subcommand not in CommandHelper.STRICT_SAFE_MODE_READ_ONLY_GIT_SUBCOMMANDS:
                    return f"git subcommand `{args[0]}` is not read-only"

        return None

    @staticmethod
    def redact_sensitive_text(text):
        if not isinstance(text, str) or text == "":
            return text

        redacted = text
        redacted = re.sub(
            r"(?i)\b(Authorization)\b(\s*[:=]\s*)Bearer\s+[A-Za-z0-9\-._~+/]+=*",
            r"\1\2Bearer <REDACTED>",
            redacted,
        )
        redacted = re.sub(
            r"(?i)\b([A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|PASSWD)[A-Z0-9_]*)\b(\s*[:=]\s*)([^\s\"']+|\"[^\"]*\"|'[^']*')",
            r"\1\2<REDACTED>",
            redacted,
        )
        redacted = re.sub(
            r"(?i)\b(Bearer)\s+[A-Za-z0-9\-._~+/]+=*",
            r"\1 <REDACTED>",
            redacted,
        )
        redacted = re.sub(r"\bsk-[A-Za-z0-9]{12,}\b", "<REDACTED_OPENAI_KEY>", redacted)
        redacted = re.sub(
            r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9._-]+\.[A-Za-z0-9._-]+\b",
            "<REDACTED_JWT>",
            redacted,
        )
        redacted = re.sub(r"\bAKIA[0-9A-Z]{16}\b", "<REDACTED_AWS_ACCESS_KEY_ID>", redacted)
        return redacted

    @staticmethod
    def _read_stream(stream, sink, color=None):
        try:
            for line in iter(stream.readline, ""):
                sink.append(line)
                if color:
                    print(colored(line.rstrip("\n"), color))
                else:
                    print(line, end="")
        finally:
            stream.close()

    @staticmethod
    def _terminate_process_tree(process):
        if process.poll() is not None:
            return

        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                return
            except OSError:
                process.kill()
            return

        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            return

        process.kill()

    def run_shell_command(self, command):
        popen_kwargs = {
            "args": command,
            "shell": True,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "universal_newlines": True,
        }

        if os.name == "posix":
            popen_kwargs["start_new_session"] = True
        elif os.name == "nt":
            popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

        process = subprocess.Popen(**popen_kwargs)
        stdout_lines = []
        stderr_lines = []

        stdout_thread = threading.Thread(
            target=CommandHelper._read_stream,
            args=(process.stdout, stdout_lines),
            daemon=True,
        )
        stderr_thread = threading.Thread(
            target=CommandHelper._read_stream,
            args=(process.stderr, stderr_lines, "red"),
            daemon=True,
        )
        stdout_thread.start()
        stderr_thread.start()

        timeout_seconds = self.timeout_seconds
        timed_out = False
        interrupted = False

        try:
            if timeout_seconds is None:
                returncode = process.wait()
            else:
                returncode = process.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
            CommandHelper._terminate_process_tree(process)
            returncode = process.wait()
            print(
                colored(
                    f"Error: Command timed out after {timeout_seconds}s",
                    "red",
                )
            )
        except KeyboardInterrupt:
            interrupted = True
            CommandHelper._terminate_process_tree(process)
            returncode = process.wait()
            print(colored("Command interrupted by user", "yellow"))
        finally:
            stdout_thread.join()
            stderr_thread.join()

        output = {
            "command": command,
            "stdout": CommandHelper.redact_sensitive_text("".join(stdout_lines)),
            "stderr": CommandHelper.redact_sensitive_text("".join(stderr_lines)),
            "returncode": returncode,
            "timed_out": timed_out,
            "interrupted": interrupted,
        }
        return output
