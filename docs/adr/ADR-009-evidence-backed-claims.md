# ADR-009: Evidence-backed generated claims

## Status

Accepted

## Context

An AI assessment that flatters the candidate with invented experience is worse than none. Every meaningful claim has to trace back to something the profile actually contains.

## Decision

The semantic evaluator is given a list of real profile records with stable ids (`experience:`, `achievement:`, `skill:`, `education:`, `portfolio:`). Each positive claim (strength or transferable match) states a `basis`: `evidence` (cites ids), `inference` (reasoned beyond the records, shown as such) or `unverified`. The application validates every response: a claim marked `evidence` that cites no ids, or any id that does not resolve to a record of that profile, is downgraded to `unverified` and its ids are dropped. Claims are stored with the evaluation (`claims_json`) and shown in the UI with their marker.

## Alternatives considered

Trusting the model's own labels (hallucinated ids pass); dropping unsupported claims silently (hides what the model said); requiring evidence for everything (blocks legitimate transferable-skill inference).

## Consequences

Users can always tell recorded fact from inference. Evidence validation is unit-tested with a fixture provider that returns hallucinated ids.
