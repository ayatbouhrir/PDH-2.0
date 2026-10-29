$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
& (Join-Path $projectRoot 'run.cmd') --setup-only --data none @args
exit $LASTEXITCODE
