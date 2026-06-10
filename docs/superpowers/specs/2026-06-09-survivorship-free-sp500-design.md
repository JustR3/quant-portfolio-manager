# Survivorship-free S&P 500 Re-test — Sub-project (validated-edge phase #4)

- **Date:** 2026-06-09
- **Status:** Approved (brainstorm complete 2026-06-09). Spikes A/B gate the build.
- **Parent arc:** Validated-edge phase. Phases #1 (momentum), #2 (deep-PIT Value/Quality), #3 (new
  q-legs) all honest NEGATIVES on free, **current-membership** large-cap US data. Every result carried
  the same standing caveat: **survivorship** (universe = CURRENT S&P 500 applied historically).
- **Direction chosen (2026-06-09):** "different universe" → its most tractable slice, **survivorship-kill
  on the S&P 500, free data** (over down-cap small/mid or paid data).

## 1. Goal & hypothesis

Re-run the factor study on a **point-in-time S&P 500 universe** — members as they actually were on each
past date, including names later removed — to answer: **does removing survivorship bias flip any prior
negative, especially the short side of net issuance / asset growth?** Heavy issuers and aggressive
asset-growers disproportionately blow up and *leave* the index, so a current-membership universe never
sees their crashes; survivorship-kill is where those factors' short side could finally appear. A clean
"no change" is a valid and likely outcome — it converts the survivorship caveat from *unaddressed* to
*tested and immaterial*.

## 2. Decisions locked (brainstorm Q&A, 2026-06-09)

- **Slice:** survivorship-kill on the existing S&P 500 (free), NOT down-cap and NOT paid data. Rationale:
  most tractable; membership change-history is free; only the ~150 names that LEFT the index in-window
  need extra prices; directly tests the standing caveat.
- **Forward returns:** **pragmatic hybrid.** PIT membership decides who is IN at each `as_of`; a member's
  forward return comes from REAL prices, including AFTER it leaves the index while it still trades
  (relegated names keep contributing; acquired names contribute up to their last/deal price). Rare
  **hard delistings (bankruptcy)** get a terminal **−100%** in their final holding period. NOT strict
  price-path-only (under-counts blow-ups) and NOT full CRSP delisting-return modeling (overkill for
  large-cap, where outright bankruptcies are rare).
- **Membership source:** **Wikipedia** "Selected changes to the S&P 500" change-history + current
  constituents (the canonical free primary source), reconstructed backward. Rejected: a third-party
  GitHub CSV (unknown provenance/quality) and a paid membership feed (breaks the free line).
- **Factor set:** value, quality, gross_profitability, net_issuance, asset_growth (momentum excluded —
  known dead).
- **Bar:** standard **|t| ≥ 2.0**. This is a different-UNIVERSE re-test of FIXED hypotheses (not a fresh
  factor sweep), so no Bonferroni inflation; the **biased-vs-survivorship-free A/B** is the headline.

## 3. Validate-first spikes (these GATE the build)

Per "validate the fuzzy data FIRST," two spikes run before any feature code, each on an `experiment/`
node with a `docs/research/` writeup. **If either fails, this becomes a short "data-not-available"
finding, not a forced build.**

- **Spike A — membership reconstruction.** Fetch + parse Wikipedia's change-history; walk it backward
  from the current constituents (~501 names already in the store) to reconstruct point-in-time
  membership for sanity dates (2016 / 2020 / 2024). **Checks:** ~500 members per date; known changes
  resolve (e.g., TSLA added 2020-12-21; a handful of removals). **Go/no-go:** if the history can't
  reconstruct cleanly back to ~2016, shrink the window or stop.
- **Spike B — removed-name price coverage (make-or-break).** Enumerate names removed in-window (~150
  from Spike A); measure the fraction that yield usable historical prices from yfinance up to removal.
  **Go/no-go:** coverage ≥ ~70% → proceed; poor coverage → the survivorship-kill is compromised, report
  that as the finding and stop (do NOT ship a half-biased result dressed as unbiased).

## 4. Architecture

- **`src/pipeline/index_membership.py`** (new, no optimizer/BL imports):
  - `fetch_changes()` → Wikipedia change-history as a tidy `(date, added, removed, reason)` table.
  - `reconstruct(current_members, changes)` → backward walk: to get membership just before a change,
    *reverse* it (drop the added ticker, restore the removed). Produces a `date → frozenset[ticker]` map.
  - `members_asof(as_of)` → the constituent set effective at `as_of`.
  - Cache the reconstructed map + the removed-name list as a regenerable artifact under
    `data/historical/` (gitignored, like prices).
- **Price + SEC cache extension:** download Close/Adj Close parquets for the removed names into the
  EXISTING store (same schema, **same `load_prices` ticker-identity guard**); extend the SEC companyfacts
  cache for those names (EDGAR retains delisted filers → fundamentals available; bounded ~150-name
  re-pull, reusing `fetch_facts`).
- **PIT universe seam in `src/research/`:** today `build_panel` ranks a fixed `universe_tickers()` list
  across all dates. Introduce a small universe provider: `StaticUniverse` (current behavior) vs
  `PITMembershipUniverse(members_asof)`. `load_inputs` loads prices for the **union** of names ever
  in-window; `build_panel` includes, at each `as_of`, only `members_asof(as_of)`. `signal-eval` gets a
  `--universe survivorship-free|current` flag so the run is an explicit, comparable A/B — not a silent
  swap.

## 5. Forward-return handling (pragmatic hybrid)

- Relegated/acquired names: forward return falls out of real prices already (relegated names keep
  trading; acquired names have prices to the deal). No special code beyond loading their prices.
- **Bankruptcy terminal −100%:** for names whose change-history `reason` flags bankruptcy/insolvency and
  whose price series ends prematurely (no price through the forward horizon at their last member date),
  inject a terminal −100% forward return in that final period. Small, bounded set; documented per name.
- The existing `forward_return` returns NaN when no future price exists; the bankruptcy rule overrides
  NaN→−1.0 only for flagged hard-delistings, so non-flagged early endings stay NaN (conservative).

## 6. Testing (TDD)

Offline (synthetic change-tables + price stubs); Wikipedia/yfinance fetch behind the `integration`
marker.
- **Reconstruction:** reversing an (added, removed) change yields the correct earlier set; `members_asof`
  picks the set effective at a date (boundary: exactly on a change date).
- **PIT-universe filtering:** `build_panel` ranks only members at each `as_of`; a name contributes at
  dates it was a member and is absent otherwise; a removed name still contributes forward return from
  real prices while it traded.
- **Bankruptcy terminal:** a flagged hard-delisting with a truncated price series gets −100% in its final
  period; a non-flagged truncation stays NaN.
- **A/B parity:** `--universe current` reproduces today's static-universe panel exactly (regression-lock).

## 7. Deliverable

Run `signal-eval` on both universes and record in
`docs/research/2026-06-09-survivorship-free-sp500-results.md`: a **biased-vs-survivorship-free** factor
table (mean IC / t / monotonicity / gross+net L-S Sharpe) for value/quality/gross_profitability/
net_issuance/asset_growth, removed-name coverage achieved, the window reconstructed, the bankruptcy
cases handled, and the verdict (**did any factor flip, especially on the short side?**). Update `memory/`
+ CLAUDE.md.

## 8. Scope / YAGNI — explicitly NOT here

- No down-cap / small-cap universe; no paid data; no index other than S&P 500.
- No full CRSP-style delisting-return model (only the bounded bankruptcy −100% rule).
- No BL/optimizer/automation/composite changes; no live `optimize`-path change.
- No git-tracking of the membership map or removed-name parquets (regenerable, gitignored — invariant).

## 9. Follow-ups (gated on results)

- If a factor **flips to passing** survivorship-free → confirm robustness (sub-period, sector, the
  specific removed names driving it) before any portfolio work; this would be the first positive of the
  whole arc.
- If **nothing flips** → survivorship is tested-and-immaterial on large-cap; the remaining edge-hunt lead
  is genuinely down-cap (needs paid/clean data) or the harness reframe. Strong, honest closure of the
  survivorship caveat.
