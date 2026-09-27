# Quant Portfolio Manager

![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-Parked%20(research%20artifact)-blue)
![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Linux-lightgrey)

> **An honest point-in-time (PIT) equity research harness — and the five pre-registered
> negative results it produced.**

This project set out to find tradable edge on free data with a factor → Black-Litterman pipeline.
It ended somewhere more valuable: a rigorously honest research harness — three decoupled
evaluation gates, two SEC PIT data pipelines, integrity-guarded price stores — and a definitive,
pre-registered answer to its own question:

**There is no demonstrated edge on free, survivorship-biased US large-cap data — confirmed five
times, across every signal class that data can test.**

The methodology is the product. Every study below was pre-registered (signals, parameters,
windows, and pass/fail gates locked *before* any result was seen), judged at
multiple-testing-adjusted bars, and shipped with its verdict — including a stopping rule that was
honored when it fired.

## The headline result: five honest negatives

| # | Study | Signal class | Verdict | Write-up |
|---|-------|--------------|---------|----------|
| 1 | Momentum (12-0 reproducible via `signal-eval`; 12-1, 6-1 and sector-neutral were reported from a since-deleted branch and are not reproducible from `main`) | Cross-sectional | ~0 IC over ~11yr; reported to fail in every variant | [signal-isolation results](docs/research/2026-06-07-signal-isolation-results.md) |
| 2 | Value / Quality on deep SEC PIT data | Cross-sectional | Value's thin lead was a small-sample mirage (t 1.58 → 1.11 with *better* data); Quality flat. **Corrected under errata: t 1.11 → −0.88 (sign flip — confirmed split-basis look-ahead via a window-matched isolation); still FAIL** | [deep-fundamentals results](docs/research/2026-06-08-deep-fundamentals-results.md), [errata](docs/research/2026-09-26-split-basis-errata.md) |
| 3 | Gross profitability, net issuance, asset growth | Cross-sectional | All flat; best t = 0.73 vs a Bonferroni 2.4 bar. **Corrected under errata: best t = 0.73 → 0.44; still all FAIL** | [new-factor-inputs results](docs/research/2026-06-09-new-factor-inputs-results.md), [errata](docs/research/2026-09-26-split-basis-errata.md) |
| 4 | Regime overlay + vol-conditioning timing rules | Time-series | All five rules fail (best p = 0.070 vs 0.010); the legacy "validated 25-yr regime" claim killed with data | [TS timing results](docs/research/2026-06-10-ts-timing-study-results.md) |
| 5 | PEAD / post-SEC-filing drift (SUE-E, SUE-R, EAR) | Event-time | All spreads *negative* net of costs; filing-reaction measure shows **reversal** (NW-t −2.04). **Corrected under errata: NW-t −2.04 → −1.96, still reversal; still FAIL. Addendum (2026-09-27, impossible imputed Q4 revenue): SUE-R −2.49% → −2.36%/yr, SUE-E and EAR unchanged; still FAIL** | [PEAD results](docs/research/2026-06-10-pead-event-drift-results.md), [errata](docs/research/2026-09-25-sec-duration-contamination-check.md) |

**Power caveat (2026-09-26):** measured after the fact, these studies had only 9–39% power
against literature-plausible effects (IC 0.02, 1–2%/yr alpha). They are failures to reject, not proof
of absence; only EAR's CI excludes a positive effect. See
[harness power & positive controls](docs/research/2026-09-26-harness-power-and-positive-controls.md).

**Errata caveat (2026-09-26):** studies #2, #3, and #5 depended on two SEC pipeline bugs (as-filed
share counts on the wrong split basis; 3-month vs year-to-date facts colliding under one cache key).
Both are fixed; studies were re-run with their original locked parameters. **No verdict flipped —
the corrected numbers above are now canonical.** See the errata docs linked in the table.

Plus a data-feasibility verdict: the **survivorship-free S&P 500 spike**
([write-up](docs/research/2026-06-09-survivorship-free-sp500-spike.md)) — membership
reconstruction works, but free sources structurally cannot supply delisted-name prices (56%
coverage, missing exactly the bankruptcies), so the survivorship question is *unanswerable on
free data*.

Each negative closed a specific escape hatch: "needs more data" (#2 made Value weaker with better
data), "needs new inputs" (#3), "timing works" (#4), "events are different" (#5). The
pre-registered stopping rule — two consecutive negatives across iters #5/#6 → stop — fired on
2026-06-10. **The edge hunt is closed.**

## Why honest negatives are the product

Most public quant repos show an overfit backtest with a heroic Sharpe. This one shows the
opposite, on purpose:

- **Expected ≠ realized.** The optimizer's in-sample expected Sharpe is never presented as an
  achievement; the backtest reports realized gross vs net separately, and the README you are
  reading once carried a fabricated "validated 25-year, 14,785%" claim that was first retracted,
  then formally killed with data (study #4).
- **Pre-registration is real.** Factor lists, rule parameters, windows, and gates are locked in
  committed spec documents before any result exists ([specs](docs/superpowers/specs/)). Bonferroni
  corrections scale with family size. Nothing gets re-tuned after a miss.
- **Data integrity is enforced, not assumed.** A full audit found 507 of 508 price files held the
  *wrong ticker's* data (a positional bug in a legacy downloader) — every prior backtest was
  invalid. The store was rebuilt with a ticker-identity guard that refuses mislabeled files
  (`historical_store.load_prices`), plus a standing verification tool.
- **PIT everywhere.** SEC fundamentals are filed-date-stamped (no restatement look-ahead; the
  event study uses first-filed values only); signals apply with an execution lag enforced in
  exactly one tested place per harness; universes and thresholds never peek.
- **Tests are adversarial.** Each harness ships with tests designed to fail under look-ahead,
  restatement leakage, boundary ties, degenerate inputs, and future-event contamination — not
  tests that assert functions return non-None.

## The three evaluation harnesses

All three are decoupled from the portfolio pipeline, run offline from local stores, and emit JSON
artifacts to `data/research/`.

### `signal-eval` — cross-sectional factor gate
Rank-IC + quantile spreads (gross and net of costs) per factor. Defaults: true-PIT SEC fundamentals
and a Bonferroni t-gate over the factors tested together (Φ⁻¹(1 − 0.025/k): 1.96 for one factor,
2.39 for three); `--t-gate` overrides it. All three harnesses return PASS / FAIL / INCONCLUSIVE.

```bash
uv run ./main.py signal-eval --factors momentum,value,quality \
  --fundamentals sec --t-gate 2.4 --start 2016-01-01 --end 2026-06-01
```

Add `--power-sim 100 --workers 8` for positive and negative controls: synthetic factors of known IC
(0, 0.02, 0.03, 0.05), injected into the real panel and calibrated to each real factor, run through
the unchanged gate. The IC-0 row is the false-positive rate.

### `ts-eval` — time-series timing gate
Pre-registered timing rules vs buy-and-hold on a 10-ETF multi-asset universe: net excess Sharpe
dominance (full window + sub-windows) AND stationary-bootstrap p on timing alpha. T-bill cash on
the uninvested fraction; shift-1 execution; costs on exposure turnover.

```bash
uv run ./main.py ts-eval            # all five pre-registered rules
```

### `pead-eval` — event-time drift gate
Calendar-time long-short quintile spreads over SEC quarterly-filing events (SUE on earnings and
revenue, filing-window abnormal return), first-filed values only, Q4 imputation with look-ahead
blocks, bootstrap alpha vs market.

```bash
uv run ./main.py pead-eval          # all three pre-registered measures
```

## Data infrastructure (all free, regenerable, gitignored)

| Store | Contents | Builder | Integrity |
|---|---|---|---|
| `data/historical/prices/` | ~500 S&P names, daily, 2015→ | `tools/download_historical_data.py` | ticker-identity guard + `tools/verify_price_store.py` |
| `data/historical/ts/` | 10 multi-asset ETFs + ^VIX/^VIX9D/^VIX3M/^IRX | `tools/download_ts_universe.py` | separate dir — never pollutes the cross-sectional universe |
| `data/historical/fundamentals_sec/` | FY companyfacts, filed-stamped (498 names) | `tools/build_sec_fundamentals_cache.py` | PIT slicing `filed ≤ as_of` |
| `data/historical/splits/` | Per-ticker split history (puts as-filed SEC shares on the price basis) | `tools/build_split_cache.py` | cross-checked by `tools/check_split_consistency.py`; missing → name excluded |
| `data/historical/fundamentals_sec_q/` | Quarterly companyfacts incl. net income (498 names) | `tools/build_sec_q_cache.py` (probe mode first) | first-filed semantics; separate dir |

## The portfolio tool (legacy, still functional)

The original factor → Black-Litterman pipeline still works and is kept as reference plumbing:
point-in-time Value/Quality/Momentum ranking (`fundamentals.compute_pit_factors`, single source of
truth for live and backtest), market-implied BL priors, a walk-forward backtester with transaction
costs and an `EXPECTED vs REALIZED` block, and portfolio snapshot / forward-validation machinery.

```bash
uv run ./main.py optimize --universe sp500 --top-n 50      # live construction
uv run ./main.py backtest --start 2023-07-01 --end 2025-06-01 --top-n 20 --frequency quarterly
uv run ./main.py verify NVDA                               # glass-box factor audit
```

**Read before trusting any number it prints:** the optimizer's expected Sharpe is an in-sample
construction artifact, not evidence; the backtest is an integrity check over a short usable
window (annual PIT fundamentals + current index membership), not statistical validation; and the
factor views it expresses have **no validated signal** behind them (see the table above). The
optional overlays (`--use-regime`, `--use-macro`, `--use-french`) are unvalidated; study #4
formally killed the regime overlay's legacy performance claims.

## House methodology rules

1. Lock signals, parameters, windows, and gates in a committed spec before touching results.
2. Correct for the family you actually tested (Bonferroni / raised bars); never widen the family
   after the fact.
3. Net of realistic costs, always; benchmarks get the benefit of the doubt.
4. PIT or it doesn't exist: filed dates, first-filed values, trailing-only thresholds, enforced
   execution lags — each with an adversarial test that fails under leakage.
5. Degenerate cases are INCONCLUSIVE, loudly: no computable statistic or too short a sample
   (< 24 IC periods / < 252 days) is never reported as FAIL, and the CLI exits 3. "No data" must
   not read as "no edge". Nothing silently degrades or falls back.
6. Report power next to every verdict: SE, 95% CI, 80%-power minimum detectable effect, and power
   at a pre-set reference effect (report-only; gates unchanged). A FAIL is evidence of absence only
   when the test could have seen a realistic effect.
7. Pre-register the stopping rule — and honor it. Negative results get the same write-up quality
   as positives would have.

## Status: PARKED (2026-06-10)

The stopping rule fired; the reframe is complete; active investment in this project has stopped.
What remains useful:

- **Claim-tester on standby.** Any strategy claim — a newsletter's, a video's, your own hunch —
  can be put through an honest, costed, PIT-correct gate in an afternoon using the three
  harnesses. That is the repo's standing job.
- **Reopening criteria (pre-registered):** a genuinely new data tier (paid, survivorship-free,
  e.g. down-cap with delisted names) AND a fresh pre-registration, treated as a new project with
  its own budget decision. Re-tuning any parameter from studies #1–#5 is not reopening; it is
  p-hacking, and nothing has earned it.

## Research log

All verdicts and spikes, chronologically, in [docs/research/](docs/research/):
feasibility ([PIT fundamentals](docs/research/2026-06-05-pit-fundamentals-feasibility.md),
[SEC EDGAR survey](docs/research/2026-06-08-sec-edgar-library-survey.md),
[SEC PIT spike](docs/research/2026-06-08-sec-edgar-pit-spike.md)),
calibration ([cost sensitivity](docs/research/2026-06-07-cost-sensitivity.md),
[net-issuance splits](docs/research/2026-06-09-net-issuance-splits-spike.md)),
and the six verdicts in the table above. Design history lives in
[docs/superpowers/specs/](docs/superpowers/specs/) and [plans](docs/superpowers/plans/).
Legacy feature guides ([regime/gods](docs/REGIME_AND_GODS_GUIDE.md),
[130/30](docs/LONG_SHORT_130_30.md)) carry retraction banners and are kept as mechanism
references only.

## Quick start

```bash
git clone https://github.com/justr3/quant-portfolio-manager.git
cd quant-portfolio-manager
uv sync
uv run pytest -q                      # 221 tests, offline
# Data (free, ~30-60 min total, all regenerable):
uv run python tools/download_historical_data.py
uv run python tools/download_ts_universe.py
EDGAR_IDENTITY="you@example.com" uv run python tools/build_sec_fundamentals_cache.py
EDGAR_IDENTITY="you@example.com" uv run python tools/build_sec_q_cache.py
```

Optional: `FRED_API_KEY` in `config/secrets.env` for live risk-free rates in the portfolio tool.

## Project structure

```
├── main.py                      # CLI: signal-eval | ts-eval | pead-eval | optimize | backtest | verify | portfolio
├── src/
│   ├── research/                # the three harnesses (panels, metrics, gates, CLIs)
│   ├── pipeline/                # price store (identity-guarded), SEC PIT pipelines (FY + quarterly), universe
│   ├── models/                  # factor engine, BL optimizer, regime detector (legacy)
│   ├── backtesting/             # walk-forward engine, costs, expected-vs-realized reporting
│   └── forward_testing/         # snapshot validator (paper forward-tests)
├── tests/                       # 221 tests incl. the adversarial PIT/leakage suites
├── tools/                       # downloaders, cache builders, integrity verifiers, spikes
└── docs/                        # research verdicts, specs, plans, legacy guides (with banners)
```

## License

MIT — see [LICENSE](LICENSE).
