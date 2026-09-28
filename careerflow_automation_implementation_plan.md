# CareerFlow — Job Search Automation Platform

> **Working name:** CareerFlow  
> **Purpose:** A reusable, self-hosted job discovery, evaluation, application-preparation, and interview-tracking platform built around independent user profiles.  
> **Primary deployment:** Podman  
> **Also supported:** Docker Desktop / Docker Compose  
> **Core principle:** Automate discovery, organization, analysis, and preparation. Keep a human approval boundary before external actions such as submitting applications or sending messages.

---

## 1. Goals

- [ ] Support multiple independent career profiles in one installation.
- [ ] Discover jobs from pluggable sources.
- [ ] Normalize all jobs into one canonical model.
- [ ] Deduplicate the same opening found through multiple sources.
- [ ] Evaluate each job independently against each profile.
- [ ] Explain strengths, gaps, blockers, and transferable experience instead of relying on a single opaque score.
- [ ] Recommend the best resume variant and accomplishments for a job.
- [ ] Generate application-preparation material without inventing experience.
- [ ] Track applications, contacts, follow-ups, and interviews.
- [ ] Preserve job descriptions after listings disappear.
- [ ] Run without an AI provider for core functionality.
- [ ] Support both hosted and local/OpenAI-compatible LLM providers.
- [ ] Be suitable as a public portfolio project using only fictional/demo data.
- [ ] Run with both `podman compose` and `docker compose`.

### Explicit non-goals for early releases

- [ ] No blind auto-apply bot.
- [ ] No CAPTCHA bypass or anti-bot circumvention.
- [ ] No automated scraping of sources that prohibit it.
- [ ] No automatic answers to legal, work-authorization, demographic, salary, or identity questions.
- [ ] No automatic recruiter messages without approval.
- [ ] No hard dependency on a commercial LLM provider.
- [ ] No user-specific assumptions embedded in code.

---

# 2. Product Model

The system should be organized around this flow:

```text
Profile
   │
   ├── Target Role Families
   ├── Career Evidence
   ├── Search Preferences
   ├── Resume Variants
   └── Scoring Preferences
          │
          ▼
Job Source Adapters
          │
          ▼
Raw Job Records
          │
          ▼
Normalize → Deduplicate → Enrich
          │
          ▼
Canonical Job
          │
          ▼
Evaluate Against Profile
          │
          ▼
Human Review
   ┌──────┼────────┐
   ▼      ▼        ▼
Reject   Save   Shortlist
                   │
                   ▼
          Application Package
                   │
                   ▼
             Human Applies
                   │
                   ▼
       Application / Interview
              Tracking
```

The same canonical job may produce very different evaluations for two different profiles.

---

# 3. Recommended Stack

## Backend

Use **Python 3.13+**.

Recommended baseline:

- FastAPI
- Pydantic
- SQLAlchemy
- Alembic
- PostgreSQL driver
- httpx
- pytest
- Ruff
- mypy or pyright
- structured logging

Python is a good fit because this project combines application development, document parsing, AI integration, and data-oriented processing.

## Frontend

Use **React + TypeScript + Vite**.

Recommended baseline:

- React
- TypeScript
- Vite
- TanStack Query
- React Router
- Playwright
- a replaceable component library

Do not make the UI component framework part of the domain architecture.

## Persistence

Use **PostgreSQL**.

Do not require a separate vector database initially. If semantic retrieval becomes useful, add `pgvector` later as an optional capability.

## Background work

Design around three logical processes:

```text
API
Worker
Scheduler
```

They may share one backend image and codebase.

Do not introduce Redis merely because background workers exist. Start with a PostgreSQL-backed queue/lease mechanism or another lightweight abstraction. Add Redis/RabbitMQ later only if there is a demonstrated need.

---

# 4. Architecture Principles

## 4.1 Profile-first

Nothing about a specific person belongs in global configuration or application code.

Bad:

```python
TARGET_ROLE = "Principal AI Engineer"
REMOTE_ONLY = True
YEARS_EXPERIENCE = 18
```

Good:

```text
Profile
 ├── Identity
 ├── Experience
 ├── Achievements
 ├── Skills
 ├── Education
 ├── Portfolio
 ├── Target Role Families
 ├── Search Preferences
 ├── Resume Variants
 └── Scoring Preferences
```

## 4.2 Provider-independent AI

Create an interface such as:

```python
class LlmProvider(Protocol):
    async def complete(self, request: CompletionRequest) -> CompletionResult:
        ...
```

Initial implementations may include:

```text
OpenAIProvider
OllamaProvider
OpenAICompatibleProvider
DisabledProvider
FixtureProvider
```

Domain code must not import provider SDK types.

## 4.3 Source-independent job ingestion

Create a source contract:

```python
class JobSourceAdapter(Protocol):
    name: str
    capabilities: SourceCapabilities

    async def discover(
        self,
        request: DiscoveryRequest,
    ) -> AsyncIterator[SourceJobReference]:
        ...

    async def fetch(
        self,
        reference: SourceJobReference,
    ) -> SourceJobDocument:
        ...
```

Possible adapters:

- manual paste
- manual URL capture
- fixture/demo JSON
- RSS/Atom
- generic JSON feed
- public job APIs
- Greenhouse
- Lever
- email alerts
- browser extension/bookmarklet
- company ATS integrations where permitted

Do **not** make LinkedIn scraping a required capability.

## 4.4 Human-in-the-loop boundary

AI may:

- summarize
- classify
- score
- compare
- identify gaps
- recommend resume content
- draft messages
- prepare interviews

AI must not automatically:

- submit applications
- send external messages
- fabricate career claims
- answer identity/legal questions
- mark an application as submitted without user or integration confirmation

## 4.5 Evidence-backed generation

Every meaningful career claim should trace back to profile evidence:

```text
Experience
Achievement
Skill
Education
Certification
Portfolio Item
```

If evidence is missing, mark the claim as `UNVERIFIED` rather than inventing it.

---

# 5. Repository Layout

Use a monorepo.

```text
careerflow/
├── README.md
├── LICENSE
├── CONTRIBUTING.md
├── SECURITY.md
├── compose.yaml
├── compose.dev.yaml
├── compose.demo.yaml
├── .env.example
├── .gitignore
│
├── docs/
│   ├── architecture/
│   │   ├── overview.md
│   │   ├── profiles.md
│   │   ├── job-ingestion.md
│   │   ├── evaluation.md
│   │   ├── security.md
│   │   └── containers.md
│   └── adr/
│
├── backend/
│   ├── Containerfile
│   ├── pyproject.toml
│   ├── migrations/
│   ├── src/careerflow/
│   │   ├── api/
│   │   ├── application/
│   │   ├── domain/
│   │   │   ├── profiles/
│   │   │   ├── jobs/
│   │   │   ├── evaluations/
│   │   │   ├── applications/
│   │   │   ├── artifacts/
│   │   │   └── interviews/
│   │   ├── infrastructure/
│   │   │   ├── database/
│   │   │   ├── jobsources/
│   │   │   ├── llm/
│   │   │   ├── storage/
│   │   │   └── tasks/
│   │   ├── workers/
│   │   └── settings.py
│   └── tests/
│       ├── unit/
│       ├── integration/
│       └── fixtures/
│
├── frontend/
│   ├── Containerfile
│   ├── package.json
│   ├── src/
│   │   ├── api/
│   │   ├── components/
│   │   ├── features/
│   │   │   ├── profiles/
│   │   │   ├── discovery/
│   │   │   ├── jobs/
│   │   │   ├── pipeline/
│   │   │   ├── applications/
│   │   │   └── settings/
│   │   └── routes/
│   └── tests/
│
├── scripts/
│   ├── dev/
│   ├── test/
│   └── demo/
│
└── examples/
    ├── profiles/
    └── jobs/
```

---

# 6. Core Domain Model

## 6.1 Profile

```text
Profile
- id
- slug
- display_name
- headline
- summary
- timezone
- status
- created_at
- updated_at
```

Keep contact information separate:

```text
ProfileContact
- profile_id
- full_name
- email
- phone
- city
- region
- country
- website
- linkedin_url
- github_url
```

All contact fields should be optional so public/demo profiles need no sensitive data.

## 6.2 Experience

```text
Experience
- id
- profile_id
- organization
- title
- start_date
- end_date
- description
- employment_type
- location
- sort_order
```

## 6.3 Achievement inventory

Treat achievements as first-class reusable evidence.

```text
Achievement
- id
- profile_id
- experience_id
- title
- situation
- action
- result
- metrics_json
- technologies[]
- competency_tags[]
- verified
```

Achievements should be reusable across:

- resumes
- cover letters
- recruiter outreach
- job evaluation
- interview prep

## 6.4 Skills

Do not use one unstructured string list.

```text
Skill
- id
- canonical_name
- category
```

```text
ProfileSkill
- profile_id
- skill_id
- proficiency
- years_experience
- last_used_year
- evidence_notes
- verified
```

```text
SkillAlias
- alias
- skill_id
```

Examples:

```text
C#             -> C Sharp
ASP.NET Core   -> .NET Web
GenAI          -> Generative AI
LLM            -> Large Language Models
```

## 6.5 Role families

A profile may target several related career tracks.

```text
RoleFamily
- id
- profile_id
- name
- priority
- enabled
```

```text
RoleTarget
- id
- role_family_id
- title_pattern
- include_keywords[]
- exclude_keywords[]
- target_seniority[]
- minimum_score
```

Do not depend on exact title matching.

## 6.6 Preferences

```text
SearchPreferences
- profile_id
- remote_preference
- allowed_countries[]
- allowed_regions[]
- allowed_cities[]
- relocation_allowed
- travel_percentage_max
- employment_types[]
- minimum_base_salary
- minimum_total_comp
- currency
- excluded_companies[]
- preferred_companies[]
- excluded_industries[]
- preferred_industries[]
```

Each preference should support a policy:

```text
REQUIRED
PREFERRED
NEUTRAL
AVOID
BLOCK
```

For example, `remote=PREFERRED` must behave differently from `remote=REQUIRED`.

---

# 7. Canonical Job Model

Every source adapter must normalize into one canonical structure.

```text
Job
- id
- canonical_url
- title
- company
- company_domain
- description_text
- description_html
- location_text
- remote_type
- employment_type
- salary_min
- salary_max
- salary_currency
- salary_period
- posted_at
- expires_at
- discovered_at
- source_updated_at
- source_status
- fingerprint
- raw_metadata_json
```

Source-specific records are retained separately:

```text
JobSourceRecord
- id
- job_id
- adapter
- external_id
- source_url
- raw_payload
- discovered_at
- last_seen_at
```

Structured requirements:

```text
JobRequirement
- id
- job_id
- type
- normalized_text
- source_text
- required_level
- category
- confidence
```

Categories:

```text
skill
experience
education
location
work_authorization
security_clearance
travel
industry
leadership
management
architecture
compensation
other
```

---

# 8. Job Lifecycle

Processing lifecycle:

```text
DISCOVERED
    ↓
INGESTED
    ↓
NORMALIZED
    ↓
DEDUPLICATED
    ↓
ENRICHED
    ↓
EVALUATED
    ↓
READY_FOR_REVIEW
```

User workflow:

```text
READY_FOR_REVIEW
   ├── SHORTLISTED
   ├── REJECTED
   ├── SAVED
   └── ARCHIVED

SHORTLISTED
   ↓
PREPARING
   ↓
READY_TO_APPLY
   ↓
APPLIED
   ↓
SCREENING
   ↓
INTERVIEWING
   ↓
FINAL
   ├── OFFER
   ├── REJECTED
   └── WITHDRAWN
```

Store every transition:

```text
JobStatusHistory
- id
- profile_id
- job_id
- old_status
- new_status
- actor
- reason
- timestamp
```

Do not overwrite history.

---

# 9. Ingestion Pipeline

```text
Source
  ↓
Fetch
  ↓
Raw Snapshot
  ↓
Normalize
  ↓
Validate
  ↓
Fingerprint
  ↓
Deduplicate
  ↓
Persist
  ↓
Extract Requirements
  ↓
Evaluate Profiles
```

Each stage must be independently testable and retryable.

## Initial adapters

### Phase 1

- [ ] `ManualJobAdapter`
  - paste description
  - optional URL
  - optional title/company metadata
- [ ] `FixtureJobAdapter`
- [ ] `RssJobAdapter`
- [ ] `GenericJsonJobAdapter`

### Phase 2

- [ ] Greenhouse adapter
- [ ] Lever adapter
- [ ] configurable approved company-careers adapter
- [ ] email alert ingestion
- [ ] additional authorized/public APIs

### Later

- [ ] browser extension
- [ ] bookmarklet
- [ ] Gmail/Outlook connectors
- [ ] community adapters

Each adapter should declare compliance/operational metadata such as:

```text
access_method
requires_credentials
rate_limit_policy
terms_url
retention_policy
redistribution_allowed
```

---

# 10. Deduplication

The same job may arrive from multiple sources.

Do not deduplicate by URL alone.

Normalize and compare:

```text
company
title
location
external requisition ID
posting date
salary range
description similarity
```

Classification:

```text
EXACT
LIKELY
POSSIBLE
DISTINCT
```

A canonical `Job` may own multiple `JobSourceRecord` objects.

Add merge/unmerge support for ambiguous cases.

---

# 11. Requirement Extraction

Input:

```text
job description
```

Expected structured output:

```json
{
  "summary": "...",
  "responsibilities": [],
  "required_skills": [],
  "preferred_skills": [],
  "experience_requirements": [],
  "education_requirements": [],
  "leadership_expectations": [],
  "architecture_expectations": [],
  "management_expectations": [],
  "location_constraints": [],
  "travel_requirements": [],
  "compensation": {},
  "potential_blockers": [],
  "ambiguous_requirements": []
}
```

Persist both structured results and original source text/provenance.

---

# 12. Evaluation Engine

Separate deterministic logic from semantic/AI evaluation.

## 12.1 Deterministic rules

Examples:

```text
remote REQUIRED + onsite role       -> blocker
salary max below required minimum    -> strong negative/blocker
excluded country                     -> blocker
excluded company                     -> blocker
required clearance unavailable       -> blocker
matching role family                  -> positive
matching preferred industry          -> positive
```

These should never require an LLM.

## 12.2 Semantic evaluation

AI may evaluate:

- equivalent technologies
- transferable skills
- architecture responsibility
- leadership scope
- likely seniority
- domain overlap
- hidden role characteristics
- whether a gap is fundamental or learnable

Example:

```text
Requirement:
AWS SageMaker

Profile evidence:
Azure ML + Databricks + production ML platform architecture

Classification:
PARTIAL_TRANSFERABLE

Explanation:
No explicit SageMaker evidence, but comparable production cloud ML platform
experience exists. Treat as a platform-specific gap rather than a missing
ML-platform capability.
```

## 12.3 Score dimensions

Store dimensions independently:

```text
role_alignment
seniority_alignment
technical_alignment
architecture_alignment
leadership_alignment
domain_alignment
location_alignment
compensation_alignment
employment_alignment
interest_alignment
```

Example configurable weights:

```yaml
role_alignment: 0.20
seniority_alignment: 0.15
technical_alignment: 0.15
architecture_alignment: 0.15
leadership_alignment: 0.10
location_alignment: 0.10
compensation_alignment: 0.10
interest_alignment: 0.05
```

Weights belong to a profile or role family.

## 12.4 Evaluation result

```text
JobEvaluation
- profile_id
- job_id
- evaluator_version
- model_provider
- model_name
- overall_score
- confidence
- dimension_scores_json
- strengths[]
- transferable_matches[]
- gaps[]
- blockers[]
- unknowns[]
- explanation
- created_at
```

Evaluations are versioned. Never silently overwrite a previous evaluation when prompts or models change.

---

# 13. Resume and Application Package Model

Do not treat resumes only as uploaded static files.

## Resume template

```text
ResumeTemplate
- id
- name
- format
- layout_config
- theme_config
```

## Resume variant

```text
ResumeVariant
- id
- profile_id
- role_family_id
- name
- summary_strategy
- preferred_skill_categories
- selected_experiences
- selected_achievements
- template_id
```

Possible variants:

```text
Principal AI Engineer
AI Architect
Staff Software Engineer
Engineering Leadership
```

## Application package

```text
ApplicationPackage
- profile_id
- job_id
- resume_variant_id
- recommended_achievements[]
- recommended_skill_order[]
- summary_suggestion
- tailoring_notes[]
- missing_evidence[]
- cover_letter_notes[]
```

Phase 1 should provide recommendations rather than automatically rewriting facts.

Later add renderers for:

```text
Markdown
HTML
DOCX
PDF
```

behind an `ArtifactRenderer` interface.

---

# 14. Application Tracking

```text
Application
- id
- profile_id
- job_id
- status
- applied_at
- source
- resume_artifact_id
- cover_letter_artifact_id
- compensation_entered
- notes
```

Contacts:

```text
Contact
- id
- name
- email
- company
- title
- profile_url
- notes
```

```text
ApplicationContact
- application_id
- contact_id
- role
```

Roles:

```text
recruiter
hiring_manager
referral
interviewer
other
```

Follow-ups:

```text
FollowUp
- application_id
- due_at
- type
- status
- notes
```

---

# 15. Interview Tracking

```text
Interview
- id
- application_id
- type
- scheduled_at
- duration
- participants[]
- meeting_url
- notes
- outcome
```

Types:

```text
recruiter
hiring_manager
coding
system_design
machine_learning
architecture
behavioral
panel
executive
other
```

Generate preparation material from both the job and profile:

```text
Likely focus areas
Relevant achievements
Potential weak spots
Questions to ask
System-design themes
AI/ML topics
Leadership stories
Company research
```

---

# 16. Dashboard

## Main dashboard

Show:

```text
New jobs
High-fit jobs
Needs review
Shortlisted
Applications in progress
Upcoming interviews
Follow-ups due
Offers
Recent activity
```

## Job inbox filters

```text
profile
role family
minimum score
company
remote type
location
salary
source
date discovered
status
skills
has blockers
```

## Job detail

Show:

1. title/company/location
2. compensation
3. source links
4. original description
5. extracted requirements
6. evaluation
7. dimension scores
8. matched evidence
9. gaps/blockers
10. resume recommendation
11. notes
12. workflow actions
13. source history
14. evaluation history

## Profile editor

Tabs:

```text
Overview
Experience
Achievements
Skills
Education
Role Targets
Search Preferences
Resume Variants
Portfolio
Scoring
Integrations
```

---

# 17. Search Definitions

```text
SearchDefinition
- id
- profile_id
- name
- enabled
- source_adapter
- query
- location
- filters_json
- schedule
- last_run_at
```

Example:

```yaml
name: Principal AI Roles
role_terms:
  - Principal AI Engineer
  - Principal Machine Learning Engineer
  - AI Architect
  - AI Platform Architect
  - Staff AI Engineer

keywords_any:
  - generative AI
  - LLM
  - agentic
  - machine learning
  - AI platform

remote:
  preferred: true
```

Search definitions should be source-independent. Each adapter translates the generic definition into source-specific syntax where possible.

---

# 18. Scheduling and Background Tasks

Persist schedules instead of relying entirely on external cron configuration.

```text
ScheduledTask
- id
- type
- profile_id
- schedule
- enabled
- last_started_at
- last_completed_at
- last_status
```

Initial scheduled operations:

- [ ] discover jobs
- [ ] refresh jobs
- [ ] check expiration
- [ ] reevaluate jobs after profile changes
- [ ] surface follow-ups
- [ ] prune old raw payloads according to retention policy

Use a database lease/distributed lock so duplicate workers do not execute the same scheduled task.

---

# 19. AI Provider System

## Configuration

```text
LlmProviderConfig
- id
- name
- provider_type
- endpoint
- model
- secret_reference
- enabled
```

Never commit API keys.

## Task-specific AI interfaces

Prefer explicit operations:

```text
extract_job_requirements()
evaluate_job_fit()
summarize_job()
suggest_resume_tailoring()
prepare_interview()
draft_recruiter_message()
```

over a giant generic prompt method in application code.

## Prompt registry

```text
PromptDefinition
- key
- version
- template
- response_schema
```

Store prompt version with every generated result.

## Structured responses

Validate AI output with JSON Schema/Pydantic.

On invalid output:

1. validate
2. retry once with a repair instruction
3. if still invalid, fail the task
4. preserve failure metadata
5. never persist partially trusted structured output as valid

## Non-AI fallback

The system must still function with:

```text
AI_ENABLED=false
```

Without AI it still supports:

- ingestion
- normalization
- deterministic filters
- keyword matching
- manual review
- application tracking
- interview tracking

---

# 20. Security and Privacy

## Secrets

Support:

```text
.env
container secrets where available
external secret stores later
```

Never commit:

- API keys
- OAuth tokens
- mailbox credentials
- private resume data
- private notes

## Profile isolation

Every profile-scoped entity must include `profile_id` or be reachable through an explicitly profile-owned aggregate.

Application/service methods should require profile context.

Create automated cross-profile leakage tests.

## Logging

Avoid logging:

- secrets
- OAuth tokens
- complete resumes by default
- unnecessary PII

Use structured IDs:

```text
request_id
task_id
profile_id
job_id
source_adapter
```

## Demo mode

Provide:

```text
DEMO_MODE=true
```

Demo mode should:

- seed fictional profiles
- seed fictional jobs
- disable external write integrations
- display a Demo Mode indicator
- support resetting to a known state
- contain no private information

---

# 21. Authentication Strategy

Do not block MVP development on a full identity platform.

## Phase 1

```text
AUTH_MODE=local
```

Assume local/self-hosted use with profile selection.

## Phase 2

Create an `AuthProvider` abstraction with possible implementations:

```text
local password
OIDC
reverse-proxy authentication
```

Authentication identity and career profile must be separate concepts so one account can own multiple profiles.

---

# 22. REST API Baseline

```text
GET    /api/health
GET    /api/version

GET    /api/profiles
POST   /api/profiles
GET    /api/profiles/{profile_id}
PATCH  /api/profiles/{profile_id}

GET    /api/jobs
POST   /api/jobs/import
GET    /api/jobs/{job_id}

GET    /api/jobs/{job_id}/evaluations
POST   /api/jobs/{job_id}/evaluate
POST   /api/jobs/{job_id}/shortlist
POST   /api/jobs/{job_id}/reject

GET    /api/applications
POST   /api/applications
PATCH  /api/applications/{application_id}

GET    /api/searches
POST   /api/searches
POST   /api/searches/{search_id}/run

GET    /api/tasks
GET    /api/activity
```

Generate OpenAPI automatically.

---

# 23. Container Architecture

Baseline services:

```text
careerflow-web
careerflow-api
careerflow-worker
careerflow-db
```

Optional later:

```text
careerflow-scheduler
careerflow-proxy
careerflow-redis
careerflow-ollama
```

`api`, `worker`, and future `scheduler` should be able to reuse the same backend image with different entry commands.

Conceptual Compose structure:

```yaml
services:
  api:
    build:
      context: ./backend
    command: ["api"]

  worker:
    build:
      context: ./backend
    command: ["worker"]

  db:
    image: postgres:<pinned-major>
```

Prefer named volumes for persistent data.

Do not set `container_name`; let the Compose project manage names.

---

# 24. Podman + Docker Desktop Compatibility

The base deployment must support both:

```bash
podman compose up -d --build
```

and:

```bash
docker compose up -d --build
```

Requirements:

- [ ] Follow the current Compose Specification.
- [ ] Do not use an obsolete top-level Compose `version:` field.
- [ ] Avoid Docker socket mounting.
- [ ] Never require `/var/run/docker.sock`.
- [ ] Avoid privileged containers.
- [ ] Avoid host networking.
- [ ] Avoid hard-coded UID assumptions.
- [ ] Test rootless Podman.
- [ ] Use named volumes where practical.
- [ ] Add container health checks.
- [ ] Use service DNS names for internal networking.
- [ ] Pin major database versions.
- [ ] Document SELinux volume considerations if bind mounts are introduced.
- [ ] Test Docker Desktop on Windows.
- [ ] Test Podman on Linux.
- [ ] Prefer OCI-compatible images/build behavior.

Only create engine-specific override files if a real difference is discovered:

```text
compose.podman.yaml
compose.docker.yaml
```

Do not fork the architecture prematurely.

---

# 25. Developer Commands

Provide cross-platform helper scripts.

Unix:

```text
scripts/dev/up.sh
scripts/dev/down.sh
scripts/dev/reset.sh
scripts/test/all.sh
```

PowerShell:

```text
scripts/dev/up.ps1
scripts/dev/down.ps1
scripts/dev/reset.ps1
scripts/test/all.ps1
```

Allow:

```text
CONTAINER_ENGINE=podman
CONTAINER_ENGINE=docker
```

Scripts should translate that into the correct Compose command without changing application behavior.

---

# 26. Observability

## Health endpoints

```text
/health/live
/health/ready
```

Readiness verifies:

- process initialized
- database reachable
- migrations compatible

External AI availability should **not** determine whether the application is healthy.

## Task execution

```text
TaskExecution
- id
- task_type
- status
- started_at
- completed_at
- attempts
- error_code
- error_message
- metadata_json
```

Expose failed tasks in the UI.

---

# 27. Testing Strategy

## Unit tests

Cover:

- profile rules
- scoring
- normalization
- title matching
- salary normalization
- location policies
- state transitions
- deduplication
- prompt-response validation

## Adapter contract tests

Every job source adapter must pass shared tests:

```text
initializes
returns canonical references
handles empty result
handles malformed data
honors timeout
honors rate limits
normalizes errors
does not leak credentials
```

## AI contract tests

Normal CI must not require paid AI calls.

Use `FixtureProvider` to test:

```text
valid response
invalid JSON
timeout
rate limit
provider unavailable
hallucinated evidence ID
unknown skill
```

Any returned evidence ID must resolve to an actual profile entity.

## Integration tests

Exercise:

```text
ingest -> normalize -> dedupe -> evaluate -> review
```

against temporary PostgreSQL.

## E2E tests

Playwright scenarios:

```text
create profile
import sample job
evaluate job
shortlist job
prepare application
mark applied
schedule interview
```

## Container smoke tests

Validate Docker Compose in CI.

Where practical, also run scheduled/rootless Linux Podman compatibility tests.

---

# 28. CI/CD

Use GitHub Actions initially.

## Pull requests

- [ ] backend lint
- [ ] backend type check
- [ ] backend tests
- [ ] frontend lint
- [ ] frontend type check
- [ ] frontend tests
- [ ] frontend build
- [ ] backend image build
- [ ] frontend image build
- [ ] Compose validation
- [ ] migration validation

## Main/tags

- [ ] all PR checks
- [ ] build OCI images
- [ ] vulnerability scan
- [ ] SBOM generation
- [ ] publish images if configured
- [ ] tagged release notes

Potential registry:

```text
ghcr.io/<owner>/careerflow-api
ghcr.io/<owner>/careerflow-web
```

---

# 29. Public Demo Requirements

The repository should demonstrate engineering quality, not just AI API usage.

Include:

- [ ] architecture diagram
- [ ] ADRs
- [ ] multi-profile demo data
- [ ] source adapter model
- [ ] LLM provider model
- [ ] deterministic + semantic evaluation
- [ ] evidence-backed generation
- [ ] comprehensive tests
- [ ] container portability
- [ ] security/privacy documentation
- [ ] one-command startup
- [ ] screenshots or short GIF/video
- [ ] documented architectural tradeoffs

A reviewer should be able to clone and run:

```bash
podman compose up -d --build
```

or:

```bash
docker compose up -d --build
```

and immediately see fictional sample data.

---

# 30. Demo Profiles

Seed at least two clearly different fictional users.

## Profile A

```text
Jordan Lee
Principal Software / AI Engineer
15 years software engineering
6 years AI/ML
Python
C#
Cloud architecture
Distributed systems
LLM applications
```

## Profile B

```text
Morgan Rivera
Senior Data Scientist
8 years analytics/data science
Python
SQL
Experimentation
Forecasting
Machine learning
Visualization
```

Seed jobs that score differently for these two profiles. The demo must visibly prove that scoring is profile-specific.

---

# 31. Implementation Phases

## Phase 0 — Repository Foundation

**Goal:** Empty but production-shaped application with engineering guardrails.

- [ ] Initialize repository.
- [ ] Choose MIT or Apache-2.0 license.
- [ ] Add README.
- [ ] Add SECURITY.md.
- [ ] Add CONTRIBUTING.md.
- [ ] Create FastAPI backend.
- [ ] Create React/TypeScript/Vite frontend.
- [ ] Add PostgreSQL.
- [ ] Add SQLAlchemy/Alembic.
- [ ] Create `compose.yaml`.
- [ ] Verify Podman startup.
- [ ] Verify Docker Desktop startup.
- [ ] Add liveness/readiness endpoints.
- [ ] Add backend tests.
- [ ] Add frontend tests.
- [ ] Add linting/type checking.
- [ ] Add GitHub Actions.
- [ ] Add `.env.example`.
- [ ] Require no external secrets just to start.

### Acceptance criteria

Both:

```bash
podman compose up -d --build
```

and:

```bash
docker compose up -d --build
```

start a healthy application from a clean clone.

---

## Phase 1 — Profile Core

**Goal:** Generic, reusable profile model.

- [ ] Profile CRUD.
- [ ] Contact information.
- [ ] Experience.
- [ ] Achievement inventory.
- [ ] Skills and aliases.
- [ ] Education.
- [ ] Portfolio items.
- [ ] Role families.
- [ ] Search preferences.
- [ ] Scoring preferences.
- [ ] Profile UI.
- [ ] Versioned JSON import/export.
- [ ] Fictional demo profiles.
- [ ] Cross-profile isolation tests.

### Acceptance criteria

Two profiles can coexist with entirely different careers, targets, preferences, and scoring rules. No personal assumptions exist in code.

---

## Phase 2 — Manual Job Inbox

**Goal:** End-to-end job workflow before external integrations.

- [ ] Canonical Job model.
- [ ] JobSourceRecord.
- [ ] Manual description import.
- [ ] Optional URL capture.
- [ ] Fixture JSON import.
- [ ] Job inbox UI.
- [ ] Job detail page.
- [ ] Workflow state machine.
- [ ] Shortlist/reject/save actions.
- [ ] Status history.
- [ ] Raw snapshot retention.

### Acceptance criteria

A user can paste a job description, inspect it, and move it through the review workflow.

---

## Phase 3 — Deterministic Evaluation

**Goal:** Useful product even with AI disabled.

- [ ] Title matching.
- [ ] Role-family matching.
- [ ] Location rules.
- [ ] Remote rules.
- [ ] Compensation rules.
- [ ] Employment-type rules.
- [ ] Keyword/skill matching.
- [ ] Hard blockers.
- [ ] Dimension scores.
- [ ] Profile-specific weights.
- [ ] Evaluation UI.

### Acceptance criteria

The same job receives meaningfully different evaluations for two profiles.

---

## Phase 4 — AI Provider Layer

**Goal:** Add AI without vendor lock-in.

- [ ] Define `LlmProvider`.
- [ ] Define task-specific AI services.
- [ ] Structured response validation.
- [ ] Prompt registry/versioning.
- [ ] `DisabledProvider`.
- [ ] `FixtureProvider`.
- [ ] One hosted provider.
- [ ] Ollama/OpenAI-compatible provider.
- [ ] Provider configuration UI.
- [ ] Timeout/retry policy.
- [ ] Usage metadata when available.

### Acceptance criteria

Providers can be changed without changing domain code. All non-AI workflows still function with AI disabled.

---

## Phase 5 — AI Job Analysis

- [ ] Extract structured requirements.
- [ ] Separate required/preferred qualifications.
- [ ] Detect architecture expectations.
- [ ] Detect leadership expectations.
- [ ] Detect management expectations.
- [ ] Infer likely seniority.
- [ ] Identify transferable skills.
- [ ] Link claims to profile evidence.
- [ ] Identify unsupported claims.
- [ ] Produce readable fit explanation.
- [ ] Persist evaluation version.
- [ ] Add manual reevaluate action.

### Acceptance criteria

Every significant positive claim points to profile evidence or is explicitly marked inference/unverified.

---

## Phase 6 — Deduplication

- [ ] Exact fingerprinting.
- [ ] Probable matching.
- [ ] Multiple-source preservation.
- [ ] Duplicate-review UI.
- [ ] Merge/unmerge.
- [ ] Tests.

---

## Phase 7 — Job Source Plugin Framework

- [ ] Finalize adapter contract.
- [ ] Source registry.
- [ ] Per-source configuration.
- [ ] Capability metadata.
- [ ] Rate limiting.
- [ ] Retry/backoff.
- [ ] Run history.
- [ ] Health state.
- [ ] Fixture adapter.
- [ ] RSS adapter.
- [ ] Generic JSON adapter.
- [ ] One ATS adapter.
- [ ] Shared adapter contract tests.

### Acceptance criteria

A new source can be added without modifying evaluation/workflow domain code.

---

## Phase 8 — Scheduled Discovery

- [ ] Search definitions.
- [ ] Persisted schedules.
- [ ] Worker leases.
- [ ] Scheduled searches.
- [ ] Search run history.
- [ ] Source error visibility.
- [ ] `Run Now` action.
- [ ] Per-profile schedules.
- [ ] Job expiration refresh.

---

## Phase 9 — Application Preparation

- [ ] Resume variants.
- [ ] Application package model.
- [ ] Recommend resume variant.
- [ ] Recommend accomplishments.
- [ ] Recommend skill ordering.
- [ ] Suggest summary changes.
- [ ] Cover-letter talking points.
- [ ] Recruiter outreach draft.
- [ ] Missing-evidence warnings.
- [ ] Approval UI.

Do not automatically rewrite verified career facts.

---

## Phase 10 — Application Tracking

- [ ] Application records.
- [ ] Applied date.
- [ ] Associated resume artifact.
- [ ] Contacts.
- [ ] Notes.
- [ ] Follow-ups.
- [ ] Kanban/pipeline view.
- [ ] Conversion metrics.

Useful metrics:

```text
jobs reviewed
jobs shortlisted
applications submitted
screens
interviews
final interviews
offers
response rate
time to response
```

---

## Phase 11 — Interview Assistant

- [ ] Interview records.
- [ ] Job-specific prep.
- [ ] Relevant-achievement suggestions.
- [ ] Technical topic suggestions.
- [ ] Architecture topic suggestions.
- [ ] Questions to ask.
- [ ] Post-interview notes.
- [ ] Next-step tracking.

---

## Phase 12 — Email Integration

Capabilities:

```text
import job alerts
identify recruiter messages
associate messages with applications
detect interview requests
detect rejection/offer messages
draft replies
```

- [ ] Define `EmailProvider`.
- [ ] Add OAuth implementation.
- [ ] Match messages to applications.
- [ ] Never auto-send by default.
- [ ] Store external message IDs rather than unnecessary mailbox copies.

---

## Phase 13 — Calendar Integration

Capabilities:

```text
import interviews
associate events with applications
show upcoming interviews
create prep reminders
```

- [ ] Define `CalendarProvider`.
- [ ] Match calendar events.
- [ ] Prevent duplicates.
- [ ] Require approval before creating/updating external events.

---

## Phase 14 — Artifact Generation

- [ ] `ArtifactRenderer` interface.
- [ ] Markdown renderer.
- [ ] HTML renderer.
- [ ] DOCX renderer.
- [ ] PDF renderer.
- [ ] Artifact versioning.
- [ ] Generation-input retention.
- [ ] Download support.
- [ ] Public/redacted render mode.

---

## Phase 15 — Public Demo Polish

- [ ] Demo reset/seed command.
- [ ] Architecture documentation.
- [ ] ADRs.
- [ ] Screenshots/GIF/video.
- [ ] API documentation.
- [ ] "How to write a job source adapter" guide.
- [ ] "How to write an LLM provider" guide.
- [ ] Scoring explanation.
- [ ] Privacy/security documentation.
- [ ] Podman setup guide.
- [ ] Docker Desktop setup guide.
- [ ] `v1.0.0` release.

---

# 32. Codex Work Order

Have Codex build **vertical slices**, not all persistence models first.

## Milestone A

```text
Repository
Containers
Database
API
Frontend shell
Health checks
CI
```

## Milestone B

```text
Profile
Experience
Achievements
Skills
Role families
Profile UI
```

## Milestone C

```text
Manual job import
Job inbox
Job detail
Workflow states
```

## Milestone D

```text
Deterministic evaluation
Multi-profile scoring
Evaluation UI
```

The project is already demonstrable here.

## Milestone E

```text
LLM abstraction
Requirement extraction
Semantic matching
Evidence linking
```

## Milestone F

```text
Source adapters
Scheduled discovery
Deduplication
```

## Milestone G

```text
Resume/application preparation
Application pipeline
Interview tracking
```

Do not start email/calendar integrations until the core pipeline is stable.

---

# 33. Coding Rules for Codex

## Architecture rules

- [ ] Domain code must not depend on FastAPI.
- [ ] Domain code must not depend on a specific LLM SDK.
- [ ] Domain code must not depend on a specific job source.
- [ ] ORM entities must not be returned directly from API routes.
- [ ] External systems must live behind interfaces/adapters.
- [ ] Profile-scoped operations require explicit profile context.
- [ ] Workflow state changes go through domain/application services.
- [ ] Generated outputs retain provenance/version metadata.
- [ ] No personal profile values in source code.

## For every work item

1. inspect the existing architecture
2. implement the smallest coherent vertical slice
3. add/update tests
4. run relevant tests
5. run lint/type checks
6. update documentation
7. verify images still build
8. verify Compose still validates
9. summarize design decisions/tradeoffs

## Avoid

- giant service classes
- business logic in FastAPI route functions
- business logic in React components
- raw SQL scattered throughout the application
- prompt strings embedded in domain services
- provider SDK objects leaking into domain models
- source-specific fields in canonical Job models
- opaque fit scores with no explanation
- silently swallowed worker failures

---

# 34. Definition of Done

A work item is complete only when:

- [ ] behavior is implemented
- [ ] tests exist
- [ ] lint passes
- [ ] type checks pass
- [ ] migrations are included where necessary
- [ ] API changes are documented
- [ ] user-facing behavior is documented
- [ ] errors are handled
- [ ] logs are useful
- [ ] profile isolation is considered
- [ ] demo data is considered
- [ ] Podman compatibility is preserved
- [ ] Docker compatibility is preserved

---

# 35. Initial GitHub Issue Backlog

## Epic — Foundation

- [ ] Initialize monorepo.
- [ ] FastAPI backend.
- [ ] React/Vite frontend.
- [ ] PostgreSQL + migrations.
- [ ] Compose deployment.
- [ ] Podman smoke test.
- [ ] Docker Compose smoke test.
- [ ] GitHub Actions CI.
- [ ] Health/readiness endpoints.

## Epic — Profiles

- [ ] Profile domain model.
- [ ] Career experience.
- [ ] Achievement inventory.
- [ ] Skills and aliases.
- [ ] Education.
- [ ] Portfolio items.
- [ ] Role families.
- [ ] Search preferences.
- [ ] Scoring configuration.
- [ ] JSON import/export.
- [ ] Demo profiles.

## Epic — Jobs

- [ ] Canonical job model.
- [ ] Manual import.
- [ ] Source records.
- [ ] Job inbox.
- [ ] Job detail.
- [ ] Workflow state machine.
- [ ] Status history.
- [ ] Raw snapshot retention.

## Epic — Evaluation

- [ ] Deterministic filter engine.
- [ ] Skill matching.
- [ ] Salary normalization.
- [ ] Location normalization.
- [ ] Multi-dimensional scoring.
- [ ] Fit explanation model.
- [ ] Profile-specific evaluation.
- [ ] Evaluation history.

## Epic — AI

- [ ] LLM provider interface.
- [ ] Disabled provider.
- [ ] Fixture provider.
- [ ] Hosted provider.
- [ ] Local/OpenAI-compatible provider.
- [ ] Prompt registry.
- [ ] Structured output validation.
- [ ] Requirement extraction.
- [ ] Transferable skill analysis.
- [ ] Evidence-backed matching.

## Epic — Discovery

- [ ] Job source interface.
- [ ] Adapter registry.
- [ ] Fixture adapter.
- [ ] RSS adapter.
- [ ] Generic JSON adapter.
- [ ] ATS adapter.
- [ ] Search definitions.
- [ ] Scheduler.
- [ ] Source run history.
- [ ] Rate limiting.
- [ ] Deduplication.

## Epic — Applications

- [ ] Resume variants.
- [ ] Application packages.
- [ ] Tailoring recommendations.
- [ ] Application records.
- [ ] Contacts.
- [ ] Follow-ups.
- [ ] Pipeline/Kanban.

## Epic — Interviews

- [ ] Interview records.
- [ ] Interview prep generator.
- [ ] Achievement recommendations.
- [ ] Interview notes.
- [ ] Upcoming interview dashboard.

---

# 36. First Codex Prompt

Use this for the first implementation pass:

```text
Implement Phase 0 of the CareerFlow implementation plan.

Goals:
- initialize the monorepo
- create a Python FastAPI backend
- create a React + TypeScript + Vite frontend
- add PostgreSQL using SQLAlchemy and Alembic
- create a portable Compose deployment
- support both `podman compose` and `docker compose`
- add liveness/readiness endpoints
- add backend/frontend test scaffolding
- add linting and type checks
- create GitHub Actions CI
- include a .env.example
- add initial architecture documentation

Constraints:
- use the current Compose Specification
- do not include engine-specific assumptions in the base compose.yaml
- do not require external API keys to start
- do not use privileged containers
- do not mount a container-engine socket
- prefer named volumes
- keep domain/application/infrastructure boundaries explicit
- make API and worker capable of sharing a backend image later
- use fictional/demo data only
- do not begin profile/job features beyond scaffolding unless required to
  demonstrate the architecture

Before completing:
- run unit tests
- run linters
- run type checks
- build all container images
- validate Compose configuration
- start the stack and verify health endpoints
- document commands for both Podman and Docker
- report any Podman/Docker compatibility differences discovered
```

---

# 37. Second Codex Prompt

```text
Implement Phase 1: Profile Core.

Create a generic multi-profile domain model supporting:
- profile
- contact information
- experience
- achievements
- skills and aliases
- education
- portfolio entries
- target role families
- search preferences
- scoring preferences

Requirements:
- no assumptions about a specific person's career
- all profile-scoped data must be isolated by profile_id
- create REST APIs and frontend editing screens
- support profile export/import as versioned JSON
- seed at least two fictional demo profiles with meaningfully different careers
- add tests proving one profile cannot accidentally retrieve another profile's
  scoped records
- preserve clean domain/application/infrastructure boundaries
- update architecture and API documentation
- run all tests and container smoke tests before completion
```

---

# 38. Third Codex Prompt

```text
Implement Phases 2 and 3 as one vertical slice:

- canonical job model
- manual job import
- fixture import
- job inbox
- job detail page
- status workflow/history
- deterministic job evaluation
- profile-specific scoring

The same job must be capable of producing different evaluations for different
profiles.

The evaluation must expose dimensions rather than only an overall score.

Do not add an LLM dependency yet.

Seed fictional jobs demonstrating:
- strong match for Profile A / weak match for Profile B
- weak match for Profile A / strong match for Profile B
- blocked job because of a hard preference
- transferable-but-not-exact skill match where deterministic rules can detect it

Add E2E tests for:
profile -> import job -> evaluate -> shortlist/reject.
```

---

# 39. Initial ADRs

Create these Architecture Decision Records as relevant decisions are implemented:

```text
ADR-001 Monorepo
ADR-002 Python/FastAPI backend
ADR-003 React/TypeScript frontend
ADR-004 PostgreSQL persistence
ADR-005 Profile-scoped domain model
ADR-006 Source adapter architecture
ADR-007 LLM provider abstraction
ADR-008 Human-in-the-loop external actions
ADR-009 Evidence-backed generated claims
ADR-010 Compose-based Podman/Docker portability
ADR-011 Deterministic plus semantic evaluation
ADR-012 Versioned prompts and evaluations
```

Each ADR should contain:

```text
Context
Decision
Alternatives considered
Consequences
Status
```

---

# 40. Future Enhancements

These should not block MVP work.

- [ ] Browser extension: "Save to CareerFlow".
- [ ] Mobile-friendly review UI.
- [ ] Gmail integration.
- [ ] Outlook integration.
- [ ] Google Calendar integration.
- [ ] Microsoft Calendar integration.
- [ ] GitHub portfolio analysis.
- [ ] Resume DOCX/PDF rendering.
- [ ] Local embeddings.
- [ ] pgvector semantic retrieval.
- [ ] Company research enrichment.
- [ ] Geographic compensation normalization.
- [ ] Contact/recruiter CRM.
- [ ] Networking follow-up tracking.
- [ ] Referral tracking.
- [ ] Skill-gap trend reports.
- [ ] Common-skill analysis across target jobs.
- [ ] Application conversion analytics.
- [ ] Interview question library.
- [ ] MCP server.
- [ ] CLI.
- [ ] API tokens.
- [ ] Webhooks.
- [ ] Community adapter/plugin system.

---

# 41. Future MCP Surface

This project is a natural candidate for an MCP server.

Possible tools:

```text
careerflow.list_profiles
careerflow.list_new_jobs
careerflow.get_job
careerflow.evaluate_job
careerflow.shortlist_job
careerflow.reject_job
careerflow.list_applications
careerflow.get_application
careerflow.prepare_application
careerflow.get_upcoming_interviews
careerflow.prepare_interview
careerflow.get_search_metrics
```

Keep external-changing actions gated by confirmation or omit them initially.

This allows the public project to demonstrate both conventional application architecture and modern agent/tool architecture.

---

# 42. Public v1 Success Criteria

A stranger should be able to:

1. clone the repository
2. run it with Podman or Docker Desktop
3. open the application
4. switch between two fictional profiles
5. view sample/discovered jobs
6. see the same jobs evaluated differently for each profile
7. understand why each evaluation was produced
8. manually import another job
9. evaluate it
10. shortlist it
11. prepare an application package
12. move it through the application pipeline
13. inspect the architecture documentation
14. understand how to add a job source
15. understand how to add an LLM provider

At that point the repository demonstrates:

```text
domain modeling
clean architecture
profile isolation
AI abstraction
provider design
data normalization
workflow/state-machine design
background processing
human-in-the-loop AI
evidence-backed generation
container deployment
testing
CI/CD
observability
security
extensibility
```

That is substantially more valuable as a public demo than a simple AI-powered job tracker.

---

# 43. Immediate Next Step

Start with **Phase 0 only**.

Do not ask Codex to implement the entire roadmap in one pass.

The first checkpoint should be:

```text
A clean repository that starts under both Podman and Docker,
has passing CI/tests, exposes healthy frontend/backend services,
and establishes architecture boundaries that later phases can extend.
```

After Phase 0 is stable, implement the Profile Core, then continue with vertical slices.
