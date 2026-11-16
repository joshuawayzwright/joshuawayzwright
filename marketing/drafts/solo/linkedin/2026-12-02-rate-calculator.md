---
brand: solo
channel: linkedin
calendar_id: solo-2026-12-02
campaign: rate-calculator
publish_on: 2026-12-02
link: https://thesoloserviceprovider.com.au/rate-calculator.html?utm_source=linkedin&utm_medium=social&utm_campaign=solo-rate-calculator
sources:
  - https://thesoloserviceprovider.com.au/rate-calculator.html
  - https://thesoloserviceprovider.com.au/rate-calculator.js
  - marketing/brands/solo.md
status: draft
---

# The hours nobody pays you for

Want to earn $80,000 a year before tax? $80,000 ÷ 52 weeks ÷ 38 hours says about $40 an hour.

For a sole trader, that sum leaves out three things.

1. Super. No employer is paying it for you. Put away 12% and you need $89,600.
2. Business costs. Tools, vehicle, fuel, phone, insurance, software. Add $12,000 and you're at $101,600.
3. Hours you can't bill. Quoting, travel, admin, invoicing, finding work. Take 6 weeks off and bill 60% of a 38-hour week: about 1,049 billable hours, not 1,976.

$101,600 ÷ 1,049 hours is about $97 an hour just to break even. Add a 15% buffer for quiet weeks and late payers and it's $112.

That's nearly three times the "salary maths" figure.

If only 60% of your time is billable, every billable hour has to cover the other 40% too.

I built a free hourly rate calculator that does this sum with your own numbers. No sign-up, and your numbers aren't sent anywhere. It doesn't include income tax: check with the ATO or your accountant.

General information only, not financial or tax advice.

Work out your rate: https://thesoloserviceprovider.com.au/rate-calculator.html?utm_source=linkedin&utm_medium=social&utm_campaign=solo-rate-calculator

#SoleTrader #SmallBusinessAustralia #Pricing

## Writer notes
- Facts used:
  - Example inputs ($80,000 income, 12% super, $12,000 costs, 6 weeks off, 38 hrs/week, 60% billable, 15% buffer) → the calculator's default example numbers (rate-calculator.html form values; DEFAULTS in rate-calculator.js)
  - Formula: rate = (income × (1 + super%) + costs) ÷ billable hours, plus buffer → rate-calculator.js header comment and calc lines. Outputs reproduced: 1,048.8 billable hrs (shown as 1,049), $101,600 needed, $96.87 break-even, $111.40 rounded up to $112 → what the page shows for the example numbers.
  - "$40 an hour": $80,000 ÷ (52 × 38) = $40.49. My own comparison sum, not on the page.
  - "1,976": 52 × 38 hours. My own sum.
  - "If only 60% of your working time is billable, every billable hour has to cover the other 40% too" → page FAQ "Why is the rate higher than I expected?"
  - Non-billable activities (quoting, travel, admin, invoicing, finding work), weeks off (holidays, public holidays, sick days), business-cost examples → page form help text
  - "No sign-up", "your numbers are never sent anywhere", "runs in your browser" → page hero and FAQ "Do you keep my numbers?"
  - Doesn't include income tax; ask the ATO or your accountant → page FAQ "Does this include income tax?"
  - Calculator is free and safe to promote → marketing/brands/solo.md status table
- Placeholders: [NEEDS OWNER APPROVAL: calculator page shows unapproved A$79 offer]
- Revision 2026-11-16: hook changed from "take home $80,000" to "earn $80,000 a year before tax" to match the calculator's "Income you want before tax" label (review below). Post now links to a page carrying the unapproved offer, so it can't go out until the owner resolves it.
- Flag for owner: the live calculator page shows "Get the toolkit → … All ten SOLO toolkits for A$79" and links to product pages, while the live shop (/shop) says "DIGITAL PRODUCTS ARE NOT ON SALE YET" and the brand file says no prices. This post deliberately doesn't mention toolkits or prices, but readers who click will see the A$79 offer. Worth resolving on the site before this goes out.
- Image: none requested; LinkedIn will use the page's link preview. If an image is wanted, see channels.md (1200×627).

## Review: 2026-11-16
Status: NEEDS CHANGES
- Opening says "Want to take home $80,000 a year?" but the calculator treats this figure as "Income you want before tax" ("Think of it as your salary. Income tax comes out of this"). "Take home" means after tax, so the hook misstates what the tool calculates (ACL: misleading). → Replace the first line with: "Want to earn $80,000 a year before tax? $80,000 ÷ 52 weeks ÷ 38 hours says about $40 an hour."
- Owner escalation (not a draft fix): the link target shows "Get the toolkit → … All ten SOLO toolkits for A$79" and links to /shop/ product pages, while the live shop says "DIGITAL PRODUCTS ARE NOT ON SALE YET" and solo.md says no prices until approved. The draft doesn't mention it, but every click lands on an unapproved price and offer. → Owner to confirm whether the A$79 bundle is approved and on sale, and either update solo.md and the shop or remove the CTA from the calculator page before 2026-12-02.
- Checked and OK: example numbers and outputs match the calculator's defaults and formula (1,048.8 billable hrs, $101,600 needed, $96.87 break-even, $111.40 rounded up to $112); the writer's own sums ($40.49, 1,976 hrs, ~2.8× "nearly three times") are correct; "no sign-up", "numbers aren't sent anywhere", income tax excluded and ATO/accountant wording match the page; "general information, not advice" line present; 1,218 characters including the link (under 1,300); one link at the end; 3 hashtags; UTM tags match channels.md; Australian English; no banned words; no other brand mentioned; no image brief needed.
- Verified: https://thesoloserviceprovider.com.au/rate-calculator.html (200, with and without UTM tags), https://thesoloserviceprovider.com.au/rate-calculator.js, https://thesoloserviceprovider.com.au/shop (200, "not on sale yet"), marketing/brands/solo.md, marketing/compliance.md, marketing/channels.md.

| Draft | Status | Top issue |
| --- | --- | --- |
| marketing/drafts/solo/linkedin/2026-12-02-rate-calculator.md | needs-changes | "take home $80,000" misstates a before-tax figure |
