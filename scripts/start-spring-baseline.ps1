$ErrorActionPreference = 'Stop'

$aieduRoot = Split-Path -Parent $PSScriptRoot
$rootEnvPath = Join-Path $aieduRoot '.env'
$springRoot = Join-Path $aieduRoot 'Aiedu-student-study 后端'
$springJar = Join-Path $springRoot 'Aiedu-server\target\Aiedu-server-1.0-SNAPSHOT.jar'

if (-not (Test-Path -LiteralPath $rootEnvPath)) {
    throw "Missing $rootEnvPath"
}

$values = @{}
foreach ($line in Get-Content -LiteralPath $rootEnvPath) {
    if ($line -match '^\s*([^#][^=]*)=(.*)$') {
        $values[$matches[1].Trim()] = $matches[2].Trim()
    }
}

foreach ($required in 'MYSQL_DATABASE', 'MYSQL_USER', 'MYSQL_PASSWORD') {
    if (-not $values.ContainsKey($required) -or [string]::IsNullOrWhiteSpace($values[$required])) {
        throw "Missing $required in $rootEnvPath"
    }
}

if (-not (Test-Path -LiteralPath $springJar)) {
    Push-Location $springRoot
    try {
        & mvn.cmd -pl Aiedu-server -am package -DskipTests
        if ($LASTEXITCODE -ne 0) {
            throw "Spring Boot package failed with exit code $LASTEXITCODE"
        }
    }
    finally {
        Pop-Location
    }
}

$env:AIEDU_DB_HOST = '127.0.0.1'
$env:AIEDU_DB_PORT = '3307'
$env:AIEDU_DB_NAME = $values['MYSQL_DATABASE']
$env:AIEDU_DB_USERNAME = $values['MYSQL_USER']
$env:AIEDU_DB_PASSWORD = $values['MYSQL_PASSWORD']
$env:AIEDU_REDIS_HOST = '127.0.0.1'
$env:AIEDU_REDIS_PORT = '6379'

Push-Location $springRoot
try {
    & java.exe -jar $springJar
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
