# ADR-003: React and TypeScript frontend

## Status

Accepted

## Context

CareerFlow needs a responsive application UI without coupling its domain model to a UI library.

## Decision

Use React, TypeScript, and Vite.

## Alternatives considered

Vue; server-rendered templates; a component-library-led architecture.

## Consequences

The UI has fast development/build tooling and can adopt routing, query, and component libraries without changing domain boundaries.
