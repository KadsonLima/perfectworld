$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$panelUrl = 'http://127.0.0.1:8090'
try {
    $response = Invoke-WebRequest -Uri "$panelUrl/api/status" -UseBasicParsing -TimeoutSec 2
    if ($response.StatusCode -eq 200) { Write-Host "PW Admin ja esta ativo: $panelUrl"; return }
} catch { }
docker info *> $null
if ($LASTEXITCODE -ne 0) { throw 'Docker indisponivel.' }
New-Item -ItemType Directory -Force -Path 'runtime\admin' | Out-Null
$panelProcess = Start-Process -FilePath 'python' -ArgumentList @('tools\admin\pw_admin.py') -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput 'runtime\admin\stdout.log' -RedirectStandardError 'runtime\admin\stderr.log'
Set-Content -LiteralPath 'runtime\admin\pid.txt' -Value $panelProcess.Id
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    Start-Sleep -Milliseconds 500
    try {
        $response = Invoke-WebRequest -Uri "$panelUrl/" -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) { Write-Host "PW Admin ativo: $panelUrl"; return }
    } catch { }
    if ($panelProcess.HasExited) { throw 'Painel encerrou. Consulte runtime\admin\stderr.log.' }
}
throw 'Painel nao respondeu. Consulte runtime\admin\stderr.log.'
