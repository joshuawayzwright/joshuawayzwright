---
brand: solo
channel: email
calendar_id: solo-2026-12-20
campaign: dec-year-end-admin
publish_on: 2026-12-22
link: https://thesoloserviceprovider.com.au/shop/?utm_source=email&utm_medium=email&utm_campaign=solo-dec-year-end-admin
sources:
  - https://thesoloserviceprovider.com.au/shop/
  - https://thesoloserviceprovider.com.au/shop/products.json
  - marketing/brands/solo.md
  - marketing/compliance.md
  - marketing/calendar/2026-12-solo.md
status: approved
---

# Year-end admin checklist (email to consented subscribers)

Audience: only people who signed up to the pricing-tips list and consented to emails from The Solo Service Provider. Do not send to anyone else.

## Subject
Before the break: a short admin checklist

## Preview text
Three jobs to tick off before the shutdown, and a thank you.

## Body

Hi,

Thanks for reading this year. We know sole traders don't get much spare time, so we appreciate you making room for these emails.

Before things go quiet, three jobs are worth ten minutes each. Doing them now means they won't be waiting for you on 4 January.

1. Get your invoices out. Send anything still unsent, and chase anything overdue with a short, polite message. Unpaid invoices are easier to sort before everyone is away.
2. Follow up your open quotes. A quote that has gone quiet is often just a quote that's been forgotten. One short message asking if they have any questions is enough.
3. Log your costs. Fuel, materials, software, phone. Get this week's receipts recorded so the details are fresh.

If you want a hand with pricing for the new year, our free pricing tips are short and practical. If you know another sole trader who'd find them useful, send them the sign-up page:
https://thesoloserviceprovider.com.au/shop/?utm_source=email&utm_medium=email&utm_campaign=solo-dec-year-end-admin

Our shutdown: we're closed from Thursday 24 December 2026 and back on Monday 4 January 2027.

Have a safe and restful break.

The Solo Service Provider

General information only, not financial or tax advice. For tax or BAS questions, talk to the ATO or a registered tax agent.

## Footer
The Solo Service Provider
ABN 63 638 672 067
Gold Coast, Queensland
Contact: hello@thesoloserviceprovider.com.au

You're receiving this because you signed up for pricing tips from The Solo Service Provider.
Unsubscribe: [UNSUBSCRIBE LINK]

## Writer notes
- Facts used: Sender name, ABN 63 638 672 067, Gold Coast QLD and contact email → brand file. Free pricing-tips sign-up is live on the shop page → https://thesoloserviceprovider.com.au/shop/. Shutdown: closed Thu 24 Dec 2026, back Mon 4 Jan 2027 → calendar Owner decisions (16 Nov 2026). Sign-up wording "I can unsubscribe at any time" → shop page. Checklist items (invoices out, quotes followed up, costs logged) → calendar row. No worked-example sums and no numbers beyond dates.
- Revision 17 Nov 2026: applied the 16 Nov review (deleted the sentence promising replies to emails sent during the break).
- Link re-checked live with curl, 17 Nov 2026: shop returns 200 with the sign-up and consent wording. `products.json` has `salesOpen: true`; the "not on sale yet" panel is `hidden`.
- Conflicts: none affecting this email. The shop is open, but the email doesn't mention toolkits or prices. The shop page shows a "LAUNCH20" 20% launch offer that isn't in the brand file, so it isn't mentioned (owner to confirm).
- Placeholders: [UNSUBSCRIBE LINK] (merge field). Send only to consented subscribers. Whether the sign-up form records consent isn't visible from the page, so the owner should confirm the list source before sending. [POSTAL ADDRESS] isn't included, since it's only needed where a law or platform requires it; the platform may add it. Phone number is on the live site but not in the brand file, so it isn't used. The promise that emails sent during the break will be answered is removed (calendar Owner decisions, 17 Nov).
- Subject length: 41 characters (limit 50).

## Review: 2026-11-16
Status: NEEDS CHANGES
- "Emails sent in that time will be answered once we're back." is a service commitment the owner hasn't made. The Owner decisions give only the closure dates, and the writer notes say it's unconfirmed. → Delete the sentence (the line before it already says when the business reopens), or get the owner's confirmation and note it in Writer notes.
- Passes otherwise. The shutdown dates match Owner decisions (Thursday 24 December 2026 to Monday 4 January 2027; I rechecked the weekdays). On the Spam Act: the email goes to the consented list only (live consent box "Yes, email me pricing tips, new tools and offers… I can unsubscribe at any time."), it identifies the sender (The Solo Service Provider, ABN 63 638 672 067, Gold Coast, contact email), and it includes `[UNSUBSCRIBE LINK]`. The advice line with the ATO or tax agent pointer is present. The subject is 41 characters (limit 50), there's one link with the correct UTM (email / email / solo-dec-year-end-admin), no products or prices, no banned words, and it's in Australian English.
- Verified: https://thesoloserviceprovider.com.au/shop/ (live, 200, 16 Nov 2026); marketing/calendar/2026-12-solo.md Owner decisions.
- Owner escalation (non-blocking for this email): the shop page links to the calculator, which still shows the unapproved "All ten SOLO toolkits for A$79" offer.

## Review: 2026-11-17 (re-review)
Status: APPROVED
- The 16 Nov fix is applied: the promise that emails sent during the break will be answered is deleted, as the calendar's 17 Nov default requires.
- Spam Act: the email goes only to the consented list (live consent box confirmed 17 Nov 2026). The sender is identified (The Solo Service Provider, ABN 63 638 672 067, Gold Coast, Queensland, contact email), and `[UNSUBSCRIBE LINK]` is present. The owner should confirm the list source before sending, as Writer notes say.
- Passed: the shutdown dates match Owner decisions (Thursday 24 December 2026 to Monday 4 January 2027; I rechecked the weekdays). Subject 41 characters (limit 50), preview text 60 characters. One link, with the correct UTM (email / email / solo-dec-year-end-admin). The advice line has the ATO or tax agent pointer. No products, prices or LAUNCH20, no banned words, and it's in Australian English.
- Note (non-blocking): "A quote that has gone quiet is often just a quote that's been forgotten" is a general observation, not a statistic. "can just be a quote that's been forgotten" is the more cautious wording if the owner prefers it.
- Owner escalations (link target, non-blocking for this draft, which doesn't mention them): (1) the shop page shows "Launch offer: 20% off everything with code LAUNCH20 at checkout. Ends 31 December 2026." The brand file hasn't confirmed this offer. If it isn't genuine and planned, the end date is a time-limited discount claim under the ACL, so confirm it in the brand file or remove it. The calculator page, linked from the shop, repeats it ("Launch offer: 20% off with code LAUNCH20 until 31 December 2026"). (2) shop.js sorts the A$79 bundle first and tags it "BEST VALUE · ALL TEN" (code comment: "it is the best value and the clearest offer"). That conflicts with the brand rule that the bundle is a convenience option, not the flagship, so the owner should decide on the order and the tag. Everything else on the page checks out: all 16 products and prices match the approved table, the meta description says "From A$9", and "A$199 if bought separately" is correct.
- Verified: https://thesoloserviceprovider.com.au/shop/?utm_source=email&utm_medium=email&utm_campaign=solo-dec-year-end-admin (200); https://thesoloserviceprovider.com.au/shop/ (200, 17 Nov 2026, with the sign-up and consent wording) plus shop.js and https://thesoloserviceprovider.com.au/shop/products.json (salesOpen true; 16 priceLabels match the approved table; the ten toolkits sum to A$199, saving A$120 against A$79); calendar Owner decisions (16 and 17 Nov).
