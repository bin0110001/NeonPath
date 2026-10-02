#!/usr/bin/env pwsh
# Required verification, mirroring CI: backend ruff + mypy + tests, frontend lint + build + tests.
. (Join-Path $PSScriptRoot '_common.ps1')

Initialize-Backend
Initialize-Frontend
Invoke-Stage 'backend-ruff' 'backend' { uv run ruff check . } | Out-Null
Invoke-Stage 'backend-mypy' 'backend' { uv run mypy src } | Out-Null
Invoke-Stage 'backend-tests' 'backend' { uv run pytest -q } 'pytest' | Out-Null
Invoke-Stage 'frontend-lint' 'frontend' { npm run lint } | Out-Null
Invoke-Stage 'frontend-build' 'frontend' { npm run build } | Out-Null
Invoke-Stage 'frontend-tests' 'frontend' { npm run test } 'vitest' | Out-Null
Complete-Run 'verify'
