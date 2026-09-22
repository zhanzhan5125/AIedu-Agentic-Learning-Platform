. (Join-Path $PSScriptRoot 'Set-AIeduDevEnvironment.ps1')

if (-not (Test-Path -LiteralPath $script:AIeduNpm)) {
    throw "Node.js 22.23.2 npm was not found at $script:AIeduNpm"
}

$env:AIEDU_FASTAPI_TARGET = 'http://127.0.0.1:9091'
Push-Location $script:AIeduFrontend
try {
    & $script:AIeduNpm run serve
    $processExitCode = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $processExitCode
