$ErrorActionPreference = 'Stop'

Push-Location $PSScriptRoot
try {
  if (-not (Get-Command node -ErrorAction SilentlyContinue) -or -not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Error 'Node.js and npm are required to run Gravity Defied Web.'
    exit 1
  }

  if (-not (Test-Path 'node_modules')) {
    Write-Host 'Installing dependencies...'
    npm install
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
  }

  npm run dev -- --open @args
  exit $LASTEXITCODE
} finally {
  Pop-Location
}
