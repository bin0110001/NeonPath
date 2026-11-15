# How a job is scored

Scores are never a single opaque number. Each evaluation stores per-dimension scores, strengths, gaps, blockers and *unknowns*, and a plain-language explanation. The same job is scored separately for every profile.

## Deterministic evaluation (always on, no AI)

`backend/src/careerflow/domain/evaluations/service.py`, evaluator `deterministic-v2.0`.

| Dimension | Signal | Notes |
|---|---|---|
| `role_alignment` | job title vs the profile's role families and role targets (title patterns with `*`, include/exclude keywords) | exclude keywords reduce the score |
| `seniority_alignment` | level words in the title (junior, senior, staff, principal, lead, director...) vs target seniority | unknown if the title states no level |
| `technical_alignment` | profile skills and their aliases found as whole words in the job text and extracted requirements | 3 matching skills = full score; shared-category skills the profile lacks are listed as *transferable matches* |
| `location_alignment` | allowed countries/regions/cities, relocation, and the remote policy (REQUIRED / PREFERRED / NEUTRAL / AVOID / BLOCK) | remote jobs ignore place restrictions |
| `compensation_alignment` | salary range vs the minimum, normalised to a yearly figure (hour 2080, day 260, week 52, month 12) | currencies are **never converted**: a mismatch is reported as unknown |
| `employment_alignment` | job employment type vs the profile's allowed types | |
| `interest_alignment` | preferred company or industry | only scored when it matches |
| `architecture_`, `leadership_`, `domain_alignment` | not scorable by rules | reported as unknown; optionally scored by the AI layer |

**Unknown is not zero.** A dimension with no signal is left out of the weighted average and listed under *unknowns*; it is never derived from another dimension.

**Weights.** Each profile has scoring weights (defaults: role 0.20, seniority 0.15, technical 0.15, architecture 0.15, leadership 0.10, location 0.10, compensation 0.10, interest 0.05). The overall score is the weighted mean over the dimensions that were scored, with the weights renormalised. `confidence` is the share of the configured weight that had a signal, so a score based on little evidence says so.

**Blockers.** Hard preferences make a job a blocker and cap the overall score at 20 %: an excluded company or industry, a location outside the allowed places (unless relocation is allowed), remote REQUIRED/BLOCK mismatches, a salary range entirely below the minimum, an employment type that is not allowed. Blockers are listed with their reason.

## Semantic evaluation (optional AI)

With AI enabled you can add a semantic pass ([ADR-011](../adr/ADR-011-deterministic-plus-semantic-evaluation.md)). It may only score the dimensions rules cannot, and adds claims such as "strength", "transferable" or "gap". Every positive claim must cite real profile records (`experience:`, `achievement:`, `skill:`, ...) or is shown as `inference` / `unverified` ([ADR-009](../adr/ADR-009-evidence-backed-claims.md)). **Deterministic blockers always win.** With AI off, the evaluation is exactly the deterministic one.

## History

Every run appends a row with the evaluator version (and provider, model, prompt version for AI runs); earlier evaluations are never overwritten. Editing a profile's preferences, skills or role targets queues a re-evaluation of that profile's jobs only.
