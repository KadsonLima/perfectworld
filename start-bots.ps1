$ErrorActionPreference = 'Stop'
Set-Location (Join-Path $PSScriptRoot 'tools\pwbot')
if (-not (Test-Path 'bots.json')) { throw 'Crie tools\pwbot\bots.json a partir de bots.example.json.' }
$log = Join-Path $PSScriptRoot 'runtime\bots.log'
Start-Process python -ArgumentList 'run_bots.py' -WindowStyle Hidden `
  -RedirectStandardError $log -PassThru | ForEach-Object { $_.Id | Out-File (Join-Path $PSScriptRoot 'runtime\bots.pid') }
Write-Host "Bots iniciados. Log: $log"
