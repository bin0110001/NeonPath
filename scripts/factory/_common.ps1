# Shared helpers for the factory validation scripts (dot-sourced).
# Contract: compact JSON on stdout, verbose logs under .factory/artifacts/, reliable exit code.
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$script:Root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$script:ArtifactDir = Join-Path $script:Root '.factory/artifacts'
New-Item -ItemType Directory -Force $script:ArtifactDir | Out-Null
$script:Stages = [System.Collections.Generic.List[object]]::new()
$script:Failures = [System.Collections.Generic.List[object]]::new()
$script:Passed = 0
$script:Failed = 0

# Run one command in a subdirectory; full output goes to an artifact, never to stdout.
function Invoke-Stage {
    param([string]$Name, [string]$Dir, [scriptblock]$Command, [string]$Kind = 'generic')
    $log = Join-Path $script:ArtifactDir "$Name.log"
    Push-Location (Join-Path $script:Root $Dir)
    try {
        $global:LASTEXITCODE = 0
        & $Command *>&1 | Out-File -FilePath $log -Encoding utf8
        $code = $global:LASTEXITCODE
    }
    catch { $_ | Out-File -FilePath $log -Append -Encoding utf8; $code = 1 }
    finally { Pop-Location }
    $text = Get-Content -Raw $log
    $text = $text -replace '\x1b\[[0-9;]*[A-Za-z]', ''
    if ($Kind -eq 'pytest') {
        if ($text -match '(\d+) passed') { $script:Passed += [int]$Matches[1] }
        if ($text -match '(\d+) failed') { $script:Failed += [int]$Matches[1] }
        foreach ($m in [regex]::Matches($text, '(?m)^FAILED (\S+)(?: - (.*))?$')) {
            $script:Failures.Add([ordered]@{ test = $m.Groups[1].Value; message = $m.Groups[2].Value.Trim(); artifact = $log })
        }
    }
    elseif ($Kind -eq 'vitest') {
        if ($text -match 'Tests\s+(?:(\d+) failed \| )?(\d+) passed') { $script:Failed += [int]$Matches[1]; $script:Passed += [int]$Matches[2] }
        foreach ($m in [regex]::Matches($text, '(?m)^\s*FAIL\s+(\S.*)$')) {
            $after = $text.Substring($m.Index + $m.Length)
            $err = [regex]::Match($after, '(?m)^\s*(?:Error|AssertionError)[^\r\n]*').Value.Trim()
            $script:Failures.Add([ordered]@{ test = $m.Groups[1].Value.Trim(); message = $err; artifact = $log })
        }
    }
    if ($code -ne 0 -and $Kind -in 'generic', 'tool') {
        # Lint/type/build failures: keep the first few error lines for the agent.
        $lines = @($text -split "`n" | Where-Object { $_ -match 'error|Error|✖|failed' } | Select-Object -First 3)
        foreach ($l in $lines) { $script:Failures.Add([ordered]@{ test = $Name; message = $l.Trim(); artifact = $log }) }
        if (-not $lines.Count) { $script:Failures.Add([ordered]@{ test = $Name; message = "exit code $code"; artifact = $log }) }
        $script:Failed += 1
    }
    elseif ($code -ne 0 -and $script:Failed -eq 0) { $script:Failed = 1 }
    $script:Stages.Add([ordered]@{ name = $Name; status = $(if ($code -eq 0) { 'passed' } else { 'failed' }); artifact = $log })
    $code
}

function Initialize-Backend {
    if (-not (Test-Path (Join-Path $script:Root 'backend/.venv'))) { Invoke-Stage 'setup-backend' 'backend' { uv sync --group dev } | Out-Null }
}
function Initialize-Frontend {
    if (-not (Test-Path (Join-Path $script:Root 'frontend/node_modules'))) { Invoke-Stage 'setup-frontend' 'frontend' { npm ci } | Out-Null }
}

# Emit the compact result and exit with a reliable code.
function Complete-Run([string]$Name) {
    $bad = @($script:Stages | Where-Object { $_.status -eq 'failed' })
    $result = [ordered]@{
        status   = $(if ($bad.Count) { 'failed' } else { 'passed' })
        stage    = $(if ($bad.Count) { $bad[0].name } else { $Name })
        passed   = $script:Passed
        failed   = $script:Failed
        stages   = @($script:Stages | ForEach-Object { "$($_.name):$($_.status)" })
        failures = @($script:Failures | Select-Object -First 10)
    }
    $json = $result | ConvertTo-Json -Depth 6
    $json | Set-Content (Join-Path $script:ArtifactDir "$Name-result.json") -Encoding utf8
    $json
    exit $(if ($bad.Count) { 1 } else { 0 })
}
