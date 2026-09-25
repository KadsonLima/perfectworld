$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw 'Docker indisponível. Reinicie o Windows e abra o Docker Desktop.' }
docker compose config --quiet
if ($LASTEXITCODE -ne 0) { throw 'Compose inválido.' }
docker compose up -d
if ($LASTEXITCODE -ne 0) { throw 'Falha ao subir os containers.' }
docker compose ps -a

& (Join-Path $PSScriptRoot 'start-admin.ps1')
