param([int]$Port = 8765, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$url = "http://127.0.0.1:$Port"
try {
    $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 2
    if ($health.app -eq 'Firefield') { if (-not $NoBrowser) { Start-Process $url }; exit 0 }
} catch { }
$candidates = @(
    (Join-Path $PSScriptRoot '.venv\Scripts\python.exe'),
    (Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe')
)
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCommand) { $candidates += $pythonCommand.Source }
$runtime = $null
foreach ($candidate in $candidates) {
    if (Test-Path -LiteralPath $candidate) {
        & $candidate -c 'import numpy; import PIL' 2>$null
        if ($LASTEXITCODE -eq 0) { $runtime = $candidate; break }
    }
}
if (-not $runtime) { throw 'Python with NumPy and Pillow is required. See README.md.' }
$logDir = Join-Path $PSScriptRoot 'reports\server'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$process = Start-Process -FilePath $runtime -ArgumentList @('-X','utf8','-m','firelab','serve','--port',"$Port") -WorkingDirectory $PSScriptRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir 'stdout.log') -RedirectStandardError (Join-Path $logDir 'stderr.log')
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    Start-Sleep -Milliseconds 300
    try {
        $health = Invoke-RestMethod "$url/api/health" -TimeoutSec 1
        if ($health.app -eq 'Firefield') {
            $process.Id | Set-Content (Join-Path $logDir 'server.pid')
            if (-not $NoBrowser) { Start-Process $url }
            exit 0
        }
    } catch { }
    if ($process.HasExited) { break }
}
throw "Server failed to start. Inspect $logDir"
