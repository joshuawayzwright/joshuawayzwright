---
brand: solo
channel: linkedin
calendar_id: solo-2026-12-14
campaign: dec-toolkits-in-development
publish_on: 2026-12-16
link: https://thesoloserviceprovider.com.au/?utm_source=linkedin&utm_medium=social&utm_campaign=solo-dec-toolkits-in-development
sources:
  - /home/user/joshuawayzwright/marketing/brands/solo.md
  - /home/user/joshuawayzwright/marketing/calendar/2026-12-solo.md
  - https://thesoloserviceprovider.com.au/shop/
  - https://thesoloserviceprovider.com.au/
status: needs-changes
---

# Ten toolkits, none on sale yet

I'm building ten toolkits for Australian sole traders. None of them are on sale yet. My shop page says so plainly, and I'd rather you hear it from me.

The planned range is all in development:

- SOLO Cashflow Control
- Quote & Invoice Builder
- Client Booking & Follow-Up
- Job Application Command Centre
- Content Repurposing Studio
- Customer Support Desk
- Small Business Operations Hub
- Digital Product Launch System
- Business Research Dashboard
- AI Workflow Starter Pack

They're aimed at the jobs that eat a sole trader's week: quoting, invoicing, follow-ups, cashflow and admin.

There are no prices and no launch dates to share, and I'm not going to pretend one of them is further along than the rest. When something is ready, I'll say so on the site first.

If you want to see what's live today and what's still being built, it's all on the homepage: https://thesoloserviceprovider.com.au/?utm_source=linkedin&utm_medium=social&utm_campaign=solo-dec-toolkits-in-development

#BuildInPublic #SoleTrader

## Writer notes
- Facts used: ten planned toolkit names, all in development → brand file (from SOLO-10-PRODUCT-RESET.md, 27 Oct 2026). Not on sale → shop page ("Digital products are not on sale yet"). "Aimed at quoting, invoicing, follow-ups, cashflow, admin" → inferred from product names and brand audience section; owner to confirm if wanted. No prices, no dates, no flagship.
- Conflicts: profile README says 16 live toolkits; live shop says none on sale. Followed the live shop; README claim not repeated. Flag README to owner.
- Placeholders: none

## Review: 2026-11-16
Status: NEEDS CHANGES
- Core claim is now false against the live site. "None of them are on sale yet. My shop page says so plainly" contradicts the rendered shop. Live shop now shows toolkits ON SALE: https://thesoloserviceprovider.com.au/shop/products.json (Last-Modified 16 Nov 2026 17:21 GMT) has "salesOpen": true and 16 priced products (ten toolkits A$9 to A$29, Revenue Rescue DIY Kit A$39, four Trade Editions A$49, "SOLO Complete Toolkit — All Ten Products" A$79 tagged "BEST VALUE · ALL TEN"). shop.js renders them as BUY NOW cards and leaves the "DIGITAL PRODUCTS ARE NOT ON SALE YET" block hidden. The page meta/og description also says "From A$9, money-back guarantee". The brand file (checked 16 Nov) says not on sale and no prices approved. → Owner decision first. (a) If sales are not meant to be open: set `salesOpen` to false or empty `products.json`, confirm the shop shows "not on sale" in a browser, then re-review this draft as is. (b) If sales are meant to be open: this post can't run. Rewrite it from approved prices and an updated brand file, and add `[NEEDS OWNER APPROVAL: price]` until then.
- "I'm building ten toolkits": the live shop also lists a DIY Kit and four Trade Editions (16 products). → Covered by the owner decision above. Keep "ten" only if the brand file stays at ten.
- "They're aimed at the jobs that eat a sole trader's week: quoting, invoicing, follow-ups, cashflow and admin" is inferred and over-reaches. Job Application Command Centre, Content Repurposing Studio, Digital Product Launch System and Business Research Dashboard don't fit it. → Replace with "Most of them are aimed at the jobs that eat a sole trader's week: quoting, invoicing, bookings, cashflow and admin."
- Note: LinkedIn posts have no title field. Don't paste the H1 "Ten toolkits, none on sale yet" as the post's first line. It repeats the false claim.
- Passed: first person; no prices, dates or flagship; length 1,014 characters including link and hashtags (limit 3,000); 2 hashtags; UTM correct (linkedin/social/solo-dec-toolkits-in-development); no banned words; Australian English.
- Owner escalations: (1) the live shop selling at unapproved prices, including the A$79 bundle the brand file says never to repeat. This blocks this draft. (2) The homepage (link target) links "EXPLORE SOLO AI" to solo-ai.html, which recruits Android early-access testers ("Testers get a free account with daily messages"), against the 16 Nov "in development only" decision. Doesn't block this draft. (3) The homepage sign-up links the calculator page, which still shows "All ten SOLO toolkits for A$79". Doesn't block this draft on its own.
- Verified: https://thesoloserviceprovider.com.au/?utm_source=linkedin&utm_medium=social&utm_campaign=solo-dec-toolkits-in-development (200); https://thesoloserviceprovider.com.au/shop/ (200) plus shop.js and products.json; brand file product range; calendar Owner decisions.
