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


# --- adversarial fuzz: duplicate keys, concept-priority collisions, extreme
# magnitudes, and impossible dates. Mirrors test_sec_fundamentals.py's coverage
# for the sibling fetch_facts_quarterly concept-priority walk. Each of these
# already behaves correctly -- regression tests, not fixes.


class _FakeCompanyDuplicateRows:
    """Same concept returns two rows for the identical (period_end, fiscal_period,
    filed) key with different values -- dedup-by-key must keep the first (100.0)."""

    _df = pd.DataFrame(
        {
            "numeric_value": [100.0, 555.0],
            "fiscal_period": ["Q1", "Q1"],
            "period_end": pd.to_datetime(["2020-03-31", "2020-03-31"]),
            "filing_date": pd.to_datetime(["2020-04-30", "2020-04-30"]),
        }
    )

    def __init__(self, ticker):
        self.facts = _FakeFacts(self._df)


def test_fetch_facts_quarterly_duplicate_key_within_concept_keeps_first(monkeypatch):
    import edgar

    monkeypatch.setattr(edgar, "Company", _FakeCompanyDuplicateRows)
    facts = sq.fetch_facts_quarterly("FAKE")
    ni = facts[facts["field"] == "net_income"]
    assert len(ni) == 1
    assert ni.iloc[0]["value"] == 100.0


class _FakeQueryPerConcept:
    def __init__(self, per_concept):
        self._per_concept = per_concept
        self._concept = None

    def by_concept(self, concept, exact=True):
        self._concept = concept
        return self

    def to_dataframe(self):
        return self._per_concept.get(self._concept, pd.DataFrame())


class _FakeFactsPerConcept:
    def __init__(self, per_concept):
        self._per_concept = per_concept

    def query(self):
        return _FakeQueryPerConcept(self._per_concept)


def test_fetch_facts_quarterly_concept_priority_keeps_first_on_value_collision(
    monkeypatch,
):
    """net_income's lower-priority ProfitLoss fallback returns a row for a
    (period_end, fiscal_period, filed) pair the higher-priority NetIncomeLoss
    concept already claimed, under a DIFFERENT value. The higher-priority value
    (100.0) must win, not be overwritten or blended with 999.0."""
    import edgar

    high, low = (
        sq.QUARTERLY_CONCEPT_MAP["net_income"][0],
        sq.QUARTERLY_CONCEPT_MAP["net_income"][1],
    )
    per_concept = {
        high: pd.DataFrame(
            {
                "numeric_value": [100.0],
                "fiscal_period": ["Q1"],
                "period_end": pd.to_datetime(["2020-03-31"]),
                "filing_date": pd.to_datetime(["2020-04-30"]),
            }
        ),
        low: pd.DataFrame(
            {
                "numeric_value": [999.0],
                "fiscal_period": ["Q1"],
                "period_end": pd.to_datetime(["2020-03-31"]),
                "filing_date": pd.to_datetime(["2020-04-30"]),
            }
        ),
    }

    class _FakeCompanyPriority:
        def __init__(self, ticker):
            self.facts = _FakeFactsPerConcept(per_concept)

    monkeypatch.setattr(edgar, "Company", _FakeCompanyPriority)
    facts = sq.fetch_facts_quarterly("FAKE")
    ni = facts[facts["field"] == "net_income"]
    assert len(ni) == 1
    assert ni.iloc[0]["value"] == 100.0


class _FakeCompanyExtremeMagnitude:
    """A finite but extreme-magnitude value (1e18) must be kept, not dropped --
    only NaN/+-inf are excluded per the fetch_facts_quarterly contract."""

    _df = pd.DataFrame(
        {
            "numeric_value": [1e18],
            "fiscal_period": ["Q1"],
            "period_end": pd.to_datetime(["2020-03-31"]),
            "filing_date": pd.to_datetime(["2020-04-30"]),
        }
    )

    def __init__(self, ticker):
        self.facts = _FakeFacts(self._df)


def test_fetch_facts_quarterly_extreme_magnitude_value_kept(monkeypatch):
    import edgar

    monkeypatch.setattr(edgar, "Company", _FakeCompanyExtremeMagnitude)
    facts = sq.fetch_facts_quarterly("FAKE")
    ni = facts[facts["field"] == "net_income"]
    assert len(ni) == 1
    assert ni.iloc[0]["value"] == 1e18


class _FakeCompanyFiledBeforePeriodEnd:
    """A filed date earlier than its own period_end is impossible in reality (a
    filer error) -- fetch_facts_quarterly does not validate filed >= period_end,
    so the row must simply pass through unmodified, never crash."""

    _df = pd.DataFrame(
        {
            "numeric_value": [50.0],
            "fiscal_period": ["Q1"],
            "period_end": pd.to_datetime(["2020-03-31"]),
            "filing_date": pd.to_datetime(["2020-01-01"]),  # before period_end
        }
    )

    def __init__(self, ticker):
        self.facts = _FakeFacts(self._df)


def test_fetch_facts_quarterly_filed_before_period_end_does_not_crash(monkeypatch):
    import edgar

    monkeypatch.setattr(edgar, "Company", _FakeCompanyFiledBeforePeriodEnd)
    facts = sq.fetch_facts_quarterly("FAKE")  # must not raise
    ni = facts[facts["field"] == "net_income"]
    assert len(ni) == 1
    assert ni.iloc[0]["filed"] == pd.Timestamp("2020-01-01")
    assert ni.iloc[0]["period_end"] == pd.Timestamp("2020-03-31")
