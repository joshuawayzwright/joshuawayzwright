# Independent AI Repository Migration Plan

This document defines the repository split from the WrightWayz nonprofit website. Commercial/general-purpose tools must live independently and must not be added back to the nonprofit repository.

## Commercial destination

https://thesoloserviceprovider.com.au

## Repository standard

Every independent repository should contain:

- README.md with purpose, screenshots/demo area, usage and commercial CTA
- source code at repository root or src/
- SECURITY.md
- CONTRIBUTING.md
- CHANGELOG.md
- .github/workflows/quality.yml
- .github/dependabot.yml when package dependencies exist
- release/download instructions
- privacy/data-handling notes
- explicit capability boundary for AI workflow helpers
- no fake APKs or binaries
- signed APK documentation only after a genuine Android build/signing pipeline exists

Recommended public-repository protection:

- protect main
- require pull request before merge
- require CI/status checks
- block force pushes
- block branch deletion
- require conversation resolution where supported
- enable Dependabot/security alerts where supported

## 25 destination repositories

### Solo Service Provider / AI workflow projects

1. ai-brief-builder
2. ai-offer-generator
3. ai-content-calendar
4. ai-hook-lab
5. ai-caption-studio
6. ai-email-sequencer
7. ai-ideal-client
8. ai-value-proposition
9. ai-faq-builder
10. ai-review-responder
11. ai-meeting-prompt
12. ai-sop-builder
13. ai-lead-magnet
14. ai-proposal-builder
15. ai-keyword-cluster
16. ai-repurpose-planner
17. ai-sales-script
18. ai-cta-lab
19. ai-brand-voice
20. ai-prompt-auditor

### General-purpose utilities to separate from WrightWayz

21. prompt-forge
22. log-scrubber
23. json-lens
24. link-cleaner
25. hash-forge

## Migration rule

Do not remove the source copy from wrightwayz-website until the matching independent repository exists and its source has been verified. After verification, remove the migrated project, its catalogue references, and project-specific tests from wrightwayz-website while retaining nonprofit-specific website code and Resource Navigator.

## Branding rule

The 20 Solo Service Provider AI repositories should lead to The Solo Service Provider. General-purpose utilities may identify Joshua Wright as maintainer and may cross-link to The Solo Service Provider, but must not imply that they are WrightWayz nonprofit programs.

## Release rule

Use semantic versioning. Source downloads may use GitHub-generated archives. Binary releases must be reproducible/traceable to source. Android APKs must not be advertised until a real signed build exists.
