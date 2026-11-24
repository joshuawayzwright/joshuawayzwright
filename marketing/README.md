# Marketing and content engine

A set of Claude Code agents that plan, write, repurpose, review and measure marketing content for three separate brands:

| Brand key | Organisation | Brand facts |
| --- | --- | --- |
| `solo` | The Solo Service Provider and SOLO AI (commercial) | [brands/solo.md](brands/solo.md) |
| `wrightwayz` | WrightWayz (not-for-profit association) | [brands/wrightwayz.md](brands/wrightwayz.md) |
| `ai-download-center` | AI Download Center (free directory) | [brands/ai-download-center.md](brands/ai-download-center.md) |

Every run, calendar and draft belongs to exactly one brand. Nothing in this engine posts, sends, schedules or publishes. A person publishes approved drafts.

## The loop

```
 /content-report ──► report ──► /content-engine ──► calendar ──► drafts ──► review ──► you publish
       ▲                                                                                  │
       └──────────────────── analytics exports in marketing/data/<brand>/ ◄───────────────┘
```

## Commands

Open Claude Code in this repository, then:

| Command | What it does |
| --- | --- |
| `/content-engine solo 2026-12` | Plans December for SOLO, drafts every calendar row, and reviews the drafts |
| `/content-engine wrightwayz 2026-12 "grow resource-page visits"` | The same, with a goal |
| `/repurpose solo https://thesoloserviceprovider.com.au/rate-calculator.html` | Turns one source into a reviewed multi-channel pack |
| `/content-report ai-download-center 2026-11` | Writes a performance report and recommendations from analytics |

You can also call one agent directly: "Use content-writer to write a LinkedIn post for wrightwayz about the Admin Mindset."

## The agents

| Agent | Model | Job | Writes to |
| --- | --- | --- | --- |
| `content-strategist` | Sonnet | Monthly calendar: pillars, channels, dates, goal | `calendar/YYYY-MM-<brand>.md` |
| `content-writer` | Sonnet | Drafts for any channel in [channels.md](channels.md) | `drafts/<brand>/<channel>/` |
| `content-repurposer` | Sonnet | One source becomes many platform-native drafts | `drafts/<brand>/<channel>/`, `drafts/<brand>/packs/` |
| `brand-reviewer` | Opus | Facts, Australian law, platform rules, brand separation, safe messaging | Review block on each draft |
| `performance-analyst` | Sonnet | Read-only analytics; writes recommendations | `reports/<brand>/YYYY-MM.md` |

The agent files are in `../.claude/agents/` and the commands in `../.claude/skills/`.

## Shared rules

- [compliance.md](compliance.md): truth, the Australian Consumer Law, the Spam Act 2003, platform rules, brand separation and placeholders.
- [channels.md](channels.md): formats, length limits, UTM convention and default cadence.
- [../BRAND-RULES.md](../BRAND-RULES.md): visual identity across all projects.

When a fact changes (a product goes on sale, a price is approved, a status changes), update the brand file. Every agent picks it up on the next run.

## Draft lifecycle

The `status:` field in each draft's front matter moves through these values:

| Status | Set by |
| --- | --- |
| `draft` | Writer |
| `approved` or `needs-changes` | `brand-reviewer` |
| `published` | You, after posting. This lets the analyst match results. |

Only publish drafts marked `approved`. A draft with any `[NEEDS ...]` placeholder can never be approved. `python3 scripts/check_marketing.py` enforces this in CI.

## Using connected tools

The analyst can read from analytics tools connected to your Claude Code session, such as GA4 or Search Console through a reporting connector, social analytics, or email platform reports. It is instructed to stay read-only. The writers and reviewer never use external posting tools.

## Relationship to the AI Download Center agents

The `ai-download-center` repository has ten specialist ad-campaign agents and an `/ad-campaign` command. Use them for single-brand sponsor and launch campaigns. Use this engine for ongoing calendars, repurposing and reporting across all three brands.
