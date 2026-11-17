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
  - https://thesoloserviceprovider.com.au/shop/
  - marketing/brands/solo.md
  - marketing/calendar/2026-12-solo.md
status: approved
---

# The hours nobody pays you for

Want to earn $80,000 a year before tax? $80,000 ÷ 52 weeks ÷ 38 hours says about $40 an hour.

For a sole trader, that sum leaves out three things.

1. Super. No employer is paying it for you. If you put away 12% (my example figure, so check the current rate with the ATO), you need $89,600.
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
- Length: about 1,290 characters including link and hashtags (ideal 1,300 or fewer, limit 3,000). One link, 3 hashtags.
- Facts used:
  - Example inputs ($80,000 income, 12% super, $12,000 costs, 6 weeks off, 38 hrs/week, 60% billable, 15% buffer) -> the calculator's default example numbers (rate-calculator.html form values; DEFAULTS in rate-calculator.js, re-fetched 17 Nov 2026). The page labels super "Your choice: put 0 if you don't plan to", so 12% is presented in the post as my example figure, not the legal rate.
  - Formula: rate = (income × (1 + super%) + costs) ÷ billable hours, plus buffer -> rate-calculator.js header comment and calc lines. Outputs for the example inputs: 1,048.8 billable hrs (shown as 1,049), $101,600 needed, $96.87 break-even, $111.40 rounded up to $112 (Math.ceil) -> derived, matching the earlier reviews' recomputation.
  - "$40 an hour": $80,000 ÷ (52 × 38) = $40.49 -> derived.
  - "1,976": 52 × 38 hours -> derived.
  - "$89,600": $80,000 × 1.12 -> derived. "$101,600": $89,600 + $12,000 -> derived.
  - "Nearly three times": 112 ÷ 40.49 = 2.77 -> derived.
  - "If only 60% of your working time is billable, every billable hour has to cover the other 40% too" -> page FAQ "Why is the rate higher than I expected?"
  - Non-billable activities, weeks off, business-cost examples -> page form help text
  - "No sign-up", "your numbers are never sent anywhere" -> page hero (re-fetched 17 Nov)
  - Doesn't include income tax; ask the ATO or your accountant -> page FAQ "Does this include income tax?"
  - Calculator is free and safe to promote -> marketing/brands/solo.md status table
- Conflicts:
  - The A$79 bundle offer that earlier reviews flagged is no longer on the calculator page; the page CTA (17 Nov) now reads "See the toolkits. Quote, invoice and track cash at this rate. Toolkits from A$9." (A$9 matches the approved table.) The sticky button still goes to the A$79 Complete Toolkit page, which is now approved. The post doesn't mention toolkits or prices.
  - The calculator CTA and the shop page also show "Launch offer: 20% off everything with code LAUNCH20, ends 31 December 2026". That offer isn't in the brand file or the owner decisions, so I haven't repeated it. Owner should confirm it's approved before this goes out, because readers who click will see it.
  - The calculator FAQ says "SOLO Cashflow Control helps you plan the set-aside" (product is approved and on sale; not repeated).
- Placeholders: none. (The earlier A$79 approval placeholder is removed: resolved by the 17 Nov owner decision. The 12% needs-info placeholder isn't used here; 12% is framed as an example per the 17 Nov defaults.)
- Revision 2026-11-17: removed the A$79 placeholder; reworded the super line to present 12% as the example and point to the ATO for the current rate. The "earn $80,000 a year before tax" hook fix from the 16 Nov review is kept. Link re-checked (200, with UTM tags).
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

## Review: 2026-11-16 (re-review)
Status: NEEDS CHANGES
- Blocking placeholder still present: `[NEEDS OWNER APPROVAL: calculator page shows unapproved A$79 offer]`. The live link target still shows "Get the toolkit → … All ten SOLO toolkits for A$79". → Hold this post until the owner removes the offer from the calculator page, or approves the price and updates solo.md and the shop. Then remove the placeholder and re-review.
- Previous issue fixed: the hook now reads "Want to earn $80,000 a year before tax?", which matches the calculator's "Income you want before tax".
- Re-checked and OK: the calculator DEFAULTS (80000, 12, 12000, 6, 38, 60, 15) and the formula in rate-calculator.js. My recomputation gives 1,048.8 billable hours, $101,600, $96.87 and $111.40, rounded up to $112; $80,000 ÷ 1,976 = $40.49; 112 ÷ 40.49 = 2.77 ("nearly three times"). "No sign-up", "never sent anywhere" and the income tax/ATO wording match the page. The advice line is present. 1,224 characters including the link, one link, 3 hashtags, UTM tags correct, Australian English, no banned words.
- Owner escalation (blocks this post; worse than at the last review): the calculator's "Get the toolkit" button and three "See inside →" cards go to live product pages with "BUY NOW · A$79", "BUY NOW · A$29" (Cashflow Control, Quote & Invoice Builder) and "BUY NOW · A$39" ("SOLO Revenue Rescue DIY Kit", which isn't in the brand file's planned range). The bundle page says "A$79 instead of A$199 bought separately" and "You save A$120". That is a was/now saving with no real prior selling price, which is an ACL risk while the shop says "DIGITAL PRODUCTS ARE NOT ON SALE YET". The calculator FAQ also promotes "SOLO Cashflow Control helps you plan the set-aside". → Owner to take the product pages and buy buttons down, or remove the links from the calculator, and remove the A$199/"You save" comparison unless there was a real prior price.
- Verified: https://thesoloserviceprovider.com.au/rate-calculator.html?utm_source=linkedin&utm_medium=social&utm_campaign=solo-rate-calculator (200), https://thesoloserviceprovider.com.au/rate-calculator.js (200), https://thesoloserviceprovider.com.au/shop/ (200), /shop/solo-complete-toolkit-bundle.html, /shop/solo-cashflow-control.html, /shop/solo-quote-invoice-builder.html, /shop/solo-revenue-rescue-kit.html (all 200), marketing/brands/solo.md.

## Review: 2026-11-17 (re-review)
Status: APPROVED
- Previous blocker cleared: the A$79 bundle is approved (solo.md, 17 Nov). The calculator page no longer shows "All ten SOLO toolkits for A$79". Its CTA now reads "Toolkits from A$9" (approved), and "Get the toolkit" goes to the A$79 bundle page, whose "A$199 if bought one by one. You save A$120" is the verified comparison. The placeholder has been removed.
- Super: "If you put away 12% (my example figure, so check the current rate with the ATO)" meets the 17 Nov owner default. The calculator labels super "Your choice".
- Recomputed against live rate-calculator.js (DEFAULTS 80000/12/12000/6/38/60/15; Math.ceil): 80,000 ÷ 1,976 = $40.49; 80,000 × 1.12 = $89,600; + 12,000 = $101,600; 46 × 38 × 0.6 = 1,048.8 hrs (about 1,049); 101,600 ÷ 1,048.8 = $96.87 (about $97); × 1.15 = $111.40, rounded up to $112; 112 ÷ 40.49 = 2.77 ("nearly three times"). All correct.
- Checked: "before tax" matches "Income you want before tax". "No sign-up", "numbers aren't sent anywhere" and income tax/ATO match the page. The advice line is present. 1,288 published characters (limit 3,000), one link, 3 hashtags, UTM linkedin/social/solo-rate-calculator. No banned words, Australian English.
- Owner escalation (post can still go out): the shop page, the calculator page and /shop/solo-complete-toolkit-bundle.html show "Launch offer: 20% off everything with code LAUNCH20 … Ends 31 December 2026". Not confirmed in solo.md. The draft doesn't mention it (correct). The owner should confirm it or remove it from the site. The calculator results box shows it right under the rate.
- Owner escalation (post can still go out): shop.js tags the Complete Toolkit "BEST VALUE · ALL TEN" and sorts it first (code comment: "it is the best value and the clearest offer"). That conflicts with solo.md's "Don't make one product look like the flagship. The bundle is a convenience option". The AI Workflow Starter Pack copy ("save hours every week") is also an unsubstantiated outcome claim (ACL). Reword both on the site.
- Verified: https://thesoloserviceprovider.com.au/rate-calculator.html?utm_source=linkedin&utm_medium=social&utm_campaign=solo-rate-calculator (200), https://thesoloserviceprovider.com.au/rate-calculator.js (200), https://thesoloserviceprovider.com.au/shop/solo-complete-toolkit-bundle.html (200), https://thesoloserviceprovider.com.au/shop/products.json (200; salesOpen true; all 16 priceLabels match the approved table; ten toolkit prices sum to A$199; bundle `includes` = the ten toolkits), https://thesoloserviceprovider.com.au/shop/ and shop/shop.js (200; "not on sale" block stays hidden while salesOpen is true), marketing/brands/solo.md, calendar Owner decisions (17 Nov).
