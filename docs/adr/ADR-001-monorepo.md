# ADR-001: Monorepo

## Status

Accepted

## Context

CareerFlow needs a web client, API, workers, deployment assets, and shared documentation that evolve together.

## Decision

Keep these components in one repository with `backend/`, `frontend/`, `docs/`, and top-level Compose files.

## Alternatives considered

Separate client and server repositories; a single full-stack framework.

## Consequences

Changes are easier to coordinate and run locally. CI must explicitly validate both application stacks.
