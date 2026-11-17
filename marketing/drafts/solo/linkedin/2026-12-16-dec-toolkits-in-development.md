---
brand: solo
channel: linkedin
calendar_id: solo-2026-12-14
campaign: dec-toolkits-in-development
publish_on: 2026-12-16
link: https://thesoloserviceprovider.com.au/shop/?utm_source=linkedin&utm_medium=social&utm_campaign=solo-dec-toolkits-in-development
sources:
  - /home/user/joshuawayzwright/marketing/brands/solo.md
  - /home/user/joshuawayzwright/marketing/calendar/2026-12-solo.md
  - https://thesoloserviceprovider.com.au/shop/
  - https://thesoloserviceprovider.com.au/shop/products.json
  - https://thesoloserviceprovider.com.au/
status: draft
---

# The SOLO range, now on sale

Sixteen digital products are now on sale at The Solo Service Provider. Here's the whole range with prices, so you can pick what fits your business, or skip it.

Most are aimed at the jobs that eat a sole trader's week: quoting, invoicing, bookings, cashflow and admin. A few cover other jobs, like job hunting and launching a digital product.

The ten toolkits:
A$29: Cashflow Control, Quote & Invoice Builder, Small Business Operations Hub
A$19: Client Booking & Follow-Up, Content Repurposing Studio, Customer Support Desk, Digital Product Launch System
A$15: Business Research Dashboard
A$12: Job Application Command Centre
A$9: AI Workflow Starter Pack

Also available:
- Revenue Rescue DIY Kit: A$39
- Trade Editions for cleaners, handyman and home maintenance, lawn mowing and gardening, and mobile dog grooming: A$49 each
- Complete Toolkit, all ten toolkits in one purchase: A$79 (A$199 if bought separately)

Prices are in AUD, one-off, with no GST charged because I'm not registered. Instant download, plus a 30-day money-back guarantee that sits alongside your consumer guarantees under Australian Consumer Law.

The shop opened on 16 November, so there's no track record to quote yet. Have a look and see if anything earns its place in your week:
https://thesoloserviceprovider.com.au/shop/?utm_source=linkedin&utm_medium=social&utm_campaign=solo-dec-toolkits-in-development

#SoleTrader #SmallBusinessAustralia

## Writer notes
- Facts used: shop open since 16 Nov 2026, 16 products, one-off payment, instant download, no GST, 30-day money-back guarantee alongside ACL → brand file (17 Nov); product names and prices → brand file price table, re-checked against live products.json (all 16 match; `salesOpen: true`). "Sixteen" → count of the table. Complete Toolkit "A$199 if bought separately" → derived: 29+29+29+19+19+19+19+15+12+9 = 199; products.json bundle description also says "A$199 if bought separately". "Most are aimed at quoting, invoicing, bookings, cashflow and admin; a few cover job hunting and launching a digital product" → product descriptions on products.json (the reviewer's suggested wording, narrowed to match). First person as Joshua → brand file.
- Fair range: ten toolkits grouped by price, then the DIY kit, Trade Editions and bundle; no product is called the flagship or best value, and no popularity or sales claims. AI Marketing Kit not mentioned.
- Link: changed from the homepage to the shop page (`/shop/`) because the homepage doesn't list the toolkits. Calendar row solo-2026-12-14 still says homepage; orchestrator to decide whether to update the row.
- Conflicts: the live shop page shows "Launch offer: 20% off everything with code LAUNCH20, ends 31 December 2026". It isn't in the brand file or the owner decisions, so it is NOT repeated here. Owner to confirm it is a real, approved offer before any post mentions it. Brand file and live site otherwise agree (prices, salesOpen). The shop HTML contains a "not on sale yet" block, but shop.js only reveals it when `salesOpen` is false, so it isn't shown. Profile README (16 live toolkits) is now consistent but wasn't used as a source.
- Placeholders: none. Note: the H1 is a working title only; LinkedIn has no title field, so don't paste it as the first line.
- Length: 1423 characters including link and hashtags (ideal 1,300 or fewer, limit 3,000), so over the ideal because it lists the range; the first two lines carry the post. 2 hashtags. Link checked 17 Nov 2026 (200).

## Review: 2026-11-16
Status: NEEDS CHANGES
- Core claim is now false against the live site. "None of them are on sale yet. My shop page says so plainly" contradicts the rendered shop. Live shop now shows toolkits ON SALE: https://thesoloserviceprovider.com.au/shop/products.json (Last-Modified 16 Nov 2026 17:21 GMT) has "salesOpen": true and 16 priced products (ten toolkits A$9 to A$29, Revenue Rescue DIY Kit A$39, four Trade Editions A$49, "SOLO Complete Toolkit — All Ten Products" A$79 tagged "BEST VALUE · ALL TEN"). shop.js renders them as BUY NOW cards and leaves the "DIGITAL PRODUCTS ARE NOT ON SALE YET" block hidden. The page meta/og description also says "From A$9, money-back guarantee". The brand file (checked 16 Nov) says not on sale and no prices approved. → Owner decision first. (a) If sales are not meant to be open: set `salesOpen` to false or empty `products.json`, confirm the shop shows "not on sale" in a browser, then re-review this draft as is. (b) If sales are meant to be open: this post can't run. Rewrite it from approved prices and an updated brand file, and add `[NEEDS OWNER APPROVAL: price]` until then.
- "I'm building ten toolkits": the live shop also lists a DIY Kit and four Trade Editions (16 products). → Covered by the owner decision above. Keep "ten" only if the brand file stays at ten.
- "They're aimed at the jobs that eat a sole trader's week: quoting, invoicing, follow-ups, cashflow and admin" is inferred and over-reaches. Job Application Command Centre, Content Repurposing Studio, Digital Product Launch System and Business Research Dashboard don't fit it. → Replace with "Most of them are aimed at the jobs that eat a sole trader's week: quoting, invoicing, bookings, cashflow and admin."
- Note: LinkedIn posts have no title field. Don't paste the H1 "Ten toolkits, none on sale yet" as the post's first line. It repeats the false claim.
- Passed: first person; no prices, dates or flagship; length 1,014 characters including link and hashtags (limit 3,000); 2 hashtags; UTM correct (linkedin/social/solo-dec-toolkits-in-development); no banned words; Australian English.
- Owner escalations: (1) the live shop selling at unapproved prices, including the A$79 bundle the brand file says never to repeat. This blocks this draft. (2) The homepage (link target) links "EXPLORE SOLO AI" to solo-ai.html, which recruits Android early-access testers ("Testers get a free account with daily messages"), against the 16 Nov "in development only" decision. Doesn't block this draft. (3) The homepage sign-up links the calculator page, which still shows "All ten SOLO toolkits for A$79". Doesn't block this draft on its own.
- Verified: https://thesoloserviceprovider.com.au/?utm_source=linkedin&utm_medium=social&utm_campaign=solo-dec-toolkits-in-development (200); https://thesoloserviceprovider.com.au/shop/ (200) plus shop.js and products.json; brand file product range; calendar Owner decisions.
