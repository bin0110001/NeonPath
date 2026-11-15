# ADR-013: Explicit Alembic baseline

## Status

Accepted

## Context

Revisions 0001-0004 called `Base.metadata.create_all`/`drop_all`, so each revision depended on the *current* ORM models. Column changes never reached existing databases and old revisions were not reproducible.

## Decision

Replace revisions 0001-0004 with a single explicit baseline, `0001_baseline`, generated with `alembic revision --autogenerate` and using only `op.create_table`/`op.create_index`. Later schema changes are new incremental revisions; applied revisions are never edited.

Existing dev databases created by the old revisions must be reset (`docker compose down -v`, or `podman compose down -v`) because their `alembic_version` row references removed revisions. No production data exists yet.

## Alternatives considered

Keep the old revisions and add a fix-up revision (keeps `create_all` hidden dependency); stamp existing databases at baseline (extra tooling for no production users).

## Consequences

`alembic check` (drift check) and an upgrade/downgrade/upgrade CI job guard every model change.
