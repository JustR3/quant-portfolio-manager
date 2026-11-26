"""TEMPORARY CI probe (fix/cli-exit-abort): count CLI aborts at exit. Removed before merge."""

import collections
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
N = 160


def _store(base: Path) -> None:
    idx = pd.bdate_range("1993-01-29", periods=60)
    close = 45 * np.exp(np.cumsum(np.random.default_rng(5).normal(0.0003, 0.011, 60)))
    cols = pd.MultiIndex.from_tuples([("Adj Close", "SPY"), ("Close", "SPY")])
    df = pd.DataFrame(np.c_[close, close], index=idx, columns=cols)
    df.index.name = "Date"
    (base / "prices").mkdir(parents=True)
    df.to_parquet(base / "prices" / "SPY.parquet")
    fetched = (idx.max() + pd.Timedelta(hours=22)).tz_localize("UTC")
    (base / "SPY.meta.json").write_text(json.dumps({"fetched_at": fetched.isoformat()}))


def test_exit_probe(tmp_path):
    _store(tmp_path / "s")
    dca = [
        sys.executable,
        "main.py",
        "dca-eval",
        "--base-dir",
        str(tmp_path / "s"),
        "--export",
        str(tmp_path / "o"),
    ]
    pq_file = str(tmp_path / "s" / "prices" / "SPY.parquet")
    variants = {
        "dca_fixed": (dca, {}, 300),
        "control_pandas_read_exit3": (
            [
                sys.executable,
                "-c",
                f"import pandas as pd, sys; pd.read_parquet({pq_file!r}); sys.exit(3)",
            ],
            {},
            200,
        ),
        "pandas_read_run_and_exit": (
            [
                sys.executable,
                "-c",
                "import pandas as pd, sys\n"
                "from src.cli_exit import run_and_exit\n"
                "def f():\n"
                f"    pd.read_parquet({pq_file!r})\n"
                "    sys.exit(3)\n"
                "run_and_exit(f)\n",
            ],
            {},
            200,
        ),
    }
    report = {}
    for name, (cmd, extra, n) in variants.items():
        env = {**os.environ, "PYTHONFAULTHANDLER": "1", **extra}

        def one(_, cmd=cmd, env=env):
            r = subprocess.run(
                cmd, cwd=ROOT, env=env, capture_output=True, text=True, timeout=120
            )
            return r.returncode, r.stderr[:2500] if r.returncode < 0 else ""

        with ThreadPoolExecutor(4) as ex:
            res = list(ex.map(one, range(n)))
        codes = collections.Counter(c for c, _ in res)
        errs = [e for c, e in res if c < 0][:2]
        report[name] = {"codes": dict(codes), "stderr": errs}
    msg = json.dumps(report, indent=1)
    print(msg)
    raise AssertionError("PROBE REPORT (intentional failure)\n" + msg)
