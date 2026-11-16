# Channels, formats and tracking

Shared by every content agent. These are the formats the engine drafts.

**Character limits are platform limits as of November 2026.** If a platform rejects a post, check its current limit and update this table.

| Channel key | Format | Length guide | Notes |
| --- | --- | --- | --- |
| `linkedin` | Post | 1,300 characters or fewer is ideal (limit 3,000). Make the first 2 lines carry the post. | Professional. Put one link at the end. At most 3 hashtags. |
| `x` | Post or thread | 280 characters per post; threads of 4 to 7 posts | Put the link in the final post. At most 2 hashtags. |
| `facebook` | Page post | 80 to 250 words | One link. Plain, community tone. |
| `instagram` | Caption plus image brief | Caption of 2,200 characters or fewer; first line is the hook | Links don't work in captions, so write "link in bio". Include an image brief (see below). |
| `threads` | Post | 500 characters or fewer | Conversational. |
| `blog` | Article | 700 to 1,500 words, with H2 sections | Include a meta title (60 characters or fewer) and a meta description (155 characters or fewer). |
| `email` | Newsletter or sequence step | Subject of 50 characters or fewer, plus preview text and body | Must comply with the Spam Act 2003 (see `compliance.md`). |
| `video-short` | Script for Shorts, Reels or TikTok | 30 to 60 seconds | Hook in the first 2 seconds. Include on-screen text and a shot list. |
| `video-long` | YouTube outline | Chapters with timestamps | Include a title, a description and chapters. |
| `gbp` | Google Business Profile post | 1,500 characters or fewer | `solo` only. Local Gold Coast angle. |

## Image briefs

When a format needs visuals, write a brief. Don't generate or alter logos.

```
Image brief
- Purpose:
- Approved asset(s) to use: <path from the brand file>
- Palette: <hex values from the brand file>
- Text on image: <≤ 8 words>
- Sizes: 1080×1080 (feed), 1080×1920 (story/reel), 1200×627 (LinkedIn/link)
- Alt text:
```

## Tracking links

Every link to an owned website gets UTM tags:

`?utm_source=<channel>&utm_medium=<medium>&utm_campaign=<brand>-<campaign-slug>`

| Medium | Channels |
| --- | --- |
| `social` | linkedin, x, facebook, instagram, threads |
| `email` | email |
| `video` | video-short, video-long |
| `organic` | blog, gbp |

- Don't add UTM tags to Hacker News posts, or to links that go to other organisations' sites.
- `wrightwayz` links to support services (Lifeline and similar) never get tags.

## Posting cadence

These are defaults. The strategist adjusts them using the latest report.

| Brand | Per week |
| --- | --- |
| `solo` | 3 LinkedIn, 2 Facebook, 1 Instagram, 1 GBP; 1 blog and 1 email every 2 weeks |
| `wrightwayz` | 2 Facebook, 1 LinkedIn, 1 Instagram; 1 blog a month |
| `ai-download-center` | 4 X, 2 LinkedIn; 1 newsletter a month |
