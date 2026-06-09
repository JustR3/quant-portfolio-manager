# New Factor Inputs (q-legs) — Pre-registered Go/No-Go

- **Date:** 2026-06-09
- **Spec/Plan:** `docs/superpowers/specs/2026-06-09-new-factor-inputs-design.md`,
  `docs/superpowers/plans/2026-06-09-new-factor-inputs.md`.
- **Spike (net-issuance splits):** `docs/research/2026-06-09-net-issuance-splits-spike.md` (heuristic
  validated → net issuance kept in the set).
- **Code:** new pure factors in `fundamentals.py` (`gross_profitability`, `asset_growth_factor`,
  `net_issuance_factor`); SEC enrichment in `sec_fundamentals.pit_factors_from_prepared`
  (prior-year + split-adjusted shares); `signal-eval --factors gross_profitability,net_issuance,asset_growth --t-gate`.
- **Run:** `signal-eval --factors gross_profitability,net_issuance,asset_growth --fundamentals sec
  --t-gate 2.4 --start 2016-01-01 --end 2026-06-01 --frequency monthly --horizon 1` (offline; cached SEC
  facts + local prices). Artifact `data/research/signal-eval-20260609_210841.json`.

## TL;DR — NO. None of the three new factors shows edge.

Pre-registered (locked before looking): **gross profitability (GP/Assets), net share issuance, asset
growth**, judged at a Bonferroni-raised bar **|t| ≥ 2.4** (k=3). Result over **125 monthly
cross-sections (~10yr, ~22.6k stock-months)**: all three are flat. The strongest, gross profitability,
reaches **t = 0.73** — not a near-miss, and far below even the un-raised 2.0. **Third honest negative
in a row** on free large-cap US data.

## Verdict table

Standard bar (PASS iff +sign, |t| ≥ **2.4**, broadly monotone, net L-S Sharpe > 0), monthly, 1m horizon,
deciles, 10 bps/side. Deep SEC PIT fundamentals, current SP500 membership, banks/financials excluded.

| Factor | mean IC | t-stat | Monotone | gross L-S Sharpe | net L-S Sharpe | N obs | Pass? |
|---|---|---|---|---|---|---|---|
| **Gross profitability** (GP/Assets) | +0.0069 | **+0.73** | No | +0.12 | +0.10 | 22,642 | ✗ |
| **Net issuance** | +0.0011 | +0.11 | No | −0.48 | −0.52 | 22,537 | ✗ |
| **Asset growth** | −0.0005 | −0.04 | No | +0.03 | +0.00 | 22,642 | ✗ |

Window 2016-01-31 → 2026-05-31, 125 periods, ~180 measurable names/period.

## Interpretation

- **Gross profitability** — the best of the three, and still nothing: t = 0.73, non-monotone deciles
  (returns flat ~1.4–1.9% across all ten buckets, no spread), net L-S Sharpe +0.10. Novy-Marx's
  large-cap "quality" premium does not show up in this universe/window.
- **Net issuance** — mean IC ≈ 0 (t = 0.11), and the long-short spread is **negative** (−0.52 net): the
  lowest bucket (heaviest issuers) had the highest forward return (2.4% vs ~1.8% for buyback-ers). The
  issuance anomaly is absent-to-reversed here. (Split contamination is ruled out — the spike validated
  the adjustment; see the splits doc.)
- **Asset growth** — dead flat (t = −0.04, net Sharpe 0.00). The investment/CMA effect is not present.
- **None is monotone**, none clears even |t| = 2.0, so the Bonferroni bar (2.4) is not the binding
  constraint — these factors simply have no signal in free, current-membership, large-cap US data.

## Caveats

- **Survivorship persists:** universe = current SP500 membership applied historically; delisted names
  absent. This *inflates* results, so a negative here is, if anything, conservative.
- **Universe held constant:** same banks/financials exclusion as Value/Quality (a name excluded there is
  excluded here) for a clean comparison — so the new factors are measured on the same ~180 names/period.
- **Stale-income edge at the final date:** a handful of names at `as_of=2026-05-31` logged the existing
  `period_misaligned` warning (income period-end older than balance/cashflow) because the curated SEC
  `CONCEPT_MAP` didn't resolve their most-recent revenue/GP tag variant. ~13 names at one of 125 dates —
  immaterial to the aggregate verdict; pre-existing behavior, not introduced here.
- **Net issuance** uses cover-page `EntityCommonStockSharesOutstanding`, split-adjusted via the
  validated ratio heuristic; it is price-free (no market-cap dependency).

## Conclusion & recommendation

**Third consecutive honest negative on free large-cap US equities** — momentum (phase #1), Value/Quality
deep-PIT (phase #2), and now the three q-legs (phase #3). The factor-zoo's most-cited free large-cap
anomalies (profitability, investment, issuance) show no cross-sectional edge here. This closes the "new
inputs" escape hatch the way phase #2 closed "more data."

The live options now (a fresh brainstorm, not a continuation of this branch):

1. **Different universe** — take these same factors (and V/Q/M) **down-cap** to small/mid-caps where the
   anomalies are documented to actually live, and/or do the **survivorship-kill** sub-project (historical
   membership + delisted prices). This is the only remaining "find real edge" path, and it is a bigger
   data lift (new prices + delisting handling).
2. **Reframe** the project as an honest, well-tested PIT research harness / methodology artifact — its
   demonstrated strength — rather than a live alpha engine. Free, current-membership, large-cap US data
   is the market's most efficient slice; three rigorous negatives is itself the finding.

Do **not** build BL view-calibration, automation, or composites on this factor set — there is no
validated signal to express.
