$ErrorActionPreference = 'Stop'
$root = Join-Path $PSScriptRoot '..'

Write-Host 'Checking Python...'
python --version
# Versions 3.11 to 3.14 are tested in CI.
python -c "import sys; v = sys.version_info[:2]; sys.exit(0 if (3, 11) <= v <= (3, 14) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Warning 'This project is tested on Python 3.11 to 3.14. Other versions may fail to install or behave differently.'
}

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw 'winget is required. Install App Installer from Microsoft before continuing.'
}

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    winget install --id Gyan.FFmpeg.Shared --exact --accept-source-agreements --accept-package-agreements
}

python -m pip install --upgrade pip
# requirements.lock pins the exact versions that passed CI.
python -m pip install -r (Join-Path $root 'requirements.txt') -c (Join-Path $root 'requirements.lock')

Write-Host ''
Write-Host 'Setup complete.'
Write-Host 'In Claude Code, run: /note <LINK> [format]   (a Xiaohongshu note or any web page)'
Write-Host 'Or extract directly: python .\scripts\extract.py "<LINK>"'
