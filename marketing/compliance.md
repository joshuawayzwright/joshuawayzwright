# Content rules for all brands

The `brand-reviewer` agent checks every draft against this file and against the brand's own file in `brands/`. Writers follow it too.

## 1. Truth

- **Facts:** every fact, number, price, date and feature must come from the brand file, a linked source, or the live website. Anything else becomes `[NEEDS INFO: ...]`.
- **Invented proof:** no invented testimonials, reviews, customer counts, traffic, results, awards, partnerships or "as seen in" claims.
- **Availability:** don't present anything as available unless the brand file or live site says it is live. "Coming soon" needs no date unless one has been announced.
- **AI-generated images:** never present them as real photos of customers, staff, premises or events.

## 2. Australian law

These rules are a checklist, not legal advice. If a draft raises a real legal question, escalate it to the owner.

- **Australian Consumer Law (Competition and Consumer Act 2010, Schedule 2):**
  - Nothing misleading or deceptive.
  - No fake scarcity, fake urgency or "was/now" prices without a real prior price.
  - Never suggest that customers lose their consumer-guarantee rights.
- **Spam Act 2003:** commercial email and SMS need:
  - **consent** from the recipient;
  - the sender clearly **identified** by name and contact details;
  - a **functional unsubscribe**.

  Drafts include `[UNSUBSCRIBE LINK]` and the sender's business name. Never draft cold commercial email to people who haven't consented. B2B sponsor outreach for `ai-download-center` must follow that repo's outreach rules and still include an opt-out.
- **Testimonials and influencers:**
  - Paid or gifted relationships are disclosed: write "Ad", "Sponsored" or "Paid partnership".
  - Testimonials must be real, with the person's permission, and representative.
- **Privacy Act 1988:** no personal information about customers, clients or community members without consent.

## 3. Platforms

- No engagement bait ("like if…", "tag 3 friends"), vote or like solicitation, fake accounts, or giveaways without proper terms.
- Don't plan to post the same text to many groups or subreddits at once. Adapt each post, and follow each community's self-promotion rules.
- Disclose that the poster built or owns the product when posting in communities.

## 4. Brand separation

- **One brand per draft.** The `brand:` field decides the logo, voice, links, contact details and calls to action.
- **WrightWayz content** never contains SOLO sales links, product promotion, shared calls to action, or shop email lists.
- **SOLO content** never uses WrightWayz's mission, lived-experience stories, or not-for-profit status to sell.
- **Logos:** never invent, redraw or swap a logo. Image briefs name approved asset paths only.

## 5. Sensitive topics

- **`wrightwayz` mental-health content:** follow the safe-messaging rules in `brands/wrightwayz.md`. They are mandatory.
- **Health, financial or legal tips (any brand):** keep them general and add "general information, not advice" when a reader could act on them. Tax or BAS content for sole traders points readers to the ATO or a registered tax agent.

## 6. Voice and spelling

- Australian English everywhere except the product name "AI Download Center".
- No banned hype words (each brand file lists them).
- Spell names correctly: Joshua Wright, The Solo Service Provider, SOLO AI, WrightWayz.

## 7. Placeholders

**Blocking placeholders.** Writers use these when they can't know something. A draft that contains any of them can't be APPROVED.

| Placeholder | Meaning |
| --- | --- |
| `[NEEDS INFO: ...]` | A fact that couldn't be verified |
| `[NEEDS OWNER APPROVAL: ...]` | A decision for the owner, such as a price, an offer, consent or a launch date |
| `[NEEDS ASSET: ...]` | A missing approved image or file |

**Merge fields.** These don't block approval. Your email platform fills them in when it sends.

| Field | Rule |
| --- | --- |
| `[UNSUBSCRIBE LINK]` | Required in every email draft |
| `[POSTAL ADDRESS]` | Use where a law or platform requires it |
