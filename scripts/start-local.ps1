$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path $PSScriptRoot -Parent
& (Join-Path $projectRoot 'run.cmd') @args
exit $LASTEXITCODE
