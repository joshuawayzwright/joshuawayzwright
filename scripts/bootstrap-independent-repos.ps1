# Bootstrap the 25 independent repositories for Joshua Wright
# Requires GitHub CLI: https://cli.github.com/
# Run after: gh auth login
# Creates PUBLIC empty repositories only; it does not delete or modify WrightWayz.

$ErrorActionPreference = "Stop"

$repos = @(
"ai-brief-builder","ai-offer-generator","ai-content-calendar","ai-hook-lab","ai-caption-studio",
"ai-email-sequencer","ai-ideal-client","ai-value-proposition","ai-faq-builder","ai-review-responder",
"ai-meeting-prompt","ai-sop-builder","ai-lead-magnet","ai-proposal-builder","ai-keyword-cluster",
"ai-repurpose-planner","ai-sales-script","ai-cta-lab","ai-brand-voice","ai-prompt-auditor",
"prompt-forge","log-scrubber","json-lens","link-cleaner","hash-forge"
)

gh auth status

foreach ($name in $repos) {
  Write-Host "Checking $name..."
  gh repo view "joshuawayzwright/$name" --json name 2>$null
  if ($LASTEXITCODE -eq 0) {
    Write-Host "Exists: $name"
    continue
  }

  gh repo create "joshuawayzwright/$name" --public --description "Independent project by Joshua Wright. Professional source, documentation, security and release workflow." --disable-wiki
  if ($LASTEXITCODE -ne 0) { throw "Failed to create $name" }
  Write-Host "Created: $name"
}

Write-Host "Repository bootstrap complete. No WrightWayz source was deleted."
