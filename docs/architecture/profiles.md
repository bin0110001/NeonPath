# Profile Core

All career data is scoped through an explicit `profile_id`; no profile-specific values are embedded in code. The Profile Core stores identity, optional contact details, experience, reusable achievements, a shared skill catalog with aliases, profile skill evidence, education, portfolio entries, role families, search preferences, and scoring weights.

The API begins at `/api/v1/profiles`. Export/import uses a versioned JSON envelope (`schema_version: 2`; v1 still imports). Every achievement optionally links to an experience, and the application service rejects a link that crosses profile boundaries.

The demo seed contains fictional Jordan Lee and Morgan Rivera profiles. It runs idempotently at container startup after migrations and never overwrites existing data.

## Endpoints (`/api/v1/profiles/{profile_id}/...`)

Records: `experiences`, `achievements`, `education`, `portfolio`, `role-families`, `role-targets` each support `GET` (list), `POST` (create), `GET|PUT|DELETE /{id}`. Record ids are always resolved through the profile in the path: an id owned by another profile returns 404 and changes nothing. An achievement cannot link another profile's experience (422); deleting an experience detaches its achievements.

Preferences: `GET|PUT search-preferences`, `GET|PUT scoring-preferences` (weight keys must be known evaluation dimensions; negative weights rejected).

Skills: `GET|POST skills`, `PUT|DELETE skills/{skill_id}` (removes the profile's link, not the shared catalog entry), and `GET|POST skills/{skill_id}/aliases`, `DELETE skills/{skill_id}/aliases/{alias}`. An alias already owned by another skill returns 409.

## Export / import

`GET /export` returns `schema_version: 2` covering every entity type (contact, experiences, achievements, skills with aliases, education, portfolio, role families/targets, search and scoring preferences). Achievements reference experiences by position (`experience_index`) so links survive import under new ids. `POST /profiles/import` accepts versions 1 and 2; a failed import removes everything it created.
