# ADR-002: Python and FastAPI backend

## Status

Accepted

## Context

The product combines HTTP APIs, document-oriented automation, and data processing.

## Decision

Use Python 3.13+, FastAPI, and Pydantic at the HTTP boundary. Domain code remains independent of FastAPI.

## Alternatives considered

Node.js API; Django; a serverless-only design.

## Consequences

The API is typed and lightweight while future AI/document tooling can remain in Python. API schemas must remain distinct from ORM entities.
