# Migrate 25 projects from joshuawayzwright/wrightwayz-website into independent repositories.
# Prerequisites: git, GitHub CLI (gh), authenticated with 'gh auth login'.
# Safety: copies first, verifies destination, and NEVER deletes WrightWayz source.

$ErrorActionPreference = "Stop"
$owner = "joshuawayzwright"
$sourceRepo = "$owner/wrightwayz-website"
$work = Join-Path $env:TEMP "jwright-repo-migration"
if (Test-Path $work) { Remove-Item $work -Recurse -Force }
New-Item -ItemType Directory -Path $work | Out-Null

$projects = @(
@{name="ai-brief-builder";source="solo-ai-labs/ai-brief-builder"},
@{name="ai-offer-generator";source="solo-ai-labs/ai-offer-generator"},
@{name="ai-content-calendar";source="solo-ai-labs/ai-content-calendar"},
@{name="ai-hook-lab";source="solo-ai-labs/ai-hook-lab"},
@{name="ai-caption-studio";source="solo-ai-labs/ai-caption-studio"},
@{name="ai-email-sequencer";source="solo-ai-labs/ai-email-sequencer"},
@{name="ai-ideal-client";source="solo-ai-labs/ai-ideal-client"},
@{name="ai-value-proposition";source="solo-ai-labs/ai-value-proposition"},
@{name="ai-faq-builder";source="solo-ai-labs/ai-faq-builder"},
@{name="ai-review-responder";source="solo-ai-labs/ai-review-responder"},
@{name="ai-meeting-prompt";source="solo-ai-labs/ai-meeting-prompt"},
@{name="ai-sop-builder";source="solo-ai-labs/ai-sop-builder"},
@{name="ai-lead-magnet";source="solo-ai-labs/ai-lead-magnet"},
@{name="ai-proposal-builder";source="solo-ai-labs/ai-proposal-builder"},
@{name="ai-keyword-cluster";source="solo-ai-labs/ai-keyword-cluster"},
@{name="ai-repurpose-planner";source="solo-ai-labs/ai-repurpose-planner"},
@{name="ai-sales-script";source="solo-ai-labs/ai-sales-script"},
@{name="ai-cta-lab";source="solo-ai-labs/ai-cta-lab"},
@{name="ai-brand-voice";source="solo-ai-labs/ai-brand-voice"},
@{name="ai-prompt-auditor";source="solo-ai-labs/ai-prompt-auditor"},
@{name="prompt-forge";source="tools/prompt-forge"},
@{name="log-scrubber";source="tools/log-scrubber"},
@{name="json-lens";source="tools/json-lens"},
@{name="link-cleaner";source="tools/link-cleaner"},
@{name="hash-forge";source="tools/hash-forge"}
)

gh auth status
$source = Join-Path $work "source"
git clone --depth 1 "https://github.com/$sourceRepo.git" $source
if ($LASTEXITCODE -ne 0) { throw "Could not clone source repository." }

foreach ($p in $projects) {
  $destFull = "$owner/$($p.name)"
  gh repo view $destFull --json name | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Destination repository missing: $destFull. Run bootstrap-independent-repos.ps1 first." }

  $src = Join-Path $source $p.source
  if (!(Test-Path $src)) { throw "Source directory missing: $($p.source)" }

  $dest = Join-Path $work $p.name
  New-Item -ItemType Directory -Path $dest | Out-Null
  Copy-Item (Join-Path $src "*") $dest -Recurse -Force

  Push-Location $dest
  git init -b main
  git add .
  git commit -m "Initial independent release migrated from WrightWayz source"
  git remote add origin "https://github.com/$destFull.git"
  git push -u origin main
  if ($LASTEXITCODE -ne 0) { Pop-Location; throw "Push failed for $destFull" }

  $localTree = (git rev-parse HEAD^{tree}).Trim()
  $remoteHead = (git ls-remote origin refs/heads/main).Split()[0]
  if (!$remoteHead) { Pop-Location; throw "Verification failed for $destFull" }

  Pop-Location
  Write-Host "Verified destination: $destFull ($remoteHead)"
}

Write-Host "All 25 destinations received source. WrightWayz remains untouched; perform connector-side verification before cleanup."
