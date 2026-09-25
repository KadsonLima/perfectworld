Set-Location $PSScriptRoot
docker info *> $null
if ($LASTEXITCODE -ne 0) { Write-Error 'Docker indisponível; verifique WSL e reinicialização do Windows.'; exit 1 }
docker compose ps -a
$ids = @(docker compose ps -q)
if ($ids.Count -gt 0) { docker stats --no-stream @ids }
'SELECT 1 AS banco_ok; SELECT COUNT(*) AS contas FROM users;' | docker compose exec -T perfectworld-db sh -c 'MYSQL_PWD=$MYSQL_ROOT_PASSWORD exec mysql -h 127.0.0.1 -u root pw --batch'
if ($LASTEXITCODE -ne 0) { Write-Error 'Banco indisponível.' }
docker compose logs --tail=200 2>&1 | Select-String -Pattern 'error|fatal|failed|panic|segmentation|exception'
