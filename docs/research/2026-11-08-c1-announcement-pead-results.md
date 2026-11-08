# C1 — Announcement-Date PEAD (8-K Item 2.02 clock): Results

- **Date:** 2026-11-08
- **Spec (locked before the run):** `docs/superpowers/specs/2026-11-08-c1-announcement-pead-design.md`
- **Plan:** `docs/superpowers/plans/2026-11-08-c1-announcement-pead.md`
- **Code:** `src/research/c1_events.py`, `src/research/c1_command.py`; CLI `uv run ./main.py c1-eval`.
- **Run:** `uv run ./main.py c1-eval` (pre-registered defaults, run once). Artifact
  `data/research/c1-eval-20261108_123431.json`.

## Verdict: FAIL on all three measures. C1 is closed.

Earnings drift after the 8-K announcement does not pass the study #5 bar on this data. No measure
is near the bar: the best one-sided p is 0.34 against 0.0167. Under spec §9, C1 is closed with no
variants. This is the sixth honest negative.

| Measure | Events | Net spread /yr | Thirds > 0 | Monotone | p_boot | NW-t | 95% CI (alpha/yr) | MDE80 | Power @ +2%/yr | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| SUE-E-a (earnings) | 19,478 | +0.47% | 1/3 | Yes | 0.338 | +0.39 | [−3.66%, +5.46%] | 6.90% | 10% | FAIL |
| SUE-R-a (revenue) | 17,324 | −1.84% | 1/3 | No | 0.704 | −0.55 | [−9.00%, +5.05%] | 10.64% | 6% | FAIL |
| EAR-a (reaction) | 20,420 | −0.71% | 1/3 | No | 0.576 | −0.17 | [−3.49%, +2.94%] | 4.87% | 18% | FAIL |

Window: entries 2015-02-01 to 2026-03-11; spread days 2,839–2,843 (about 11.3 years). Turnover
355–364 over the window, so the cost drag is about 3.2%/yr at 10 bps/side.

## Probe (spec §6, run before any returns)

| Count | Value |
|---|---|
| Quarters in window (denominator) | 21,164 |
| Matched to an 8-K | 20,521 (**97.0%**, fork bar 70% → PASS) |
| Quarters with 2+ matching 8-Ks (latest kept) | 1,065 |
| 8-Ks with no match / dropped by rule 2 only | 445 / 374 |
| Filing on the same day as the 8-K | 6,818 (33%) |
| Days from 8-K to first filing, p10 / p50 / p90 | 0 / 1 / 20 |
| After-close acceptances (≥ 16:00 ET) | 8,740 |

**Important for interpretation:** the median gap between the earnings release and the first
XBRL filing is **1 day**, and a third of events file the same day. For example, AAPL released
after the close on 2026-07-30 and filed its 10-Q on 2026-07-31. So for most large caps the 8-K
clock is only 0–1 day earlier than study #5's filing clock. The candidate-claims premise ("days to
weeks after the press release") holds only for the slowest ~10% of filers.

## Interpretation

- **SUE-E-a is the closest, and still far.** Its event-level quintile drift is broadly monotone
  (Q1 −0.16% → Q5 +0.75% over 60 days), and its gross spread is about +3.7%/yr. Costs take
  3.2%/yr, which leaves +0.47%/yr net with p = 0.34. Only 1 of 3 sub-periods is positive.
- **SUE-R-a and EAR-a show no direction.** Their quintile drift is U-shaped (both tails above the
  middle), as in study #5.
- **EAR-a no longer shows reversal.** In #5, post-filing EAR had NW-t −1.96. On the 8-K clock it is
  −0.17. The #5 reversal was most likely a filing-window effect, not an earnings-reaction effect.
- **Power is low, as stated before the run (spec §7).** Only EAR-a's CI excludes a +3% effect.
  A FAIL here rules out only large effects (above the MDE80: 4.9–10.6%/yr).

## Diagnostics (un-gated; spec §8 — not used for the verdict)

| Measure | Filing clock, same events: net/yr (p_boot) | H = 20 net/yr |
|---|---|---|
| SUE-E-a | −1.27% (0.646) | −10.3% |
| SUE-R-a | −3.14% (0.811) | −16.6% |
| EAR-a | −1.04% (0.637) | −12.2% |

The earlier clock improves each measure by about 0.3–1.7%/yr against the same events on the
filing clock, but none comes close to the bar. The H = 20 lines are deeply negative because the
cost drag is about 3× larger at the shorter hold. 379 (SUE-E) and 250 (SUE-R) events had their
first filing more than 30 days after the reaction day. 50 imputed Q4 revenues < 0 were skipped
(count over all periods).

Note: `excluded_days` in the artifact (~5,550) counts SPY calendar days outside the event window
(the calendar starts in 1993), not days lost to the min-10-per-leg rule.

## Caveats

1. SUE is information-PIT: the first-filed 10-Q value is used at the 8-K date. Matching rule 2
   needs a filing within 60 days, which a real-time trader cannot know.
2. Current S&P 500 membership (survivorship); a negative is conservative.
3. Low power (above).
4. Daily closes only.

## Outcome (spec §9, locked)

All FAIL → **C1 is closed.** No variants: no other horizon, decile legs, entry lag, matching
window, sector split, or measure. The candidate-claims list has no open free-data claim left.
The project stays PARKED; the reopening criteria are unchanged.
