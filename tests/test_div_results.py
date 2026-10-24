"""Gate and artifact tests — effective-bets diagnostic (spec §6, §9 items 6 and 9)."""

import json

import pytest

from src.research import div_results as dr


def _m(full=3.0, stress=(2.5, 2.2, 2.1), delta=0.2):
    return {
        "n_eff_full": full,
        "n_eff_stress": {"GFC": stress[0], "COVID": stress[1], "2022": stress[2]},
        "sharpe_delta": delta,
    }


class TestGate:
    def test_locked_thresholds(self):
        assert (dr.G1_MIN_NEFF_FULL, dr.G2_MIN_NEFF_STRESS, dr.G3_MIN_SHARPE_DELTA) == (
            2.5,
            2.0,
            0.10,
        )

    def test_all_pass_is_go(self):
        assert dr.gate_verdict(_m(), gated=True) == "GO"

    @pytest.mark.parametrize(
        "m", [_m(full=2.4999), _m(stress=(2.5, 1.9999, 3.0)), _m(delta=0.0999)]
    )
    def test_any_single_failure_is_no_go(self, m):
        assert dr.gate_verdict(m, gated=True) == "NO-GO"

    def test_exact_thresholds_pass(self):
        assert (
            dr.gate_verdict(
                _m(full=2.5, stress=(2.0, 2.0, 2.0), delta=0.10), gated=True
            )
            == "GO"
        )

    @pytest.mark.parametrize(
        "m",
        [
            _m(full=float("nan")),
            _m(stress=(float("nan"), 3.0, 3.0)),
            _m(delta=float("nan")),
        ],
    )
    def test_nan_metric_is_degenerate_never_pass(self, m):
        assert dr.gate_verdict(m, gated=True) == "FAIL (degenerate)"

    def test_missing_stress_window_is_degenerate(self):
        m = _m()
        del m["n_eff_stress"]["COVID"]
        assert dr.gate_verdict(m, gated=True) == "FAIL (degenerate)"

    def test_degenerate_reason_overrides_everything(self):
        assert (
            dr.gate_verdict(_m(), gated=True, degenerate_reason="stale")
            == "FAIL (degenerate)"
        )
        assert (
            dr.gate_verdict(None, gated=True, degenerate_reason="stale")
            == "FAIL (degenerate)"
        )

    def test_ungated_run_never_emits_go_or_no_go(self):
        assert dr.gate_verdict(_m(), gated=False) == "UN-GATED DIAGNOSTIC"
        assert dr.gate_verdict(_m(full=1.0), gated=False) == "UN-GATED DIAGNOSTIC"


def _reject_constant(c):
    raise ValueError(f"non-strict JSON constant {c}")


class TestArtifact:
    @staticmethod
    def _result(**kw):
        base = dict(
            verdict="NO-GO",
            gated=True,
            params={"a": 1},
            gate_metrics=_m(delta=float("nan")),
            diagnostics={"x": float("nan")},
            spike_log=[],
            caveats=["c"],
            degenerate_reason=None,
        )
        base.update(kw)
        return dr.DivEvalResult(**base)

    def test_json_is_strict_and_nan_becomes_null(self, tmp_path):
        p = tmp_path / "a.json"
        self._result().to_json(p)
        data = json.loads(p.read_text(), parse_constant=_reject_constant)
        assert data["gate_metrics"]["sharpe_delta"] is None
        assert data["diagnostics"]["x"] is None
        assert data["gated"] is True and data["verdict"] == "NO-GO"

    def test_render_states_verdict_and_gated_flag(self):
        txt = self._result(verdict="UN-GATED DIAGNOSTIC", gated=False).render()
        assert "UN-GATED DIAGNOSTIC" in txt
        assert "gated: false" in txt.lower()
