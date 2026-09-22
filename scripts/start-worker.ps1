. (Join-Path $PSScriptRoot 'Set-AIeduDevEnvironment.ps1')

Push-Location $script:AIeduBackend
try {
    & $script:AIeduUv run python -m app.worker
    $processExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $processExitCode
