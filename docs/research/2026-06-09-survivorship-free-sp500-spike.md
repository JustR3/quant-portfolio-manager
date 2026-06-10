# Survivorship-free S&P 500 — Spikes A & B (viability gate)

- **Date:** 2026-06-09
- **Spec:** `docs/superpowers/specs/2026-06-09-survivorship-free-sp500-design.md` (phase #4).
- **Runners:** `tools/sp500_membership_spike.py` (A), `tools/sp500_delisted_coverage_spike.py` (B).
- **Verdict: NO-GO on free data.** Membership reconstruction works; but free prices for the removed
  names cover only **56%**, and the missing 44% are precisely the delisted names that matter.

## Spike A — membership reconstruction: PASS

Wikipedia's "Selected changes to the S&P 500" (399 dated rows, back to 1976) + current constituents,
walked backward (reverse each post-`as_of` change), reconstructs point-in-time membership cleanly:

- `members_asof`: 2016-06 → 509, 2020-06 → 506, 2020-12-31 → 506, 2024-06 → 503 (all ~sane; S&P 500
  carries ~503 tickers for ~500 firms via dual-class).
- Known change validates: **TSLA** absent 2020-06, present 2020-12-31 (added 2020-12-21). ✓
- **208 names removed in-window** (2016-01→2026-06, not current members) — the set needing extra prices.

Reconstruction is sound and reusable. The block is not membership; it is prices.

## Spike B — removed-name price coverage: FAIL (56%)

Probed all 208 removed names against yfinance (2015-2026):

| Removal bucket | FULL | NONE | usable % |
|---|---|---|---|
| 2016-18 | 37 | 38 | 49% |
| 2019-21 | 32 | 25 | 56% |
| 2022-24 | 30 | 20 | 60% |
| 2025-26 | 17 | 9 | 65% |
| **Total** | **116** | **92** | **56%** |

Coverage is **binary** (full history or nothing — 0 partial) and **non-random**:

- The **116 FULL** are mostly *relegated* names that still trade (dropped from the index, still public)
  → full continuous history.
- The **92 NONE** are the *genuinely delisted* names (acquired / merged / taken-private / bankrupt).
  **yfinance drops a ticker's entire history once it delists** — so these return `n=0`, not partial.
- The missing set includes the **exact short-side-thesis names**: **SIVB** (Silicon Valley Bank) and
  **FRC** (First Republic) — the 2023 bank failures — plus TWTR, ATVI, PXD, MRO, DISH, ABMD, K, WBA,
  HES, ANSS… The blow-ups whose inclusion would most test net-issuance/asset-growth short-side edge are
  precisely the ones free data cannot supply.

The shortfall is even across the decade (49–65%), so extending the window or waiting does not help — it
is a structural property of free survivorship-biased feeds, not a stale-ticker artifact.

## Why this is a clean no-go (not a "proceed with caveats")

Proceeding at 56% would include the relegated losers but systematically exclude the acquired/bankrupt
names — i.e. a *half-survivorship-killed* universe that still drops the most factor-relevant exits. That
is exactly the "half-biased result dressed as unbiased" the spec's go/no-go forbids. The pre-registered
bar (≥70%) is not met, and the composition makes 56% worse than a random 56%.

## Spike B2 — Stooq fallback: BLOCKED (anti-bot)

Stooq is the usual free fallback that retains some delisted US tickers. Its CSV endpoint
(`stooq.com/q/d/l/?s=<tkr>.us&i=d`) now returns a **JavaScript anti-bot challenge** ("This site
requires JavaScript to verify your browser") for *every* request — including live tickers (AAPL) — even
with full browser headers and a session warm-up. So this is not "Stooq lacks the data," it is "Stooq
will not serve it to scripts." The only bypass is a headless browser solving the JS challenge for 92
names — circumventing an explicit bot measure, slow and fragile — which we decline.

## The finding (and what it implies)

**The S&P 500 survivorship caveat cannot be cleanly removed on free data.** Both free automated sources
fail, for different reasons:
- **yfinance** drops a delisted ticker's entire history → 56% coverage, missing exactly the
  acquired/bankrupt names (SIVB, FRC, TWTR, …) that the short side needs.
- **Stooq** bot-blocks its CSV feed behind a JS challenge.

This is itself an honest result: the survivorship question is *unanswerable on free data*, and a rigorous
survivorship-kill — or any down-cap study, where delistings are far more frequent — requires a
survivorship-free **paid** source (CRSP / Sharadar / EODHD-delisted). The spike did its job: it prevented
building universe plumbing for a study the data cannot support.

**Decision (see chat):** with free large-cap now exhausted (three factor negatives + this data block),
the remaining paths are cheap-paid survivorship-free data (the real edge-hunt: down-cap + true
survivorship-kill) or reframing the project as a PIT research-harness artifact.
