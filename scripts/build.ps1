$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

python -m pip install -e "${Backend}[test]"
python -m compileall (Join-Path $Backend "naratrace")

if (Test-Path (Join-Path $Frontend "package.json")) {
    Push-Location $Frontend
    try {
        npm install
        npm run build
    }
    finally {
        Pop-Location
    }
}
