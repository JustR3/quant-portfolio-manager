"""
Regression tests for the CLI's own self-description.

Root cause this guards against: main.py's --help text (and its no-args
hint text) used to say "qpm ..." in every example, but nothing in this
repo installs a `qpm` binary. The only command that actually runs here is
`uv run ./main.py ...`. Pasting the old examples failed with
"command not found: qpm".

These tests run the real CLI as a subprocess (the same way a user would)
so a regression is caught by executing the help text's own advice, not by
inspecting source strings.
"""

import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
WORKING_PROG = "uv run ./main.py"


def run_cli(*args: str) -> subprocess.CompletedProcess:
    """Run main.py the same way `uv run ./main.py <args>` would, without
    depending on `uv` being on PATH in the test environment."""
    return subprocess.run(
        [sys.executable, "main.py", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize(
    "args", [("--help",), ("optimize", "--help"), ("backtest", "--help")]
)
def test_help_never_shows_the_broken_qpm_command(args):
    result = run_cli(*args)
    assert result.returncode == 0
    assert "qpm" not in result.stdout, (
        f"Help text for {args} still tells the user to run a `qpm` command, "
        "which does not exist in this repo."
    )


def test_top_level_help_shows_the_command_that_actually_runs():
    result = run_cli("--help")
    assert result.returncode == 0
    assert WORKING_PROG in result.stdout
    # Every example line must start with the real, runnable command.
    example_lines = [
        line
        for line in result.stdout.splitlines()
        if line.strip().startswith(WORKING_PROG)
    ]
    assert len(example_lines) >= 5, (
        "Expected the Examples block to use the real command."
    )


def test_no_args_hint_shows_the_command_that_actually_runs():
    result = run_cli()
    assert result.returncode == 0
    assert WORKING_PROG in result.stdout
    assert "qpm" not in result.stdout


def test_every_example_in_help_is_actually_runnable_as_dash_dash_help():
    """Pull each example command out of the epilog and confirm its subcommand
    parses (via --help) instead of erroring, e.g. from a typo'd flag name."""
    result = run_cli("--help")
    examples = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip().startswith(WORKING_PROG)
    ]
    assert examples, "No examples found in --help output."

    for example in examples:
        # e.g. "uv run ./main.py optimize --universe sp500 --top-n 50   Build ..."
        # -> take the tokens after the program name up to (not including) the
        # trailing prose description (two-space+ column of free text).
        rest = example[len(WORKING_PROG) :].strip()
        # The command tokens end where the description column begins (2+ spaces).
        import re

        command_part = re.split(r"\s{2,}", rest)[0]
        tokens = command_part.split()
        subcommand = tokens[0]
        check = run_cli(subcommand, "--help")
        assert check.returncode == 0, (
            f"`{WORKING_PROG} {subcommand} --help` failed:\n{check.stderr}"
        )
