$ErrorActionPreference = 'Stop'

$script:AIeduRoot = Split-Path -Parent $PSScriptRoot
$rootEnvPath = Join-Path $script:AIeduRoot '.env'
$aiEnvPath = Join-Path $script:AIeduRoot '.env.ai'
if (-not (Test-Path -LiteralPath $rootEnvPath)) {
    throw "Missing $rootEnvPath. Copy .env.example to .env and set local secrets first."
}

$values = @{}
foreach ($envPath in @($rootEnvPath, $aiEnvPath)) {
    if (-not (Test-Path -LiteralPath $envPath)) { continue }
    foreach ($line in Get-Content -LiteralPath $envPath) {
        if ($line -match '^\s*([^#][^=]*)=(.*)$') {
            $values[$matches[1].Trim()] = $matches[2].Trim()
        }
    }
}

foreach ($required in 'MYSQL_DATABASE', 'MYSQL_USER', 'MYSQL_PASSWORD', 'REDIS_PASSWORD', 'AIEDU_JWT_SECRET') {
    if (-not $values.ContainsKey($required) -or [string]::IsNullOrWhiteSpace($values[$required])) {
        throw "Missing $required in $rootEnvPath"
    }
}

$mysqlUser = [Uri]::EscapeDataString($values['MYSQL_USER'])
$mysqlPassword = [Uri]::EscapeDataString($values['MYSQL_PASSWORD'])
$redisPassword = [Uri]::EscapeDataString($values['REDIS_PASSWORD'])
$database = [Uri]::EscapeDataString($values['MYSQL_DATABASE'])

$env:AIEDU_ENV = 'development'
$env:AIEDU_DATABASE_URL = "mysql+pymysql://${mysqlUser}:${mysqlPassword}@127.0.0.1:3307/${database}?charset=utf8mb4"
$env:AIEDU_REDIS_URL = "redis://:${redisPassword}@127.0.0.1:6379/0"
$env:AIEDU_QDRANT_URL = 'http://127.0.0.1:6333'
$env:AIEDU_JWT_SECRET = $values['AIEDU_JWT_SECRET']
$env:AIEDU_CORS_ORIGINS = 'http://localhost:8080'
$env:AIEDU_ROCKETMQ_ENDPOINT = '127.0.0.1:8081'
$env:AIEDU_ROCKETMQ_TOPIC = if ($values['AIEDU_ROCKETMQ_TOPIC']) { $values['AIEDU_ROCKETMQ_TOPIC'] } else { 'aiedu-ai-jobs' }
$env:AIEDU_ROCKETMQ_LOG_DIR = Join-Path $script:AIeduRoot '.cache\rocketmq'
$env:AIEDU_ROCKETMQ_WORKER_CONCURRENCY = if ($values['AIEDU_ROCKETMQ_WORKER_CONCURRENCY']) { $values['AIEDU_ROCKETMQ_WORKER_CONCURRENCY'] } else { '4' }
$env:AIEDU_ROCKETMQ_INVISIBLE_DURATION_SECONDS = if ($values['AIEDU_ROCKETMQ_INVISIBLE_DURATION_SECONDS']) { $values['AIEDU_ROCKETMQ_INVISIBLE_DURATION_SECONDS'] } else { '1800' }
$env:AIEDU_ENABLE_MQ = 'true'
$env:AIEDU_ENABLE_LLM = if ($values['AIEDU_ENABLE_LLM']) { $values['AIEDU_ENABLE_LLM'] } else { 'false' }
$env:AIEDU_AI_BASE_URL = if ($values['AIEDU_AI_BASE_URL']) { $values['AIEDU_AI_BASE_URL'] } else { 'https://api.openai.com/v1' }
$env:AIEDU_AI_API_KEY = $values['AIEDU_AI_API_KEY']
$env:AIEDU_LLM_MODEL = $values['AIEDU_LLM_MODEL']
$env:AIEDU_QDRANT_COLLECTION = if ($values['AIEDU_QDRANT_COLLECTION']) { $values['AIEDU_QDRANT_COLLECTION'] } else { 'aiedu_course_resources_v2' }
$env:AIEDU_EMBEDDING_MODEL = 'text-embedding-3-large'
$env:AIEDU_EMBEDDING_DIMENSIONS = if ($values['AIEDU_EMBEDDING_DIMENSIONS']) { $values['AIEDU_EMBEDDING_DIMENSIONS'] } else { '3072' }
$env:AIEDU_EMBEDDING_BATCH_SIZE = if ($values['AIEDU_EMBEDDING_BATCH_SIZE']) { $values['AIEDU_EMBEDDING_BATCH_SIZE'] } else { '64' }
$env:AIEDU_RAG_CHUNK_SIZE_CHARS = if ($values['AIEDU_RAG_CHUNK_SIZE_CHARS']) { $values['AIEDU_RAG_CHUNK_SIZE_CHARS'] } else { '1200' }
$env:AIEDU_RAG_CHUNK_OVERLAP_CHARS = if ($values['AIEDU_RAG_CHUNK_OVERLAP_CHARS']) { $values['AIEDU_RAG_CHUNK_OVERLAP_CHARS'] } else { '200' }
$env:AIEDU_UPLOAD_DIR = Join-Path $script:AIeduRoot 'Aiedu-student-study FastAPI后端\uploads'
$env:AIEDU_MAX_UPLOAD_BYTES = '10485760'
# Local infrastructure must never be routed through a Windows/system proxy.
# urllib/httpx also consult the Windows proxy registry when HTTP_PROXY is absent.
$localNoProxy = @('localhost', '127.0.0.1', '::1')
$existingNoProxy = @($env:NO_PROXY -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$env:NO_PROXY = (@($existingNoProxy + $localNoProxy) | Select-Object -Unique) -join ','
$env:UV_PYTHON_INSTALL_DIR = 'D:\applications\aiedu-runtimes\python'
$env:UV_CACHE_DIR = Join-Path $script:AIeduRoot '.cache\uv'

$script:AIeduBackend = Join-Path $script:AIeduRoot 'Aiedu-student-study FastAPI后端'
$script:AIeduFrontend = Join-Path $script:AIeduRoot 'Aiedu-student-study 前端'
$script:AIeduUv = 'D:\applications\bin\uv.exe'
$script:AIeduNodeHome = 'D:\applications\aiedu-runtimes\node-v22.23.2-win-x64'
$script:AIeduNpm = Join-Path $script:AIeduNodeHome 'npm.cmd'
$env:Path = "$script:AIeduNodeHome;$env:Path"

if (-not (Test-Path -LiteralPath $script:AIeduUv)) {
    throw "uv 0.12.17 was not found at $script:AIeduUv"
}
