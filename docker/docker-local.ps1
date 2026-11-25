param(
    [ValidateSet('validate','up','build','ps','logs','down')][string]$Action = 'up'
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$installedDockerBin = 'D:/DevTools/Docker/app-current/resources/bin'
if (Test-Path -LiteralPath $installedDockerBin) {
    $env:PATH = $installedDockerBin + ';' + $env:PATH
}
# Docker's build client needs proxy environment variables; reuse the enabled Windows proxy.
# This only affects this PowerShell process and its children, not Windows settings.
if (-not $env:HTTPS_PROXY) {
    $registryProxy = Get-ItemProperty -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Internet Settings' -ErrorAction SilentlyContinue
    if ($registryProxy.ProxyEnable -eq 1 -and $registryProxy.ProxyServer -match '^[^;=]+:\d+$') {
        $env:HTTPS_PROXY = 'http://' + $registryProxy.ProxyServer
        if (-not $env:HTTP_PROXY) { $env:HTTP_PROXY = $env:HTTPS_PROXY }
    }
}
$docker = Get-Command docker -ErrorAction SilentlyContinue
$dockerExe = if ($docker) { $docker.Source } else { Join-Path $projectRoot '.data/tools/docker-cli/docker.exe' }
if (-not (Test-Path -LiteralPath $dockerExe)) { throw 'Install and start Docker Desktop first; docker.exe was not found.' }
$composeExe = Join-Path $projectRoot '.data/tools/docker-cli/docker-compose.exe'
$envFile = Join-Path $PSScriptRoot '.env.docker'
if (-not (Test-Path -LiteralPath $envFile)) { Copy-Item -LiteralPath "$PSScriptRoot/.env.docker.example" -Destination $envFile }
$composeArgs = @('--env-file', $envFile, '-f', "$PSScriptRoot/compose.yaml")

function Invoke-Compose([string[]]$Arguments) {
    # Compose writes normal progress to stderr; use its exit code to determine failure.
    $savedPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        if (Test-Path -LiteralPath $composeExe) { & $composeExe @composeArgs @Arguments }
        else { & $dockerExe compose @composeArgs @Arguments }
        $composeExit = $LASTEXITCODE
    } finally { $ErrorActionPreference = $savedPreference }
    if ($composeExit -ne 0) { throw "Docker Compose failed (exit $composeExit)." }
}

Invoke-Compose @('config', '--quiet')
if ($Action -eq 'validate') { Write-Output 'Compose configuration is valid; no containers were started.'; exit 0 }
$previousPreference = $ErrorActionPreference
try {
    $ErrorActionPreference = 'Continue'
    & $dockerExe info --format '{{.ServerVersion}}' 2>$null
    $engineExit = $LASTEXITCODE
} finally { $ErrorActionPreference = $previousPreference }
if ($engineExit -ne 0) { throw 'Docker client is available, but the container engine is not reachable. Install/start Docker Desktop in Linux containers mode, then retry. Existing local Nginx deployment was not changed.' }
switch ($Action) {
    'up' { Invoke-Compose @('up','--build','--detach','--wait','--wait-timeout','180') }
    'build' { Invoke-Compose @('build') }
    'ps' { Invoke-Compose @('ps') }
    'logs' { Invoke-Compose @('logs','--tail','100') }
    'down' { Invoke-Compose @('down') }
}
