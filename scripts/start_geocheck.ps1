param(
    [int]$Port = 8788
)

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "未找到虚拟环境。请先在项目根目录运行：python -m venv .venv；.\.venv\Scripts\python.exe -m pip install -e '.[web]'"
}

$env:PORT = $Port
& $python -m webapp.server
