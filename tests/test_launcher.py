import os
import shutil
import stat
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


class LauncherScriptTests(unittest.TestCase):
    def test_launcher_runs_without_forwarded_args(self):
        repo_root = Path(__file__).resolve().parent.parent
        source_script = repo_root / "prompt2shell.sh"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            launcher_copy = temp_root / "prompt2shell.sh"
            shutil.copyfile(source_script, launcher_copy)

            venv_bin = temp_root / ".venv" / "bin"
            venv_bin.mkdir(parents=True)

            activate_path = venv_bin / "activate"
            activate_path.write_text(
                textwrap.dedent(
                    f"""\
                    VIRTUAL_ENV="{temp_root / ".venv"}"
                    PATH="$VIRTUAL_ENV/bin:$PATH"
                    export VIRTUAL_ENV PATH
                    """
                ),
                encoding="utf-8",
            )

            fake_python = venv_bin / "python"
            fake_python.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    set -euo pipefail

                    if [ "${1-}" = "-" ]; then
                      exit 0
                    fi

                    printf 'ARGS:%s\\n' "$*"
                    """
                ),
                encoding="utf-8",
            )
            fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

            result = subprocess.run(
                ["bash", str(launcher_copy)],
                cwd=temp_root,
                capture_output=True,
                text=True,
                env=os.environ.copy(),
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(f"ARGS:{temp_root / 'prompt2shell.py'}", result.stdout)

    def test_launcher_forwards_runtime_arguments_to_python(self):
        repo_root = Path(__file__).resolve().parent.parent
        source_script = repo_root / "prompt2shell.sh"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            launcher_copy = temp_root / "prompt2shell.sh"
            shutil.copyfile(source_script, launcher_copy)

            venv_bin = temp_root / ".venv" / "bin"
            venv_bin.mkdir(parents=True)

            activate_path = venv_bin / "activate"
            activate_path.write_text(
                textwrap.dedent(
                    f"""\
                    VIRTUAL_ENV="{temp_root / ".venv"}"
                    PATH="$VIRTUAL_ENV/bin:$PATH"
                    export VIRTUAL_ENV PATH
                    """
                ),
                encoding="utf-8",
            )

            fake_python = venv_bin / "python"
            fake_python.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    set -euo pipefail

                    if [ "${1-}" = "-" ]; then
                      exit 0
                    fi

                    printf 'ARGS:%s\\n' "$*"
                    """
                ),
                encoding="utf-8",
            )
            fake_python.chmod(fake_python.stat().st_mode | stat.S_IEXEC)

            result = subprocess.run(
                ["bash", str(launcher_copy), "-m5", "--dry-run", "inspect", "logs"],
                cwd=temp_root,
                capture_output=True,
                text=True,
                env=os.environ.copy(),
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--model=gpt-5-mini --dry-run inspect logs", result.stdout)

    def test_add_alias_targets_zsh_profile(self):
        repo_root = Path(__file__).resolve().parent.parent
        source_script = repo_root / "prompt2shell.sh"

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            launcher_copy = temp_root / "prompt2shell.sh"
            shutil.copyfile(source_script, launcher_copy)

            env = os.environ.copy()
            env["HOME"] = str(temp_root)
            env["SHELL"] = "/bin/zsh"

            result = subprocess.run(
                ["bash", str(launcher_copy), "--add-alias"],
                cwd=temp_root,
                capture_output=True,
                text=True,
                env=env,
                check=False,
            )

            zshrc_path = temp_root / ".zshrc"

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(zshrc_path.exists())
            self.assertIn("alias p2s=", zshrc_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
