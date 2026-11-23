# PostgreSQL Backup and Recovery

## Status

The application database is PostgreSQL. Backups must be encrypted at rest and
must never be written to Git, the repository, or an unprotected shared folder.
The procedures below never restore over `nexmarket`.

## Prerequisites

- PostgreSQL 17 client tools (`pg_dump.exe`, `pg_restore.exe`).
- OpenSSL 3 or another approved OpenSSL installation.
- An authorized database account with read access for backups and restore
  access to a separate recovery database.
- A protected process environment variable named
  `NEXMARKET_BACKUP_PASSPHRASE`. Do not put it in a command line, `.env` file,
  shell history, logs, or source control.
- `POSTGRES_BIN` may point to the PostgreSQL `bin` directory. On this Windows
  host it is `C:\Program Files\PostgreSQL\17\bin`.

## Encrypted backup

From the repository root in PowerShell:

```powershell
$securePassphrase = Read-Host "Backup passphrase" -AsSecureString
$env:NEXMARKET_BACKUP_PASSPHRASE = [System.Net.NetworkCredential]::new("", $securePassphrase).Password
$env:POSTGRES_BIN = "C:\Program Files\PostgreSQL\17\bin"
.\scripts\postgres_backup.ps1 -BackupDirectory "D:\protected\nexmarket-backups" -KeepCount 7
Remove-Item Env:NEXMARKET_BACKUP_PASSPHRASE
```

The script:

1. Reads `DATABASE_URL` from the process environment.
2. Creates a temporary ACL-restricted `PGPASSFILE`; the password is never a
   command-line argument.
3. Creates a PostgreSQL custom-format dump with `pg_dump`.
4. Encrypts it with OpenSSL AES-256-CBC, PBKDF2, a 600,000-iteration work
   factor, and a random salt.
5. Deletes the plaintext dump.
6. Writes a SHA-256 sidecar checksum.
7. Retains the newest `KeepCount` encrypted backups and never removes the
   newest backup or any backup lacking its checksum sidecar.

The default retention is seven successful encrypted backups. Store copies in
at least two protected locations, ideally with one offline or immutable copy.
Retention cleanup is local to the selected backup directory; it does not
delete database rows or alter PostgreSQL.

## Separate-database restore verification

Provision a separate database named like `nexmarket_restore_20261102` using an
administrator-approved recovery role. Do not use `nexmarket` and do not point
the restore command at a production database:

```powershell
$securePassphrase = Read-Host "Backup passphrase" -AsSecureString
$env:NEXMARKET_BACKUP_PASSPHRASE = [System.Net.NetworkCredential]::new("", $securePassphrase).Password
.\scripts\postgres_restore_verify.ps1 `
  -BackupFile "D:\protected\nexmarket-backups\nexmarket-YYYYMMDD-HHMMSS.dump.enc" `
  -TargetDatabase "nexmarket_restore_20261102"
```

After restore, verify:

```sql
SELECT version_num FROM alembic_version;
SELECT count(*) FROM pg_catalog.pg_tables WHERE schemaname = 'public';
SELECT count(*) FROM campaigns;
SELECT count(*) FROM analytics_events;
SELECT count(*) FROM posters p
  LEFT JOIN campaigns c ON c.id = p.campaign_id
  WHERE c.id IS NULL;
```

Expected results are the backup's recorded migration revision and row counts,
20 application/schema tables including `alembic_version`, and zero orphaned
posters. Remove only the separately provisioned restore database after these
checks and after retaining the evidence required by the recovery procedure.

## Failure handling

- A failed `pg_dump`, encryption, checksum, or retention step is a failed
  backup; do not delete older backups.
- If checksum verification fails, quarantine the file and restore from another
  backup.
- If decryption or `pg_restore` fails, preserve the error output without
  exposing credentials, and use the next verified backup.
- Never use `alembic stamp` to bypass a restore or migration failure.
- A backup is not considered recoverable until it has been restored into a
  separate database and its revision, row counts, and relationship checks pass.

## Current validation limitation

The configured application role is non-superuser and has `rolcreatedb=false`.
The current environment therefore cannot safely provision the separate
PostgreSQL database required for restore or full PostgreSQL migration-cycle
testing. Use an administrator-provisioned recovery database or an isolated CI
PostgreSQL service; do not grant `CREATEDB` or `SUPERUSER` to the application
role merely to run this validation.
