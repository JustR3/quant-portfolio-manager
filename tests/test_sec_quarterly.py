import pandas as pd

from src.pipeline import sec_quarterly as sq


# --- self-harden: fetch_facts_quarterly must drop non-finite fact values ----
# Same gap as sec_fundamentals.fetch_facts: `.notna()` drops NaN but not +-inf.


class _FakeQuery:
    def __init__(self, df):
        self._df = df

    def by_concept(self, concept, exact=True):
        return self

    def to_dataframe(self):
        return self._df


class _FakeFacts:
    def __init__(self, df):
        self._df = df

    def query(self):
        return _FakeQuery(self._df)


class _FakeCompany:
    """Every concept probe returns the same fixed rows; only exercises the
    numeric_value filtering, not the concept-priority walk."""

    _df = pd.DataFrame(
        {
            "numeric_value": [50.0, float("inf"), float("-inf")],
            "fiscal_period": ["Q1", "Q2", "Q3"],
            "period_end": pd.to_datetime(["2020-03-31", "2020-06-30", "2020-09-30"]),
            "filing_date": pd.to_datetime(["2020-04-30", "2020-07-30", "2020-10-30"]),
        }
    )

    def __init__(self, ticker):
        self.facts = _FakeFacts(self._df)


def test_fetch_facts_quarterly_drops_non_finite_values(monkeypatch):
    import edgar

    monkeypatch.setattr(edgar, "Company", _FakeCompany)
    facts = sq.fetch_facts_quarterly("FAKE")
    assert not facts.empty
    assert facts["value"].apply(lambda v: v == v and abs(v) != float("inf")).all()
    # the finite Q1 row must still survive for every field
    assert (facts["fiscal_period"] == "Q1").sum() == len(sq.QUARTERLY_CONCEPT_MAP)


class _FakeCompanyNonNumeric(_FakeCompany):
    """Adversarial-review finding: np.isfinite on a mixed dtype (object) column crashes
    instead of dropping the bad row."""

    _df = pd.DataFrame(
        {
            "numeric_value": [50.0, "N/A", float("-inf")],
            "fiscal_period": ["Q1", "Q2", "Q3"],
            "period_end": pd.to_datetime(["2020-03-31", "2020-06-30", "2020-09-30"]),
            "filing_date": pd.to_datetime(["2020-04-30", "2020-07-30", "2020-10-30"]),
        }
    )


def test_fetch_facts_quarterly_drops_non_numeric_values_without_crashing(monkeypatch):
    import edgar

    monkeypatch.setattr(edgar, "Company", _FakeCompanyNonNumeric)
    facts = sq.fetch_facts_quarterly("FAKE")  # must not raise
    assert not facts.empty
    assert (facts["fiscal_period"] == "Q1").sum() == len(sq.QUARTERLY_CONCEPT_MAP)
    assert (facts["fiscal_period"] == "Q2").sum() == 0
    assert (facts["fiscal_period"] == "Q3").sum() == 0
