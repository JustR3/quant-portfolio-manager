#!/usr/bin/env python3
"""
WS0 feasibility spike: can yfinance supply point-in-time fundamentals + shares?

Checks, for a sector-diverse sample of S&P names, whether yfinance returns:
  - Annual statements with fiscal PERIOD-END DATES as columns
  - The exact fields the FactorEngine needs:
      Value:   'Free Cash Flow' (cashflow), 'EBIT' (income)
      Quality: 'EBIT', 'Gross Profit', 'Total Revenue' (income),
               'Total Assets', 'Current Liabilities' (balance)
  - Shares-outstanding history (get_shares_full) for PIT market cap = shares x price
  - How many annual periods and how far back -> the reliable backtest window
  - A lag sanity check: is statement period-end far enough before "known" dates?

Throwaway / research only. Output drives the GO/NO-GO in
docs/research/2026-06-05-pit-fundamentals-feasibility.md
"""
from __future__ import annotations

import warnings
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

SAMPLE = ["AAPL", "MSFT", "JPM", "XOM", "PFE", "KO",
          "CAT", "NVDA", "WMT", "DUK", "BA", "AMZN"]

INCOME_FIELDS = ["EBIT", "Gross Profit", "Total Revenue"]
BALANCE_FIELDS = ["Total Assets", "Current Liabilities"]
CASHFLOW_FIELDS = ["Free Cash Flow"]


def _periods(df: pd.DataFrame) -> list:
    """Return sorted column dates of a yfinance statement, if any."""
    if df is None or df.empty:
        return []
    try:
        return sorted([pd.to_datetime(c) for c in df.columns])
    except Exception:
        return []


def _has(df: pd.DataFrame, field: str) -> bool:
    return df is not None and not df.empty and field in df.index


def probe(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    inc = t.income_stmt
    bal = t.balance_sheet
    cf = t.cashflow

    inc_p, _bal_p, _cf_p = _periods(inc), _periods(bal), _periods(cf)

    # Shares-outstanding history
    try:
        shares = t.get_shares_full(start="2015-01-01")
    except Exception as e:
        shares = None
        shares_err = str(e)[:60]
    else:
        shares_err = ""

    sh_start = sh_end = sh_n = None
    if shares is not None and len(shares) > 0:
        sh_idx = pd.to_datetime(shares.index)
        sh_start, sh_end, sh_n = sh_idx.min(), sh_idx.max(), len(shares)

    return {
        "ticker": ticker,
        "inc_periods": len(inc_p),
        "inc_earliest": inc_p[0].date() if inc_p else None,
        "inc_latest": inc_p[-1].date() if inc_p else None,
        "inc_fields_ok": all(_has(inc, f) for f in INCOME_FIELDS),
        "inc_missing": [f for f in INCOME_FIELDS if not _has(inc, f)],
        "bal_fields_ok": all(_has(bal, f) for f in BALANCE_FIELDS),
        "bal_missing": [f for f in BALANCE_FIELDS if not _has(bal, f)],
        "cf_fields_ok": all(_has(cf, f) for f in CASHFLOW_FIELDS),
        "cf_missing": [f for f in CASHFLOW_FIELDS if not _has(cf, f)],
        "shares_n": sh_n,
        "shares_start": sh_start.date() if sh_start is not None else None,
        "shares_end": sh_end.date() if sh_end is not None else None,
        "shares_err": shares_err,
    }


def main() -> None:
    rows = []
    for tk in SAMPLE:
        try:
            rows.append(probe(tk))
            r = rows[-1]
            print(f"  {tk:5s} inc={r['inc_periods']}p "
                  f"({r['inc_earliest']}..{r['inc_latest']}) "
                  f"fields[i/b/c]={int(r['inc_fields_ok'])}/{int(r['bal_fields_ok'])}/{int(r['cf_fields_ok'])} "
                  f"shares_n={r['shares_n']} ({r['shares_start']}..{r['shares_end']})")
            if r["inc_missing"] or r["bal_missing"] or r["cf_missing"]:
                print(f"         MISSING: inc={r['inc_missing']} bal={r['bal_missing']} cf={r['cf_missing']}")
        except Exception as e:
            print(f"  {tk:5s} ERROR: {e}")

    df = pd.DataFrame(rows)
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    n = len(df)
    print(f"Tickers probed: {n}")
    print(f"All income fields present:   {df['inc_fields_ok'].sum()}/{n}")
    print(f"All balance fields present:  {df['bal_fields_ok'].sum()}/{n}")
    print(f"All cashflow fields present: {df['cf_fields_ok'].sum()}/{n}")
    print(f"Annual periods (min/median/max): "
          f"{df['inc_periods'].min()}/{int(df['inc_periods'].median())}/{df['inc_periods'].max()}")
    earliest = pd.to_datetime(df['inc_earliest'].dropna())
    if len(earliest):
        print(f"Earliest annual period-end across sample: {earliest.min().date()} "
              f"(latest-earliest: {earliest.max().date()})")
    print(f"Shares history available: {df['shares_n'].notna().sum()}/{n}")
    sh_start = pd.to_datetime(df['shares_start'].dropna())
    if len(sh_start):
        print(f"Shares history earliest start (min/max across sample): "
              f"{sh_start.min().date()} / {sh_start.max().date()}")
    all_ok = df[['inc_fields_ok', 'bal_fields_ok', 'cf_fields_ok']].all(axis=1) & df['shares_n'].notna()
    print(f"\nTickers with EVERYTHING (all fields + shares): {all_ok.sum()}/{n}")


if __name__ == "__main__":
    main()
