[CmdletBinding()]
param(
    [string]$DatabaseUrl = $env:DATABASE_URL,
    [string]$BackupDirectory = (Join-Path $PSScriptRoot "..\backups\postgres"),
    [int]$KeepCount = 7,
    [string]$PgBin = $env:POSTGRES_BIN,
    [string]$OpenSsl = "openssl"
)

$ErrorActionPreference = "Stop"

if ($KeepCount -lt 1) {
    throw "KeepCount must be at least 1."
}
if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
    throw "Set DATABASE_URL or pass -DatabaseUrl. Do not pass credentials on the command line."
}
if ([string]::IsNullOrWhiteSpace($env:NEXMARKET_BACKUP_PASSPHRASE)) {
    throw "Set NEXMARKET_BACKUP_PASSPHRASE in the protected process environment."
}

if ([string]::IsNullOrWhiteSpace($PgBin)) {
    $PgBin = "C:\Program Files\PostgreSQL\17\bin"
}
$pgDump = Join-Path $PgBin "pg_dump.exe"
if (-not (Test-Path -LiteralPath $pgDump)) {
    throw "pg_dump.exe not found at '$pgDump'. Pass -PgBin with the PostgreSQL client bin directory."
}
$null = Get-Command $OpenSsl -ErrorAction Stop

try {
    $uri = [System.Uri]$DatabaseUrl
    if ($uri.Scheme -notin @("postgresql", "postgresql+psycopg2", "postgresql+asyncpg")) {
        throw "DATABASE_URL must use a PostgreSQL scheme."
    }
    $hostName = $uri.Host
    $port = if ($uri.Port -gt 0) { $uri.Port } else { 5432 }
    $userName = [System.Uri]::UnescapeDataString($uri.UserInfo.Split(":", 2)[0])
    $databaseName = $uri.AbsolutePath.TrimStart("/")
    if ([string]::IsNullOrWhiteSpace($hostName) -or
        [string]::IsNullOrWhiteSpace($userName) -or
        [string]::IsNullOrWhiteSpace($databaseName)) {
        throw "DATABASE_URL must include host, username, and database name."
    }
}
catch {
    throw "Could not parse DATABASE_URL without exposing credentials: $($_.Exception.Message)"
}

$backupRoot = if ([System.IO.Path]::IsPathRooted($BackupDirectory)) {
    [System.IO.Path]::GetFullPath($BackupDirectory)
} else {
    [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot $BackupDirectory))
}
New-Item -ItemType Directory -Force -Path $backupRoot | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$baseName = "nexmarket-$timestamp"
$plainDump = Join-Path $backupRoot "$baseName.dump"
$encryptedDump = Join-Path $backupRoot "$baseName.dump.enc"
$checksum = Join-Path $backupRoot "$baseName.dump.enc.sha256"
$pgPassFile = Join-Path ([System.IO.Path]::GetTempPath()) "nexmarket-pgpass-$([guid]::NewGuid().ToString('N'))"
$backupPass = $env:NEXMARKET_BACKUP_PASSPHRASE

try {
    $password = ""
    if ($uri.UserInfo.Contains(":")) {
        $password = [System.Uri]::UnescapeDataString($uri.UserInfo.Split(":", 2)[1])
    }
    Set-Content -LiteralPath $pgPassFile -Value "$hostName`:$port`:$databaseName`:$userName`:$password" -NoNewline
    $acl = Get-Acl -LiteralPath $pgPassFile
    $acl.SetAccessRuleProtection($true, $false)
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
        $identity,
        [System.Security.AccessControl.FileSystemRights]::Read,
        [System.Security.AccessControl.AccessControlType]::Allow
    )
    $acl.SetAccessRule($rule)
    Set-Acl -LiteralPath $pgPassFile -AclObject $acl

    $env:PGPASSFILE = $pgPassFile
    & $pgDump --format=custom --no-password --file=$plainDump --host=$hostName --port=$port --username=$userName --dbname=$databaseName
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $plainDump)) {
        throw "pg_dump failed."
    }

    & $OpenSsl enc -aes-256-cbc -pbkdf2 -iter 600000 -salt `
        -in $plainDump -out $encryptedDump -pass env:NEXMARKET_BACKUP_PASSPHRASE
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $encryptedDump)) {
        throw "OpenSSL encryption failed."
    }
    Remove-Item -LiteralPath $plainDump -Force

    $hash = (Get-FileHash -LiteralPath $encryptedDump -Algorithm SHA256).Hash.ToLowerInvariant()
    Set-Content -LiteralPath $checksum -Value "$hash *$([System.IO.Path]::GetFileName($encryptedDump))"

    $validBackups = Get-ChildItem -LiteralPath $backupRoot -Filter "*.dump.enc" -File |
        Sort-Object LastWriteTimeUtc -Descending
    if ($validBackups.Count -gt $KeepCount) {
        $validBackups | Select-Object -Skip $KeepCount | ForEach-Object {
            $candidateChecksum = "$($_.FullName).sha256"
            if (Test-Path -LiteralPath $candidateChecksum) {
                Remove-Item -LiteralPath $_.FullName, $candidateChecksum -Force
            }
        }
    }

    Write-Output "Encrypted PostgreSQL backup created: $([System.IO.Path]::GetFileName($encryptedDump))"
    Write-Output "SHA256 checksum: $hash"
}
finally {
    Remove-Item Env:PGPASSFILE -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $pgPassFile) {
        Remove-Item -LiteralPath $pgPassFile -Force -ErrorAction SilentlyContinue
    }
    if (Test-Path -LiteralPath $plainDump) {
        Remove-Item -LiteralPath $plainDump -Force -ErrorAction SilentlyContinue
    }
    $env:NEXMARKET_BACKUP_PASSPHRASE = $backupPass
}
