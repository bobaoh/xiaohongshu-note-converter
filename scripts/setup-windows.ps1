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
Write-Host 'In Claude Code, run: /xhs-note <PUBLIC_XHS_LINK> [format]'
Write-Host 'Or extract directly: python .\scripts\extract_note.py "<PUBLIC_XHS_LINK>" --output .\output\<name>'
