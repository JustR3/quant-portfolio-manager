"""DCA RSI(2) timing command: store loading, session cut, contracts, offline smoke, CLI."""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from src.research import dca_command as dc

PROJECT_ROOT = Path(__file__).parent.parent


def fake_store(base: Path, n: int = 3200, fetched="2005-09-01T22:00:00+00:00") -> None:
    rng = np.random.default_rng(5)
    idx = pd.bdate_range("1993-01-29", periods=n)
    close = 45 * np.exp(np.cumsum(rng.normal(0.0003, 0.011, n)))
    adj = close * np.linspace(0.6, 1.0, n)
    cols = pd.MultiIndex.from_tuples([("Adj Close", "SPY"), ("Close", "SPY")])
    df = pd.DataFrame(np.c_[adj, close], index=idx, columns=cols)
    df.index.name = "Date"
    (base / "prices").mkdir(parents=True)
    df.to_parquet(base / "prices" / "SPY.parquet")
    (base / "SPY.meta.json").write_text(json.dumps({"fetched_at": fetched}))


def test_last_session_rule():
    assert dc.last_session(pd.Timestamp("2026-11-25 17:34", tz="UTC")) == pd.Timestamp(
        "2026-11-24"
    )
    assert dc.last_session(pd.Timestamp("2026-11-25 21:00", tz="UTC")) == pd.Timestamp(
        "2026-11-25"
    )


def test_prepare_cuts_partial_bar_and_checks_age(tmp_path):
    fake_store(tmp_path)
    px, fetched = dc.load_store(tmp_path)
    last = px.index.max()
    early = (last + pd.Timedelta(hours=15)).tz_localize(
        "UTC"
    )  # same UTC date, before 21:00
    assert dc.prepare(px, early).index.max() < last
    with pytest.raises(ValueError, match="more than"):
        dc.prepare(px, (last + pd.Timedelta(days=30)).tz_localize("UTC"))


def test_load_store_missing(tmp_path):
    with pytest.raises(ValueError, match="download_dca_spy"):
        dc.load_store(tmp_path)


def test_run_offline_smoke(tmp_path, capsys):
    fake_store(tmp_path / "store")
    px, _ = dc.load_store(tmp_path / "store")
    fetched = (px.index.max() + pd.Timedelta(hours=22)).tz_localize("UTC")
    (tmp_path / "store" / "SPY.meta.json").write_text(
        json.dumps({"fetched_at": fetched.isoformat()})
    )
    args = SimpleNamespace(
        base_dir=str(tmp_path / "store"), export=str(tmp_path / "out")
    )
    res = dc.run_dca_eval(args)
    d = res.data
    assert d["months"] >= 120 and d["verdict"] in {"PASS", "FAIL"}
    assert res.rules[0]["verdict"] == d["verdict"]
    for x in ("B", "C"):
        lo, hi = d[x]["ci"]
        assert lo <= hi
    art = list((tmp_path / "out").glob("dca-eval-*.json"))
    assert len(art) == 1 and json.loads(art[0].read_text())["verdict"] == d["verdict"]
    assert "VERDICT:" in capsys.readouterr().out


def test_cli_help_and_readme_command():
    """The README's dca-eval line names a real subcommand with working help."""
    out = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "main.py"), "dca-eval", "--help"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert out.returncode == 0 and "uv run ./main.py dca-eval" in out.stdout
    readme = (PROJECT_ROOT / "README.md").read_text()
    assert "uv run ./main.py dca-eval" in readme
    assert "uv run python tools/download_dca_spy.py" in readme
    assert (PROJECT_ROOT / "tools" / "download_dca_spy.py").exists()


def test_too_few_months_is_inconclusive_and_exits_3(tmp_path):
    fake_store(tmp_path / "s", n=60)  # under 3 months of bars
    px, _ = dc.load_store(tmp_path / "s")
    fetched = (px.index.max() + pd.Timedelta(hours=22)).tz_localize("UTC")
    (tmp_path / "s" / "SPY.meta.json").write_text(
        json.dumps({"fetched_at": fetched.isoformat()})
    )
    res = dc.evaluate(dc.prepare(px, fetched), fetched)
    assert (
        res.data["verdict"] == "INCONCLUSIVE"
        and "months" in res.data["inconclusive_reason"]
    )
    assert "INCONCLUSIVE" in res.render()
    out = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "main.py"),
            "dca-eval",
            "--base-dir",
            str(tmp_path / "s"),
            "--export",
            str(tmp_path / "o"),
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode == 3, out.stdout + out.stderr


def test_one_bootstrap_draw_shared_by_b_and_c(tmp_path, monkeypatch):
    fake_store(tmp_path / "s")
    px, _ = dc.load_store(tmp_path / "s")
    fetched = (px.index.max() + pd.Timedelta(hours=22)).tz_localize("UTC")
    calls = []
    orig = dc.de.block_positions
    monkeypatch.setattr(
        dc.de, "block_positions", lambda *a, **k: calls.append(a) or orig(*a, **k)
    )
    dc.evaluate(dc.prepare(px, fetched), fetched)
    assert len(calls) == 1


def test_signal_uses_raw_close_and_buys_use_adjusted(tmp_path):
    fake_store(tmp_path / "s")
    px, _ = dc.load_store(tmp_path / "s")
    fetched = (px.index.max() + pd.Timedelta(hours=22)).tz_localize("UTC")
    base = dc.evaluate(dc.prepare(px, fetched), fetched).data
    # A different adjustment path: buy prices change, the signal (raw close) does not.
    alt = px.assign(adj=px["adj"] * np.linspace(1.0, 1.3, len(px)))
    got = dc.evaluate(dc.prepare(alt, fetched), fetched).data
    assert got["A"]["share_on_rsi"] == base["A"]["share_on_rsi"]
    assert got["B"]["tw"] != base["B"]["tw"]


def test_download_tool_refuses_to_overwrite(tmp_path):
    (tmp_path / "data/historical/dca/prices").mkdir(parents=True)
    (tmp_path / "data/historical/dca/prices/SPY.parquet").write_bytes(b"x")
    out = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "tools" / "download_dca_spy.py")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert out.returncode != 0 and "--force" in out.stderr
    help_out = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "tools" / "download_dca_spy.py"), "--help"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert help_out.returncode == 0 and "--force" in help_out.stdout
    assert (tmp_path / "data/historical/dca/prices/SPY.parquet").read_bytes() == b"x"
