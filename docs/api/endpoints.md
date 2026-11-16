# API endpoints

Generated from the OpenAPI document by `python -m careerflow.scripts.docs_api`; do not edit by
hand (a test fails if it is stale). Interactive docs: `/docs`. Machine-readable: `/openapi.json`.
Every path below is relative to the API origin; profile-owned data lives under
`/api/v1/profiles/{profile_id}/...`.


## ai

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/ai/config` | Get Config |
| PUT | `/api/v1/ai/config` | Put Config |
| DELETE | `/api/v1/ai/config` | Reset Config |
| GET | `/api/v1/ai/status` | Ai Status |
| POST | `/api/v1/ai/test` | Test Connection |

## artifact-formats

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/artifact-formats` | Formats |

## config

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/config` | Get Config |

## duplicates

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/duplicates` | List Duplicates |
| POST | `/api/v1/duplicates/{duplicate_id}/dismiss` | Dismiss Duplicate |
| POST | `/api/v1/duplicates/{duplicate_id}/merge` | Merge Duplicate |

## health

| Method | Path | Summary |
|---|---|---|
| GET | `/health/live` | Liveness |
| GET | `/health/ready` | Readiness |

## integrations

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/integrations/google/callback` | Callback |

## jobs

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/jobs` | List Jobs |
| POST | `/api/v1/jobs` | Create Job |
| GET | `/api/v1/jobs/dashboard` | Dashboard |
| POST | `/api/v1/jobs/import` | Import Job |
| GET | `/api/v1/jobs/{job_id}` | Get Job |
| PUT | `/api/v1/jobs/{job_id}` | Update Job |
| PATCH | `/api/v1/jobs/{job_id}` | Update Job |
| DELETE | `/api/v1/jobs/{job_id}` | Delete Job |
| POST | `/api/v1/jobs/{job_id}/archive` | Archive Job |
| GET | `/api/v1/jobs/{job_id}/comparison` | Compare Profiles |
| POST | `/api/v1/jobs/{job_id}/evaluate` | Evaluate Job |
| POST | `/api/v1/jobs/{job_id}/evaluate-all` | Evaluate Job For All Profiles |
| GET | `/api/v1/jobs/{job_id}/evaluations` | List Evaluations |
| POST | `/api/v1/jobs/{job_id}/evaluations` | Evaluate Job |
| GET | `/api/v1/jobs/{job_id}/evaluations/latest` | Get Latest Evaluation |
| POST | `/api/v1/jobs/{job_id}/extract-requirements` | Extract Requirements |
| POST | `/api/v1/jobs/{job_id}/reject` | Reject Job |
| GET | `/api/v1/jobs/{job_id}/requirements` | List Requirements |
| POST | `/api/v1/jobs/{job_id}/requirements` | Add Requirement |
| POST | `/api/v1/jobs/{job_id}/save` | Save Job |
| POST | `/api/v1/jobs/{job_id}/shortlist` | Shortlist Job |
| GET | `/api/v1/jobs/{job_id}/sources` | List Source Records |
| POST | `/api/v1/jobs/{job_id}/sources` | Add Source Record |
| GET | `/api/v1/jobs/{job_id}/status-history` | Get Status History |
| POST | `/api/v1/jobs/{job_id}/transition` | Transition |
| GET | `/api/v1/jobs/{job_id}/workflow` | Get Workflow Status |

## merges

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/merges` | List Merges |
| POST | `/api/v1/merges` | Merge Jobs |
| POST | `/api/v1/merges/{merge_id}/unmerge` | Unmerge |

## profiles

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles` | List Profiles |
| POST | `/api/v1/profiles` | Create Profile |
| POST | `/api/v1/profiles/import` | Import Profile |
| GET | `/api/v1/profiles/{profile_id}` | Get Profile |
| PUT | `/api/v1/profiles/{profile_id}` | Update Profile |
| DELETE | `/api/v1/profiles/{profile_id}` | Delete Profile |

## profiles/{id}/achievements

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/achievements` | List Achievements |
| POST | `/api/v1/profiles/{profile_id}/achievements` | Add Achievement |
| GET | `/api/v1/profiles/{profile_id}/achievements/{item_id}` | Get Achievements |
| PUT | `/api/v1/profiles/{profile_id}/achievements/{item_id}` | Update Achievements |
| DELETE | `/api/v1/profiles/{profile_id}/achievements/{item_id}` | Delete Achievements |

## profiles/{id}/applications

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/applications` | List Applications |
| POST | `/api/v1/profiles/{profile_id}/applications` | Create Application |
| GET | `/api/v1/profiles/{profile_id}/applications/{application_id}` | Get Application |
| PUT | `/api/v1/profiles/{profile_id}/applications/{application_id}` | Update Application |
| DELETE | `/api/v1/profiles/{profile_id}/applications/{application_id}` | Delete Application |
| GET | `/api/v1/profiles/{profile_id}/applications/{application_id}/contacts` | List Application Contacts |
| POST | `/api/v1/profiles/{profile_id}/applications/{application_id}/contacts` | Link Contact |
| DELETE | `/api/v1/profiles/{profile_id}/applications/{application_id}/contacts/{contact_id}` | Unlink Contact |

## profiles/{id}/artifacts

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/artifacts` | List Artifacts |
| POST | `/api/v1/profiles/{profile_id}/artifacts` | Create Artifact |
| GET | `/api/v1/profiles/{profile_id}/artifacts/{artifact_id}` | Get Artifact |
| GET | `/api/v1/profiles/{profile_id}/artifacts/{artifact_id}/download` | Download Artifact |
| POST | `/api/v1/profiles/{profile_id}/artifacts/{artifact_id}/rerender` | Rerender Artifact |

## profiles/{id}/calendar

| Method | Path | Summary |
|---|---|---|
| POST | `/api/v1/profiles/{profile_id}/calendar/import` | Import Events |
| GET | `/api/v1/profiles/{profile_id}/calendar/requests` | List Requests |
| POST | `/api/v1/profiles/{profile_id}/calendar/requests` | Propose Event |
| POST | `/api/v1/profiles/{profile_id}/calendar/requests/{request_id}/approve` | Approve Request |
| POST | `/api/v1/profiles/{profile_id}/calendar/requests/{request_id}/reject` | Reject Request |

## profiles/{id}/contact

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/contact` | Get Contact |
| PUT | `/api/v1/profiles/{profile_id}/contact` | Replace Contact |

## profiles/{id}/contacts

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/contacts` | List Contacts |
| POST | `/api/v1/profiles/{profile_id}/contacts` | Create Contact |
| PUT | `/api/v1/profiles/{profile_id}/contacts/{contact_id}` | Update Contact |
| DELETE | `/api/v1/profiles/{profile_id}/contacts/{contact_id}` | Delete Contact |

## profiles/{id}/education

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/education` | List Education |
| POST | `/api/v1/profiles/{profile_id}/education` | Add Education |
| GET | `/api/v1/profiles/{profile_id}/education/{item_id}` | Get Education |
| PUT | `/api/v1/profiles/{profile_id}/education/{item_id}` | Update Education |
| DELETE | `/api/v1/profiles/{profile_id}/education/{item_id}` | Delete Education |

## profiles/{id}/email

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/email/links` | List Links |
| POST | `/api/v1/profiles/{profile_id}/email/links/{link_id}/confirm` | Confirm Link |
| POST | `/api/v1/profiles/{profile_id}/email/links/{link_id}/dismiss` | Dismiss Link |
| POST | `/api/v1/profiles/{profile_id}/email/links/{link_id}/draft` | Draft Reply |
| GET | `/api/v1/profiles/{profile_id}/email/links/{link_id}/drafts` | List Drafts |
| POST | `/api/v1/profiles/{profile_id}/email/sync` | Sync Email |

## profiles/{id}/experiences

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/experiences` | List Experiences |
| POST | `/api/v1/profiles/{profile_id}/experiences` | Add Experience |
| GET | `/api/v1/profiles/{profile_id}/experiences/{item_id}` | Get Experiences |
| PUT | `/api/v1/profiles/{profile_id}/experiences/{item_id}` | Update Experiences |
| DELETE | `/api/v1/profiles/{profile_id}/experiences/{item_id}` | Delete Experiences |

## profiles/{id}/export

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/export` | Export Profile |

## profiles/{id}/follow-ups

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/follow-ups` | List Follow Ups |
| POST | `/api/v1/profiles/{profile_id}/follow-ups` | Create Follow Up |
| PUT | `/api/v1/profiles/{profile_id}/follow-ups/{follow_up_id}` | Update Follow Up |
| DELETE | `/api/v1/profiles/{profile_id}/follow-ups/{follow_up_id}` | Delete Follow Up |
| POST | `/api/v1/profiles/{profile_id}/follow-ups/{follow_up_id}/{action}` | Resolve Follow Up |

## profiles/{id}/integrations

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/integrations` | Integrations |
| DELETE | `/api/v1/profiles/{profile_id}/integrations/{kind}` | Disconnect |
| POST | `/api/v1/profiles/{profile_id}/integrations/{kind}/connect` | Connect |

## profiles/{id}/interviews

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/interviews` | List Interviews |
| POST | `/api/v1/profiles/{profile_id}/interviews` | Create Interview |
| GET | `/api/v1/profiles/{profile_id}/interviews/{interview_id}` | Get Interview |
| PUT | `/api/v1/profiles/{profile_id}/interviews/{interview_id}` | Update Interview |
| DELETE | `/api/v1/profiles/{profile_id}/interviews/{interview_id}` | Delete Interview |
| POST | `/api/v1/profiles/{profile_id}/interviews/{interview_id}/prepare` | Prepare Interview |

## profiles/{id}/jobs

| Method | Path | Summary |
|---|---|---|
| POST | `/api/v1/profiles/{profile_id}/jobs/{job_id}/prepare` | Prepare Application |
| POST | `/api/v1/profiles/{profile_id}/jobs/{job_id}/prepare/approve` | Approve Preparation |

## profiles/{id}/overview

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/overview` | Overview |

## profiles/{id}/packages

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/packages` | List Packages |
| GET | `/api/v1/profiles/{profile_id}/packages/by-job/{job_id}` | Package For Job |
| PUT | `/api/v1/profiles/{profile_id}/packages/by-job/{job_id}` | Save Package |
| DELETE | `/api/v1/profiles/{profile_id}/packages/{package_id}` | Delete Package |

## profiles/{id}/pipeline

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/pipeline` | Pipeline |

## profiles/{id}/portfolio

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/portfolio` | List Portfolio |
| POST | `/api/v1/profiles/{profile_id}/portfolio` | Add Portfolio |
| GET | `/api/v1/profiles/{profile_id}/portfolio/{item_id}` | Get Portfolio |
| PUT | `/api/v1/profiles/{profile_id}/portfolio/{item_id}` | Update Portfolio |
| DELETE | `/api/v1/profiles/{profile_id}/portfolio/{item_id}` | Delete Portfolio |

## profiles/{id}/resume-variants

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/resume-variants` | List Variants |
| POST | `/api/v1/profiles/{profile_id}/resume-variants` | Create Variant |
| GET | `/api/v1/profiles/{profile_id}/resume-variants/{variant_id}` | Get Variant |
| PUT | `/api/v1/profiles/{profile_id}/resume-variants/{variant_id}` | Update Variant |
| DELETE | `/api/v1/profiles/{profile_id}/resume-variants/{variant_id}` | Delete Variant |

## profiles/{id}/role-families

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/role-families` | List Role-Families |
| POST | `/api/v1/profiles/{profile_id}/role-families` | Add Role-Families |
| GET | `/api/v1/profiles/{profile_id}/role-families/{item_id}` | Get Role-Families |
| PUT | `/api/v1/profiles/{profile_id}/role-families/{item_id}` | Update Role-Families |
| DELETE | `/api/v1/profiles/{profile_id}/role-families/{item_id}` | Delete Role-Families |

## profiles/{id}/role-targets

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/role-targets` | List Role-Targets |
| POST | `/api/v1/profiles/{profile_id}/role-targets` | Add Role-Targets |
| GET | `/api/v1/profiles/{profile_id}/role-targets/{item_id}` | Get Role-Targets |
| PUT | `/api/v1/profiles/{profile_id}/role-targets/{item_id}` | Update Role-Targets |
| DELETE | `/api/v1/profiles/{profile_id}/role-targets/{item_id}` | Delete Role-Targets |

## profiles/{id}/scoring-preferences

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/scoring-preferences` | Get Scoring Preferences |
| PUT | `/api/v1/profiles/{profile_id}/scoring-preferences` | Replace Scoring Preferences |

## profiles/{id}/search-preferences

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/search-preferences` | Get Search Preferences |
| PUT | `/api/v1/profiles/{profile_id}/search-preferences` | Replace Search Preferences |

## profiles/{id}/searches

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/searches` | List Searches |
| POST | `/api/v1/profiles/{profile_id}/searches` | Create Search |
| PATCH | `/api/v1/profiles/{profile_id}/searches/{search_id}` | Update Search |
| DELETE | `/api/v1/profiles/{profile_id}/searches/{search_id}` | Delete Search |
| POST | `/api/v1/profiles/{profile_id}/searches/{search_id}/run` | Run Now |
| GET | `/api/v1/profiles/{profile_id}/searches/{search_id}/runs` | List Runs |

## profiles/{id}/skills

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/profiles/{profile_id}/skills` | List Skills |
| POST | `/api/v1/profiles/{profile_id}/skills` | Add Skill |
| PUT | `/api/v1/profiles/{profile_id}/skills/{skill_id}` | Update Skill |
| DELETE | `/api/v1/profiles/{profile_id}/skills/{skill_id}` | Remove Skill |
| GET | `/api/v1/profiles/{profile_id}/skills/{skill_id}/aliases` | List Aliases |
| POST | `/api/v1/profiles/{profile_id}/skills/{skill_id}/aliases` | Add Alias |
| DELETE | `/api/v1/profiles/{profile_id}/skills/{skill_id}/aliases/{alias}` | Remove Alias |

## resume-templates

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/resume-templates` | List Templates |

## sources

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/sources` | List Sources |
| POST | `/api/v1/sources` | Create Source |
| GET | `/api/v1/sources/adapters` | List Adapters |
| PATCH | `/api/v1/sources/{source_id}` | Update Source |
| DELETE | `/api/v1/sources/{source_id}` | Delete Source |
| POST | `/api/v1/sources/{source_id}/run` | Run Now |
| GET | `/api/v1/sources/{source_id}/runs` | List Runs |

## tasks

| Method | Path | Summary |
|---|---|---|
| GET | `/api/v1/tasks` | List Tasks |
| POST | `/api/v1/tasks` | Enqueue Task |
| POST | `/api/v1/tasks/{task_id}/retry` | Retry Task |
