$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:UV_PROJECT_ENVIRONMENT = Join-Path $PSScriptRoot '.venv-runtime'
uv run python main.py
