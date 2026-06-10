"""Gate logic (both parts required, NaN-safe) and artifact round-trip."""
import json

from src.research import ts_results as tr


def _metrics(p_boot, full_dom, sub_dom):
    return dict(rule="x", window="2011-01-03..2026-05-31", p_boot=p_boot,
                sharpe_strat=1.0 if full_dom else 0.4, sharpe_bench=0.5,
                sub_dominance=sub_dom, alpha=0.0002, beta=0.8, nw_t=2.5,
                n_days=5000, turnover=3.2, cost_drag=0.001)


def test_gate_requires_both_parts():
    assert tr.gate_pass(_metrics(0.009, True, [True, True, False]))       # 2/3 + p ok
    assert not tr.gate_pass(_metrics(0.011, True, [True, True, False]))   # p fails at 0.01
    assert not tr.gate_pass(_metrics(0.009, True, [True, False, False]))  # 1/3 sub-windows
    assert not tr.gate_pass(_metrics(0.009, False, [True, True, True]))   # full-window dom fails


def test_nan_p_fails_gate():
    assert not tr.gate_pass(_metrics(float("nan"), True, [True, True, True]))


def test_boundary_p_exactly_at_gate_fails():
    assert not tr.gate_pass(_metrics(0.01, True, [True, True, True]))  # strict <


def test_json_round_trip_and_render(tmp_path):
    m = _metrics(0.5, False, [False, False, False])
    m["pass"] = tr.gate_pass(m)
    res = tr.TSEvalResult(rules=[m], params={"p_gate": 0.01, "cost_bps": 10}, caveats=["c1"])
    out = tmp_path / "a.json"
    res.to_json(out)
    data = json.loads(out.read_text())
    assert data["rules"][0]["rule"] == "x" and data["params"]["p_gate"] == 0.01
    text = res.render()
    assert "FAIL" in text and "x" in text
