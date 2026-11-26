"""CLI exit path: the exit code survives a native abort in interpreter teardown (Linux).

See docs/DECISIONS.md, entry "2026-11-26 cli-exit-abort".
"""

import subprocess
import sys
from pathlib import Path

import pytest

from src import cli_exit

ROOT = Path(__file__).resolve().parents[1]


class _Exited(Exception):
    def __init__(self, code):
        self.code = code


@pytest.fixture
def calls(monkeypatch):
    log = []

    def fake_exitfuncs():
        log.append("exitfuncs")

    def fake_os_exit(code):
        log.append(("os._exit", code))
        raise _Exited(code)

    monkeypatch.setattr(cli_exit.atexit, "_run_exitfuncs", fake_exitfuncs)
    monkeypatch.setattr(cli_exit.os, "_exit", fake_os_exit)
    return log


@pytest.mark.parametrize(
    ("value", "code"), [(None, 0), (0, 0), (3, 3), (1, 1), (True, 1), ("boom", 1)]
)
def test_exit_status_follows_python_rules(value, code, capsys):
    assert cli_exit.exit_status(value) == code
    if isinstance(value, str):
        assert "boom" in capsys.readouterr().err


def _run(fn):
    with pytest.raises(_Exited) as e:
        cli_exit.run_and_exit(fn)
    return e.value.code


def test_system_exit_code_reaches_os_exit_after_exit_handlers(calls):
    def fn():
        raise SystemExit(3)

    assert _run(fn) == 3
    assert calls == ["exitfuncs", ("os._exit", 3)]


def test_normal_return_exits_0(calls):
    assert _run(lambda: None) == 0
    assert calls[-1] == ("os._exit", 0)


def test_uncaught_error_prints_traceback_and_exits_1(calls, capsys):
    def fn():
        raise ValueError("bad input")

    assert _run(fn) == 1
    err = capsys.readouterr().err
    assert "Traceback" in err and "ValueError: bad input" in err


def test_keyboard_interrupt_is_not_swallowed(calls):
    def fn():
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        cli_exit.run_and_exit(fn)
    assert calls == []


def test_cli_still_runs_python_exit_handlers():
    """`main.py` ends with os._exit, so it must run atexit handlers itself (yfinance cache)."""
    code = (
        "import atexit, runpy, sys\n"
        "atexit.register(lambda: print('ATEXIT-RAN', flush=True))\n"
        "sys.argv = ['main.py', '--help']\n"
        "runpy.run_path('main.py', run_name='__main__')\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert out.returncode == 0, out.stderr
    assert "ATEXIT-RAN" in out.stdout
    assert out.stdout.index("ATEXIT-RAN") > out.stdout.index("usage")
