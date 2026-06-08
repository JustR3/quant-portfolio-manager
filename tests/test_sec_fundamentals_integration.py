import os
import pandas as pd
import pytest
from src.pipeline import sec_fundamentals as sf

pytestmark = pytest.mark.integration


def test_fetch_facts_aapl_has_deep_revenue():
    os.environ.setdefault("EDGAR_IDENTITY", "whispersdi3@gmail.com")
    facts = sf.fetch_facts("AAPL")
    rev = facts[facts["field"] == "revenue"]
    assert rev["period_end"].min() <= pd.Timestamp("2010-12-31")   # deep history
    assert facts["filed"].notna().all()


def test_jpm_excluded_for_missing_current_liabilities():
    os.environ.setdefault("EDGAR_IDENTITY", "whispersdi3@gmail.com")
    facts = sf.fetch_facts("JPM")
    pf = sf.pit_factors_from_facts(facts, pd.Timestamp("2020-06-30"), price=100.0)
    assert pf.excluded   # banks lack LiabilitiesCurrent
