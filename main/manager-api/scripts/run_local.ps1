Param(
    [string]$EnvFile = "$PSScriptRoot\..\.env.manager-api"
)

if (-Not (Test-Path $EnvFile)) {
    Write-Error "Env file not found: $EnvFile"
    exit 1
}

Write-Output "Loading env from $EnvFile"
Get-Content $EnvFile | Where-Object { $_ -notmatch '^\s*#' -and $_ -match '=' } | ForEach-Object {
    $parts = $_ -split '=',2
    $k = $parts[0].Trim()
    $v = $parts[1].Trim().Trim('"')
    Write-Output "Setting env $k"
    [System.Environment]::SetEnvironmentVariable($k, $v, 'Process')
}

Write-Output "Running mvn spring-boot:run"
mvN -DskipTests spring-boot:run



