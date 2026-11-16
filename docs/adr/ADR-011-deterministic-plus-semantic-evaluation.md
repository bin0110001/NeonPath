# ADR-011: Deterministic plus semantic evaluation

## Status

Accepted

## Context

Hard preferences (remote required, salary floor, excluded companies) must be reliable, explainable and free. Judging transferable skills, architecture and leadership scope needs language understanding.

## Decision

Evaluation has two layers. The deterministic evaluator is always run and needs no LLM. The semantic layer is optional: it may only score dimensions rules cannot (architecture, leadership, domain), add evidence-linked claims and gaps, and its output is merged onto the deterministic result. Deterministic blockers always win: they remain and cap the overall score. With AI off, the stored evaluation is exactly the deterministic one. Each run appends a row carrying evaluator version, provider, model and prompt version.

## Alternatives considered

LLM-only scoring (opaque, costly, not reproducible); letting the model veto blockers (unsafe).

## Consequences

The product is fully usable with AI disabled, and AI can only add information, never silently override a hard rule.
