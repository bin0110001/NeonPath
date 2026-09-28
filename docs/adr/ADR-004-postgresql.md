# ADR-004: PostgreSQL persistence

## Status

Accepted

## Context

The platform needs reliable transactional persistence for profiles, jobs, workflow history, and scheduled work.

## Decision

Use PostgreSQL with SQLAlchemy and Alembic migrations. Do not add a vector database initially.

## Alternatives considered

SQLite; a document database; PostgreSQL plus a separate vector database from day one.

## Consequences

The application has a production-capable relational foundation. Semantic retrieval can later use optional pgvector if justified.
