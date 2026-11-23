# Windows Server backup (run from Task Scheduler). Requires PostgreSQL client tools on PATH.
#   $env:PGPASSWORD = '...'; .\scripts\backup_postgres.ps1 -Dest D:\Backups
param([string]$Dest = "D:\Backups", [string]$Db = "ucfin", [string]$PgUser = "ucfin_app", [string]$PgHost = "localhost",
      [string]$Attachments = "C:\UCFinance\storage\attachments")
$ErrorActionPreference = "Stop"
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
New-Item -ItemType Directory -Force -Path $Dest | Out-Null
& pg_dump --format=custom --no-owner -h $PgHost -U $PgUser --file "$Dest\ucfin_$stamp.dump" $Db
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed" }
& pg_restore --list "$Dest\ucfin_$stamp.dump" | Out-Null
if (Test-Path $Attachments) { Compress-Archive -Path $Attachments -DestinationPath "$Dest\attachments_$stamp.zip" }
Get-ChildItem $Dest -Filter "ucfin_*.dump" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item
Get-ChildItem $Dest -Filter "attachments_*.zip" | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-30) } | Remove-Item
Write-Output "Backup written: $Dest\ucfin_$stamp.dump"
