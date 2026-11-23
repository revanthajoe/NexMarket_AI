[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$BackupFile,
    [Parameter(Mandatory = $true)]
    [string]$TargetDatabase,
    [string]$DatabaseUrl = $env:DATABASE_URL,
    [string]$PgBin = $env:POSTGRES_BIN,
    [string]$OpenSsl = "openssl"
)

$ErrorActionPreference = "Stop"
if ([string]::IsNullOrWhiteSpace($env:NEXMARKET_BACKUP_PASSPHRASE)) {
    throw "Set NEXMARKET_BACKUP_PASSPHRASE in the protected process environment."
}
if ($TargetDatabase -notmatch "^nexmarket_restore_[a-z0-9_]+$") {
    throw "TargetDatabase must be an isolated name matching nexmarket_restore_<suffix>."
}
if ([string]::IsNullOrWhiteSpace($DatabaseUrl)) {
    throw "Set DATABASE_URL or pass -DatabaseUrl without exposing credentials."
}
if ([string]::IsNullOrWhiteSpace($PgBin)) {
    $PgBin = "C:\Program Files\PostgreSQL\17\bin"
}
$pgRestore = Join-Path $PgBin "pg_restore.exe"
if (-not (Test-Path -LiteralPath $pgRestore)) {
    throw "pg_restore.exe not found at '$pgRestore'."
}
if (-not (Test-Path -LiteralPath $BackupFile)) {
    throw "Backup file not found."
}

$uri = [System.Uri]$DatabaseUrl
$hostName = $uri.Host
$port = if ($uri.Port -gt 0) { $uri.Port } else { 5432 }
$userInfo = $uri.UserInfo.Split(":", 2)
$userName = [System.Uri]::UnescapeDataString($userInfo[0])
$password = if ($userInfo.Count -gt 1) {
    [System.Uri]::UnescapeDataString($userInfo[1])
} else {
    ""
}
$pgPassFile = Join-Path ([System.IO.Path]::GetTempPath()) "nexmarket-pgpass-$([guid]::NewGuid().ToString('N'))"
$decryptedDump = Join-Path ([System.IO.Path]::GetTempPath()) "nexmarket-restore-$([guid]::NewGuid().ToString('N')).dump"
$backupPass = $env:NEXMARKET_BACKUP_PASSPHRASE

try {
    $checksumFile = "$BackupFile.sha256"
    if (Test-Path -LiteralPath $checksumFile) {
        $expected = (Get-Content -LiteralPath $checksumFile -Raw).Split(" ")[0].Trim().ToLowerInvariant()
        $actual = (Get-FileHash -LiteralPath $BackupFile -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($expected -ne $actual) {
            throw "Backup checksum verification failed."
        }
    }

    & $OpenSsl enc -d -aes-256-cbc -pbkdf2 -iter 600000 `
        -in $BackupFile -out $decryptedDump -pass env:NEXMARKET_BACKUP_PASSPHRASE
    if ($LASTEXITCODE -ne 0) {
        throw "OpenSSL decryption failed."
    }
    Set-Content -LiteralPath $pgPassFile -Value "$hostName`:$port`:*`:$userName`:$password" -NoNewline
    $env:PGPASSFILE = $pgPassFile

    & $pgRestore --exit-on-error --no-owner --no-privileges --host=$hostName --port=$port --username=$userName --dbname=$TargetDatabase $decryptedDump
    if ($LASTEXITCODE -ne 0) {
        throw "pg_restore failed. The target database was not modified by this script beyond restore operations."
    }
    Write-Output "Backup restored into isolated database '$TargetDatabase'."
    Write-Output "Verify alembic_version, table count, row counts, and relationship queries before considering recovery successful."
}
finally {
    Remove-Item Env:PGPASSFILE -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $pgPassFile, $decryptedDump -Force -ErrorAction SilentlyContinue
    $env:NEXMARKET_BACKUP_PASSPHRASE = $backupPass
}
