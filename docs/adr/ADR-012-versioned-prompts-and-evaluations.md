# ADR-012: Versioned prompts and evaluations

## Status

Accepted

## Context

Generated results change when prompts or models change. Silently overwriting them would hide regressions and make results irreproducible.

## Decision

Prompts are files: `application/ai/prompts/<key>/v<N>/{system,user}.txt` with `$placeholders`; code never embeds prompt text. The registry returns the highest version unless one is pinned. Every persisted AI result stores provider, model, prompt key and version (`StructuredResult`). Invalid structured output is retried once with a repair instruction and then rejected with the raw text and errors preserved; it is never stored as valid. Evaluations are append-only rows tagged with `evaluator_version`; a new prompt or model produces a new row.

## Alternatives considered

Prompts as Python strings (versioning by git only, hard to review); overwriting the latest evaluation (loses history).

## Consequences

Changing a prompt means adding a new `vN` directory; old results remain attributable to the version that produced them.
