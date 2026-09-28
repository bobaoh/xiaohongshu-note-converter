$ErrorActionPreference = 'Stop'

Write-Host 'Checking Python...'
python --version

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    throw 'winget is required. Install App Installer from Microsoft before continuing.'
}

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    winget install --id Gyan.FFmpeg.Shared --exact --accept-source-agreements --accept-package-agreements
}

python -m pip install --upgrade pip
python -m pip install -r (Join-Path $PSScriptRoot '..\requirements.txt')

Write-Host ''
Write-Host 'Setup complete.'
Write-Host 'Run: python .\scripts\extract_recipe.py "<PUBLIC_XHS_LINK>" --output .\output'
