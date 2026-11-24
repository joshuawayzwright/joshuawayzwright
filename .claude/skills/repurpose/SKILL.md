---
name: repurpose
description: Turn one piece of content (a file, URL, blog post, transcript or release note) into reviewed, platform-native drafts for one brand. Use when the user says "repurpose this", "turn this into posts", "make social posts from this article", or "/repurpose <brand> <source> [channels]".
---

# Repurpose a source

**Arguments:** `<brand> <source> [channels]`

- **Brand:** one of `solo`, `wrightwayz` or `ai-download-center`. If it's missing, ask the user.
- **Source:** a file path in this workspace, or a URL.
- **Channels:** optional, comma-separated channel keys from `marketing/channels.md`.

## Steps

1. **Repurpose:** run `content-repurposer` with the brand, source and channels. Read the pack index it writes in `marketing/drafts/<brand>/packs/`.
2. **Check the source:** if the repurposer reports that the source belongs to another brand, or conflicts with the brand file, stop and tell the user before going on.
3. **Review:** run `brand-reviewer` on every draft listed in the pack index.
4. **Calendar:** if a calendar exists for the drafts' month (`marketing/calendar/YYYY-MM-<brand>.md`), append the drafts as rows with `calendar_id: adhoc` and their review status.
5. **Report to the user:**
   - the pack index as a link;
   - each draft with its channel, publish date and review status;
   - the placeholders the user must resolve.

Nothing is posted or published.
