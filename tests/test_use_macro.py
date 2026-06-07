def test_display_cape_summary_is_defined_and_runs(capsys):
    from src.pipeline.external.shiller import display_cape_summary
    display_cape_summary({"current_cape": 35.0, "risk_scalar": 0.7,
                          "regime": "EXPENSIVE", "description": "elevated"})
    out = capsys.readouterr().out
    assert "CAPE" in out
    assert "0.70x" in out


def test_workflow_namespace_has_display_cape_summary():
    # The --use-macro path calls display_cape_summary; it must be importable there,
    # otherwise the NameError is swallowed and macro is silently disabled.
    import src.pipeline.systematic_workflow as wf
    assert hasattr(wf, "display_cape_summary")
