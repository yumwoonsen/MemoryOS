$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonPath = Join-Path $repoRoot ".venv\Scripts\python.exe"
$frontendPath = Join-Path $repoRoot "frontend"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "The local Python environment is missing. Run: python -m venv .venv"
}

if (-not (Test-Path -LiteralPath (Join-Path $frontendPath "node_modules"))) {
    throw "Frontend packages are missing. Run: cd frontend; pnpm install"
}

$env:MEMORYOS_PROVIDER = "deterministic"
$env:NEXT_PUBLIC_MEMORYOS_API_BASE_URL = "http://127.0.0.1:8000"
$backendOutput = Join-Path $repoRoot "backend-local.log"
$backendErrors = Join-Path $repoRoot "backend-local-error.log"

$backendProcess = Start-Process `
    -FilePath $pythonPath `
    -ArgumentList @("-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "8000") `
    -WorkingDirectory $repoRoot `
    -WindowStyle Hidden `
    -RedirectStandardOutput $backendOutput `
    -RedirectStandardError $backendErrors `
    -PassThru

try {
    Write-Host "MemoryOS local engine: http://127.0.0.1:8000" -ForegroundColor Green
    Write-Host "MemoryOS Review Studio: http://localhost:3000" -ForegroundColor Green
    Write-Host "Press Ctrl+C to stop both." -ForegroundColor DarkGray
    Set-Location -LiteralPath $frontendPath
    & pnpm run dev
}
finally {
    $runningBackend = Get-Process -Id $backendProcess.Id -ErrorAction SilentlyContinue
    if ($runningBackend) {
        Stop-Process -Id $backendProcess.Id
    }
    Set-Location -LiteralPath $repoRoot
}
