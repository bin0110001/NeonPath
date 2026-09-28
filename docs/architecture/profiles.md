# Profile Core

All career data is scoped through an explicit `profile_id`; no profile-specific values are embedded in code. The Profile Core stores identity, optional contact details, experience, reusable achievements, a shared skill catalog with aliases, profile skill evidence, education, portfolio entries, role families, search preferences, and scoring weights.

The API begins at `/api/v1/profiles`. Export/import uses a versioned JSON envelope (`schema_version: 1`) for the currently supported profile, contact, experience, and achievement records. Every achievement optionally links to an experience, and the application service rejects a link that crosses profile boundaries.

The demo seed contains fictional Jordan Lee and Morgan Rivera profiles. It runs idempotently at container startup after migrations and never overwrites existing data.
