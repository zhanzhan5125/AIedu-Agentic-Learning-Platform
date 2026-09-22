param([switch]$Reload, [switch]$NoReload)

. (Join-Path $PSScriptRoot 'Set-AIeduDevEnvironment.ps1')

Push-Location $script:AIeduBackend
try {
    & $script:AIeduUv run alembic upgrade head
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    # Windows 上 reload 子进程可能因命名管道权限退出；默认使用稳定单进程，
    # 只有显式传入 -Reload 时才启用热重载。保留 -NoReload 兼容旧命令。
    if ($Reload -and -not $NoReload) {
        & $script:AIeduUv run uvicorn app.main:app --host 0.0.0.0 --port 9091 --reload
    }
    else {
        & $script:AIeduUv run uvicorn app.main:app --host 0.0.0.0 --port 9091
    }
    $processExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $processExitCode
