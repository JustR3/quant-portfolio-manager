"""End the CLI process so that its exit code cannot be lost in interpreter teardown.

On the GitHub Linux runner, a process that called `pandas.read_parquet` sometimes aborts
after all Python code is done: native teardown calls `std::terminate` ("terminate called
without an active exception", SIGABRT). The exit code then becomes -6, so a script reads an
INCONCLUSIVE run (exit 3) or a good run (exit 0) as a crash. A CI probe measured about 2 % of
runs; `pyarrow.parquet.read_table` alone and `pyarrow.fs.finalize_s3()` did not show it or fix
it. See docs/DECISIONS.md, entry "2026-11-26 cli-exit-abort".

`run_and_exit` runs the CLI, then runs the Python exit handlers (atexit: logging, the yfinance
cache), flushes stdout and stderr, and calls `os._exit`. Only the native teardown is skipped.
"""

from __future__ import annotations

import atexit
import os
import sys
import traceback
from collections.abc import Callable


def exit_status(value: object) -> int:
    """The process exit code for `SystemExit(value)`, with the same rules as Python."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    print(value, file=sys.stderr)
    return 1


def run_and_exit(fn: Callable[[], object]) -> None:
    """Run `fn`, then end the process with its exit code. Never returns.

    KeyboardInterrupt (and other BaseException that is not SystemExit) is not caught, so
    Ctrl-C keeps the normal Python behaviour.
    """
    try:
        fn()
        code = 0
    except SystemExit as e:
        code = exit_status(e.code)
    except Exception:
        traceback.print_exc()
        code = 1
    atexit._run_exitfuncs()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except (OSError, ValueError):
            pass
    os._exit(code)
