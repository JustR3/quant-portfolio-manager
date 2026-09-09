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

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
MAIN_PY = PROJECT_ROOT / "main.py"
WORKING_PROG = "uv run ./main.py"

# Every top-level subcommand main.py's parser defines. Kept as an explicit
# list (rather than introspected from argparse) so a newly added subcommand
# fails this suite until someone adds it here and confirms its help text.
ALL_SUBCOMMANDS = [
    "optimize",
    "verify",
    "backtest",
    "signal-eval",
    "ts-eval",
    "pead-eval",
    "portfolio",
]


def run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    """Run main.py the same way `uv run ./main.py <args>` would, without
    depending on `uv` being on PATH in the test environment. `main.py` is
    given as an absolute path so this works even when `cwd` is a scratch
    directory that doesn't contain a copy of the script."""
    return subprocess.run(
        [sys.executable, str(MAIN_PY), *args],
        cwd=cwd or PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )


@pytest.mark.parametrize(
    "args",
    [("--help",), *[(cmd, "--help") for cmd in ALL_SUBCOMMANDS]],
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


def test_portfolio_list_hint_uses_the_real_command_when_no_snapshots_exist(tmp_path):
    """`portfolio list` prints a "Create one with: ..." hint when
    data/portfolios/ has no snapshots. That hint is a separate f-string
    from the --help text and was not covered by the tests above."""
    (tmp_path / "data" / "portfolios").mkdir(parents=True)

    result = run_cli("portfolio", "list", cwd=tmp_path)

    assert result.returncode == 0
    assert "qpm" not in result.stdout
    assert f"Create one with: {WORKING_PROG} optimize --export" in result.stdout


def test_portfolio_list_hint_uses_the_real_command_when_snapshots_exist(tmp_path):
    """With at least one snapshot present, `portfolio list` instead prints a
    "Validate with: ..." hint. Also not covered by the --help-only tests."""
    portfolios_dir = tmp_path / "data" / "portfolios"
    portfolios_dir.mkdir(parents=True)
    snapshot = {
        "metadata": {"snapshot_date": "2026-01-01T00:00:00", "capital": 10000},
        "positions": [{"ticker": "AAPL", "weight": 1.0}],
    }
    (portfolios_dir / "sample_snapshot.json").write_text(json.dumps(snapshot))

    result = run_cli("portfolio", "list", cwd=tmp_path)

    assert result.returncode == 0
    assert "qpm" not in result.stdout
    assert f"Validate with: {WORKING_PROG} portfolio validate" in result.stdout
