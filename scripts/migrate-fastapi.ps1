. (Join-Path $PSScriptRoot 'Set-AIeduDevEnvironment.ps1')

Push-Location $script:AIeduBackend
try {
    & $script:AIeduUv run alembic upgrade head
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
finally {
    Pop-Location
}
