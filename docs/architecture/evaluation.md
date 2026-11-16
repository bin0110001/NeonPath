# Evaluation and workflow

## Per-profile workflow (`domain/jobs/workflow.py`)

A job has a processing lifecycle (`jobs.status`, ending at `READY_FOR_REVIEW`). What a *profile* does with it is separate: `profile_jobs` holds one row per (profile, job); no row means `READY_FOR_REVIEW`. Allowed transitions live in `ALLOWED_TRANSITIONS`; anything else (including same-status) returns HTTP 409 and writes nothing. Every successful transition appends exactly one `job_status_history` row (profile, actor, reason). History is never updated or deleted.

API (all take `profile_id`): `POST /api/v1/jobs/{id}/shortlist|save|reject|archive`, `GET /jobs/{id}/workflow?profile_id=`, `GET /jobs/{id}/status-history?profile_id=`.

## Deterministic evaluator (`domain/evaluations/service.py`, `deterministic-v2.0`)

Rule-based, no LLM, no framework imports. Each dimension is derived from its own signals only.

- Scored: role, seniority, technical (skills + aliases, word-boundary), location (allowed places + remote policy), compensation, employment, interest (preferred company/industry).
- Not scored, reported under `unknowns`: architecture, leadership, domain (need semantic evaluation); and any dimension whose data is missing (e.g. no salary, currency mismatch, unknown period).
- Weights come from the profile's scoring preferences, restricted to scored dimensions and renormalised. `confidence` is the share of configured weight that had a signal.
- Hard blockers: excluded company/industry, location outside allowed places (unless relocation is allowed), remote REQUIRED/BLOCK mismatch, salary below the minimum, employment type not allowed. Any blocker caps `overall_score` at 0.2.
- Salary is annualised (hour 2080, day 260, week 52, month 12). Currencies are never converted.
- Transferable matches: a catalog skill mentioned in the job, not held by the profile, sharing a category with a held skill.

Evaluations are append-only (`job_evaluations`); each run stores `evaluator_version`.
