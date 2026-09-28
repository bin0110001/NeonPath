# ADR-010: Compose-based Podman and Docker portability

## Status

Accepted

## Context

The project must run on Podman and Docker Desktop.

## Decision

Use the Compose Specification without an engine-specific `version` field, named volumes, standard images, and no socket mounts or privileged containers.

## Alternatives considered

Engine-specific deployment manifests; Kubernetes-only setup.

## Consequences

The stack has a simple local startup path. Developers must use a Compose implementation that supports `depends_on.condition` health dependencies.
