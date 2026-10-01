# Apply professional baseline protection to the 25 independent public repositories.
# Requires GitHub CLI authenticated as repository administrator.
# GitHub plan/repository visibility rules may affect availability.

$ErrorActionPreference = "Stop"
$owner="joshuawayzwright"
$repos=@(
"ai-brief-builder","ai-offer-generator","ai-content-calendar","ai-hook-lab","ai-caption-studio",
"ai-email-sequencer","ai-ideal-client","ai-value-proposition","ai-faq-builder","ai-review-responder",
"ai-meeting-prompt","ai-sop-builder","ai-lead-magnet","ai-proposal-builder","ai-keyword-cluster",
"ai-repurpose-planner","ai-sales-script","ai-cta-lab","ai-brand-voice","ai-prompt-auditor",
"prompt-forge","log-scrubber","json-lens","link-cleaner","hash-forge"
)

gh auth status

foreach($name in $repos){
  $repo="$owner/$name"
  gh repo view $repo --json name | Out-Null
  if($LASTEXITCODE -ne 0){ throw "Missing repository: $repo" }

  $body=@{
    required_status_checks=$null
    enforce_admins=$true
    required_pull_request_reviews=@{
      dismiss_stale_reviews=$true
      require_code_owner_reviews=$false
      required_approving_review_count=0
    }
    restrictions=$null
    required_linear_history=$true
    allow_force_pushes=$false
    allow_deletions=$false
    block_creations=$false
    required_conversation_resolution=$true
    lock_branch=$false
    allow_fork_syncing=$true
  } | ConvertTo-Json -Depth 6

  $body | gh api --method PUT -H "Accept: application/vnd.github+json" -H "X-GitHub-Api-Version: 2022-11-28" "/repos/$repo/branches/main/protection" --input -
  if($LASTEXITCODE -ne 0){ throw "Protection failed for $repo. Check repository visibility/plan/admin permission." }
  Write-Host "Protected: $repo/main"
}

Write-Host "Protection baseline applied to all 25 repositories."
