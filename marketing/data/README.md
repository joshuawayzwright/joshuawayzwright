# Analytics exports

The `performance-analyst` agent reads exports from this folder. Put each brand's files in its own subfolder, and never mix brands.

```
marketing/data/
├── solo/
├── wrightwayz/
└── ai-download-center/
```

## File names

Name each file `<platform>-<YYYY-MM>.<csv|json>`, for example `linkedin-2026-11.csv` or `ga4-2026-11.csv`.

## Useful exports

| Platform | Where to export | What it gives |
| --- | --- | --- |
| GA4 | Reports → Acquisition → Traffic acquisition, with the "Session campaign" dimension; export as CSV | Visits and conversions per `utm_campaign` and `utm_source` |
| Google Search Console | Performance → Export | Blog queries, clicks and CTR |
| LinkedIn | Page or creator analytics → Content → Export | Impressions, reactions and clicks per post |
| Meta (Facebook and Instagram) | Meta Business Suite → Insights → Content → Export | Reach and engagement per post |
| X | Analytics → Export data | Impressions and engagements per post |
| Email platform | Campaign report export | Sends, opens, clicks and unsubscribes |

Menu paths change. If one has moved, export the per-post or per-campaign table with dates and URLs.

## Privacy

Strip personal data before committing: no subscriber emails, names, or customer records. Aggregate or per-post metrics only.

Raw exports are git-ignored by default (see `.gitignore`), so only the reports get committed. Commit an export only when it has no personal data and you want it kept.
