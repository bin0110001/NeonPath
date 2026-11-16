# ADR-005: Profile-scoped domain model

## Status

Accepted

## Context

One installation holds several independent career profiles (for example a data scientist and a software architect). Their evidence, preferences, evaluations, applications and documents must never mix, and no person's details may be hard-coded anywhere. A single missing filter that leaks one profile's data into another would be both a privacy and a correctness failure.

## Decision

Every profile-owned record carries an explicit `profile_id`, or is reachable only through a profile-owned parent. Application services take the profile as an argument and resolve every record id *through* that profile: `ProfileService.get_profile_item(model, profile_id, item_id)` treats a record that exists but belongs to another profile exactly like a missing one (HTTP 404, nothing changes). Cross-profile *links* are rejected in the service layer (an achievement cannot reference another profile's experience, a resume variant cannot select another profile's achievements, a contact cannot be attached to another profile's application).

Jobs, skills (a shared catalogue) and resume templates are installation-wide; everything a profile *does* with them (workflow status, evaluations, applications, search definitions, packages, artifacts) is profile-scoped. Workflow state is per profile (`profile_jobs`), so shortlisting a job for one profile never affects another.

Tests enforce the rule: a parametrised isolation test per record type, API-level 404 checks for every nested endpoint, and per-profile queries for dashboards, pipelines and metrics.

## Alternatives considered

Row-level security in PostgreSQL (strong, but hard to test portably and invisible to application code); one database or schema per profile (heavy, complicates shared jobs); a global "current profile" in request state (implicit context is easy to get wrong in workers and scripts).

## Consequences

Services need an explicit profile argument and every new profile-owned table needs an isolation test. The benefit is that leakage is impossible to introduce by omission in a query that goes through the shared lookup helpers, and the demo can show two very different profiles side by side.
