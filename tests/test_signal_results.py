import numpy as np
import pandas as pd
from src.research import results as R


def _predictive_panel(factor_col, periods=12, names=200, seed=0):
    rng = np.random.default_rng(seed)
    frames = []
    for m in range(periods):
        x = rng.normal(size=names)
        fwd = x * 0.05 + rng.normal(size=names) * 0.01     # strong positive relationship
        df = pd.DataFrame({factor_col: x, "fwd_return": fwd})
        df["ticker"] = [f"T{i}" for i in range(names)]
        df["date"] = pd.Timestamp("2021-01-31") + pd.offsets.MonthEnd(m)
        frames.append(df)
    panel = pd.concat(frames, ignore_index=True)
    for c in ("momentum_raw", "value_raw", "quality_raw"):
        if c not in panel:
            panel[c] = np.nan
    return panel


def test_evaluate_factor_passes_strong_signal():
    panel = _predictive_panel("momentum_raw")
    res = R.evaluate_factor(panel, "momentum", q=5, min_names=10,
                            frequency="monthly", cost_bps=10)
    assert res.factor == "momentum"
    assert res.ic["t_stat"] > 2
    assert res.monotonic is True
    assert res.net_spread["sharpe"] > 0
    assert res.passed is True


def test_evaluate_factor_fails_pure_noise():
    rng = np.random.default_rng(7)
    frames = []
    for m in range(12):
        df = pd.DataFrame({"value_raw": rng.normal(size=200),
                           "fwd_return": rng.normal(size=200)})
        df["ticker"] = [f"T{i}" for i in range(200)]
        df["date"] = pd.Timestamp("2021-01-31") + pd.offsets.MonthEnd(m)
        df["momentum_raw"] = np.nan
        df["quality_raw"] = np.nan
        frames.append(df)
    panel = pd.concat(frames, ignore_index=True)
    res = R.evaluate_factor(panel, "value", q=5, min_names=10,
                            frequency="monthly", cost_bps=10)
    assert res.passed is False


def test_evaluate_factor_wrong_sign_fails_even_if_significant():
    panel = _predictive_panel("momentum_raw")
    panel["momentum_raw"] = -panel["momentum_raw"]   # significant but NEGATIVE IC
    res = R.evaluate_factor(panel, "momentum", q=5, min_names=10,
                            frequency="monthly", cost_bps=10)
    assert res.ic["t_stat"] < -2
    assert res.passed is False


def test_build_caveats_flags_overlap_and_survivorship():
    cav = R.build_caveats(frequency="monthly", horizon_months=3, factors=["value"])
    text = " ".join(cav).lower()
    assert "survivorship" in text
    assert "overlap" in text                  # horizon (3) != monthly spacing (1)
    assert any("value" in c.lower() or "fundamental" in c.lower() for c in cav)


def test_build_caveats_sec_source_drops_thin_yfinance_note():
    yf = " ".join(R.build_caveats("monthly", 1, ["value"], fundamentals_source="yfinance")).lower()
    sec = " ".join(R.build_caveats("monthly", 1, ["value"], fundamentals_source="sec")).lower()
    assert "yfinance" in yf and "~2021-2022" in yf
    assert "yfinance" not in sec
    assert "sec" in sec and ("operatingincomeloss" in sec or "price store" in sec)


def test_signal_eval_result_json_roundtrip(tmp_path):
    panel = _predictive_panel("momentum_raw")
    fr = R.evaluate_factor(panel, "momentum", q=5, min_names=10,
                           frequency="monthly", cost_bps=10)
    result = R.SignalEvalResult(
        factors=[fr], caveats=["x"], params={"frequency": "monthly", "horizon_months": 1})
    out = tmp_path / "res.json"
    result.to_json(out)
    loaded = R.json.loads(out.read_text())
    assert loaded["factors"][0]["factor"] == "momentum"
    assert loaded["factors"][0]["passed"] is True
    assert loaded["params"]["frequency"] == "monthly"


def test_signal_eval_result_render_contains_verdict_and_caveats():
    panel = _predictive_panel("momentum_raw")
    fr = R.evaluate_factor(panel, "momentum", q=5, min_names=10,
                           frequency="monthly", cost_bps=10)
    text = R.SignalEvalResult(factors=[fr], caveats=["SURVIVORSHIP note"],
                              params={}).render()
    assert "MOMENTUM" in text.upper()
    assert "PASS" in text.upper()
    assert "SURVIVORSHIP note" in text


def test_build_panel_for_args_selects_sec_provider(monkeypatch):
    from types import SimpleNamespace
    from src.research import command as cmd
    captured = {}

    def _fake_build_panel(tickers, obs_dates, horizon_months, close_prices, adj_prices, fundamentals):
        captured["provider"] = type(fundamentals).__name__
        return _predictive_panel("momentum_raw")

    monkeypatch.setattr(cmd.sp, "universe_tickers", lambda: ["AAA"])
    monkeypatch.setattr(cmd.sp, "load_inputs", lambda tickers, **k: ({"AAA": None}, {"AAA": None}))
    monkeypatch.setattr(cmd.sp, "build_panel", _fake_build_panel)
    args = SimpleNamespace(factors="value", frequency="monthly", horizon=1, quantiles=5,
                           min_names_per_bucket=10, start="2021-01-01", end="2021-12-31",
                           transaction_cost_bps=10, export=None, fundamentals="sec")
    cmd._build_panel_for_args(args)
    assert captured["provider"] == "SECFundamentals"


def test_run_signal_eval_with_injected_panel(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace
    from src.research import command as cmd
    panel = _predictive_panel("momentum_raw")
    # Inject a prebuilt panel so the command runs fully offline (no store/network).
    monkeypatch.setattr(cmd, "_build_panel_for_args", lambda args: panel)
    args = SimpleNamespace(
        factors="momentum", frequency="monthly", horizon=1, quantiles=5,
        min_names_per_bucket=10, start="2021-01-01", end="2021-12-31",
        transaction_cost_bps=10, export=str(tmp_path),
    )
    result = cmd.run_signal_eval(args)
    out = capsys.readouterr().out
    assert "MOMENTUM" in out.upper()
    assert result.factors[0].factor == "momentum"
    # JSON artifact written under export dir
    assert any(p.suffix == ".json" for p in tmp_path.iterdir())


def _strong_factor_panel(n=60, seed=0):
    """A factor with a strong, monotone, positive relationship to forward return.
    Factor values are fixed per period (zero leg turnover); only fwd has noise, so
    the IC time-series has finite, non-degenerate variance (real t-stat)."""
    import numpy as np
    import pandas as pd
    rng = np.random.default_rng(seed)
    rows = []
    for d in pd.date_range("2016-01-31", periods=n, freq="ME"):
        for i in range(20):
            rows.append({"date": d, "ticker": f"T{i}",
                         "gross_profitability_raw": float(i),
                         "fwd_return": 0.05 * i + rng.normal(0, 0.02)})
    return pd.DataFrame(rows)


def test_evaluate_factor_respects_t_gate():
    from src.research import results as R
    panel = _strong_factor_panel()
    common = dict(q=5, min_names=10, frequency="monthly", cost_bps=10)
    res_low = R.evaluate_factor(panel, "gross_profitability", t_gate=2.0, **common)
    res_high = R.evaluate_factor(panel, "gross_profitability", t_gate=1e9, **common)
    assert res_low.passed is True
    assert res_high.passed is False                    # same data, only the gate changed
    assert res_low.ic["t_stat"] == res_high.ic["t_stat"]


def test_build_caveats_has_qleg_and_issuance_notes():
    from src.research import results as R
    cav = " ".join(R.build_caveats("monthly", 1, ["net_issuance", "asset_growth"],
                                   fundamentals_source="sec"))
    assert "issuance" in cav.lower() or "split" in cav.lower()
    assert "bonferroni" in cav.lower() or "q-leg" in cav.lower() or "rmw" in cav.lower()
