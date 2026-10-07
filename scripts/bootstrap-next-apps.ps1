# Create the next 15 independent downloadable app repositories.
# Requires GitHub CLI and: gh auth login
# Creates repository containers only. It does not modify WrightWayz.

$ErrorActionPreference = "Stop"
$owner = "joshuawayzwright"

$apps = @(
  @{name="ai-client-onboarding"; description="Local-first AI client onboarding brief builder for service businesses."},
  @{name="ai-social-repurposer"; description="Local-first social content repurposing brief builder."},
  @{name="ai-quote-builder"; description="Local-first quote and scope brief builder for service providers."},
  @{name="ai-testimonial-miner"; description="Local-first testimonial theme and marketing insight tool."},
  @{name="ai-competitor-brief"; description="Local-first competitor research brief builder."},
  @{name="ai-customer-journey"; description="Local-first customer journey mapping tool for service businesses."},
  @{name="ai-follow-up-planner"; description="Local-first ethical client and lead follow-up planner."},
  @{name="ai-service-pricing"; description="Local-first service pricing input and positioning planner."},
  @{name="ai-case-study-builder"; description="Local-first case study drafting brief builder."},
  @{name="ai-local-seo-brief"; description="Local-first SEO research and page brief builder for local services."},
  @{name="ai-video-brief"; description="Local-first video hook, run-of-show and production brief builder."},
  @{name="ai-content-gap"; description="Local-first customer-question and content-gap planning tool."},
  @{name="ai-objection-mapper"; description="Local-first sales objection evidence and response mapper."},
  @{name="ai-referral-campaign"; description="Local-first referral campaign planning tool."},
  @{name="ai-review-insights"; description="Local-first customer review theme and action-item analyzer."}
)

gh auth status
if ($LASTEXITCODE -ne 0) { throw "GitHub CLI is not authenticated." }

foreach ($app in $apps) {
  $full = "$owner/$($app.name)"
  gh repo view $full --json name 2>$null | Out-Null
  if ($LASTEXITCODE -eq 0) {
    Write-Host "Exists: $full"
    continue
  }

  gh repo create $full --public --description $app.description --disable-wiki
  if ($LASTEXITCODE -ne 0) { throw "Failed to create $full" }
  Write-Host "Created: $full"
}

Write-Host "15 repository containers ready. Populate and verify products before advertising downloads."
