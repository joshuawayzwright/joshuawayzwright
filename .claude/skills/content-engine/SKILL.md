---
name: content-engine
description: Run a month of marketing content for one brand end to end. The strategist plans the calendar from the latest performance report, writers draft every row in parallel, and the brand reviewer checks everything. Use when the user says "plan and write content", "content for December", "run the content engine", or "/content-engine <brand> [YYYY-MM] [goal]".
---

# Run the content engine

**Arguments:** `<brand> [YYYY-MM] [goal]`

- **Brand:** one of `solo`, `wrightwayz` or `ai-download-center`. If it's missing or ambiguous, ask the user. Never run two brands in one pass. For several brands, run the engine once per brand.
- **Month:** defaults to next calendar month.
- **Goal:** optional. The strategist picks one if none is given.

## Steps

1. **Report:**
   - If `marketing/reports/<brand>/` has no report for the previous month and `marketing/data/<brand>/` has new exports, run `performance-analyst` first for the previous month.
   - Otherwise skip this step and say so.
2. **Plan:**
   - Run `content-strategist` with the brand, month and goal.
   - Read the calendar it writes to `marketing/calendar/YYYY-MM-<brand>.md`.
   - If the calendar has a "Needs owner decision" section, show it to the user before going on.
3. **Write:**
   - Split the calendar rows into batches of about 5, grouped by channel.
   - Run one `content-writer` per batch, all in parallel and in the background. Give each the calendar path and its row ids.
   - If the calendar names a hero piece, write it first. Then run `content-repurposer` with that hero draft as the source instead of writing those rows from scratch.
4. **Update the calendar yourself**, not the agents, so parallel writers never edit the same file. Fill each row's `draft` column with the file path and set `status` to `drafted`.
5. **Review:**
   - Run `brand-reviewer` on every draft from this run. With more than 15 drafts, use parallel reviewers in batches of 10.
   - Set each calendar row's status to `approved` or `needs-changes`.
6. **Report to the user:**
   - The calendar file and the count of approved drafts out of the total.
   - Each draft as a link with its status, grouped by week.
   - Every placeholder (`[NEEDS INFO]`, `[NEEDS OWNER APPROVAL]`, `[NEEDS ASSET]`) the user must resolve, deduplicated.
   - A reminder to export the month's analytics into `marketing/data/<brand>/` so that `/content-report` can close the loop.

## Boundaries

- Nothing in this workflow posts, sends, schedules or publishes. The user publishes approved drafts themselves.
- **Brand separation:** one brand per run, per calendar and per draft. If an agent's output mixes brands, discard it and rerun that agent.
