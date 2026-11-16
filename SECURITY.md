# Security policy

Please do not open public issues for vulnerabilities. Report them privately to the repository maintainer with a description, reproduction steps, impact, and suggested mitigation.

CareerFlow is designed to keep human approval before external actions. Never commit real resumes, credentials, access tokens, or personal contact information. The default Compose password is development-only and must be replaced for any exposed deployment.

## Logging policy

Logs are one JSON object per line on stdout. Every request line carries a `request_id` (an inbound `X-Request-ID` is accepted only if it is 1-64 characters of `[A-Za-z0-9._-]`, otherwise one is generated and returned in the response header); `profile_id` and `job_id` are added when present in the URL, and workers will add `task_id` and `source_adapter`.

A redaction filter runs on the log handler, so library output is covered too. It removes the database password, every value listed in `LOG_REDACT_VALUES`, bearer/basic tokens, `key=value` style secrets (`password`, `token`, `api_key`, ...), credentials embedded in URLs and e-mail addresses. Do not log resume text or free-form notes; log ids instead. Redaction is a safety net, not a licence to log secrets.

## Demo mode

`DEMO_MODE=true` shows a banner, disables every external write integration (code must call `ensure_external_writes_allowed()` before sending mail or creating calendar events) and permits `python -m careerflow.demo reset`, which deletes all data and reseeds the fictional demo state. Reset refuses to run otherwise. Never enable demo mode on a database holding real data.
