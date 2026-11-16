---
name: content-report
description: Build a content performance report for one brand and period from analytics exports or connected analytics tools, with recommendations that feed the next content calendar. Use when the user asks "how did our content do", "content report for November", or "/content-report <brand> [YYYY-MM]".
---

# Report on content performance

**Arguments:** `<brand> [YYYY-MM]`

- **Brand:** one of `solo`, `wrightwayz` or `ai-download-center`. If it's missing, ask the user.
- **Period:** defaults to the previous calendar month.

## Steps

1. **Check for data.** Look in `marketing/data/<brand>/` for exports covering the period.
   - If there are none, tell the user which exports would help (see `marketing/data/README.md`).
   - Then ask whether the analyst should use connected analytics tools only.
2. **Analyse.** Run `performance-analyst` with the brand and period. It is read-only on every external system.
3. **Report to the user:**
   - the report file as a link;
   - its headline;
   - its numbered recommendations;
   - its data gaps.
4. **Offer next month's calendar.** Offer to run `/content-engine <brand> <next month>`. The strategist applies these recommendations automatically.
