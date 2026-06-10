"""Gate logic (every condition required, NaN-safe, strict p boundary) and artifact round-trip."""
import json
import math

from src.research import pead_results as pr


def _m(p=0.001, mean=1e-4, thirds=(True, True, False), mono=True):
    return dict(measure="sue_e", window="2015-02-02..2026-03-06", p_boot=p, net_mean=mean,
                thirds_positive=list(thirds), monotone=mono, alpha=1e-4, beta=0.05, nw_t=2.5,
                n_days=2500, n_events=15000, turnover=80.0, cost_drag=0.002, sharpe_net=0.8)


def test_gate_requires_every_condition():
    assert pr.gate_pass(_m())
    assert not pr.gate_pass(_m(p=0.02))                       # p >= 0.05/3
    assert not pr.gate_pass(_m(mean=-1e-5))                   # net mean <= 0
    assert not pr.gate_pass(_m(thirds=(True, False, False)))  # 1/3 thirds
    assert not pr.gate_pass(_m(mono=False))                   # quintiles not monotone
    assert not pr.gate_pass(_m(p=float("nan")))               # degenerate


def test_p_gate_boundary_strict():
    assert pr.gate_pass(_m(p=0.0166))
    assert not pr.gate_pass(_m(p=0.05 / 3))


def test_render_and_json(tmp_path):
    m = _m(p=0.5, mean=-1e-5, thirds=(False, False, False), mono=False)
    m["pass"] = pr.gate_pass(m)
    res = pr.PEADResult(measures=[m], params={"p_gate": 0.05 / 3, "horizon": 60}, caveats=["c1"])
    text = res.render()
    assert "FAIL" in text and "sue_e" in text
    out = tmp_path / "r.json"
    res.to_json(out)
    data = json.loads(out.read_text())
    assert data["measures"][0]["measure"] == "sue_e"
    assert data["params"]["horizon"] == 60
    assert not math.isnan(data["params"]["p_gate"])
