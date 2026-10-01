#!/usr/bin/env pwsh
# Full backend + frontend test suites. Compact JSON on stdout; logs in .factory/artifacts/.
. (Join-Path $PSScriptRoot '_common.ps1')

Initialize-Backend
Initialize-Frontend
Invoke-Stage 'backend-tests' 'backend' { uv run pytest -q } 'pytest' | Out-Null
Invoke-Stage 'frontend-tests' 'frontend' { npm run test } 'vitest' | Out-Null
Complete-Run 'test-full'
