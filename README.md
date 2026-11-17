<div align="center">

<img src="assets/profile-header.svg" width="798" alt="Joshua Wright · Sudo — Practical tools. Community technology." />

**Founder · Full-stack developer · AI tools and agents · Automation · Community technology**

Gold Coast, Queensland, Australia · Studying Computer Science at Griffith University

<a href="https://www.linkedin.com/in/joshuawright-solo"><img src="https://img.shields.io/badge/LinkedIn-joshuawright--solo-0087FF?style=for-the-badge&logo=linkedin&logoColor=white&labelColor=0A0A0A" alt="LinkedIn" /></a>
<a href="https://github.com/joshuawayzwright"><img src="https://img.shields.io/badge/GitHub-joshuawayzwright-8A8F98?style=for-the-badge&logo=github&logoColor=white&labelColor=0A0A0A" alt="GitHub" /></a>
<a href="mailto:superadmin2712@gmail.com"><img src="https://img.shields.io/badge/Email-Get_in_touch-D4AF37?style=for-the-badge&logo=gmail&logoColor=white&labelColor=0A0A0A" alt="Email" /></a>

</div>

## About me

G'day, I'm **Joshua Wright** (Sudo). I build practical software for people who work for themselves, and community technology for people who've been let down by the systems meant to help them.

Right now I'm:

- 🛠️ **Running [The Solo Service Provider](https://thesoloserviceprovider.com.au/)**: an online shop of digital toolkits, calculators and services for Australian sole traders and small service businesses.
- 🤖 **Building SOLO AI**: a practical AI assistant for small businesses, with a web app and a native Android app written in Kotlin and Jetpack Compose. Accounts, sources-backed answers and account deletion are built; the Google Play release is being prepared.
- 🧠 **Building Jarvis**: my own AI engineering agent for the terminal. It searches code across GitHub, pulls repositories, makes changes, runs tests and opens draft pull requests, and you can talk to it by voice. It lives in [this repository](jarvis/).
- 🗂️ **Maintaining [AI Download Centre](https://joshuawayzwright.github.io/ai-download-center/)**: a public directory of 980+ AI models, assistants and tools with links to official sources.
- 🔥 **Developing [WrightWayz](https://www.wrightwayz.com/)**: a Gold Coast community initiative focused on lived experience, recovery, connection and responsible technology.
- 🎓 **Studying Computer Science** at Griffith University, and learning in public as I go.

I build things end to end, test them properly, and say clearly what each product does today.

## Follow along

| Where | The Solo Service Provider | WrightWayz |
|---|---|---|
| **Website** | [thesoloserviceprovider.com.au](https://thesoloserviceprovider.com.au/) | [wrightwayz.com](https://www.wrightwayz.com/) |
| **YouTube** | [@TheSoloServiceProvider](https://www.youtube.com/@TheSoloServiceProvider) | |
| **X** | [@TheSoloService](https://x.com/TheSoloService) | |
| **Instagram** | [@soloservicepro](https://www.instagram.com/soloservicepro/) | [@wrightwayzcharity](https://www.instagram.com/wrightwayzcharity/) |
| **Threads** | [@soloservicepro](https://www.threads.com/@soloservicepro) | |
| **Facebook** | [The Solo Service Provider](https://www.facebook.com/share/1ZSV63yiV3/) | [WrightWayz](https://www.facebook.com/people/Wrightwayz/61592187395142/) |

Personal: [LinkedIn](https://www.linkedin.com/in/joshuawright-solo) · [GitHub](https://github.com/joshuawayzwright)

## The Solo Service Provider

<a href="https://thesoloserviceprovider.com.au/"><img src="assets/solo-banner.png" width="798" alt="SOLO Service Provider — Work smarter. Go further. Original gold and steel emblem with the hooded SOLO AI guardian." /></a>

**WORK SMARTER. GO FURTHER.** Practical digital tools for Australian sole traders and small service businesses.

- **[SOLO online shop](https://thesoloserviceprovider.com.au/shop/)**: 16 ready-to-use digital toolkits for quoting and invoicing, cashflow, bookings, customer support, operations and AI workflows, including four **Trade Editions** for cleaners, handymen, lawn and garden businesses and mobile dog groomers. One-off purchases with a 30-day money-back guarantee.
- **[Free hourly rate calculator](https://thesoloserviceprovider.com.au/rate-calculator.html)**: works out what a sole trader needs to charge after super, business costs, time off and unbillable hours.
- **[Revenue Rescue](https://thesoloserviceprovider.com.au/revenue-rescue.html)**: a service that helps local businesses turn more website visitors into paid jobs.
- **SOLO AI**: in testing on web and Android; not yet on Google Play.

**What I built behind it (private repository):**

- A static site and shop on **Vercel**, with **Node.js serverless functions** for checkout, webhooks, downloads and the SOLO AI API.
- **Stripe** checkout and webhooks, with idempotent event handling and refund processing.
- **Supabase (PostgreSQL)** for orders, accounts and access grants, with row-level security and service-role-only access.
- Secure, expiring download links, emailed access-link recovery and **Klaviyo** email automation.
- The **SOLO AI Android app** in Kotlin and Jetpack Compose: streaming replies, answers with web sources, emailed-code sign-up and password reset, Keystore-encrypted sessions and in-app account deletion.
- Privacy-aware analytics with **GA4**, **Google Ads** and **Meta Pixel** that respect Global Privacy Control and Do Not Track, behind a strict Content Security Policy.
- **300+ automated tests** run on every deploy.

## Projects

### [Jarvis](jarvis/)

An AI engineering agent for the terminal, built on the Claude API. It searches code across all public GitHub repositories, pulls projects from GitHub, GitLab, Codeberg and Bitbucket, and answers questions about them. It can also build features: research how other projects solve a problem, make the change, run the tests, commit to a feature branch and open a draft pull request. Extras include voice mode with a "Hey Jarvis" wake word, MCP server support, long-term memory, a CI doctor that reads failed GitHub Actions logs, and a web and phone interface.

**[Read the Jarvis guide](jarvis/README.md)**

### [AI Download Centre](https://joshuawayzwright.github.io/ai-download-center/)

A live public directory of AI models, assistants and tools: 112 hand-picked listings plus 870+ community model cards from Hugging Face, with live Hugging Face search. It also includes Creator Studio, a browser planner for the upcoming AI Field Notes video channel.

**[Open the directory](https://joshuawayzwright.github.io/ai-download-center/) · [Source](https://github.com/joshuawayzwright/ai-download-center) · [Submit a tool](https://github.com/joshuawayzwright/ai-download-center/issues/new?template=submit-tool.yml)**

### [ProjectForge AI](https://joshuawayzwright.github.io/projectforge-ai/)

A project planning and learning workspace with eight browser tools: Prompt Vault, Idea Canvas, Priority Coach, Study Cards, Content Planner, Research Tracker, GitHub Live Hub and Workflow Lab. It runs in the browser with local storage; there's no model inference or cloud sync.

**[Open ProjectForge](https://joshuawayzwright.github.io/projectforge-ai/) · [Source](https://github.com/joshuawayzwright/projectforge-ai)**

### [WrightWayz website](https://www.wrightwayz.com/)

Information about peer and community support, a support enquiry form, an accessibility statement and free browser tools. A static site on Vercel with a Content Security Policy and automated Python and browser tests.

## WrightWayz

<a href="https://www.wrightwayz.com/"><img src="assets/wrightwayz-banner.jpg" width="798" alt="WrightWayz — Broken Systems. Unbreakable Bonds. Gold phoenix, human and cybernetic handshake, steel gear and electric-blue accents." /></a>

**Broken Systems. Unbreakable Bonds. · #WeWalkAsOne**

WrightWayz is my separate Gold Coast community initiative, focused on lived experience, recovery, connection and responsible technology. The AI Bridge and a physical community hub are in development or planning.

Commercial products and WrightWayz keep separate identities, governance, funds and data. WrightWayz is not an emergency or clinical service.

**[Explore WrightWayz](https://www.wrightwayz.com/) · [Instagram](https://www.instagram.com/wrightwayzcharity/) · [Facebook](https://www.facebook.com/people/Wrightwayz/61592187395142/)**

## Skills and technologies

| Area | Tools and skills |
|---|---|
| **Languages** | JavaScript (Node.js), HTML5, CSS3, SQL (PostgreSQL), Python, Kotlin and Java (Android), Bash, PowerShell |
| **Platforms** | Vercel (serverless functions), Supabase, Stripe, GitHub Actions, GitHub Pages, Android (Jetpack Compose) |
| **AI** | Claude API and agents, Gemini API, Model Context Protocol (MCP), Hugging Face, voice interfaces |
| **Integrations** | Stripe Checkout and webhooks, Klaviyo, Google Analytics 4, Google Ads, Meta Pixel and Ads |
| **Practices** | Automated testing, secure payment and delivery flows, row-level security, Content Security Policy, privacy by design, SEO, accessibility, responsive design |
| **Business** | Product design and pricing, e-commerce, email marketing, digital advertising, small-business operations |

## How I build

- **Useful tools:** solve a real problem for a real person, then make it simple.
- **Tested before it ships:** automated tests and a real end-to-end check before launch.
- **Honest about status:** I clearly separate what's live, what's in testing and what's planned.
- **Responsible systems:** protect credentials, respect privacy, and keep community and commercial work separate.

## Contact

**Joshua Wright**<br />
**Email:** [superadmin2712@gmail.com](mailto:superadmin2712@gmail.com) · Business: [hello@thesoloserviceprovider.com.au](mailto:hello@thesoloserviceprovider.com.au)<br />
**Phone:** [0452 272 820](tel:+61452272820) · International: +61 452 272 820<br />
**LinkedIn:** [linkedin.com/in/joshuawright-solo](https://www.linkedin.com/in/joshuawright-solo)<br />
**Location:** Gold Coast, Queensland, Australia

When you get in touch, please name **The Solo Service Provider**, **SOLO AI**, **Jarvis**, **AI Download Centre**, **ProjectForge** or **WrightWayz** so your message reaches the right project.

---

<div align="center">

**REAL TOOLS. REAL RESULTS.**

Profile updated **17 November 2026** · [Profile audit and earlier status notes](PROFILE-AUDIT.md) · [Original artwork sources](assets/README.md)

</div>
