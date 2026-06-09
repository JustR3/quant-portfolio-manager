# Net-Issuance Splits Spike — validate the split-adjustment heuristic

- **Date:** 2026-06-09
- **Parent:** Validated-edge phase #3 (new factor inputs). Spec
  `docs/superpowers/specs/2026-06-09-new-factor-inputs-design.md`, plan
  `docs/superpowers/plans/2026-06-09-new-factor-inputs.md` (Task 1).
- **Runner:** `tools/net_issuance_splits_spike.py` (offline — reads the existing SEC cache).

## Question

The cached `shares` field is the raw cover-page `dei:EntityCommonStockSharesOutstanding` count,
reported **as-filed** (point-in-time, *not* back-adjusted for later splits). So a stock split inflates
the count (e.g. 4×) with zero economic issuance and would masquerade as a huge "issuance," poisoning a
net-issuance factor. **Can a simple-multiple ratio heuristic remove splits cleanly without a
price-domain dependency?**

## Method

Operate purely on the `shares` series. Build one latest-filed value per `period_end` (sorted by
period_end); for each consecutive pair in the trailing year, if the ratio is within `TOL` of a simple
split multiple `m ∈ {1.5,2,3,4,5,6,7,8,10,15,20}` (or its reciprocal, for reverse splits), treat it as
a split and divide it out. Net issuance = `−( log(shares_now / split_factor) − log(shares_prior) )`,
oriented so **positive = net buyback** (predicted higher return). `TOL = 0.05` (±5% around the
multiple).

## Result — heuristic works; net issuance is IN

`uv run python tools/net_issuance_splits_spike.py`:

| Case | Known event | Detected factor (ratio) | raw −Δlog (artifact) | **adjusted** | Economic check |
|---|---|---|---|---|---|
| AAPL @2021-06 | 4:1 split Aug 2020 | **4.0** (3.971) | −1.3481 | **+0.0382** | heavy buyback ✓ |
| NVDA @2022-06 | 4:1 split Jul 2021 | **4.0** (4.013) | −1.3895 | **−0.0032** | ~flat ✓ |
| TSLA @2021-06 | 5:1 split Aug 2020 | **5.0** (5.087) | −1.6480 | **−0.0386** | mild raise ✓ |
| AMZN @2023-06 | 20:1 split Jun 2022 | **20.0** (20.017) | −3.0041 | **−0.0084** | ~flat ✓ |
| AAPL @2019-06 | none | 1.0 | +0.0660 | **+0.0660** | buyback ✓ |
| MSFT @2019-06 | none | 1.0 | +0.0027 | **+0.0027** | ~flat ✓ |

- **All four splits detected** with the exactly-correct multiple; observed ratios (3.97 / 4.01 / 5.09 /
  20.0) all land inside ±5%. The widest miss is TSLA at 1.7% off 5.0 — comfortable margin.
- **Zero false positives** on the two no-split years (factor stays 1.0).
- **Adjusted issuance is economically correct:** AAPL's well-known buybacks come out positive (+3.8% /
  +6.6% share-count shrink), TSLA/NVDA mild dilution comes out slightly negative. The raw (un-adjusted)
  column shows the −1.3 to −3.0 split artifacts the heuristic removes.

## Decision

- **Net issuance is IN** → the pre-registered set stays **k=3** (gross profitability, net issuance,
  asset growth), Bonferroni bar **|t| ≥ 2.4**.
- **Locked constants** (→ `sec_fundamentals.py`): `SIMPLE_SPLIT_MULTIPLES = [1.5,2,3,4,5,6,7,8,10,15,20]`,
  `SPLIT_RATIO_TOL = 0.05`. Split detection lives in `sec_fundamentals` operating on the shares series
  only — **no price import**, factor stays price-free.

## Caveats / known edge

- The `1.5` multiple is ambiguous between a 3:2 split and a genuine ~50% one-quarter secondary; both are
  rare for S&P-500 large-caps and none appeared in validation. A sudden ~1.5× single-gap jump is treated
  as a split. Documented; revisit only if a name shows an implausible result.
- Detection is on **consecutive filing gaps** (~quarterly), so gradual issuance never trips it; only
  near-integer single-gap jumps do. This is the desired behavior.
