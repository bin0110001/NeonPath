# ADR-014: Local auth mode and demo mode

## Status

Accepted

## Context

The MVP must start with no external secrets and no identity provider, yet the project is also a public demo that must never hold private data or write to outside systems.

## Decision

`AUTH_MODE=local` assumes a single-user, self-hosted installation: the user picks a profile, there is no login. Authentication identity and career profile stay separate concepts so a later `AuthProvider` (local password, OIDC, reverse proxy) can let one account own several profiles. `DEMO_MODE=true` marks the installation as a demo: UI banner, external writes blocked by one shared guard, and a reset command that restores the seeded state.

## Alternatives considered

Building login first (blocks the MVP); a separate demo build (two code paths to maintain).

## Consequences

Local mode must not be exposed to untrusted networks without a reverse proxy providing authentication. Integrations must route external writes through the guard.
