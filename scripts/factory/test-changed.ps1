#!/usr/bin/env pwsh
# Tests relevant to what changed vs the base branch (plus uncommitted work).
# Backend: changed test files if any, otherwise the whole (fast, SQLite-backed) suite. Frontend: its suite.
param([string]$Base = 'main')
. (Join-Path $PSScriptRoot '_common.ps1')

Push-Location $script:Root
$changed = @(git diff --name-only "$Base...HEAD" 2>$null) + @(git diff --name-only HEAD 2>$null) + @(git ls-files --others --exclude-standard 2>$null) | Sort-Object -Unique
Pop-Location
$changed | Set-Content (Join-Path $script:ArtifactDir 'changed-files.txt')

$backend = @($changed | Where-Object { $_ -like 'backend/*' })
$frontend = @($changed | Where-Object { $_ -like 'frontend/*' })

if ($backend.Count) {
    Initialize-Backend
    $tests = @($backend | Where-Object { $_ -match '^backend/tests/.*\.py$' -and (Test-Path (Join-Path $script:Root $_)) } | ForEach-Object { $_ -replace '^backend/', '' })
    Invoke-Stage 'backend-tests' 'backend' { uv run pytest -q @tests } 'pytest' | Out-Null
}
if ($frontend.Count) {
    Initialize-Frontend
    Invoke-Stage 'frontend-tests' 'frontend' { npm run test } 'vitest' | Out-Null
}
if (-not $backend.Count -and -not $frontend.Count) { $script:Stages.Add([ordered]@{ name = 'no-code-changes'; status = 'passed'; artifact = '' }) }
Complete-Run 'test-changed'
