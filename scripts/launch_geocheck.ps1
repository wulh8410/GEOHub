param(
    [int]$Port = 8788,
    [switch]$NoBrowser
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$url = "http://127.0.0.1:$Port/"

if (-not (Test-Path -LiteralPath $python)) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show(
        "未找到 GEO Check 的 Python 环境。请在项目目录重新执行安装。",
        "GEO Check",
        "OK",
        "Error"
    ) | Out-Null
    exit 1
}

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if (-not $listener) {
    $env:PORT = $Port
    Start-Process -FilePath $python -ArgumentList "-m", "webapp.server" -WorkingDirectory $projectRoot -WindowStyle Hidden
    $deadline = (Get-Date).AddSeconds(20)
    do {
        Start-Sleep -Milliseconds 400
        try {
            Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2 | Out-Null
            $ready = $true
        } catch {
            $ready = $false
        }
    } while (-not $ready -and (Get-Date) -lt $deadline)
    if (-not $ready) {
        Add-Type -AssemblyName PresentationFramework
        [System.Windows.MessageBox]::Show(
            "GEO Check 启动失败，请检查网络或 Python 环境。",
            "GEO Check",
            "OK",
            "Error"
        ) | Out-Null
        exit 1
    }
}

if (-not $NoBrowser) {
    Start-Process $url
}
