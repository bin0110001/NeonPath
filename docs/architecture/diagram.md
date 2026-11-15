# Architecture diagram

```mermaid
flowchart LR
    user([Person]) --> web[React web<br/>nginx]
    web -->|/api/v1| api[FastAPI API]

    subgraph backend [Backend image: one codebase, two commands]
        api --> app[Application services]
        worker[Worker<br/>queue + scheduler] --> app
        app --> domain[[Domain<br/>rules, state machines,<br/>evaluation, ports]]
        app --> infra[Infrastructure adapters]
    end

    infra --> db[(PostgreSQL<br/>data, task queue,<br/>schedules)]
    infra --> sources[/Job sources<br/>manual, fixture, RSS,<br/>JSON, Greenhouse/]
    infra --> llm[/LLM providers<br/>disabled, fixture, OpenAI-compatible,<br/>Ollama, Anthropic/]
    infra --> google[/Google mail + calendar<br/>read-only mail,<br/>approved calendar writes/]
    infra --> files[Artifact renderers<br/>MD, HTML, DOCX, PDF]

    classDef optional stroke-dasharray: 4 3;
    class sources,llm,google optional;
```

Dashed boxes are optional integrations: the product works with none of them configured (AI off, no mailbox, manual and fixture sources only). The domain depends on nothing outside itself; adapters implement ports defined in `domain/*/ports.py`.

## Request path

`Browser → web → API route (validation, schemas) → application service (profile-scoped use case) → domain rules + infrastructure (SQLAlchemy / adapters) → PostgreSQL`

## Background path

`Scheduler tick (row-locked) → task row → worker lease → handler (search, extract, re-evaluate, prune) → result or recorded failure`
