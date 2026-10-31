$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$env:UV_PROJECT_ENVIRONMENT = Join-Path $PSScriptRoot '.venv-runtime'
$buildStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$buildWork = Join-Path $PSScriptRoot ('build/' + $buildStamp)
$buildOutput = Join-Path $PSScriptRoot ('releases/' + $buildStamp)
$routeSource = Get-Item -LiteralPath 'native/route_search.c'
$routeLibrary = Get-Item -LiteralPath 'native/route_search.dll' -ErrorAction SilentlyContinue
if (!$routeLibrary -or $routeSource.LastWriteTimeUtc -gt $routeLibrary.LastWriteTimeUtc) {
    uv run --no-project --with ziglang==0.13.0 python -m ziglang cc -O3 -std=c11 -shared -s -target x86_64-windows-gnu native/route_search.c -o native/route_search.dll
    if ($LASTEXITCODE -ne 0) { throw 'Route engine compilation failed.' }
}
$pluginStage = Join-Path $buildWork 'plugin-data'
uv run python tools/stage_plugins.py plugins $pluginStage
if ($LASTEXITCODE -ne 0) { throw 'Plugin staging failed.' }
$skinStage = Join-Path $buildWork 'ui-skin'
New-Item -ItemType Directory -Path $skinStage -Force | Out-Null
Get-ChildItem -LiteralPath 'assets/skin' -Filter '*.png' | Where-Object { $_.Name -notlike '*-source.png' } | Copy-Item -Destination $skinStage
uv run --group dev pyinstaller --noconfirm --windowed --onedir --name Waymark --icon assets/waymark.ico --workpath $buildWork --distpath $buildOutput --hidden-import exile.navigation --hidden-import exile.reader --hidden-import exile.mapview --hidden-import exile.routing --hidden-import exile.destinations --hidden-import exile.native_route --add-binary 'native/route_search.dll;native' --add-data ($pluginStage + ';plugins') --add-data 'profiles;profiles' --add-data 'assets/rare_mod_catalog.json.z;assets' --add-data ($skinStage + ';assets/skin') --add-data 'README.md;.' --add-data 'MULTIPLAYER.md;.' --add-data 'THIRD_PARTY.md;.' main.py
if ($LASTEXITCODE -ne 0) { throw 'Application packaging failed.' }
uv run --group dev python tools/fix_bundle.py (Join-Path $buildOutput 'Waymark')
if ($LASTEXITCODE -ne 0) { throw 'Application dependency verification failed.' }
Write-Output ('Built ' + (Join-Path $buildOutput 'Waymark/Waymark.exe'))
