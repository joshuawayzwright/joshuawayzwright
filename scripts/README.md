# Repository Migration Automation

Professional migration tooling for separating commercial/general-purpose software from the WrightWayz nonprofit website.

## Required tools

- Git
- GitHub CLI (`gh`)
- PowerShell 7+ recommended
- GitHub authentication: `gh auth login`

## Order of operations

1. `bootstrap-independent-repos.ps1`
   - creates the 25 public repository containers if missing
   - does not alter WrightWayz

2. `migrate-independent-repos.ps1`
   - clones the current WrightWayz source
   - copies each project into its matching independent repository
   - creates an independent Git history
   - pushes `main`
   - verifies a remote `main` exists
   - does not delete WrightWayz source

3. `protect-independent-repos.ps1`
   - applies a professional `main` protection baseline
   - blocks force pushes and deletion
   - enforces linear history and conversation resolution
   - requires administrator privileges and GitHub support for branch protection

## Safety model

The scripts intentionally separate **copy/verify** from **cleanup**. WrightWayz cleanup is not automated here because deletion must occur only after the connected GitHub workflow verifies all 25 destinations and their contents.

No script creates or commits signing keys, API keys, tokens, passwords or other secrets.

## Licensing

No software license is selected automatically. A public repository without an explicit license is publicly viewable but does not automatically grant broad reuse rights. Choose licensing deliberately before marketing projects as open source.

## APK policy

No placeholder APKs are generated. Android binaries may be published only after a genuine build, signing and verification workflow is implemented.
