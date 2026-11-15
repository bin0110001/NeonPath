# ADR-008: Human-in-the-loop for external actions

## Status

Accepted

## Context

The product automates discovery, organisation, analysis and preparation. The costly mistakes are in the other direction: sending a message the user did not approve, submitting an application, or publishing invented claims. AI output is probabilistic and must never be able to act on the world by itself.

## Decision

CareerFlow *prepares*; the person *acts*. Concretely:

- **No send path exists.** The `EmailProvider` port has no send or draft-in-mailbox method, the only mailbox scope requested is `gmail.readonly`, and a test scans the code base for sending APIs. Reply and outreach drafts are stored locally and labelled as drafts to copy and send manually.
- **Writes need approval.** The only code that writes to an external calendar is `CalendarService.approve`, which acts on a stored request the user explicitly approved. Proposing a change writes nothing. Write-capable calendar access is a separate, opt-in OAuth scope.
- **AI proposes, people approve.** Application preparation returns a read-only proposal; nothing is stored until the user approves it (`POST .../prepare/approve`). Applications are never marked submitted automatically: workflow transitions are user-initiated and validated.
- **Evidence over assertion.** Generated claims cite profile records or are flagged `inference` / `unverified` (ADR-009). Verified career facts are never rewritten.
- **Demo mode** disables real integrations and external writes entirely (ADR-014).

## Alternatives considered

Auto-send with an "undo" window (an undo cannot unsend an email); a global "autonomous mode" switch (one setting away from the failure we want to prevent); trusting the model to ask before acting (not a control).

## Consequences

Some flows need an extra click. In exchange, the question "can CareerFlow do something I did not approve?" has a structural answer, and tests can prove it (`test_no_code_path_sends_email`, `test_nothing_is_written_until_the_user_approves`, `test_nothing_is_persisted_until_the_user_approves`).
