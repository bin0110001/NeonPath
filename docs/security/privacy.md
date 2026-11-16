# Privacy and security

CareerFlow is built to be self-hosted by one person (or household) and to be safe to show publicly with fictional data. To report a vulnerability see [SECURITY.md](../../SECURITY.md).

## What is stored, and where

| Data | Stored | Notes |
|---|---|---|
| Profiles, experience, achievements, skills, preferences | PostgreSQL | Contact details are optional per profile and kept in a separate table |
| Jobs and raw source payloads | PostgreSQL | Raw payloads are pruned after `RAW_PAYLOAD_RETENTION_DAYS` (default 90; `0` keeps them). The canonical job text is never pruned, so evaluations stay reproducible after a listing disappears |
| Mailbox | **ids and routing facts only** | Message id, thread id, sender domain, classification, time. Subjects, snippets and bodies are used in memory to classify and then discarded |
| OAuth tokens | PostgreSQL, **encrypted** (Fernet) | Key in `INTEGRATION_ENCRYPTION_KEY`; never returned by any endpoint; never logged |
| AI API key | Environment only | `AI_API_KEY`; the settings page only shows whether it is set |
| Generated documents | PostgreSQL | Each version keeps its generation inputs so it can be reproduced; "public copy" omits contact details |

No analytics, telemetry or third-party calls happen unless you configure an integration. AI features send job text and the profile *evidence you selected* to the provider you chose; use a local provider (Ollama) to keep everything on your machine.

## Controls that protect you

- **Profile isolation**: every profile-owned record is reached through its profile; another profile's id returns 404 ([ADR-005](../adr/ADR-005-profile-scoped-domain-model.md)).
- **Human approval**: nothing is sent or written externally without an explicit approval; there is no email-sending code at all ([ADR-008](../adr/ADR-008-human-in-the-loop-external-actions.md)). Mailbox access uses the read-only scope; calendar write access is a separate opt-in.
- **Evidence-backed AI output**: generated claims cite your records or are flagged unverified ([ADR-009](../adr/ADR-009-evidence-backed-claims.md)). AI is optional and off by default.
- **Secrets hygiene**: secrets never go in the database or in URLs (`*_env` config keys name an environment variable). Validation errors never echo submitted values.
- **Logging**: JSON logs with a per-request id. A redaction filter removes configured secret values, the database password, bearer/basic tokens, `key=value` style secrets, credentials in URLs and e-mail addresses. Do not log resumes or free-form notes. Redaction is a safety net, not a licence to log secrets. Extra values to redact: `LOG_REDACT_VALUES`.
- **Safe rendering**: the HTML renderer escapes all profile text; Markdown neutralises raw HTML; downloads are served as attachments with `X-Content-Type-Options: nosniff`.
- **XML**: RSS/Atom feeds are parsed with `defusedxml` (no entity expansion).
- **Containers**: no privileged containers, no host networking, no container-engine socket; the worker and API share one unprivileged image.

## Demo mode

`DEMO_MODE=true` (the default in `.env.example`) shows a banner, uses only fictional seed data, disables connecting real mailboxes/calendars and any external write, and allows `python -m careerflow.demo reset`. Never enable it on a database that holds real data: reset deletes everything.

## Your responsibilities

- `AUTH_MODE=local` has **no login**. Run CareerFlow on localhost or behind a reverse proxy that authenticates users; do not expose it directly to the internet ([ADR-014](../adr/ADR-014-local-auth-and-demo-mode.md)).
- Replace the development database password before any shared deployment and keep `.env` out of version control.
- Back up the database and keep `INTEGRATION_ENCRYPTION_KEY` with it: without the key stored tokens cannot be decrypted (reconnect the accounts).
- Only point source adapters at services whose terms permit it, and set a sensible rate limit.

## Known limitations

- Mail/calendar and hosted-AI integrations were verified against recorded API responses, not live services.
- PDF output uses built-in Latin-1 fonts (other characters print as `?`); use DOCX/HTML/Markdown for non-Latin text.
- Keyword/skill matching is word-based and does not understand synonyms beyond the aliases you define.
