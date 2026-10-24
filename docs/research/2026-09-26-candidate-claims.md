# Candidate Claims (not pre-registered, not scheduled)

Ideas a review surfaced that could deserve a test. Listing one here is **not** a reopening.
CLAUDE.md's reopening criteria still apply: a genuinely new data tier plus a fresh pre-registration,
with its own budget decision. Revisit only after the open errata re-runs (#2, #3, #5) are published.

## C1 — Announcement-date PEAD on the free 8-K Item 2.02 clock (added 2026-09-26)

- **Why study #5 under-tests PEAD:** its events are 10-Q/10-K **filing** dates, typically days to weeks
  after the earnings press release. The post-announcement drift window is partly over before entry,
  and the filing-window "EAR" mixes in non-earnings news. The #5 verdict speaks to post-*filing* drift.
- **Correction to the #5 write-up:** announcement timestamps are **not** paid-only. Companies furnish
  the earnings release on Form 8-K Item 2.02 ("Results of Operations and Financial Condition"),
  usually the same day. EDGAR's submissions index lists 8-K filing dates and items for free.
- **Does it meet the reopening criteria?** No: it is free data, not a new paid tier. Testing it would
  need either an explicit amendment to the criteria or a treatment as a separate project with its own
  budget.
- **What a pre-registration would need to lock:** event clock (8-K 2.02 acceptance time → first
  tradable close); matching rule from 8-K to fiscal quarter; measures (SUE on the same first-filed
  10-Q values, plus announcement-window EAR); horizon; quintile legs, min per leg, costs; gate
  (the #5 two-part gate); Bonferroni k; universe (current S&P 500, survivorship caveat); positive and
  negative controls and a power statement **before** results (reference effect 2%/yr; with ~25k events
  the #5 design had ~11% power, so the design must say how it does better or accept a low-power
  verdict); and a stopping rule.
- **Known confounders to handle in the spec:** 8-Ks filed after the close (acceptance time vs filing
  date), amended 8-Ks, companies that file the 10-Q the same day as the release (no clock difference),
  and non-earnings 2.02 filings (guidance updates).
